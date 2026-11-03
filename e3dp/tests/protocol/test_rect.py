"""rect_server 정류기 폴링(DP -> 정류기, TCP 2000, Modbus ASCII)과 값 변환.
명세 출처: e3dp.2.1/src/rect/rect_server.c (process_rt_request, SendRecvManager, RectUpdate, make_LRC), src/rect/rect.h
  - 요청: ':' 01 04 0100 004B LRC CR LF (17바이트). 응답 9번째 문자부터 레지스터 75개(각 4자리 16진), LRC 는 검사하지 않음
  - ACDS(301) 포트 1~7 = ac_v_R/S/T, ac_a_R/S/T, temp(원시값), 포트 22 = rackN_ac_fail(하위 12비트 > 0 이면 N번째 비트 설정, SetBit 은 1부터 센다: rack1 = 값 1, rack3 = 값 4)
  - DCDS(302) 포트 1 = dc_v/10, 포트 2 = dc_a, 포트 3 = batt_a(MSB 1 이면 -(~v & 0x7FFF))
  - RECT(303) channel 1 = rack1: 포트 1 = output_a, 2 = temp, 3 = output_v/10, 4 = batt_a(부호 규칙 같음)
  - 연속 51회 초과 실패하면 셸프 통신 이상(3), 해당 셸프 LPORT 상태 22
"""
import os

import pytest

import dpapi
from sim import rectsim

pytestmark = pytest.mark.device

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IP = dpapi.RECT_SIM_IP
CTL = dpapi.RECTSIM_CTL


@pytest.fixture(scope="module")
def rdp(board):
    board.env_up(HERE, rect=True)
    yield board
    board.env_down()


def rs(b, req):
    r = b.sim(req, CTL)
    assert r.get("ok"), r
    return r


def setreg(b, name, value):
    rs(b, {"op": "set_reg", "ip": IP, "name": name, "value": value})


def val(b, name, no, port):
    v = dpapi.lport(b, name, no, port)
    return None if v is None else v["val"]


def wait_val(b, name, no, port, want, timeout=15):
    got = dpapi.wait_for(lambda: abs((val(b, name, no, port) or 0) - want) < 1e-3 or None, timeout=timeout, step=1.0)
    return got, val(b, name, no, port)


def test_request_frame_and_lrc(rdp, evidence):
    log = dpapi.wait_for(lambda: rs(rdp, {"op": "get_log"})["log"] or None, timeout=30)
    assert log, "정류기 폴링 요청이 없음"
    reqs = set(x["req"] for x in log)
    evidence("requests", sorted(reqs))
    for x in log:
        assert x["req"] == ":01040100004B" + rectsim.lrc_ascii("01040100004B") + "\r\n", x
        assert x["lrc_ok"] and x["func"] == "04" and x["addr"] == "0100" and x["val"] == "004B"


def test_polling_period(rdp, evidence):
    rs(rdp, {"op": "clear_log"})
    import time
    time.sleep(10)
    n = len(rs(rdp, {"op": "get_log"})["log"])
    evidence("polls_in_10s", n)
    assert 5 <= n <= 25


def test_acds_values(rdp, evidence):
    for name, port, v in (("ac_v_R", 1, 2200), ("ac_v_S", 2, 2210), ("ac_v_T", 3, 2190),
                          ("ac_a_R", 4, 15), ("ac_a_S", 5, 16), ("ac_a_T", 6, 17), ("temp", 7, 25)):
        setreg(rdp, name, v)
    res = {}
    for port, want in ((1, 2200), (2, 2210), (3, 2190), (4, 15), (5, 16), (6, 17), (7, 25)):
        ok, got = wait_val(rdp, "ACDS", 1, port, want)
        res[port] = got
        assert ok, "ACDS 포트 %d: 기대 %s, 실제 %s" % (port, want, got)
    evidence("acds", res)


