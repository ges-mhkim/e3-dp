"""Host -> DP 설정 서비스 중 한계치(EC_SVC_UPDATE_LIMIT, 409)와 경보 마스크(EC_SVC_ALARM_MASK, 407).
경로: Host UDP 요청 -> main_server(7999) -> config_server(7032) -> 응답 UDP(요청의 caddr)
명세 출처: e3dp.2.1/src/config/config_handler.c (DrScan__lport_set, DrScan__limit_set, DrScan__alarmmask_set,
          DrScan__send_response), src/main/main_dispatch.c, sim/ber.py(요청 PDU 형식)
  - 요청 변수: 1.1.6.1.1.5.0.<stationid>.<compid>.<compno>.<portno>.<status> = INTEGER value
      한계치: status = 상한(float2int), value = 하한(float2int). 상한 < 하한이면 거부(응답 service=0).
      마스크: value 의 최하위 비트가 1이면 AI 경보 억제.
  - 대상 LPORT를 찾지 못해도 오류 없이 성공 응답한다.
  - 한계치·마스크 변경 후 nelite.db 를 다시 저장한다(store_db).
  - 응답: EC_REQUEST(1) 헤더, service = 요청 서비스(거부 시 0), rid = 요청 rid, 본문에 stationid/equip/compno/portno/value/status
"""
import re
import time

import pytest

import dpapi
from sim import ber
from sim import hostclient as hc

pytestmark = pytest.mark.device

STATION = 139600
ACON, COMPID = "ACON", 501
SVC_LIMIT, SVC_MASK = 409, 407
GW1 = "10.99.0.11"
ORIG_HIGH, ORIG_LOW = 36.0, 5.0       # nelite.db 의 ACON 1.1 한계치


def limit_pdu(high, low, compno=1, portno=1, compid=COMPID):
    return ber.rt_request(STATION, compid, compno, portno, hc.float2int(high), hc.float2int(low))


def set_limits(dp, high, low, **kw):
    r = dpapi.host_request(dp, SVC_LIMIT, limit_pdu(high, low, **kw))
    assert len(r) == 1, "응답 수: %d" % len(r)
    return ber.parse_rt_response(r[0]), r[0]


def lp(dp):
    return dpapi.lport(dp, ACON, 1, 1)


@pytest.fixture
def restore_limits(dp):
    yield
    set_limits(dp, ORIG_HIGH, ORIG_LOW)
    dpapi.host_request(dp, SVC_MASK, ber.rt_request(STATION, COMPID, 1, 1, 0, 0))
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 20.0})
    time.sleep(1)


def test_limit_set_updates_lport_and_replies_with_echo(dp, restore_limits, evidence):
    (h, f), raw = set_limits(dp, 30.0, 10.0)
    p = lp(dp)
    assert (p["high"], p["low"]) == (30.0, 10.0)
    assert h["type"] == 1 and h["service"] == SVC_LIMIT and h["rid"] == 7
    assert h["size"] == len(raw) - ber.HDR_LEN
    assert f == {"stationid": STATION, "equip": ACON, "compno": 1, "portno": 1, "value": 10000, "status": SVC_LIMIT}
    evidence("limit_response", {"header": {k: v for k, v in h.items() if k not in ("ip", "port", "family")},
                                "fields": f, "len": len(raw)})


def test_limit_set_is_persisted_to_local_db(dp, restore_limits):
    set_limits(dp, 31.0, 11.0)
    db = dp.get_text("/opt/e3dp/conf/nelite.db")
    rows = [l.split() for l in db.splitlines() if re.match(r"\s*501\s+ACON\s+1\s+1\s", l)]
    assert rows and float(rows[0][5]) == 31.0 and float(rows[0][6]) == 11.0, rows


def test_limit_with_high_below_low_is_rejected(dp, restore_limits, evidence):
    before = lp(dp)
    (h, f), raw = set_limits(dp, 5.0, 10.0)
    assert h["service"] == 0                       # 거부 응답은 서비스 코드 0
    assert (lp(dp)["high"], lp(dp)["low"]) == (before["high"], before["low"])
    evidence("limit_reject_service", h["service"])


def test_limit_for_unknown_lport_is_acknowledged_without_change(dp, restore_limits):
    before = lp(dp)
    (h, f), raw = set_limits(dp, 30.0, 10.0, compno=77, portno=99)
    assert h["service"] == SVC_LIMIT                # 찾지 못해도 성공 응답
    assert (lp(dp)["high"], lp(dp)["low"]) == (before["high"], before["low"])


def test_new_limit_drives_alarm_to_host(dp, restore_limits, evidence):
    dpapi.drain_alarms(dp)
    dp.sim({"op": "clear_log"}, dpapi.HOSTSIM_CTL)
    set_limits(dp, 30.0, 10.0)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 33.0})     # 기존 상한 36 이하, 새 상한 30 초과
    a = dpapi.wait_for(lambda: next((x for x in dpapi.host_alarms(dp) if x[2].get("equip") == ACON
                                     and x[2].get("compno") == 1 and x[2].get("portno") == 1
                                     and x[2].get("status") == 2), None), timeout=45, step=1.0)
    assert a, "새 상한(30) 초과 경보가 Host에 도착하지 않음"
    f = a[2]
    assert (f["value"], f["high"], f["low"]) == (33000, 30000, 10000)
    evidence("alarm_after_limit_change", {k: f[k] for k in ("value", "high", "low", "status")})


def test_alarm_mask_suppresses_status_and_alarm(dp, restore_limits, evidence):
    dpapi.drain_alarms(dp)
    r = dpapi.host_request(dp, SVC_MASK, ber.rt_request(STATION, COMPID, 1, 1, 0, 1))      # value 1 = 마스크
    assert len(r) == 1 and ber.parse_rt_response(r[0])[0]["service"] == SVC_MASK
    out = dp.tool("comp ACON 1 1")
    assert re.search(r"mask\(0x0001\)", out), out
    dp.sim({"op": "clear_log"}, dpapi.HOSTSIM_CTL)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 40.0})
    time.sleep(12)
    assert lp(dp)["st"] == 0, "마스크된 LPORT가 상한 상태가 됨: %s" % lp(dp)
    high_alarms = [x for x in dpapi.host_alarms(dp) if x[2].get("equip") == ACON and x[2].get("compno") == 1
                   and x[2].get("portno") == 1 and x[2].get("status") == 2]
    assert not high_alarms, "마스크 중인데 상한 경보가 전송됨"
    evidence("masked_status", lp(dp)["st"])
