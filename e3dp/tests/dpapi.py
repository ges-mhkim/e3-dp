"""DP 상태 조회/설정 보조: 보드의 emon/comp 출력 파싱, 시뮬레이터 주소 변환, 대기 함수."""
import re
import time

import os

FIXTURE = "fixtures/ref_220/"
SIM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim")
# Host 시뮬레이터 주소. gather_server가 자신의 UDP 7062에 바인딩되어 있으므로 127.0.0.1로 두면 정시 데이터가
# 자기 자신에게 돌아온다. 루프백 /8 의 다른 주소를 써서 분리한다.
HOST_SIM_IP = "127.0.0.2"


def make_db(src_text, period=None):
    """기준 장치 nelite.db의 GW 주소(192.168.123.1N)를 시뮬레이터 주소(10.99.0.1N)로 바꾼다.
    period: 정시 수집 주기(분: 10, 60, 120). 'Wire Info' 절의 마지막 값을 바꾼다."""
    t = re.sub(r"192\.168\.123\.(1\d)\b", r"10.99.0.\1", src_text)
    if period is not None:
        lines = t.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("* Wire Info"):
                j = i + 1
                while not lines[j].strip():
                    j += 1
                f = lines[j].split()
                f[-1] = str(period)
                lines[j] = " ".join(f) + " "
                break
        t = "\n".join(lines)
    return t


def make_conf(src_text, board_ip):
    """기준 장치 nelite.conf를 시험용으로 변환: 상위 서버·경보 서버는 Host 시뮬레이터 주소, 자기 주소는 보드 주소."""
    t = src_text.replace("ALARM_HOST_IP = 10.10.0.144", "ALARM_HOST_IP = " + HOST_SIM_IP)
    t = t.replace("HOST_IP = 10.10.0.144", "HOST_IP = " + HOST_SIM_IP)
    return t.replace("MIH_IP = 10.10.0.220", "MIH_IP = " + board_ip)


def parse_lport(out):
    """`comp <NAME> <no> <port>` 출력 -> dict(type, val, st, com, high, low)"""
    m = re.search(r"type\(\s*(\d+):\w+\)\s+val\(\s*([-\d.]+)\)\s+st\(\s*(\d+):(\w+)\s*\)\s+com\((0x[0-9a-fA-F]+)", out)
    if not m:
        return None
    h = re.search(r"high\(\s*([-\d.]+)\)\s+low\(\s*([-\d.]+)\)", out)
    return {"type": int(m.group(1)), "val": float(m.group(2)), "st": int(m.group(3)),
            "st_name": m.group(4), "com": int(m.group(5), 16),
            "high": float(h.group(1)) if h else None, "low": float(h.group(2)) if h else None}


def lport(board, name, no, port):
    return parse_lport(board.tool("comp %s %d %d" % (name, no, port)))


def shelves(board):
    """`emon sys` -> {(unit, modbus_port): status}. status 0=정상, 3=통신이상"""
    out = board.tool("emon sys")
    res = {}
    for m in re.finditer(r"Unit\(\s*(\d+)\)\s+Modbus\(\s*(\d+)\).*?\bst\(\s*(\d+)\)", out):
        res[(int(m.group(1)), int(m.group(2)))] = int(m.group(3))
    return res