def test_acds_ac_fail_bits(rdp, evidence):
    for r in range(1, 6):
        setreg(rdp, "rack%d_ac_fail" % r, 0)
    setreg(rdp, "rack1_ac_fail", 1)
    setreg(rdp, "rack3_ac_fail", 0x0F00)
    setreg(rdp, "rack5_ac_fail", 0x1000)       # 하위 12비트(0xFFF)만 보므로 발생 아님
    ok, got = wait_val(rdp, "ACDS", 1, 22, (1 << 0) | (1 << 2))
    evidence("acds22", got)
    assert ok, "ACDS 22: 기대 %d, 실제 %s" % ((1 << 0) | (1 << 2), got)
    setreg(rdp, "rack1_ac_fail", 0)
    ok, got = wait_val(rdp, "ACDS", 1, 22, 1 << 2)
    assert ok, "복구 후 비트 해제 안 됨: %s" % got


@pytest.mark.parametrize("raw,want", [(0x0005, 5), (0x7FFF, 32767), (0xFFFA, -5), (0x8000, -32767), (0, 0)])
def test_dcds_batt_current_sign(rdp, raw, want, evidence):
    setreg(rdp, "dcds_batt_a", raw)
    ok, got = wait_val(rdp, "DCDS", 1, 3, want)
    evidence("dcds3_%04X" % raw, got)
    assert ok, "DCDS 3: 0x%04X -> 기대 %s, 실제 %s" % (raw, want, got)


def test_dcds_voltage_current(rdp, evidence):
    setreg(rdp, "dcds_dc_v", 543)
    setreg(rdp, "dcds_dc_a", 120)
    ok1, v1 = wait_val(rdp, "DCDS", 1, 1, 54.3)
    ok2, v2 = wait_val(rdp, "DCDS", 1, 2, 120)
    evidence("dcds1", v1)
    evidence("dcds2", v2)
    assert ok1, v1
    assert ok2, v2


def test_rect_rack1_values(rdp, evidence):
    setreg(rdp, "rack1_output_a", 33)
    setreg(rdp, "rack1_output_temp", 41)
    setreg(rdp, "rack1_output_v", 541)
    setreg(rdp, "rack1_batt_a", 0xFFF6)
    res = {}
    for port, want in ((1, 33), (2, 41), (3, 54.1), (4, -9)):
        ok, got = wait_val(rdp, "RECT", 1, port, want)
        res[port] = got
        assert ok, "RECT 포트 %d: 기대 %s, 실제 %s" % (port, want, got)
    evidence("rect1", res)


def test_short_and_garbage_replies_do_not_crash(rdp, evidence):
    for mode in ("short", "badframe"):
        rs(rdp, {"op": "mode", "ip": IP, "mode": mode})
        import time
        time.sleep(4)
        procs = rdp.procs()
        assert "rect_server" in procs, "rect_server 종료됨(%s)" % mode
    rs(rdp, {"op": "mode", "ip": IP, "mode": "normal"})
    evidence("survived", True)


def test_comm_failure_and_recovery(rdp, evidence):
    rs(rdp, {"op": "mode", "ip": IP, "mode": "normal"})
    assert dpapi.wait_for(lambda: dpapi.shelves(rdp).get((dpapi.RECT_SHELF, 1)) == 0 or None, timeout=30) is not None
    rs(rdp, {"op": "ip_down", "ip": IP})
    st = dpapi.wait_for(lambda: dpapi.shelves(rdp).get((dpapi.RECT_SHELF, 1)) == 3 or None, timeout=240, step=3.0)
    evidence("comm_alarm", bool(st))
    assert st, "연속 실패 뒤에도 정류기 셸프가 통신 이상이 되지 않음: %s" % dpapi.shelves(rdp)
    p = dpapi.lport(rdp, "ACDS", 1, 1)
    evidence("lport_status_on_fail", p["st"])
    rs(rdp, {"op": "ip_up", "ip": IP})
    ok = dpapi.wait_for(lambda: dpapi.shelves(rdp).get((dpapi.RECT_SHELF, 1)) == 0 or None, timeout=60, step=2.0)
    assert ok, "정류기 복구 후 정상으로 돌아오지 않음"
