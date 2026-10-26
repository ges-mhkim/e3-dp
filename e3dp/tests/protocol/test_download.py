"""Host 설정 다운로드(db_server): START -> SHELF -> MODULE -> EQUIP -> LPORT -> POINT -> END.
명세: sim/dbdl.py 상단 주석, 출처 e3dp.2.1/src/db/ldb_decode.c, ldb_download.c
  - 메시지마다 DP가 요청 caddr로 TCP 연결해 1024바이트 응답을 보낸다
  - END 처리 후 DP가 DB를 /opt/e3dp/conf/nelite.db 에 저장하고 서버들이 새 설정으로 동작한다
  - shelf IP는 정수(inet_ntoa에 넣는 호스트 순서)로 전달된다
"""
import os
import re
import time

import pytest

import dpapi
from sim import dbdl

pytestmark = pytest.mark.device

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = dpapi.make_db(open(os.path.join(HERE, dpapi.FIXTURE, "nelite.db"), encoding="utf-8", errors="replace").read())
GW1 = "10.99.0.11"


def stored(dp):
    return dp.get_text("/opt/e3dp/conf/nelite.db")


def wait_stored_equals(dp, text, timeout=90):
    return dpapi.wait_for(lambda: sum(dpapi.db_row_diffs(text, stored(dp)).values()) == 0, timeout=timeout, step=2.0)


@pytest.fixture(scope="module", autouse=True)
def restore_base(dp):
    yield
    dpapi.download(dp, BASE)


def test_download_replays_whole_db_and_dp_stores_identical_rows(dp, evidence):
    sizes = dpapi.download(dp, BASE)
    n_msgs = len(dbdl.messages(dbdl.parse_db(BASE)))
    assert len(sizes) == n_msgs
    assert all(s == [1024] for s in sizes), sizes            # 메시지마다 1024바이트 응답 1건
    assert wait_stored_equals(dp, BASE), dpapi.db_row_diffs(BASE, stored(dp))
    evidence("download_message_count", n_msgs)
    evidence("download_response_sizes", sorted({s[0] for s in sizes}))
    evidence("download_row_diffs", dpapi.db_row_diffs(BASE, stored(dp)))


def test_downloaded_limit_change_takes_effect(dp, evidence):
    changed = re.sub(r"(\n\s*501\s+ACON\s+1\s+1\s+1\s+)36\.000(\s+5\.000)", r"\g<1>33.000\g<2>", BASE, count=1)
    assert changed != BASE
    dpapi.download(dp, changed)
    got = dpapi.wait_for(lambda: (lambda p: p and p["high"] == 33.0 and p)(dpapi.lport(dp, "ACON", 1, 1)), timeout=90)
    assert got, dpapi.lport(dp, "ACON", 1, 1)
    evidence("download_changed_limit", [got["high"], got["low"]])
    assert wait_stored_equals(dp, changed)


def test_dp_polls_gw_again_after_download(dp, evidence):
    dpapi.download(dp, BASE)
    assert dpapi.wait_for(lambda: dpapi.shelves(dp).get((1, 0)) == 0, timeout=90, step=2.0), "상위 GW 상태가 정상으로 돌아오지 않음"
    dp.sim({"op": "set_ai", "ip": GW1, "port": 1, "ch": 1, "value": 21.5})
    got = dpapi.wait_for(lambda: (lambda p: p and abs(p["val"] - 21.5) < 0.01 and p)(dpapi.lport(dp, "ACON", 1, 1)), timeout=90, step=2.0)
    assert got, "다운로드 후 GW 값이 반영되지 않음: %s" % dpapi.lport(dp, "ACON", 1, 1)
    evidence("download_polling_resumes", True)
