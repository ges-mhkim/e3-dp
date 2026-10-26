"""설정 다운로드 변환기(sim/dbdl.py) 검증(PC에서 실행): nelite.db -> 다운로드 메시지 -> 다시 해석 -> 원래 행과 비교."""
import os

import pytest

import dpapi
from sim import ber, dbdl

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = open(os.path.join(HERE, dpapi.FIXTURE, "nelite.db"), encoding="utf-8", errors="replace").read()
DB = dbdl.parse_db(TEXT)


def decoded(service):
    """해당 서비스 메시지들의 변수 [(arcs, value)]"""
    out = []
    for svc, dg in dbdl.messages(DB):
        if svc != service:
            continue
        for oid, tag, val in ber.parse_varbinds(dg[ber.HDR_LEN + 4:]):
            out.append((ber.decode_oid(oid), val))
    return out


def test_message_order_and_size():
    msgs = dbdl.messages(DB)
    svcs = [s for s, _ in msgs]
    assert svcs[0] == dbdl.SVC_START and svcs[-1] == dbdl.SVC_END
    order = [dbdl.SVC_SHELF, dbdl.SVC_MODULE, dbdl.SVC_EQUIP, dbdl.SVC_LPORT, dbdl.SVC_POINT]
    seen = [s for i, s in enumerate(svcs[1:-1]) if i == 0 or s != svcs[i]]
    assert seen == order
    assert all(len(dg) <= dbdl.MAX_DATAGRAM for _, dg in msgs)


def test_every_record_is_sent_once():
    assert len(decoded(dbdl.SVC_SHELF)) == len(DB["shelves"])
    assert len(decoded(dbdl.SVC_EQUIP)) == len(DB["comps"])
    assert len(decoded(dbdl.SVC_LPORT)) == len(DB["lports"])
    assert len(decoded(dbdl.SVC_POINT)) == len(DB["points"])
    assert len(decoded(dbdl.SVC_MODULE)) == 1


def test_module_record_fields():
    (arcs, val), = decoded(dbdl.SVC_MODULE)
    w = DB["wire"]
    assert arcs[:6] == (1, 1, 5, 6, 0, w[0]) and arcs[6:] == tuple(w[1:5]) and val == w[5]


def test_shelf_ip_roundtrips_through_host_order_integer():
    import socket
    import struct
    for (arcs, val), row in zip(decoded(dbdl.SVC_SHELF), DB["shelves"]):
        ip = socket.inet_ntoa(struct.pack("<i", val))
        assert ip == row[5]
        assert arcs[7:] == tuple(int(x) for x in row[:5])


def test_lport_limits_use_float2int_and_mask_rules():
    from sim import hostclient as hc
    for (arcs, val), row in zip(decoded(dbdl.SVC_LPORT), DB["lports"]):
        cid, cno, pno, typ, hi, lo, mask = arcs[6:]
        assert (cid, cno, pno, typ) == (int(row[0]), int(row[2]), int(row[3]), int(row[4]))
        assert hi == hc.float2int(float(row[5])) and lo == hc.float2int(float(row[6]))
        want = (~int(row[7])) & 0xFFFF if typ == 0 else int(row[7]) & 0xFFFF
        assert mask == want and val == int(row[8])


def test_point_fields():
    for (arcs, val), row in zip(decoded(dbdl.SVC_POINT), DB["points"]):
        got = list(arcs[6:]) + [val]
        want = [int(row[0])] + [int(x) for x in row[2:]]
        assert got == want
