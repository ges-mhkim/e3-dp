"""Host 설정 다운로드(db_server) 시뮬레이터: nelite.db 텍스트를 다운로드 메시지(UDP 7999)로 변환한다.

명세 출처: e3dp.2.1/src/db/ldb_decode.c, ldb_download.c, ldb_handler.c, lib/mpu/ldb_oid.c, include/pdu/module_mib.h
메시지 순서: START(0x02000001) -> SHELF(0x02000111) -> MODULE(0x02000501) -> EQUIP(0x02000507)
             -> LPORT(0x0200050A) -> POINT(0x0200050D) -> END(0x02000002)
각 STORE 메시지는 변수 여러 개(레코드당 1개). 전체 UDP 데이터그램은 2048바이트 이하(main_server 제한).
변수 이름 = <테이블 prefix>.<값 필드>.0.<인덱스들>, 값 = 마지막 필드(정수).
  module : 1.1.5.6.0.<stationid>.<type>.<usedcomps>.<total_ports>.<total_points>            = periodinterval
  comp   : 1.1.5.7.11.0.<facilid>.<compid>.<compno>.<par1id>.<par1no>.<par2id>.<par2no>.<maxcomp>.<bucket>.<usedports> = seq
  lport  : 1.1.5.8.8.0.<compid>.<compno>.<portno>.<type>.<high>.<low>.<mask>                = usedpoints
            high/low = float2int (compid 103 포트 11·12, 107/108/201/207 포트 10 은 원시 정수), mask = DI는 ~mask&0xFFFF, AI는 mask&0xFFFF
  point  : 1.1.5.9.11.0.<compid>.<compno>.<portno>.<bitno>.<serial>.<rack>.<shelf>.<board>.<channel>.<contact> = durtime
  shelf  : 1.1.5.10.1.6.0.<rack>.<shelf>.<compid>.<compno>.<maxcomp>                        = IPv4 주소(inet_ntoa에 넣는 호스트 순서 정수)
"""
import socket
import struct

from sim import ber
from sim import hostclient as hc

SVC_START, SVC_END = 0x02000001, 0x02000002
SVC_SHELF, SVC_MODULE, SVC_EQUIP, SVC_LPORT, SVC_POINT = 0x02000111, 0x02000501, 0x02000507, 0x0200050A, 0x0200050D
MAX_DATAGRAM = 2048
SPECIAL_RAW_LIMITS = {(103, 11), (103, 12), (107, 10), (108, 10), (201, 10), (207, 10)}


def _section(text, title):
    rows, on = [], False
    for line in text.splitlines():
        if line.startswith("* " + title):
            on = True
            continue
        if line.startswith("* ") and on:
            break
        if on and line.strip():
            rows.append(line.split())
    return rows


def parse_db(text):
    wire = [int(x) for x in _section(text, "Wire Info")[0]]
    return {
        "wire": wire,
        "shelves": _section(text, "System Info"),
        "comps": _section(text, "Component Info"),
        "lports": _section(text, "Logicalport Info"),
        "points": _section(text, "Point Info"),
    }


def _ip_int(ip):
    """inet_ntoa(in) 에 넣는 정수: s_addr 은 네트워크 바이트 순서로 저장되므로 호스트(LE)에서 바이트를 그대로 읽은 값"""
    return struct.unpack("<i", socket.inet_aton(ip))[0]


def _vb(arcs, value):
    return ber.enc_varbind(arcs, ber.enc_int(value))


def varbinds(db):
    """테이블별 변수 바인딩 목록 {서비스: [bytes...]}"""
    w = db["wire"]
    out = {}
    out[SVC_MODULE] = [_vb((1, 1, 5, 6, 0, w[0], w[1], w[2], w[3], w[4]), w[5])]
    out[SVC_SHELF] = [_vb((1, 1, 5, 10, 1, 6, 0, int(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4])), _ip_int(r[5]))
                      for r in db["shelves"]]
    out[SVC_EQUIP] = []
    for r in db["comps"]:
        facil, _name, cid, cno, p1i, p1n, p2i, p2n, mx, bk, up, seq = [r[0], r[1]] + [int(x) for x in r[2:]]
        out[SVC_EQUIP].append(_vb((1, 1, 5, 7, 11, 0, int(facil), cid, cno, p1i, p1n, p2i, p2n, mx, bk, up), seq))
    out[SVC_LPORT] = []
    for r in db["lports"]:
        cid, cno, pno, typ = int(r[0]), int(r[2]), int(r[3]), int(r[4])
        hi, lo, mask, used = float(r[5]), float(r[6]), int(r[7]), int(r[8])
        if (cid, pno) in SPECIAL_RAW_LIMITS:
            hi_i, lo_i = int(hi), int(lo)
        else:
            hi_i, lo_i = hc.float2int(hi), hc.float2int(lo)
        arc_mask = (~mask) & 0xFFFF if typ == 0 else mask & 0xFFFF
        out[SVC_LPORT].append(_vb((1, 1, 5, 8, 8, 0, cid, cno, pno, typ, hi_i, lo_i, arc_mask), used))
    out[SVC_POINT] = []
    for r in db["points"]:
        v = [int(x) for x in r[:1] + r[2:]]
        cid, cno, pno, bit, ser, rack, shelf, board, ch, contact, dur = v
        out[SVC_POINT].append(_vb((1, 1, 5, 9, 11, 0, cid, cno, pno, bit, ser, rack, shelf, board, ch, contact), dur))
    return out


def chunk(vbs, max_pdu):
    """변수 바인딩을 PDU 크기 제한에 맞게 묶는다"""
    groups, cur, size = [], [], 0
    for v in vbs:
        if cur and size + len(v) > max_pdu:
            groups.append(cur)
            cur, size = [], 0
        cur.append(v)
        size += len(v)
    if cur:
        groups.append(cur)
    return groups


def messages(db, rid_start=100, caddr_port=40300):
    """다운로드 전체의 (서비스, UDP 데이터그램) 목록"""
    vb = varbinds(db)
    max_pdu = MAX_DATAGRAM - ber.HDR_LEN - 16 - 1000        # 헤더·PDU 머리 여유 + 안전 여유(응답 시 main_server 가 2048바이트로 복사)
    out = [(SVC_START, ber.build_request_datagram(SVC_START, b"", rid_start, caddr_port=caddr_port))]
    rid = rid_start
    for svc in (SVC_SHELF, SVC_MODULE, SVC_EQUIP, SVC_LPORT, SVC_POINT):
        for g in chunk(vb[svc], max_pdu):
            rid += 1
            pdu = ber.build_pdu(ber.SET_REQ_MSG, g, reqid=rid)
            out.append((svc, ber.build_request_datagram(svc, pdu, rid, caddr_port=caddr_port)))
    out.append((SVC_END, ber.build_request_datagram(SVC_END, b"", rid + 1, caddr_port=caddr_port)))
    return out
