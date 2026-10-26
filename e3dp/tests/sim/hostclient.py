"""Host(상위 서버) 역할의 클라이언트. 현재는 realdata_server(TCP 7995) 프로토콜.

명세 출처: e3dp.2.1/src/realdata/realdata_server.c, realdata_struct.h
  헤더 15바이트(packed, 멀티바이트는 호스트(ARM little-endian) 순서):
    wire_id[6] ASCII | svc_type[2] ASCII('00' 전체, '01' DI, '02' AI) | data_len short | data_cnt short
    | next_yn char('Y'/'N') | result[2] ASCII
  요청 본문: data_cnt * 8 바이트(내용 무시). data_cnt 0 이거나 wire_id가 다르면 result '01'로 응답 후 연결 종료.
  응답 레코드 22바이트(packed): index_id[8] | value int | min_value int | max_value int | status ushort
    index_id = compname(4) + compno(2자리) + portno(2자리)
    AI value = float2int(v): v<0 이면 int(-v*1000)+1e9, 아니면 int(v*1000). 응답은 최대 90건씩 나뉘어 오며
    마지막 메시지의 next_yn 은 'N'.
"""
import struct

HEADER = struct.Struct("<6s2shhc2s")
RECORD = struct.Struct("<8siiiH")
MAX_RAW = 90


def float32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def float2int(v):
    """DP(lib/e3/e3lib.c float2int)의 계산을 그대로 모사. 입력은 float32로 취급."""
    f = float32(v)
    if f < 0:
        return int(f * -1000.0) + 1000000000
    return int(f * 1000.0)


def build_request(wire_id, svc="00", cnt=1, next_yn=b"Y", body=None, data_len=0):
    body = bytes(cnt * 8) if body is None else body
    return HEADER.pack(("%06d" % wire_id).encode(), svc.encode(), data_len, cnt, next_yn, b"00") + body


def read_exact(ch, n):
    buf = b""
    while len(buf) < n:
        d = ch.recv(n - len(buf))
        if not d:
            raise EOFError("연결 종료 (%d/%d 바이트)" % (len(buf), n))
        buf += d
    return buf


def read_messages(ch, limit=200):
    """next_yn 이 'N' 인 메시지까지 읽는다. 반환: [(헤더 dict, [레코드 dict...])]"""
    msgs = []
    for _ in range(limit):
        raw = read_exact(ch, HEADER.size)
        wire, svc, dlen, cnt, nxt, res = HEADER.unpack(raw)
        body = read_exact(ch, dlen) if dlen else b""
        recs = []
        for i in range(0, len(body), RECORD.size):
            idx, val, mn, mx, st = RECORD.unpack(body[i:i + RECORD.size])
            recs.append({"index_id": idx.decode(errors="replace"), "value": val, "min": mn, "max": mx, "status": st})
        msgs.append(({"wire_id": wire.decode(), "svc": svc.decode(), "data_len": dlen, "data_cnt": cnt,
                      "next_yn": nxt.decode(), "result": res.decode()}, recs))
        if nxt == b"N":
            break
    return msgs


def query(board, wire_id, svc="00", port=7995, **kw):
    ch = board.tcp(port)
    try:
        ch.sendall(build_request(wire_id, svc, **kw))
        return read_messages(ch)
    finally:
        ch.close()


# ---------------------------------------------------------------- acon_agent (Modbus TCP 서버, 포트 9785)
def acon_request(txid, unit, func, addr, count):
    return struct.pack(">HHHBBHH", txid, 0, 6, unit, func, addr, count)


def acon_query(board, addr, count, func=4, unit=1, txid=1, port=9785):
    """acon_agent에 Modbus 읽기 요청을 보내고 응답 바이트를 반환한다."""
    ch = board.tcp(port)
    try:
        ch.sendall(acon_request(txid, unit, func, addr, count))
        buf = b""
        ch.settimeout(5)
        while True:
            try:
                d = ch.recv(4096)
            except Exception:
                break
            if not d:
                break
            buf += d
            if len(buf) >= 9 and len(buf) >= 9 + buf[8] and buf[7] < 0x80:
                break
            if len(buf) >= 9 and buf[7] >= 0x80:
                break
        return buf
    finally:
        ch.close()


def acon_registers(resp):
    """정상 응답 -> 16비트 레지스터 목록 (헤더 9바이트: txid proto len unit func bytecnt)"""
    n = resp[8]
    return list(struct.unpack(">%dH" % (n // 2), resp[9:9 + n]))
