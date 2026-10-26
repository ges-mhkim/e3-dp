"""gcov 커버리지 측정 도구(신 보드 전용).

순서:
  python tools/coverage.py build      # /tmp/cov 에 소스를 복사해 --coverage 로 전체 빌드 (약 3분)
  python tools/coverage.py install    # /opt/e3dp/bin 을 /tmp/orig_bin 에 백업하고 계측 바이너리로 교체
  COVERAGE=1 BOARD_PW=... python -m pytest protocol ...   # 테스트 실행(종료 시 SIGTERM, LD_PRELOAD 적용)
  python tools/coverage.py collect    # gcov 집계 -> out/coverage.json, out/coverage.md
  python tools/coverage.py restore    # 원래 바이너리 복원

설계:
  - 평소 빌드와 섞이지 않도록 /tmp/cov(소스 복사본), /tmp/cov_bin(산출물)을 쓴다. 원본 트리는 건드리지 않는다.
  - 서버가 kill -9 로 끝나면 .gcda 가 기록되지 않으므로 tools/c/gcovflush.c 를 LD_PRELOAD 해 SIGTERM 에서 exit(0) 하게 한다.
  - 집계 대상은 src/ 와 lib/ 의 .c. 진단 도구(emon, comp 등 src/util, src/emon)는 따로 표시한다.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.path.insert(0, HERE)
from board import Board  # noqa: E402

OUT = os.path.join(HERE, "out")

# 보드에서 실행하는 집계 스크립트(Python 3.13). 표준 출력으로 JSON을 낸다.
SUMMARY_PY = r'''
import glob, gzip, json, os, subprocess, sys, tempfile
root = "/tmp/cov"
work = tempfile.mkdtemp(prefix="covjson")
for g in glob.glob(root + "/**/*.gcda", recursive=True):
    subprocess.run(["gcov", "-j", "-b", "-o", os.path.dirname(g), g], cwd=work,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
files = {}
for jf in glob.glob(work + "/*.gcov.json.gz"):
    d = json.load(gzip.open(jf))
    for f in d.get("files", []):
        path = f["file"]
        if not path.endswith(".c"):
            continue
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(d.get("current_working_directory", ""), path))
        e = files.setdefault(path, {"lines": {}, "funcs": {}})
        for ln in f.get("lines", []):
            n = ln["line_number"]
            e["lines"][n] = e["lines"].get(n, 0) + ln["count"]
        for fn in f.get("functions", []):
            e["funcs"][fn["name"]] = e["funcs"].get(fn["name"], 0) + fn["execution_count"]
out = {}
for path, e in files.items():
    out[path] = {"total": len(e["lines"]), "hit": sum(1 for c in e["lines"].values() if c > 0),
                 "funcs": e["funcs"],
                 "missed_lines": sorted(n for n, c in e["lines"].items() if c == 0)}
print(json.dumps(out))
'''


def build(b):
    # 소스 복사 후 platform.tools 수정
    b.sh("rm -rf /tmp/cov /tmp/cov_bin; mkdir -p /tmp/cov_bin; cp -a ~/e3dp.2.1 /tmp/cov", timeout=300)
    b.sh("cd /tmp/cov && find . -name '*.o' -delete; find . -name '*.a' -delete; find . -name '*.gc*' -delete", timeout=120)
    pt = b.get_text("/tmp/cov/make/platform.tools")
    pt = pt.replace("/home/e3dp/e3dp.2.1", "/tmp/cov").replace("/opt/e3dp/bin", "/tmp/cov_bin")
    pt += "\nCFLAGS += --coverage -O0\nLDLIBS += --coverage\n"
    b.put_text(pt, "/tmp/cov/make/platform.tools")
    b.put(os.path.join(HERE, "tools", "c", "gcovflush.c"), "/tmp/gcovflush.c")
    b.sh("gcc -shared -fPIC -o /tmp/gcovflush.so /tmp/gcovflush.c")
    rc, out, err = b.run("cd /tmp/cov && make clean all > /tmp/cov_build.log 2>&1; echo EXIT=$?; "
                         "grep -c 'error:' /tmp/cov_build.log; ls /tmp/cov_bin | wc -l", timeout=900)
    print(out)


def install(b):
    b.root("rm -rf /tmp/orig_bin; cp -a /opt/e3dp/bin /tmp/orig_bin; cp -f /tmp/cov_bin/* /opt/e3dp/bin/; "
           "find /tmp/cov -name '*.gcda' -delete; chmod 666 /tmp/gcovflush.so; true")
    print(b.sh("ls /opt/e3dp/bin | wc -l; strings -a /opt/e3dp/bin/gw_server | grep -c gcov"))


def collect(b):
    b.put_text(SUMMARY_PY, "/tmp/covsum.py")
    rc, out, err = b.run("python3 /tmp/covsum.py", timeout=600)
    if rc != 0:
        raise RuntimeError(err)
    data = json.loads(out.strip().splitlines()[-1])
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "coverage.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    write_md(data)
    return data


def module_of(path):
    p = path.replace("\\", "/")
    for key in ("/src/", "/lib/"):
        if key in p:
            rest = p.split(key, 1)[1]
            return key.strip("/") + "/" + rest.split("/")[0]
    return "기타"


def write_md(data):
    mods = {}
    for path, e in data.items():
        m = mods.setdefault(module_of(path), {"total": 0, "hit": 0, "files": []})
        m["total"] += e["total"]
        m["hit"] += e["hit"]
        m["files"].append((path, e))
    lines = ["# 코드 커버리지 (gcov, 신 보드)", "",
             "측정 방법: `--coverage -O0` 계측 빌드 + 전체 protocol 테스트 실행. 줄 단위(실행 가능한 줄 기준).", "",
             "## 모듈별", "", "| 모듈 | 실행 줄 | 전체 줄 | 비율 |", "|---|---|---|---|"]
    tt = th = 0
    for name, m in sorted(mods.items()):
        pct = 100.0 * m["hit"] / m["total"] if m["total"] else 0
        lines.append("| %s | %d | %d | %.1f%% |" % (name, m["hit"], m["total"], pct))
        if not name.startswith(("src/util", "src/emon")):
            tt += m["total"]
            th += m["hit"]
    lines += ["", "진단 도구(src/util, src/emon)를 제외한 합계: %d / %d (%.1f%%)" % (th, tt, 100.0 * th / tt if tt else 0), "",
              "## 파일별", "", "| 파일 | 실행 | 전체 | 비율 | 실행되지 않은 함수 |", "|---|---|---|---|---|"]
    for name, m in sorted(mods.items()):
        for path, e in sorted(m["files"]):
            pct = 100.0 * e["hit"] / e["total"] if e["total"] else 0
            missed = [fn for fn, c in sorted(e["funcs"].items()) if c == 0]
            lines.append("| %s | %d | %d | %.1f%% | %s |" % (
                path.replace("/tmp/cov/", ""), e["hit"], e["total"], pct,
                ", ".join(missed[:8]) + (" 외 %d" % (len(missed) - 8) if len(missed) > 8 else "")))
    with open(os.path.join(OUT, "coverage.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:30]))


def restore(b):
    b.root("if [ -d /tmp/orig_bin ]; then cp -f /tmp/orig_bin/* /opt/e3dp/bin/; fi; true")
    print("restored")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    board = Board.new()
    {"build": build, "install": install, "collect": collect, "restore": restore}[cmd](board)
