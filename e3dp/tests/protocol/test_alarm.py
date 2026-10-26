"""alarm_server -> Host(UDP 7704) 경보 송신과 ACK(rid) 처리.
명세: sim/ber.py 상단 주석, 출처 e3dp.2.1/src/alarm/alarm_handler.c, alarm_sender.c
  - 정지-대기: 1건 송신 후 최대 5초 ACK 대기, 없으면 같은 항목 재전송, ACK(rid)면 항목 삭제 후 다음 건
  - 상태 코드: 0 정상, 1 하한, 2 상한, 3 디지털, 21 GW 설정 없음, 22 통신 이상
"""
import time

import pytest

import dpapi
from sim import ber

pytestmark = pytest.mark.device

GW1 = "10.99.0.11"
CTL = 19001
SVC_ALARM = 201
LOW, HIGH, NORMAL = 1, 2, 0


def packets(dp):
    return dp.sim({"op": "get_log"}, CTL)["log"]


def alarms(dp):
    return [(p,) + ber.parse_alarm(bytes.fromhex(p["hex"])) for p in packets(dp) if p["port"] == 7704]


def ack_mode(dp, mode):
    dp.sim({"op": "ack_mode", "mode": mode}, CTL)


def drain(dp, quiet=6.0, timeout=150):
    """ACK를 켜고 새 경보가 quiet초 동안 없을 때까지 기다린다(기동 직후 모든 LPORT의 초기 경보 처리)."""
    ack_mode(dp, "rid")
    t_end = time.time() + timeout
    last_n, last_t = -1, time.time()
    while time.time() < t_end:
        n = len(packets(dp))
        if n != last_n:
            last_n, last_t = n, time.time()
        elif time.time() - last_t >= quiet:
            return n
        time.sleep(1)
    pytest.fail("경보가 계속 발생하여 안정되지 않음")


@pytest.fixture(scope="module")
def drained(dp):
    drain(dp)
    yield dp
    ack_mode(dp, "rid")


def _wait_alarm(dp, pred, timeout=40):
    return dpapi.wait_for(lambda: next((a for a in alarms(dp) if pred(a)), None), timeout=timeout, step=1.0)


def masked(pkt, h, f, host):
    """환경마다 달라지는 값(보드 주소, 시각)을 마스킹한 증거 값"""
    raw = bytes.fromhex(pkt["hex"])
    raw = raw[:12] + bytes(4) + raw[16:]          # rid는 ACB 카운터라 앞선 경보 수에 따라 달라짐
    k = raw.find(b"\xa8\x00\x02\x01")                # PDU 헤더의 요청 ID(pdu_requestid 전역 카운터) 1바이트
    if k >= 0:
        raw = raw[:k + 4] + b"\x00" + raw[k + 5:]
    for tail in (b"\x06\x05\x29\x02\x04\x01\x08\x43\x04", b"\x06\x05\x29\x02\x04\x01\x09\x43\x04"):
        i = raw.find(tail)
        if i >= 0:
            k = i + len(tail)
            raw = raw[:k] + b"\x00\x00\x00\x00" + raw[k + 4:]
    hh = {k: v for k, v in h.items() if k != "rid"}
    hh["ip"] = "<MIH>" if h["ip"] == host else h["ip"]
    ff = {k: v for k, v in f.items() if k not in ("otime", "rtime")}
    return {"header": hh, "fields": ff, "len": len(raw), "raw_hex_masked": raw.hex().replace(
        "".join("%02x" % int(x) for x in host.split(".")), "<mih>")}


def _acon11(status):
    return lambda a: (a[2].get("equip") == "ACON" and a[2].get("compno") == 1
                      and a[2].get("portno") == 1 and a[2].get("status") == status)


def test_header_layout_of_alarm_packet(drained, evidence):
    dp = drained
    dp.sim({"op": "clear_log"}, CTL)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 40.0})
    a = _wait_alarm(dp, _acon11(HIGH))
    assert a, "상한 경보가 도착하지 않음"
    pkt, h, f = a
    evidence("alarm_high_packet", masked(pkt, h, f, dp.host))
    assert h["type"] == 1 and h["service"] == SVC_ALARM and h["protocol"] == 1
    assert h["size"] == pkt["len"] - ber.HDR_LEN
    assert (h["family"], h["port"], h["ip"]) == (2, 7042, dp.host)
    assert pkt["sport"] == 7042 and pkt["src"] == "127.0.0.1"


def test_high_alarm_body_fields(drained):
    dp = drained
    a = _wait_alarm(dp, _acon11(HIGH))
    assert a
    f = a[2]
    assert f["stationid"] == 139600
    assert f["value"] == 40000                       # float2int(40.0)
    assert f["type"] == 1                            # AI
    assert (f["high"], f["low"]) == (36000, 5000)    # nelite.db 한계치 * 1000
    assert abs(f["otime"] - time.time()) < 3600 * 24 * 365 * 40


def test_recovery_sends_normal_status_with_rtime(drained, evidence):
    dp = drained
    dp.sim({"op": "clear_log"}, CTL)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 20.0})
    a = _wait_alarm(dp, _acon11(NORMAL))
    assert a, "복구 경보가 도착하지 않음"
    f = a[2]
    evidence("alarm_recovery_packet", masked(a[0], a[1], a[2], dp.host))
    assert "rtime" in f and "otime" not in f         # 정상 상태에서는 복구시각(rtime)을 보낸다
    assert f["value"] == 20000


def test_low_alarm(drained, evidence):
    dp = drained
    dp.sim({"op": "clear_log"}, CTL)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 1.0})
    a = _wait_alarm(dp, _acon11(LOW))
    assert a and a[2]["value"] == 1000
    evidence("alarm_low_packet", masked(a[0], a[1], a[2], dp.host))
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 20.0})


def test_rid_unique_when_acked(drained):
    dp = drained
    dp.sim({"op": "clear_log"}, CTL)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 2, "ch": 1, "value": 40.0})
    dp.sim({"op": "set_ai", "ip": GW1, "port": 3, "ch": 1, "value": 40.0})
    time.sleep(25)
    rids = [a[1]["rid"] for a in alarms(dp)]
    assert len(rids) >= 2 and len(rids) == len(set(rids)), "ACK 후 같은 rid가 재전송됨: %s" % rids
    dp.sim({"op": "set_ai", "ip": GW1, "port": 2, "ch": 1, "value": 20.0})
    dp.sim({"op": "set_ai", "ip": GW1, "port": 3, "ch": 1, "value": 20.0})


def test_without_ack_same_alarm_is_resent_after_about_5s(dp):
    drain(dp)
    ack_mode(dp, "none")
    dp.sim({"op": "clear_log"}, CTL)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 4, "ch": 1, "value": 41.0})
    assert dpapi.wait_for(lambda: len(alarms(dp)) >= 3, timeout=40, step=1.0), "재전송이 일어나지 않음"
    al = alarms(dp)
    rid0 = al[0][1]["rid"]
    same = [a for a in al if a[1]["rid"] == rid0]
    assert len(same) >= 2
    gap = same[1][0]["t"] - same[0][0]["t"]
    assert 4.0 <= gap <= 8.0, "재전송 간격 %.1fs (명세: 5초 응답 대기)" % gap
    ack_mode(dp, "rid")
    dp.sim({"op": "set_ai", "ip": GW1, "port": 4, "ch": 1, "value": 20.0})
