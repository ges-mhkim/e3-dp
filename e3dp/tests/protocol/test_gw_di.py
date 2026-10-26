"""GW 응답의 DI(접점) 값이 LPORT 비트로 반영되고 디지털 경보로 이어지는 경로.
명세 출처: e3dp.2.1/src/gw/gw_server.c (update_di_value, set_di_lport), include/nelite.h (DI_REVERSE=17)
  - 응답의 DI 40 × uint16 중 채널 c 의 값 0/비0 -> 포인트 테이블(shelf=GW, board=port, channel=c)의 LPORT 비트(bitno-1)를 해제/설정
  - 접점이 DI_REVERSE(17)이면 반전. 이 DB의 DI 포인트는 모두 18(정상)
  - ACON 1.23: 채널 17 -> 비트 1, 채널 18 -> 비트 2 (같은 LPORT)
"""
import pytest

import dpapi

pytestmark = pytest.mark.device

GW1 = "10.99.0.11"
LPORT = ("ACON", 1, 23)
CH_BIT1, CH_BIT2 = 17, 18


def set_di(dp, ch, v):
    dp.sim({"op": "set_di", "ip": GW1, "port": 1, "ch": ch, "value": v})


def value(dp):
    return dpapi.lport(dp, *LPORT)["val"]


def wait_value(dp, v, timeout=30):
    return dpapi.wait_for(lambda: value(dp) == v, timeout=timeout)


@pytest.fixture
def clean(dp):
    set_di(dp, CH_BIT1, 0)
    set_di(dp, CH_BIT2, 0)
    assert wait_value(dp, 0), "초기화 실패"
    yield
    set_di(dp, CH_BIT1, 0)
    set_di(dp, CH_BIT2, 0)
    wait_value(dp, 0)


def test_di_bits_follow_channels(dp, clean, evidence):
    seq = []
    for ch, v, expect in ((CH_BIT1, 1, 1), (CH_BIT2, 1, 3), (CH_BIT1, 0, 2), (CH_BIT2, 0, 0)):
        set_di(dp, ch, v)
        assert wait_value(dp, expect), "ch%d=%d 후 값 %s, 기대 %d" % (ch, v, value(dp), expect)
        seq.append(value(dp))
    evidence("di_sequence", seq)


def test_nonzero_value_counts_as_set(dp, clean):
    set_di(dp, CH_BIT1, 0x1234)
    assert wait_value(dp, 1)


def test_digital_alarm_is_sent_to_host(dp, clean, evidence):
    dpapi.drain_alarms(dp)
    dp.sim({"op": "clear_log"}, dpapi.HOSTSIM_CTL)
    set_di(dp, CH_BIT1, 1)
    a = dpapi.wait_for(lambda: next((x for x in dpapi.host_alarms(dp) if x[2].get("equip") == "ACON"
                                     and x[2].get("compno") == 1 and x[2].get("portno") == 23), None),
                       timeout=45, step=1.0)
    assert a, "디지털 경보가 Host에 도착하지 않음"
    f = a[2]
    evidence("di_alarm_fields", {k: f[k] for k in ("value", "status", "type", "high", "low")})
    assert f["type"] == 0 and f["value"] == 1
