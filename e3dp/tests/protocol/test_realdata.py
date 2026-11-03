"""realdata_server (TCP 7995): Host가 전체/DI/AI 원시값을 조회하는 프로토콜.
명세: sim/hostclient.py 상단 주석 (출처 e3dp.2.1/src/realdata/realdata_server.c)
"""
import os

import pytest

import dpapi
from sim import hostclient as hc

pytestmark = pytest.mark.device

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = open(os.path.join(HERE, dpapi.FIXTURE, "nelite.db"), encoding="utf-8", errors="replace").read()
LPORTS = dpapi.parse_lports(DB)
WIRE = dpapi.station_id(DB)
DI, AI, DO, RMM = 0, 1, 2, 3


def _expected(types):
    return ["%-4s%02d%02d" % (l["compname"], l["compno"], l["portno"]) for l in LPORTS if l["type"] in types]


def _records(msgs):
    return [r for _, recs in msgs for r in recs]


def test_fixture_has_all_lport_types():
    types = {l["type"] for l in LPORTS}
    assert {DI, AI} <= types and WIRE == 139600


def test_all_request_returns_di_and_ai_lports_in_db_order(dp, evidence):
    msgs = hc.query(dp, WIRE, "00")
    evidence("realdata_all_headers", [h for h, _ in msgs])
    evidence("realdata_all_ids", [r["index_id"] for r in _records(msgs)])
    ids = [r["index_id"] for r in _records(msgs)]
    assert ids == _expected({DI, AI})


@pytest.mark.parametrize("svc,types", [("01", {DI}), ("02", {AI})])
def test_typed_request_returns_only_that_type(dp, svc, types):
    ids = [r["index_id"] for r in _records(hc.query(dp, WIRE, svc))]
    assert ids == _expected(types)


def test_response_is_chunked_by_90_and_next_yn_marks_last(dp):
    msgs = hc.query(dp, WIRE, "00")
    total = len(_expected({DI, AI}))
    assert total > hc.MAX_RAW, "chunk 시험에는 90건을 넘는 LPORT 필요"
    sizes = [h["data_cnt"] for h, _ in msgs]
    assert sizes[:-1] == [hc.MAX_RAW] * (len(sizes) - 1) and sum(sizes) == total
    assert [h["next_yn"] for h, _ in msgs] == ["Y"] * (len(msgs) - 1) + ["N"]
    for h, recs in msgs:
        assert h["data_len"] == len(recs) * hc.RECORD.size == h["data_cnt"] * hc.RECORD.size
        assert h["result"] == "00" and h["wire_id"] == "%06d" % WIRE


def test_header_echoes_service_type(dp):
    msgs = hc.query(dp, WIRE, "02")
    assert all(h["svc"] == "02" for h, _ in msgs)


@pytest.mark.parametrize("bad", [dict(wire_id=WIRE + 1), dict(wire_id=WIRE, cnt=0, body=b"")])
def test_invalid_request_gets_empty_result01_and_close(dp, bad):
    ch = dp.tcp(7995)
    try:
        ch.sendall(hc.build_request(bad.pop("wire_id"), "00", **bad))
        (h, recs), = hc.read_messages(ch)
        assert (h["data_cnt"], h["next_yn"], h["result"]) == (0, "N", "01") and not recs
    finally:
        ch.close()


def test_server_still_serves_after_invalid_requests(dp):
    test_invalid_request_gets_empty_result01_and_close(dp, dict(wire_id=WIRE + 7))
    assert _records(hc.query(dp, WIRE, "02"))


@pytest.mark.parametrize("value", [0.0, 12.5, -3.25, 35.999, 0.0004, 1234.567])
def test_ai_value_encoding(dp, value, evidence):
    """ACON 1 번 LPORT 1(shelf 1, port 1, ch 1)에 값을 주입하고 float2int 인코딩을 확인."""
    dp.sim({"op": "set_ai", "ip": "10.99.0.11", "port": 1, "ch": 1, "value": value})
    assert dpapi.wait_for(lambda: (lambda p: p and abs(p["val"] - hc.float32(value)) < 0.01 and p)(
        dpapi.lport(dp, "ACON", 1, 1)), timeout=30), "값 주입 반영 실패"
    # 상태(NORM/LOW/HIGH)는 scan_server가 값 반영보다 늦게 계산하므로 정착할 때까지 기다린 뒤 조회한다.
    lp = dpapi.lport(dp, "ACON", 1, 1)
    exp = 2 if hc.float32(value) > lp["high"] else 1 if hc.float32(value) < lp["low"] else 0
    assert dpapi.wait_for(lambda: (lambda p: p and p["st"] == exp and p)(dpapi.lport(dp, "ACON", 1, 1)),
                          timeout=30), "상태가 %d로 정착하지 않음" % exp
    recs = {r["index_id"]: r for r in _records(hc.query(dp, WIRE, "02"))}
    got = recs["ACON0101"]["value"]
    evidence("ai_value_%s" % value, {"encoded": got, "min": recs["ACON0101"]["min"],
                                      "max": recs["ACON0101"]["max"], "status": recs["ACON0101"]["status"]})
    assert got == hc.float2int(value), "value=%s: 응답 %d, 기대 %d" % (value, got, hc.float2int(value))
