"""DP가 Host와 주고받는 메시지 해석: 44바이트 공통 헤더 + BER(ASN.1, SNMP 유사) 본문.

공통 헤더(44바이트, include/com/DrCom.h EcDispatchHeaderRec 크기):
  type,size,service,rid : 4바이트 빅엔디안(전송 직전 htonl)
  protocol              : 4바이트 호스트(little-endian) 순서
  caddr(sockaddr_in 16) : family 빅엔디안 2 | port 네트워크 2 | addr 4 | zero 8
  priority, did         : 4바이트 호스트 순서
본문(PDU): a8 00 + 정수 3개(02 01 00) 뒤에 변수 바인딩. 각 바인딩은 `30 82 <len16>` + OID(06) + 값.
  값 태그: 02 정수(부호 있는 빅엔디안), 04 문자열, 43 TIMETICKS(부호 없는 빅엔디안)
알람 OID 마지막 바이트(prefix 29 02 04 01 xx): 01 stationid, 02 equipid, 03 equipno, 04 portno, 05 value,
  06 status, 07 peakvalue, 08 otime, 09 rtime, 0a type, 0b highlimit, 0c lowlimit
"""
import struct

ALARM_FIELDS = {1: "stationid", 2: "equip", 3: "compno", 4: "portno", 5: "value", 6: "status",
                7: "peak", 8: "otime", 9: "rtime", 10: "type", 11: "high", 12: "low"}
HDR_LEN = 44


def parse_header(raw):
    t, size, service, rid = struct.unpack(">iiii", raw[:16])
    protocol, = struct.unpack("<i", raw[16:20])
    fam, port, = struct.unpack(">HH", raw[20:24])
    ip = ".".join(str(b) for b in raw[24:28])
    priority, did = struct.unpack("<ii", raw[36:44])
    return {"type": t, "size": size, "service": service, "rid": rid, "protocol": protocol,
            "family": fam, "port": port, "ip": ip, "priority": priority, "did": did}


def _len(raw, i):
    b = raw[i]
    if b < 0x80:
        return b, i + 1
    n = b & 0x7F
    return int.from_bytes(raw[i + 1:i + 1 + n], "big"), i + 1 + n


def parse_varbinds(body):
    """본문에서 (oid 바이트, 태그, 값) 목록을 추출한다."""
    i = body.find(b"\x30\x82")
    out = []
    while i >= 0 and i + 4 <= len(body) and body[i] == 0x30:
        ln, j = _len(body, i + 1)
        end = j + ln
        if body[j] != 0x06:
            break
        ol, k = _len(body, j + 1)
        oid = bytes(body[k:k + ol])
        k += ol
        tag = body[k]
        vl, k2 = _len(body, k + 1)
        v = bytes(body[k2:k2 + vl])
        if tag == 0x02:
            val = int.from_bytes(v, "big", signed=True)
        elif tag == 0x43:
            val = int.from_bytes(v, "big")
        elif tag == 0x04:
            val = v.decode("ascii", errors="replace")
        else:
            val = v
        out.append((oid, tag, val))
        i = end
    return out


def parse_alarm(raw):
    """UDP 데이터그램 전체 -> (헤더 dict, 필드 dict)"""
    h = parse_header(raw)
    f = {}
    for oid, tag, val in parse_varbinds(raw[HDR_LEN:]):
        name = ALARM_FIELDS.get(oid[-1])
        if name:
            f[name] = val
    return h, f


# ---------------------------------------------------------------- 빌더 (Host -> DP 요청 본문)
SET_REQ_MSG = 0xA3
REPO_REQ_MSG = 0xA8
RT_VALUE_OID = (1, 1, 6, 1, 1, 5)           # ev_rt__value_oid (trailing 0 제외); 요청에서는 0 + 5개 인덱스를 붙인다


def enc_len(n):
    """DP의 varbind 길이는 항상 `82 hh ll` (2바이트 확장형)"""
    return b"\x82" + struct.pack(">H", n)


