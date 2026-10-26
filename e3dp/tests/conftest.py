"""공통 fixture. 접속 정보는 환경 변수(BOARD_PW 등)로 받는다.

device 마커 테스트는 DP_TARGET 에 따라 신 보드(new, 기본) 또는 기준 장치(ref)에서 실행한다.
DP는 module 범위로 기동하고 시뮬레이터와 함께 정리한다.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, HERE)

import dpapi  # noqa: E402,F401
from board import Board  # noqa: E402

TARGET = os.environ.get("DP_TARGET", "new")  # new: 신 보드, ref: 기준 장치(구 환경)

# ---- 증거(evidence): 테스트가 관측한 정규화된 값을 기록해 신·구 환경을 비교한다 ----
# 시각·보드 주소처럼 환경마다 달라지는 값은 테스트에서 마스킹해서 기록한다.
_EVIDENCE = {}


def pytest_collection_modifyitems(config, items):
    need = "REF_PW" if TARGET == "ref" else "BOARD_PW"
    for it in items:
        if "device" in it.keywords and need not in os.environ:
            it.add_marker(pytest.mark.skip(reason=need + " 미설정"))


@pytest.fixture
def evidence(request):
    store = _EVIDENCE.setdefault(request.node.nodeid, {})

    def add(key, value):
        store[key] = value
    return add


def pytest_sessionfinish(session, exitstatus):
    """증거를 out/evidence_<TARGET>.json 에 병합 저장한다(부분 실행이 다른 테스트의 증거를 지우지 않도록).
    처음부터 새로 만들려면 EVIDENCE_RESET=1."""
    if _EVIDENCE:
        import json
        out = os.path.join(HERE, "out")
        os.makedirs(out, exist_ok=True)
        path = os.environ.get("EVIDENCE_FILE", os.path.join(out, "evidence_%s.json" % TARGET))
        data = {}
        if os.path.exists(path) and not os.environ.get("EVIDENCE_RESET"):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        data.update(_EVIDENCE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)


@pytest.fixture(scope="session")
def board():
    b = Board.ref() if TARGET == "ref" else Board.new()
    yield b
    b.close()


@pytest.fixture(scope="session", autouse=True)
def ref_guard(request):
    """보드가 필요한 실행에서만 동작한다(환경 변수가 없으면 건너뜀: unit 테스트).
    - 시험 환경 정보를 증거(_env)에 기록
    - 기준 장치 대상이면 세션 시작에 설정을 백업하고, 세션 끝에 한 번만 원래 운영 상태로 복구한다.
      복구 후 프로세스 목록이 백업 시점과 다르면 테스트를 실패시킨다."""
    if ("REF_PW" if TARGET == "ref" else "BOARD_PW") not in os.environ:
        yield
        return
    board = request.getfixturevalue("board")
    _EVIDENCE["_env"] = {
        "os": board.sh("(. /etc/os-release; echo $PRETTY_NAME)").strip(),
        "kernel": board.sh("uname -srm").strip(),
        "gcc": board.sh("strings -a /opt/e3dp/bin/gw_server | grep -m1 'GCC:'").strip().lstrip("2*"),
        "python": board.sh("python3 --version").strip(),
        "version": board.sh("cat /opt/e3dp/bin/VERSION 2>/dev/null || echo '(VERSION 파일 없음)'").strip(),
    }
    if TARGET != "ref":
        yield
        return
    import time
    backup = os.path.join(HERE, "out", "ref_backup_" + time.strftime("%Y%m%d_%H%M%S"))
    board.ref_save(backup)
    print("[ref_guard] 백업: " + backup)
    try:
        yield
    finally:
        ok, now = board.ref_restore(backup)
        print("[ref_guard] 복구 후 프로세스 목록 일치: %s" % ok)
        assert ok, "기준 장치 복구 후 프로세스 목록이 백업 시점과 다름: " + now.replace(chr(10), " ")


@pytest.fixture(scope="module")
def dp(board):
    """시뮬레이터(GW, Host) + DP 기동 상태의 대상 장치. 모듈 종료 시 DP·시뮬레이터 종료."""
    board.env_up(HERE)
    yield board
    board.env_down()
