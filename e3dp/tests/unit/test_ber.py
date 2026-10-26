"""BER 빌더 검증(PC에서 실행): DP가 실제로 보낸 경보 패킷을 파싱 -> 재구성했을 때 바이트가 같아야 한다.
샘플(fixtures/samples/*.hex)은 신 보드가 보낸 경보 데이터그램이며 rid·요청 ID·시각은 마스킹(0)되어 있다."""
import os

import pytest

from sim import ber

SAMPLES = ["alarm_high_packet", "alarm_low_packet", "alarm_recovery_packet"]


def sample(name):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "fixtures", "samples", name + ".hex")) as f:
        raw = bytes.fromhex(f.read().strip())
    return raw[ber.HDR_LEN:]          # 44바이트 헤더 뒤의 PDU


@pytest.mark.parametrize("name", SAMPLES)
def test_parse_then_rebuild_gives_same_varbinds_bytes(name):
    body = sample(name)
    vbs = ber.parse_varbinds(body)
    assert len(vbs) == 11, [ber.decode_oid(o) for o, _, _ in vbs]    # otime/rtime 중 하나만 포함
    start = body.find(b"\x30\x82")
    assert ber.rebuild_alarm_body(vbs) == body[start:]


@pytest.mark.parametrize("name", SAMPLES)
def test_pdu_prefix_is_type_and_three_integers(name):
    body = sample(name)
    start = body.find(b"\x30\x82")
    assert body[:start] == ber.build_pdu(ber.REPO_REQ_MSG, [], reqid=0)   # reqid는 마스킹되어 0


def test_integer_encoding_is_minimal_signed():
    assert ber.enc_int(0) == b"\x02\x01\x00"
    assert ber.enc_int(127) == b"\x02\x01\x7f"
    assert ber.enc_int(128) == b"\x02\x02\x00\x80"
    assert ber.enc_int(-1) == b"\x02\x01\xff"
    assert ber.enc_int(139600) == b"\x02\x03\x02\x21\x50"


def test_oid_roundtrip_with_multibyte_arc():
    arcs = (1, 1, 6, 1, 1, 5, 0, 139600, 501, 1, 1, 36000)
    enc = ber.enc_oid(arcs)
    assert ber.decode_oid(enc[2:]) == arcs


def test_rt_request_layout():
    pdu = ber.rt_request(139600, 501, 1, 1, 36000, 5000)
    assert pdu[:2] == b"\xa3\x00"
    vbs = ber.parse_varbinds(pdu)
    assert len(vbs) == 1
    oid, tag, val = vbs[0]
    assert ber.decode_oid(oid) == (1, 1, 6, 1, 1, 5, 0, 139600, 501, 1, 1, 36000) and tag == 2 and val == 5000
