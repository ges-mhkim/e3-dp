"""시험 환경을 pytest 없이 올리고 내리는 개발용 도구.

사용: BOARD_PW=<비번> python tools/devenv.py up|down|status
(기준 장치는 refsession.ref_session()을 사용한다. 이 도구는 신 보드 전용)
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from board import Board  # noqa: E402

b = Board.new()
cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
if cmd == "up":
    b.env_up(HERE)
    print(b.procs())
elif cmd == "down":
    b.env_down()
    print("down")
else:
    print(b.procs())
