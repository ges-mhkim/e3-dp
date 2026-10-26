"""acon_agent (Modbus TCP 서버, 포트 9785): 외부 클라이언트가 DP의 ACON 값을 읽는 경로.
명세 출처: e3dp.2.1/src/acon_agent/acon_handler.c (MakeReadPacket, Svr_RecvHandler)
  - 요청 12바이트 `[txid][0][6][unit][func][addr][count]` (빅엔디안). 읽기는 func 0x04. count <= 125 워드
  - 응답 `[txid][0][len][unit][func][bytecnt]` + 레지스터. 레지스터 열:
      stationid 상위·하위 16비트 2워드, 이어서 ACON(번호 오름차순)마다 7워드
      [번호, 설정온도(ACON n.3)*10, 현재온도(ACON n.1)*10, 인버터 출력(n.18), ON/OFF(n.20), 압축기1(n.23 bit1), 압축기2(n.23 bit2)]
  - 범위 초과(addr+count > 전체 워드 수)는 예외 응답: func|0x80, bytecnt 2
  - 지원하지 않는 func 는 func 0x84 + bytecnt 1 로 응답
  - ACON 1.x 값 주입: GW1 port 1 의 채널 (1.1 -> ch1, 1.3 -> ch3, 1.18 -> ch18, 1.20 DI -> ch1, 1.23 DI -> ch17/18)
"""
import os
import time

import pytest

import dpapi
from sim import hostclient as hc

pytestmark = pytest.mark.device

GW1 = "10.99.0.11"
STATION = 139600
IS_REF = os.environ.get("DP_TARGET") == "ref"
# 알려진 차이(task 004): 기준 장치에 배포된 acon_agent(2026-03-10)는 저장소 소스와 다른 개정판이다.
# 배포본은 ACON당 11워드 [번호, 설정온도, 현재온도, (미상 0), 인버터, ON/OFF, 압축기1, 압축기2, 미상 3워드]를 돌려준다.
# 소스(7워드 블록)로 만든 신 환경 빌드는 소스 레이아웃을 따른다. 배포본의 실제 소스를 확보해 반영해야 한다.
REVISION_DIFF = "배포된 acon_agent는 저장소 소스와 다른 개정판(ACON당 11워드). 실제 소스 확보 필요"


def set_ai(dp, ch, v):
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": ch, "value": v})


def set_di(dp, ch, v):
    dp.sim({"op": "set_di", "ip": GW1, "port": 1, "ch": ch, "value": v})


def regs(dp, addr=0, count=9):
    return hc.acon_registers(hc.acon_query(dp, addr, count))


def wait_regs(dp, pred, timeout=40):
    return dpapi.wait_for(lambda: (lambda r: r if pred(r) else None)(regs(dp)), timeout=timeout, step=1.0)


def test_station_id_is_first_two_registers(dp, evidence):
    r = regs(dp, 0, 2)
    assert r == [STATION >> 16, STATION & 0xFFFF]
    evidence("acon_station_regs", r)


def test_acon1_registers_follow_lport_values(dp, evidence):
    if IS_REF:
        # 증거만 기록하고(신·구 비교에서 차이로 나타남) 소스 레이아웃 검증은 건너뛴다
        set_ai(dp, 1, 25.5)
        set_ai(dp, 3, 24.0)
        set_ai(dp, 18, 7.0)
        set_di(dp, 1, 1)
        set_di(dp, 17, 1)
        set_di(dp, 18, 0)
        time.sleep(15)
        evidence("acon1_registers", regs(dp)[2:9])
        evidence("acon_block_words_second_acon_at", next((i for i, v in enumerate(regs(dp, 0, 40)[3:], 3) if v == 2), None))
        pytest.xfail(REVISION_DIFF)
    set_ai(dp, 1, 25.5)       # ACON 1.1 현재온도
    set_ai(dp, 3, 24.0)       # ACON 1.3 설정온도
    set_ai(dp, 18, 7.0)       # ACON 1.18 인버터 출력
    set_di(dp, 1, 1)          # ACON 1.20 ON
    set_di(dp, 17, 1)         # ACON 1.23 bit1 -> 압축기1
    set_di(dp, 18, 0)         # 압축기2 OFF
    want = [1, 240, 255, 7, 1, 1, 0]
    got = wait_regs(dp, lambda r: r[2:9] == want)
    assert got, "ACON 1 레지스터 %s, 기대 %s" % (regs(dp)[2:9], want)
    evidence("acon1_registers", got[2:9])
    evidence("acon_block_words_second_acon_at", next((i for i, v in enumerate(regs(dp, 0, 40)[3:], 3) if v == 2), None))
    set_di(dp, 18, 1)
    got = wait_regs(dp, lambda r: r[2:9] == [1, 240, 255, 7, 1, 1, 1])
    assert got, "압축기2 비트 반영 실패"


def test_temperature_registers_are_value_times_10_truncated(dp, evidence):
    out = {}
    for v in (0.0, 0.05, 12.34, 99.9):
        set_ai(dp, 1, v)
        want = int(hc.float32(v) * 10.0)
        got = wait_regs(dp, lambda r: r[4] == want)
        assert got, "v=%s: 현재온도 레지스터 %s, 기대 %d" % (v, regs(dp)[4], want)
        out[str(v)] = want
    evidence("acon_temperature_scaling", out)


def test_registers_continue_across_acon_blocks(dp):
    """ACON 2의 7워드는 ACON 1 바로 뒤(워드 9~15)에 이어진다"""
    if IS_REF:
        pytest.xfail(REVISION_DIFF)
    r = regs(dp, 0, 16)
    assert r[2] == 1 and r[9] == 2


def test_out_of_range_read_returns_exception(dp, evidence):
    resp = hc.acon_query(dp, 0, 125, func=4)           # 전체 워드 수(2+7*ACON 수)보다 큼
    total_ok = len(resp) > 9 and resp[7] == 4
    if total_ok:
        # ACON 수가 많아 125워드도 범위 안이면 더 큰 주소로 시도
        resp = hc.acon_query(dp, 10000, 1, func=4)
    assert resp[7] == 0x84, resp.hex()
    evidence("acon_range_exception", resp.hex()[8:])


def test_unsupported_function_code_gets_0x84_error(dp, evidence):
    resp = hc.acon_query(dp, 0, 1, func=3)
    assert resp[7] == 0x84 and resp[8] == 1
    evidence("acon_unsupported_func", resp.hex()[8:])


def test_word_count_over_125_is_rejected(dp):
    resp = hc.acon_query(dp, 0, 126, func=4)
    assert resp[7] == 0x84


def test_short_request_gets_error_response(dp, evidence):
    ch = dp.tcp(9785)
    try:
        ch.sendall(b"\x00\x01\x00\x00\x00\x02\x01\x04")
        time.sleep(1)
        resp = ch.recv(64)
    finally:
        ch.close()
    assert len(resp) == 9 and resp[7] == 0x90 and resp[8] == 4, resp.hex()
    evidence("acon_short_request", resp.hex())
