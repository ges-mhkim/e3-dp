"""GW 이상 응답에 대한 DP(gw_server) 동작.
명세 출처: e3dp.2.1/src/gw/gw_server.c process_rt_request
  - 12바이트 응답            : "No Configuration in E3-GW" -> shelf status COMM_ALARM(3)
  - 249바이트 아님            : 무시(FAIL), 상태·값 변경 없음
  - 응답 port(EquipID) 불일치 : 무시(FAIL)
  - 마지막 바이트(DI40 하위) != 0 : 통신 이상 -> shelf status COMM_ALARM(3)
  - 응답 없음(500ms poll)     : 무시(FAIL)
  - 정상 응답 + 마지막 바이트 0   : shelf status COMM_NORMAL(0), 값 반영
"""
import pytest

import dpapi

pytestmark = pytest.mark.device

GW1 = "10.99.0.11"
PORT = 2          # GW1의 port 2 (shelf unit 1, modbus 2)
COMM_NORMAL, COMM_ALARM = 0, 3


def _status(dp):
    return dpapi.shelves(dp).get((1, PORT))


@pytest.fixture
def clean_port(dp):
    """각 테스트 전후에 port 2를 정상 응답으로 되돌린다."""
    def reset():
        dp.sim({"op": "mode", "ip": GW1, "port": PORT, "mode": "normal"})
        assert dpapi.wait_for(lambda: _status(dp) == COMM_NORMAL, timeout=40), "정상 복귀 실패"
    reset()
    yield
    reset()


def test_normal_response_marks_port_normal(dp, clean_port):
    assert _status(dp) == COMM_NORMAL


def test_noconfig_response_sets_comm_alarm_and_recovers(dp, clean_port):
    dp.sim({"op": "mode", "ip": GW1, "port": PORT, "mode": "noconfig"})
    assert dpapi.wait_for(lambda: _status(dp) == COMM_ALARM, timeout=40)
    dp.sim({"op": "mode", "ip": GW1, "port": PORT, "mode": "normal"})
    assert dpapi.wait_for(lambda: _status(dp) == COMM_NORMAL, timeout=40)


def test_commfail_flag_sets_comm_alarm(dp, clean_port):
    dp.sim({"op": "mode", "ip": GW1, "port": PORT, "mode": "commfail"})
    assert dpapi.wait_for(lambda: _status(dp) == COMM_ALARM, timeout=40)


@pytest.mark.parametrize("mode", ["badsize", "wrongport"])
def test_invalid_response_is_ignored(dp, clean_port, mode):
    """잘못된 응답은 상태와 값을 바꾸지 않는다."""
    dp.sim({"op": "set_ai", "ip": GW1, "port": PORT, "ch": 1, "value": 11.0})
    ref = dpapi.wait_for(lambda: (lambda p: p and abs(p["val"] - 11.0) < 0.01 and p)(dpapi.lport(dp, "ACON", 2, 1)), 40)
    assert ref, "기준 값 반영 실패"
    dp.sim({"op": "mode", "ip": GW1, "port": PORT, "mode": mode})
    dp.sim({"op": "set_ai", "ip": GW1, "port": PORT, "ch": 1, "value": 22.0})
    dp.sim({"op": "clear_log"})
    assert dpapi.wait_for(lambda: any(r["port"] == PORT for r in dp.sim({"op": "get_log"})["log"]), 30)
    import time
    time.sleep(8)  # 최소 한 사이클 이상 대기
    p = dpapi.lport(dp, "ACON", 2, 1)
    assert abs(p["val"] - 11.0) < 0.01, "잘못된 응답(%s)이 값을 바꿈: %s" % (mode, p)
    assert _status(dp) == COMM_NORMAL


def test_silent_gw_does_not_stop_other_ports(dp, clean_port):
    """무응답 port가 있어도 다른 port 폴링은 계속된다(응답 대기 500ms 후 다음 port)."""
    dp.sim({"op": "mode", "ip": GW1, "port": PORT, "mode": "silent"})
    dp.sim({"op": "clear_log"})
    def others():
        ports = {r["port"] for r in dp.sim({"op": "get_log"})["log"] if r["ip"] == GW1 and r.get("func") == 3}
        return {1, 3, 4, 5} <= ports
    assert dpapi.wait_for(others, timeout=40)
    assert "gw_server" in dp.procs()


def test_connection_refused_does_not_crash_dp(dp, clean_port):
    dp.sim({"op": "ip_down", "ip": GW1})
    try:
        import time
        time.sleep(10)
        procs = dp.procs()
        for name in ("gw_server", "modbus_server", "netcheck_server", "scan_server", "main_server"):
            assert name in procs, name + " 종료됨"
    finally:
        dp.sim({"op": "ip_up", "ip": GW1})
