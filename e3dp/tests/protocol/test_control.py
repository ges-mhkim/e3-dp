"""Host -> DP 수동 제어(EVR_CTRL_SCRIPT_CM_RUN, 0x01000101)와 GW 쓰기.
경로: Host UDP 요청 -> main_server(7999) -> control_server(8022) -> 제어 LPORT(포트 28) 값 설정
      -> gw_server가 다음 폴링에서 값을 읽어 GW에 Modbus func 0x06 쓰기 (addr=채널, count=명령)
      DP가 요청의 caddr로 TCP 연결을 맺어 응답(2건)을 보낸다.
명세 출처: e3dp.2.1/src/control/control_handler.c, control_process.c, src/gw/gw_server.c (check_control)
  - 본문: 44바이트 헤더 뒤에 ASCII `<wire_id> <구성품명 4자> <구성품번호> <명령>` (공백 구분, 24바이트까지 해석)
  - 응답 본문 `0x<ret2> 0x<ret1> `: 성공 `0x0000 0x0000`, 구성품 없음 `0x0552 0x0000`
  - wire_id는 검증하지 않음. 명령에 대응하는 포인트(bitno == 명령)가 없으면 성공 응답하지만 GW에는 쓰지 않음.
  - 이 DB의 ACON 1.28: bit 1 -> 채널 1, bit 2 -> 채널 2 (shelf 1, board 1)
"""
import re
import time

import pytest

import dpapi
from sim import ber

pytestmark = pytest.mark.device

SVC_CM_RUN = 0x01000101
PORT = 40100
GW1 = "10.99.0.11"


def control(dp, text, rid=9, wait=6):
    """제어 요청을 보내고 (응답 본문 텍스트, TCP 스트림 hex) 를 반환한다."""
    dg = ber.build_request_datagram(SVC_CM_RUN, text.encode().ljust(30, bytes(1)), rid=rid, caddr_port=PORT)
    r = dp.host_request_tcp(dpapi.SIM_DIR + "/hostreq.py", dg, PORT, wait=wait)
    streams = ["".join(chunks) for chunks in r["tcp"]]
    assert len(streams) == 1, "DP가 TCP 응답 연결을 1개 맺어야 함: %d" % len(streams)
    raw = bytes.fromhex(streams[0])
    m = re.findall(rb"0x[0-9a-f]{4} 0x[0-9a-f]{4}", raw)
    assert m, raw
    return m[-1].decode(), streams[0]


def gw_writes(dp):
    return [(x["port"], x["addr"], x["cnt"]) for x in dp.sim({"op": "get_log"})["log"]
            if x.get("func") == 6 and x["ip"] == GW1]


@pytest.mark.parametrize("cmd,addr", [(1, 1), (2, 2)])
def test_manual_control_is_acked_and_written_to_gw(dp, cmd, addr, evidence):
    dp.sim({"op": "clear_log"})
    text, stream = control(dp, "139600 ACON 1 %d" % cmd)
    assert text == "0x0000 0x0000"
    got = dpapi.wait_for(lambda: gw_writes(dp), timeout=30, step=1.0)
    assert got, "GW에 쓰기 프레임이 도착하지 않음"
    assert got[0] == (1, addr, cmd), got
    evidence("control_response_stream_cmd%d" % cmd, stream)
    evidence("control_gw_write_cmd%d" % cmd, list(got[0]))


def test_unknown_component_is_rejected(dp, evidence):
    dp.sim({"op": "clear_log"})
    text, _ = control(dp, "139600 ACON 77 1")
    assert text == "0x0552 0x0000"
    time.sleep(8)
    assert gw_writes(dp) == []
    evidence("control_unknown_component", text)


def test_command_without_matching_point_acks_but_writes_nothing(dp, evidence):
    """특성 테스트: 명령 9에 대응하는 포인트가 없어도 성공으로 응답하고 GW에는 쓰지 않는다."""
    dp.sim({"op": "clear_log"})
    text, _ = control(dp, "139600 ACON 1 9")
    assert text == "0x0000 0x0000"
    time.sleep(10)
    assert gw_writes(dp) == []
    evidence("control_unmapped_command", text)


def test_wire_id_is_not_validated(dp):
    """특성 테스트: 다른 국 번호(wire_id)의 제어 요청도 실행된다."""
    dp.sim({"op": "clear_log"})
    text, _ = control(dp, "999999 ACON 1 1")
    assert text == "0x0000 0x0000"
    assert dpapi.wait_for(lambda: gw_writes(dp), timeout=30, step=1.0)
