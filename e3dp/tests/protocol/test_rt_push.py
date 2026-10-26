"""rt_server 실시간 구독·푸시: Host 구독 요청(403) -> DP가 Host로 TCP 연결 -> 값이 바뀔 때 ASCII 레코드 푸시 -> 404로 해제.
명세 출처: e3dp.2.1/src/rt/rt_server.c (add_client, send_rt_response, RealTimeClearSocket)
  - 요청(UDP, 7999로 보내면 main_server가 rt_server 8052로 중계): 44바이트 헤더 + ASCII `403` + 개수(4자리) + 항목들
      항목 14자: 국번 6자리 + 구성품명 4자 + 구성품번호 2자리 + 포트번호 2자리 (예: 139600ACON0101)
  - DP가 요청 헤더의 caddr(IP:포트)로 TCP 연결하고, 구독 목록 중 값 또는 상태가 마지막 전송값과 다를 때만 푸시
      (처음에는 마지막 값이 999999.999/상태 99 라서 모두 푸시). SEND_COUNT(2)는 송신 실패 시 재시도 횟수(중복 송신 아님)
  - 푸시 메시지: 44바이트 헤더(size 만 채움, htonl) + ASCII 레코드
      AI : %06d%4s%02d%02d%10.3f%04d   (국번 구성품 번호 포트 값 상태)
      DI·특수(포트 20~50, VCB 11/12 등): %06d%4s%02d%02d%10d%04d
  - 구독 목록에 없는 항목은 푸시하지 않음. Host가 TCP로 `404`(헤더 44바이트 뒤)를 보내면 구독 해제
"""
import re
import threading
import time

import pytest

import dpapi
from sim import ber

pytestmark = pytest.mark.device

PORT = 40200
GW1 = "10.99.0.11"
HDR = 44


def sub_request(items):
    body = b"403" + b"%04d" % len(items) + b"".join(i.encode() for i in items)
    return ber.build_request_datagram(403, body, rid=11, caddr_port=PORT)


def records(dp, items, wait=8.0, stop_after=None):
    """구독 후 wait초 동안 받은 푸시 레코드 [(시각, 문자열)] 와 연결이 닫혔는지"""
    r = dp.host_request_tcp(dpapi.SIM_DIR + "/hostreq.py", sub_request(items), PORT, wait=wait,
                            stop_after=stop_after, stop_data=(bytes(HDR) + b"404") if stop_after else b"")
    out = []
    for chunks, times in zip(r["tcp"], r["tcp_t"]):
        for ch, t in zip(chunks, times):
            raw = bytes.fromhex(ch)
            # 한 청크에 여러 메시지가 합쳐질 수 있음: 헤더 44바이트 + size 바이트 단위로 분해
            while len(raw) > HDR:
                n = int.from_bytes(raw[4:8], "big")
                out.append((t, raw[HDR:HDR + n].decode(errors="replace")))
                raw = raw[HDR + n:]
    return out, any(r["closed"])


def parse(rec):
    m = re.match(r"(\d{6})(.{4})(\d{2})(\d{2})(.{10})(\d{4})$", rec)
    assert m, rec
    return {"station": int(m.group(1)), "comp": m.group(2), "no": int(m.group(3)), "port": int(m.group(4)),
            "value": m.group(5), "status": int(m.group(6))}


def test_subscribe_pushes_initial_value_once_per_item(dp, evidence):
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 12.5})
    assert dpapi.wait_for(lambda: abs(dpapi.lport(dp, "ACON", 1, 1)["val"] - 12.5) < 0.01, 30)
    recs, _ = records(dp, ["139600ACON0101", "139600ACON0123"])
    got = [r for _, r in recs]
    assert got, "푸시가 오지 않음"
    ai = [parse(r) for r in got if r[12:14] == "01"]
    di = [parse(r) for r in got if r[12:14] == "23"]
    assert ai and di
    assert len(ai) == 1 and len(di) == 1, "항목마다 초기값 1건: AI %d, DI %d" % (len(ai), len(di))
    assert ai[0]["value"] == "    12.500" and ai[0]["station"] == 139600 and ai[0]["no"] == 1
    assert di[0]["value"] == "         0"          # DI는 %10d
    evidence("rt_initial_records", sorted(set(got)))


def test_record_is_28_chars_with_ascii_value_and_4digit_status(dp):
    recs, _ = records(dp, ["139600ACON0101"], wait=5)
    assert recs and all(len(r) == 28 for _, r in recs), [r for _, r in recs]


def test_unchanged_value_is_not_pushed_again(dp, evidence):
    recs, _ = records(dp, ["139600ACON0101"], wait=10)
    # 초기값 1건 이후 값이 변하지 않으므로 더 오지 않아야 함
    assert len(recs) == 1, "변화 없는데 %d건 수신: %s" % (len(recs), [r for _, r in recs])
    evidence("rt_unchanged_count", len(recs))


def test_changed_value_is_pushed(dp, evidence):
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("r", records(dp, ["139600ACON0101"], wait=14)))
    th.start()
    time.sleep(5)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 21.25})
    th.join()
    vals = [parse(r)["value"] for _, r in res["r"][0]]
    assert "    21.250" in vals, vals
    evidence("rt_change_values", vals)
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 12.5})


def test_unknown_item_is_ignored(dp):
    recs, _ = records(dp, ["139600ZZZZ9999", "139600ACON0101"], wait=6)
    assert recs and all(r[6:10] == "ACON" for _, r in recs)


def test_stop_request_404_closes_subscription(dp, evidence):
    recs, closed = records(dp, ["139600ACON0101"], wait=10, stop_after=4)
    evidence("rt_closed_after_404", bool(closed))
    assert closed, "404 후 DP가 연결을 닫지 않음"
