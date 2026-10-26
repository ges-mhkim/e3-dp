"""기준 장치에서 실험할 때의 안전 래퍼: 시작 시 백업, 끝에 반드시 복구하고 프로세스 목록 일치를 확인한다.

사용:
    with ref_session() as b:   # b: 시험 DP 기동 직전 상태의 Board.ref()
        ...
"""
import contextlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board import Board, SIM_IPS  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.contextmanager
def ref_session(start_dp=True):
    import dpapi
    b = Board.ref()
    backup = os.path.join(HERE, "out", "ref_backup_" + time.strftime("%Y%m%d_%H%M%S"))
    b.ref_save(backup)
    print("[ref_session] backup:", backup, flush=True)
    try:
        if start_dp:
            src = os.path.join(HERE, dpapi.FIXTURE)
            db = dpapi.make_db(open(src + "nelite.db", encoding="utf-8", errors="replace").read())
            conf = dpapi.make_conf(open(src + "nelite.conf", encoding="utf-8").read(), b.host)
            b.dp_stop()
            b.alias_add(SIM_IPS)
            b.prepare(db, conf)
            b.sim_start(os.path.join(HERE, "sim", "gwsim.py"))
            b.dp_start()
        yield b
    finally:
        b.alias_del(SIM_IPS)
        ok, now = b.ref_restore(backup)
        print("[ref_session] restore ok:", ok, flush=True)
        if not ok:
            print(now)
