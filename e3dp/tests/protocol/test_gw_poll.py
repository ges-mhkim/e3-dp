"""DP -> GW(Modbus TCP 1502) 폴링 요청 형식과 값 반영.
명세 출처: e3dp.2.1/src/gw/gw_server.c (process_rt_request, update_ai_value)
"""
import struct

import pytest

import dpapi

pytestmark = pytest.mark.device

GW1 = "10.99.0.11"


def _reqs(dp, ip=GW1, func=3):
    return [x for x in dp.sim({"op": "get_log"})["log"] if x["ip"] == ip and x.get("func") == func]


def test_tsync_request_sent_at_start_with_current_time(dp):
    """gw_server는 기동 직후 첫 GW(parent)에 시각 동기(func 0x64, port 0, txid 0)를 보낸다.
    본문은 time_t 하위 4바이트(little-endian). 이 테스트는 모듈 첫 테스트여야 한다(로그 초기화 전).
    전송 여부 자체가 기동 경쟁에 달려 있어 미전송이면 건너뛴다."""
    ts = [r for r in dp.sim({"op": "get_log"})["log"] if r.get("func") == 0x64]
    if not ts:
        # gw_server는 tsync_cnt==1인 첫 루프에서만(이후 21600 사이클마다) 시각 동기를 보낸다.
        # 그 시점에 상위 GW 상태가 아직 COMM_ALARM이면 전송 없이 건너뛴다(netcheck_server 판정과의 경쟁).
        pytest.skip("첫 루프에서 시각 동기가 전송되지 않음(상위 GW 상태 판정 지연으로 건너뜀)")
    raw = bytes.fromhex(ts[0]["hex"])
    txid, proto, ln, port, func = struct.unpack("!HHHBB", raw[:8])
    assert (txid, proto, ln, port, func) == (0, 0, 6, 0, 0x64)
    epoch = struct.unpack("<I", raw[8:12])[0]
    assert abs(epoch - ts[0]["t"]) < 10


def test_poll_request_format_is_12byte_read_120_registers(dp, evidence):
    dp.sim({"op": "clear_log"})
    dpapi.wait_for(lambda: len(_reqs(dp)) >= 5, timeout=30)
    reqs = _reqs(dp)
    assert reqs
    # txid는 마스킹, 나머지는 환경과 무관해야 한다
    evidence("poll_request_shapes", sorted({r["hex"][4:] for r in reqs}))
    for r in reqs:
        raw = bytes.fromhex(r["hex"])
        txid, proto, ln, port, func, addr, cnt = struct.unpack("!HHHBBHH", raw)
        assert (proto, ln, func, addr, cnt) == (0, 6, 3, 0, 120)
        assert 1 <= port <= 5


def test_poll_sends_one_request_per_port(dp):
    dp.sim({"op": "clear_log"})
    dpapi.wait_for(lambda: len({r["port"] for r in _reqs(dp)}) >= 5, timeout=30)
    assert {r["port"] for r in _reqs(dp)} >= {1, 2, 3, 4, 5}


def test_txid_increments_across_requests(dp):
    dp.sim({"op": "clear_log"})
    dpapi.wait_for(lambda: len(_reqs(dp)) >= 6, timeout=30)
    ids = [r["txid"] for r in _reqs(dp)]
    assert ids == sorted(ids) or ids[-1] < ids[0]  # 증가 또는 0xFFFF 이후 1로 순환


@pytest.mark.parametrize("value", [0.0, 12.5, -3.25, 35.999])
def test_ai_value_reflected_in_lport(dp, value):
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": value})
    got = dpapi.wait_for(lambda: (lambda p: p and abs(p["val"] - value) < 0.01 and p)(dpapi.lport(dp, "ACON", 1, 1)),
                         timeout=30)
    assert got, "LPORT 값이 %s로 바뀌지 않음: %s" % (value, dpapi.lport(dp, "ACON", 1, 1))


def test_ai_limit_status(dp):
    """highlimit 36, lowlimit 5 (nelite.db) 기준 상태 판정: 정상/상한/하한"""
    lp = dpapi.lport(dp, "ACON", 1, 1)
    hi, lo = lp["high"], lp["low"]
    for value, name in ((20.0, "NORM"), (hi + 1, "HIGH"), (lo - 1, "LOW")):
        dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": value})
        got = dpapi.wait_for(lambda: (lambda p: p and p["st_name"].startswith(name) and p)(dpapi.lport(dp, "ACON", 1, 1)),
                             timeout=30)
        assert got, "value=%s 에서 상태 %s 기대, 실제 %s" % (value, name, dpapi.lport(dp, "ACON", 1, 1))
