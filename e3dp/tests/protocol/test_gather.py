"""gather_server 정시 수집 송신(UDP 7062, DP -> Host).
명세 출처: e3dp.2.1/src/gather/gather_server.c (DrPeriod__check_period_time, gather_period_data, send_handler,
          append_pdu_message, send_period_data)
  - 주기(`Wire Info`의 마지막 값): 10분이면 분(minute)이 10의 배수가 되는 순간, 60분이면 정각, 120분이면 짝수 시 정각
  - 수집 대상: AI(type 1)·RMM(type 3) LPORT. 제외: compid 302의 포트 7·8, compid 111, compid 501의 포트 11
  - 전송: SET 요청 PDU, 메시지당 변수 20개(마지막 메시지는 나머지). 변수 이름 = 1.1.3.5.1.6(period value) + .1.<국번>.<compid>.<번호>.<포트>.<상태>.<시각>.<type>.<min>.<max>, 값 = 현재값
          값·min·max 는 float2int 인코딩. 헤더: type·size·service 는 빅엔디안, rid(1000+일련번호)는 htonl 없이 호스트(LE) 순서로 기록됨
  - Host 가 헤더의 rid 를 응답 헤더(res.rid)로 돌려주면 다음 메시지를 보낸다(응답 대기 TIMEOUT 5초)
  - 시험 방법: Host 시각 응답에 오프셋을 줘서 보드 시계가 다음 10분 경계 직전이 되게 한다(tests/tools/board.py env_up)
"""
import os
import time

import pytest

import dpapi
from sim import ber
from sim import hostclient as hc

pytestmark = pytest.mark.device

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = open(os.path.join(HERE, dpapi.FIXTURE, "nelite.db"), encoding="utf-8", errors="replace").read()
LPORTS = dpapi.parse_lports(DB)
GW1 = "10.99.0.11"
SVC_PERIODIC = 301
PERIOD_VALUE_PREFIX = (1, 1, 3, 5, 1, 6)
IS_REF = os.environ.get("DP_TARGET") == "ref"
# 알려진 소스 차이(task 004): 작업 트리의 gather_server.c(jhcho 2024.12.27)는 정시 데이터를 Host 7062로 보내고
# TIMEOUT 이 40초이다. 기준 장치의 배포본은 HEAD와 같은 이전 동작으로 EC_REQUEST_UPORT(7000)로 보내고 TIMEOUT 이 10초이다.
DEST_PORT = 7000 if IS_REF else 7062


def expected_targets():
    out = []
    for l in LPORTS:
        if l["type"] not in (1, 3):
            continue
        if l["compid"] == 302 and l["portno"] in (7, 8):
            continue
        if l["compid"] == 111 or (l["compid"] == 501 and l["portno"] == 11):
            continue
        out.append(l)
    return out


@pytest.fixture(scope="module")
def gdp(board):
    board.env_up(HERE, period=10, boundary_in=110)
    dpapi.ack_mode(board, "rid")
    # 기준 값 주입(경계 전에): ACON 1.1 = 12.5
    board.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 12.5})
    assert dpapi.wait_for(lambda: abs(dpapi.lport(board, "ACON", 1, 1)["val"] - 12.5) < 0.01, 30), "값 주입 실패"
    yield board
    board.env_down()


def period_messages(dp):
    msgs = []
    for p in dpapi.host_packets(dp):
        if p["port"] != DEST_PORT:
            continue
        raw = bytes.fromhex(p["hex"])
        h = ber.parse_header(raw)
        vbs = []
        for oid, tag, val in ber.parse_varbinds(raw[ber.HDR_LEN:]):
            a = ber.decode_oid(oid)
            vbs.append({"arcs": a, "value": val})
        h["rid_le"] = int.from_bytes(raw[12:16], "little")
        msgs.append({"t": p["t"], "header": h, "vbs": vbs, "len": len(raw)})
    return msgs


@pytest.fixture(scope="module")
def msgs(gdp):
    """경계가 지나 정시 메시지가 모두 도착할 때까지 기다린 뒤 해석한 메시지 목록"""
    n_expected = len(expected_targets())

    def complete():
        m = period_messages(gdp)
        return m if sum(len(x["vbs"]) for x in m) >= n_expected else None
    got = dpapi.wait_for(complete, timeout=240, step=2.0)
    assert got, "정시 수집 메시지가 도착하지 않음 (%d건)" % len(period_messages(gdp))
    return got


def test_period_messages_arrive_at_ten_minute_boundary(gdp, msgs, evidence):
    t = msgs[0]["t"]
    # 보드 시계가 경계에 맞춰져 있으므로 첫 메시지 시각의 분이 10의 배수 (초 단위로 몇 초 이내)
    boundary_offset = int(t) % 600
    assert boundary_offset < 40 or boundary_offset > 590, "경계에서 %d초 지난 뒤 도착" % boundary_offset
    evidence("period_first_message_within_40s_of_boundary", True)
    evidence("period_destination_port", DEST_PORT)          # 의도된 소스 차이: 신 7062, 구 7000


def test_header_and_chunking_of_20_variables(gdp, msgs, evidence):
    n = len(expected_targets())
    assert sum(len(m["vbs"]) for m in msgs) == n
    sizes = [len(m["vbs"]) for m in msgs]
    assert sizes == [20] * (n // 20) + ([n % 20] if n % 20 else []), sizes
    for m in msgs:
        h = m["header"]
        # protocol·priority·did 는 send_period_data 가 설정하지 않아 재사용 버퍼의 이전 내용이 나간다(비결정). 검사하지 않는다.
        assert (h["type"], h["service"]) == (1, SVC_PERIODIC)
        # caddr.sin_family 는 경보 메시지(htons 적용)와 달리 호스트(LE) 순서로 나간다: 바이트 `02 00` -> 빅엔디안 해석 512
        assert (h["family"], h["port"], h["ip"]) == (512, 7062, gdp.host)
        assert h["size"] == m["len"] - ber.HDR_LEN
    rids = [m["header"]["rid_le"] for m in msgs]
    assert rids == list(range(rids[0], rids[0] + len(rids))), rids      # 1씩 증가
    evidence("period_chunk_sizes", sizes)
    evidence("period_first_rid", rids[0])


def test_variable_name_layout_and_values(gdp, msgs, evidence):
    by_key = {}
    for m in msgs:
        for v in m["vbs"]:
            a = v["arcs"]
            assert a[:6] == PERIOD_VALUE_PREFIX and len(a) == 16, a
            ctrl, sid, cid, cno, pno, st, tm, typ, mn, mx = a[6:16]
            assert ctrl == 1 and sid == 139600
            by_key[(cid, cno, pno)] = {"status": st, "type": typ, "min": mn, "max": mx, "value": v["value"]}
    targets = {(l["compid"], l["compno"], l["portno"]): l for l in expected_targets()}
    assert set(by_key) == set(targets)
    one = by_key[(501, 1, 1)]
    assert one["value"] == hc.float2int(12.5) and one["type"] == 1
    # 시각 필드: 첫 메시지 도착 시각과 같은 분(경계 직후)
    tms = {v["arcs"][12] for m in msgs for v in m["vbs"]}
    assert len(tms) == 1 and abs(tms.pop() - msgs[0]["t"]) < 5
    evidence("period_acon11", {k: one[k] for k in ("value", "type", "status")})
    evidence("period_variable_count", len(by_key))


def test_periodic_data_is_acked_by_rid(gdp, msgs):
    """모든 메시지가 한 번씩만 도착(ACK 후 재전송 없음)"""
    rids = [m["header"]["rid_le"] for m in msgs]
    assert len(rids) == len(set(rids)), rids