def wait_for(fn, timeout=20.0, step=0.5):
    """fn()이 truthy를 반환할 때까지 대기. 반환값 또는 None."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def parse_lports(db_text):
    """nelite.db의 'Logicalport Info' 절 -> [dict(compid, compname, compno, portno, type)] (DB 순서 = DrDB->lport 순서)"""
    res = []
    on = False
    for line in db_text.splitlines():
        if line.startswith("* Logicalport Info"):
            on = True
            continue
        if line.startswith("* ") and on:
            break
        if on and line.strip():
            f = line.split()
            res.append({"compid": int(f[0]), "compname": f[1], "compno": int(f[2]),
                        "portno": int(f[3]), "type": int(f[4])})
    return res


def station_id(db_text):
    """'Wire Info' 절의 첫 값(stationid)"""
    on = False
    for line in db_text.splitlines():
        if line.startswith("* Wire Info"):
            on = True
            continue
        if on and line.strip():
            return int(line.split()[0])
    return None


# ---- Host 시뮬레이터(hostsim) 조작 보조 ----
HOSTSIM_CTL = 19001


def host_packets(dp):
    return dp.sim({"op": "get_log"}, HOSTSIM_CTL)["log"]


def host_alarms(dp):
    """Host가 받은 경보(UDP 7704)를 [(패킷, 헤더, 필드)]로 해석"""
    from sim import ber
    return [(p,) + ber.parse_alarm(bytes.fromhex(p["hex"])) for p in host_packets(dp) if p["port"] == 7704]


def ack_mode(dp, mode):
    dp.sim({"op": "ack_mode", "mode": mode}, HOSTSIM_CTL)


def drain_alarms(dp, quiet=6.0, timeout=150):
    """ACK(rid)를 켜고 새 경보가 quiet초 동안 없을 때까지 기다린다(기동 직후 모든 LPORT의 초기 경보 처리)."""
    ack_mode(dp, "rid")
    t_end = time.time() + timeout
    last_n, last_t = -1, time.time()
    while time.time() < t_end:
        n = len(host_packets(dp))
        if n != last_n:
            last_n, last_t = n, time.time()
        elif time.time() - last_t >= quiet:
            return n
        time.sleep(1)
    raise AssertionError("경보가 계속 발생하여 안정되지 않음")


def host_request(dp, service, pdu, rid=7, port=40000, wait=3.0):
    """Host -> DP(main_server UDP 7999) 요청을 보내고 caddr 포트로 돌아오는 응답 데이터그램 목록(bytes)을 반환한다."""
    from sim import ber
    dg = ber.build_request_datagram(service, pdu, rid, "127.0.0.1", port)
    return [bytes.fromhex(h) for h in dp.udp_send(7999, dg, src_port=port, wait=wait)]


def download(dp, db_text, caddr_port=40300):
    """Host 설정 다운로드(START -> STORE들 -> END)를 수행하고 메시지별 TCP 응답 바이트 수 목록을 반환한다.
    DP는 메시지마다 요청의 caddr로 TCP 연결해 1024바이트 응답을 보낸다(sim/dbdl.py 참조)."""
    from sim import dbdl
    sizes = []
    for svc, dg in dbdl.messages(dbdl.parse_db(db_text), caddr_port=caddr_port):
        wait = 4 if svc == dbdl.SVC_START else 7 if svc == dbdl.SVC_END else 1.2
        r = dp.host_request_tcp(SIM_DIR + "/hostreq.py", dg, caddr_port, wait=wait)
        sizes.append([len(bytes.fromhex("".join(c))) for c in r["tcp"]])
    return sizes


def db_row_diffs(a_text, b_text):
    """두 nelite.db 텍스트의 섹션별 행 차이 수 {섹션: 차이 행 수} (행 수가 다르면 큰 값)"""
    from sim import dbdl
    A, B = dbdl.parse_db(a_text), dbdl.parse_db(b_text)
    out = {}
    for k in ("wire", "shelves", "comps", "lports", "points"):
        a, c = (A[k], B[k]) if k != "wire" else ([A[k]], [B[k]])
        a = [[str(x) for x in r] for r in a]
        c = [[str(x) for x in r] for r in c]
        out[k] = sum(1 for r1, r2 in zip(a, c) if r1 != r2) + abs(len(a) - len(c))
    return out


RECT_SIM_IP = "10.99.0.17"
RECT_SHELF = 7          # 정류기 셸프 번호(rack 1, Modbus# 1 = board 1)
RECTSIM_CTL = 19002
# (compid, 이름, compno, 포트, 타입) : ACDS 301 AI 1~7 + DI 22, DCDS 302 AI 1~3, RECT 303 AI 1~4
RECT_PORTS = ([(301, "ACDS", 1, p, 1) for p in range(1, 8)] + [(301, "ACDS", 1, 22, 0)]
              + [(302, "DCDS", 1, p, 1) for p in (1, 2, 3)] + [(303, "RECT", 1, p, 1) for p in (1, 2, 3, 4)])


def make_db_rect(src_text, ip=RECT_SIM_IP):
    """시험용 DB에 정류기 셸프(MR-RECT)와 ACDS/DCDS/RECT 구성품·포트·포인트를 추가한다. 섹션 건수와 Wire Info 합계를 갱신."""
    lines = src_text.split("\n")

    def insert(title, rows):
        i = next(k for k, l in enumerate(lines) if l.startswith("* " + title))
        m = re.match(r"(.*\()(\d+)(\).*)", lines[i])
        lines[i] = "%s%d%s" % (m.group(1), int(m.group(2)) + len(rows), m.group(3))
        j = i + 1
        while j < len(lines) and not lines[j].startswith("* "):
            j += 1
        while not lines[j - 1].strip():
            j -= 1
        lines[j:j] = rows

    insert("System Info", ["   1    %d    1    3   32 %s" % (RECT_SHELF, ip)])
    insert("Component Info", ["   3 %s  %d    1    0    0    0    0    1   50    %d    1" % (n, c, sum(1 for x in RECT_PORTS if x[0] == c))
                              for c, n in ((301, "ACDS"), (302, "DCDS"), (303, "RECT"))])
    insert("Logicalport Info", ["%4d %s %4d %4d %4d %10.3f %10.3f %5d %4d %10.3f" %
                                (c, n, no, p, t, 0.0, 0.0, 65535 if t == 0 else 0, 1, 0.0) for c, n, no, p, t in RECT_PORTS])
    insert("Point Info", ["%4d %s %4d %4d %4d %4d %4d %4d %4d %4d %4d %4d" %
                          (c, n, no, p, 0, k + 1, 1, RECT_SHELF, 1, 1 if c == 303 else k + 1, 18, 0) for k, (c, n, no, p, t) in enumerate(RECT_PORTS)])
    i = next(k for k, l in enumerate(lines) if l.startswith("* Wire Info"))
    j = i + 1
    while not lines[j].strip():
        j += 1
    f = lines[j].split()
    f[2], f[3], f[4] = str(int(f[2]) + 3), str(int(f[3]) + len(RECT_PORTS)), str(int(f[4]) + len(RECT_PORTS))
    lines[j] = " ".join(f) + " "
    return "\n".join(lines)

