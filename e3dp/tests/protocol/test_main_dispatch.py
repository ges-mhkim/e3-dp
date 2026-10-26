"""main_server(UDP 7999): Host 요청 진입점의 기동 절차, 서비스 라우팅, 비정상 입력 처리.
명세 출처: e3dp.2.1/src/main/main_server.c, main_dispatch.c, main_tsync.c
  - 기동: Host(UDP 37)에 "What time is it?"(16바이트)를 보내 RFC 868 응답(1900년 기준 초, 4바이트 BE)을 받아
          stime()으로 시스템 시각 설정 후 메인 루프 진입. 응답이 없으면 계속 재요청하며 UDP 7999를 열지 않는다.
  - 요청 헤더(Host->DP): type=1(EC_REQUEST), size, service, rid, protocol 모두 빅엔디안, caddr(sockaddr_in) = 응답 받을 주소
  - size > 2048 이면 "Invalid Data Size"로 폐기, 알 수 없는 service 는 "can't find service"로 폐기
  - 라우팅(_smtable): 409 등 EC_SVC_* -> config_server(UDP 7032), 2051 등 정전/입전/디멘드 룰 -> control_server(UDP 8022),
          403/404 -> rt_server(UDP 8052), 0x0200xxxx(DB 다운로드·저장) -> db_server(UDP 8002)
"""
import re
import struct
import time

import pytest

import dpapi
from sim import ber

pytestmark = pytest.mark.device

SVC_LIMIT, SVC_CUTOFF_RULE, SVC_RT_SET, SVC_UNKNOWN = 409, 2051, 403, 9999
EC_REQUEST, EC_REPLY = 1, 4


def request(service, body=b"", rid=7, size=None, type_=EC_REQUEST, port=40000):
    """Host가 보내는 UDP 요청 데이터그램(44바이트 헤더 + 본문)"""
    size = len(body) if size is None else size
    hdr = struct.pack(">iiiii", type_, size, service, rid, 1)
    hdr += struct.pack(">HH", 2, port) + bytes([127, 0, 0, 1]) + bytes(8) + struct.pack(">i", 0)
    return hdr + bytes(4) + body


class Log(object):
    """서버 로그 파일의 '이 시점 이후' 내용을 읽는 도우미"""
    def __init__(self, dp, name):
        self.dp, self.path = dp, "/opt/e3dp/log/%s.out" % name
        self.start = int(dp.sh("wc -l < %s" % self.path).strip() or 0)

    def new(self, wait=0.0):
        time.sleep(wait)
        return self.dp.sh("tail -n +%d %s" % (self.start + 1, self.path))


def send(dp, data, wait=1.0):
    r = dp.udp_send(7999, data, wait=wait)
    return r


def alive(dp):
    p = dp.procs()
    return all(n in p for n in ("main_server", "db_server", "config_server", "control_server", "rt_server",
                                "scan_server", "alarm_server", "gather_server", "gw_server"))


def test_startup_time_sync_with_host_then_serves_udp_7999(dp, evidence):
    log = [p for p in dp.sim({"op": "get_log"}, 19001)["log"] if p["port"] == 37]
    assert log, "main_server가 Host(UDP 37)에 시각 요청을 보내지 않음"
    assert bytes.fromhex(log[0]["hex"]) == b"What time is it?"
    evidence("time_request_payload", log[0]["hex"])
    main_log = dp.sh("cat /opt/e3dp/log/main_server.out")
    assert "system time initialize ok!" in main_log
    assert "Main Server Running Now" in main_log and "[Port : 7999]" in main_log
    # /proc/net/udp: 로컬 주소 컬럼 `0.0.0.0:1F3F`(7999). 구 장치의 ss는 UDP 리스너를 표시하지 못해 직접 읽는다.
    assert dp.sh("grep -c ':1F3F ' /proc/net/udp").strip() == "1"


def test_unknown_service_is_logged_and_ignored(dp, evidence):
    log = Log(dp, "main_server")
    assert send(dp, request(SVC_UNKNOWN)) == []
    txt = log.new(1.0)
    m = re.search(r"can't find service\. size=\((\d+)\) service=\((0x[0-9A-Fa-f]+)\)", txt)
    assert m, txt
    evidence("unknown_service_log", [m.group(1), m.group(2)])
    assert alive(dp)


def test_oversize_request_is_discarded(dp, evidence):
    log = Log(dp, "main_server")
    send(dp, request(SVC_LIMIT, size=5000))
    txt = log.new(1.0)
    m = re.search(r"Invalid Data Size\.+ \((0x[0-9A-Fa-f]+) : (\d+)\)", txt)
    assert m, txt
    evidence("oversize_log", [m.group(1), m.group(2)])
    assert alive(dp)


VALID_LIMIT_BODY = ber.rt_request(139600, 501, 1, 1, 36000, 5000)     # 현재 한계치와 같은 값(변경 없음)


@pytest.mark.parametrize("name,service,server,pattern,body", [
    ("limit_to_config", SVC_LIMIT, "config_server", r"service : 409", VALID_LIMIT_BODY),
    ("cutoff_rule_to_control", SVC_CUTOFF_RULE, "control_server", r"Control Request Received\.+ service\(0x00000803\)", b""),
    ("realtime_set_to_rt", SVC_RT_SET, "rt_server", r"recv len : 2048", b""),
], ids=["limit_to_config", "cutoff_rule_to_control", "realtime_set_to_rt"])
def test_service_is_routed_to_owner_server(dp, evidence, name, service, server, pattern, body):
    log = Log(dp, server)
    send(dp, request(service, body=body))
    txt = log.new(1.5)
    assert re.search(pattern, txt), "%s 로그에 라우팅 흔적 없음:\n%s" % (server, txt)
    evidence("routed_" + name, re.search(pattern, txt).group(0))
    assert alive(dp)


def test_malformed_pdu_body_is_rejected(dp, evidence):
    """BER이 아닌 본문(바이트 1..8)은 파서가 거부하고 요청은 실행되지 않는다."""
    log = Log(dp, "config_server")
    send(dp, request(SVC_LIMIT, body=bytes([1, 2, 3, 4, 5, 6, 7, 8])))
    txt = log.new(2.0)
    assert "service : 409" in txt, txt
    assert "request decoding error" in txt and "Service Received" not in txt, txt
    evidence("malformed_body_rejected", True)
    assert alive(dp)


@pytest.mark.xfail(reason="알려진 결함(task 004): 본문이 빈 요청도 초기화되지 않은 rt_info로 성공 처리하고 nelite.db를 재저장함",
                   strict=False)
def test_empty_pdu_body_should_be_rejected(dp):
    log = Log(dp, "config_server")
    send(dp, request(SVC_LIMIT, body=b""))
    txt = log.new(2.0)
    assert "Send Response OK" not in txt and "Update Local DB Success" not in txt, txt


@pytest.mark.parametrize("size", [1, 10, 43])
def test_truncated_datagram_does_not_crash(dp, size):
    send(dp, request(SVC_LIMIT)[:size])
    time.sleep(1)
    assert alive(dp)


def test_non_request_type_is_ignored(dp):
    log = Log(dp, "main_server")
    send(dp, request(SVC_LIMIT, type_=EC_REPLY))
    txt = log.new(1.0)
    assert "can't find service" not in txt     # EC_REPLY 는 라우팅하지 않음
    assert alive(dp)


def test_burst_of_requests_keeps_servers_alive(dp):
    for i in range(50):
        dp.udp_send(7999, request(SVC_LIMIT, rid=i), wait=0)
    time.sleep(2)
    assert alive(dp)
    assert dpapi.shelves(dp).get((1, 0)) == 0