def enc_int(v):
    """부호 있는 최소 길이 정수 (tag 02)"""
    n = 1
    while not (-(1 << (8 * n - 1)) <= v < (1 << (8 * n - 1))):
        n += 1
    return b"\x02" + bytes([n]) + v.to_bytes(n, "big", signed=True)


def enc_uint_ticks(v):
    """TIMETICKS(tag 43)는 DP가 항상 4바이트(unsigned long, 32비트)로 인코딩한다"""
    return b"\x43\x04" + v.to_bytes(4, "big")


def enc_str(s):
    b = s.encode("ascii")
    return b"\x04" + bytes([len(b)]) + b


def enc_oid(arcs):
    body = bytes([arcs[0] * 40 + arcs[1]])
    for a in arcs[2:]:
        chunk = [a & 0x7F]
        a >>= 7
        while a:
            chunk.append(0x80 | (a & 0x7F))
            a >>= 7
        body += bytes(reversed(chunk))
    return b"\x06" + bytes([len(body)]) + body


def enc_varbind(arcs, value_tlv):
    inner = enc_oid(arcs) + value_tlv
    return b"\x30" + enc_len(len(inner)) + inner


def build_pdu(msg_type, varbinds, reqid=0):
    """PDU 본문: [type, 00] + 정수 reqid, errstat, errindex + varbind 목록. (최상위 길이는 0으로 두는 것이 DP 형식)"""
    return bytes([msg_type, 0]) + enc_int(reqid) + enc_int(0) + enc_int(0) + b"".join(varbinds)


def rt_request(stationid, compid, compno, portno, status, value, reqid=0):
    """실시간/설정 계열 요청(409 한계치 등)의 PDU. 변수 이름 = 1.1.6.1.1.5.0.<stationid>.<compid>.<compno>.<portno>.<status>"""
    name = RT_VALUE_OID + (0, stationid, compid, compno, portno, status)
    return build_pdu(SET_REQ_MSG, [enc_varbind(name, enc_int(value))], reqid)


def build_request_datagram(service, pdu, rid=7, caddr_ip="127.0.0.1", caddr_port=40000):
    """Host -> DP UDP 요청 (44바이트 헤더 + PDU). 모든 정수 필드가 빅엔디안(main_server가 htonl로 읽음)."""
    hdr = struct.pack(">iiiii", 1, len(pdu), service, rid, 1)
    hdr += struct.pack(">HH", 2, caddr_port) + bytes(int(x) for x in caddr_ip.split(".")) + bytes(8)
    hdr += struct.pack(">i", 0)
    return hdr + bytes(4) + pdu


def rebuild_alarm_body(fields_in_order):
    """파싱한 (oid, tag, value) 목록으로 본문을 다시 만든다(왕복 검증용)."""
    out = []
    for oid_bytes, tag, val in fields_in_order:
        arcs = decode_oid(oid_bytes)
        if tag == 0x02:
            tlv = enc_int(val)
        elif tag == 0x43:
            tlv = enc_uint_ticks(val)
        else:
            tlv = enc_str(val)
        out.append(enc_varbind(arcs, tlv))
    return b"".join(out)


def decode_oid(b):
    arcs = [b[0] // 40, b[0] % 40]
    v = 0
    for x in b[1:]:
        v = (v << 7) | (x & 0x7F)
        if not x & 0x80:
            arcs.append(v)
            v = 0
    return tuple(arcs)


RT_FIELDS = {1: "stationid", 2: "equip", 3: "compno", 4: "portno", 5: "value", 6: "status", 7: "type"}


def parse_rt_response(raw):
    """DP -> Host 응답(설정 계열 서비스): 헤더 + 변수 이름 1.1.6.1.1.<필드>"""
    h = parse_header(raw)
    f = {}
    for oid, tag, val in parse_varbinds(raw[HDR_LEN:]):
        name = RT_FIELDS.get(oid[-1])
        if name:
            f[name] = val
    return h, f
