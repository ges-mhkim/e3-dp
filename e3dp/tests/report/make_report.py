"""테스트 결과 리포트 생성: JUnit XML(신/구) + 증거(JSON) 비교 -> tests/report/<년월일시분초>.md

사용: python report/make_report.py
입력: tests/out/junit_new.xml, junit_ref.xml (pytest --junitxml), evidence_new.json, evidence_ref.json
출력: tests/report/<년월일시분초>.md (실행마다 새 파일)
구분(하위 장치/서버)과 프로토콜은 아래 MODULES 표로 매핑한다. 새 테스트 모듈을 추가하면 이 표에 추가한다.
"""
import datetime
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
from compare_evidence import diff  # noqa: E402

OUT = os.path.join(HERE, "out")

# 모듈 -> (구분, 프로토콜)
MODULES = {
    "test_gw_poll": ("하위 장치", "GW Modbus TCP 1502 (폴링)"),
    "test_gw_errors": ("하위 장치", "GW Modbus TCP 1502 (이상 응답)"),
    "test_gw_di": ("하위 장치", "GW Modbus TCP 1502 (DI 접점)"),
    "test_acon_agent": ("하위 장치", "ACON Modbus TCP 서버 9785"),
    "test_rect": ("하위 장치", "정류기 Modbus ASCII TCP 2000"),
    "test_control": ("서버(Host)", "제어 요청 UDP 7999 + TCP 응답 (→GW 쓰기)"),
    "test_config_limit": ("서버(Host)", "설정 요청 UDP 7999 (한계치·마스크)"),
    "test_main_dispatch": ("서버(Host)", "진입점 UDP 7999 (기동·라우팅·이상 입력)"),
    "test_alarm": ("서버(Host)", "경보 UDP 7704 (DP→Host)"),
    "test_rt_push": ("서버(Host)", "실시간 구독 UDP 7999 → 푸시 TCP (DP→Host)"),
    "test_gather": ("서버(Host)", "정시 수집 UDP 7062 (DP→Host)"),
    "test_download": ("서버(Host)", "설정 다운로드 UDP 7999 → db_server (TCP 응답)"),
    "test_realdata": ("서버(Host)", "원시값 조회 TCP 7995 (Host→DP)"),
}

# 모듈 -> tests/inventory.md 의 ID
INVENTORY = {
    "test_gw_poll": "GW-01, GW-02, GW-07",
    "test_gw_errors": "GW-03~06",
    "test_gw_di": "GW-10",
    "test_acon_agent": "ACON-01",
    "test_rect": "RECT-01~03",
    "test_control": "HOST-05, GW-08",
    "test_config_limit": "HOST-01, HOST-02",
    "test_main_dispatch": "HOST-04, HOST-07, HOST-10, TS-01",
    "test_alarm": "ALM-01~03",
    "test_rt_push": "RT-01~03",
    "test_gather": "GAT-01",
    "test_download": "HOST-08",
    "test_realdata": "RD-01~03",
}

# 이 테스트 체계로 검증하지 못하는 영역(리포트에 항상 표시)
UNVERIFIED = [
    ("하드웨어", "GPIO·LED(wan_led, libfahw), 시리얼, 이더넷 드라이버(ASIX USB), RTC. 보드가 달라서 시뮬레이터로 대체 불가"),
    ("현장 장비의 실제 응답", "정상 GW 응답·정류기 응답·Host 요청은 소스 해석으로 만든 시뮬레이터 입력. 실제 장비 예외 동작은 미검증"),
    ("타이밍", "폴링 주기, 응답 대기, 시각 동기(6시간 주기), RT 푸시 10ms. CPU·커널이 달라 수치는 보장하지 않음"),
    ("장시간 동작", "메모리 누수, 파일 증가(alarm.db, periodic), 며칠 단위 동작, smm 재부팅 경로"),
    ("부팅·운영 기동", "init 스크립트, smm 기동·감시, 전원 투입 순서. 테스트는 서버를 직접 기동"),
    ("Host 설정 요청(UDP 7999)", "설정 다운로드·한계치·제어 요청의 PDU 처리. 미구현(task 004 후속)"),
    ("정류기 통신(TCP 2000)", "rect_server 시뮬레이터 미구현(task 006)"),
]


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_junit(path):
    """-> {(module, name): ('PASS'|'FAIL'|'SKIP', 메시지)}"""
    res = {}
    if not os.path.exists(path):
        return res
    for tc in ET.parse(path).getroot().iter("testcase"):
        mod = tc.get("classname", "").split(".")[-1]
        name = tc.get("name")
        st, msg = "PASS", ""
        for child in tc:
            if child.tag in ("failure", "error"):
                st, msg = "FAIL", (child.get("message") or "")[:120]
            elif child.tag == "skipped":
                st, msg = "SKIP", (child.get("message") or "")[:120]
        res[(mod, name)] = (st, msg)
    return res


def main():
    new, ref = load_junit(os.path.join(OUT, "junit_new.xml")), load_junit(os.path.join(OUT, "junit_ref.xml"))
    ev_new, ev_ref = load_json(os.path.join(OUT, "evidence_new.json")), load_json(os.path.join(OUT, "evidence_ref.json"))
    env_new, env_ref = ev_new.get("_env", {}), ev_ref.get("_env", {})

    keys = sorted(set(new) | set(ref), key=lambda k: (list(MODULES).index(k[0]) if k[0] in MODULES else 99, k[1]))
    lines = []
    w = lines.append
    w("# E3-DP 통신 테스트 리포트")
    w("")
    w("생성: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    w("")
    w("## 시험 환경")
    w("")
    w("| 구분 | 신 환경 | 구 환경(기준) |")
    w("|---|---|---|")
    for k, label in (("os", "OS"), ("kernel", "커널"), ("gcc", "빌드 컴파일러"), ("python", "Python"), ("version", "DP 버전")):
        w("| %s | %s | %s |" % (label, env_new.get(k, "-"), env_ref.get(k, "-")))
    w("")

    # ---- 요약 ----
    summ = {}
    for (mod, name) in keys:
        cat = MODULES.get(mod, ("기타", mod))
        row = summ.setdefault(cat, {"new": [0, 0, 0], "ref": [0, 0, 0]})
        for tag, src in (("new", new), ("ref", ref)):
            st = src.get((mod, name), ("-", ""))[0]
            if st in ("PASS", "FAIL", "SKIP"):
                row[tag][("PASS", "FAIL", "SKIP").index(st)] += 1
    w("## 요약 (통과 / 실패 / 건너뜀)")
    w("")
    w("| 구분 | 프로토콜 | 신 환경 | 구 환경 |")
    w("|---|---|---|---|")
    tot = {"new": [0, 0, 0], "ref": [0, 0, 0]}
    for (cat, proto), row in sorted(summ.items()):
        w("| %s | %s | %d / %d / %d | %d / %d / %d |" % ((cat, proto) + tuple(row["new"]) + tuple(row["ref"])))
        for t in tot:
            tot[t] = [a + b for a, b in zip(tot[t], row[t])]
    w("| **합계** | | %d / %d / %d | %d / %d / %d |" % (tuple(tot["new"]) + tuple(tot["ref"])))
    w("")

    # ---- 증거 비교 ----
    w("## 신·구 증거 비교")
    w("")
    w("테스트가 관측한 정규화 값(패킷 바이트, 인코딩 결과 등)을 신/구 환경에서 비교한 결과.")
    w("")
    w("| 구분 | 테스트 | 증거 | 결과 | 차이 |")
    w("|---|---|---|---|---|")
    same = total = 0
    for test in sorted(set(ev_new) | set(ev_ref)):
        if test.startswith("_"):
            continue
        n, r = ev_new.get(test, {}), ev_ref.get(test, {})
        mod = test.split("::")[0].split("/")[-1].replace(".py", "")
        cat = MODULES.get(mod, ("기타", ""))[0]
        for key in sorted(set(n) | set(r)):
            total += 1
            if key not in n or key not in r:
                w("| %s | %s | %s | 한쪽만 기록 | |" % (cat, test.split("::")[-1], key))
                continue
            d = diff(n[key], r[key])
            if not d:
                same += 1
            w("| %s | %s | %s | %s | %s |" % (
                cat, test.split("::")[-1], key, "일치" if not d else "**차이 %d건**" % len(d),
                "; ".join("%s: 신=%s 구=%s" % (p, str(x)[:50], str(y)[:50]) for p, x, y in d[:3]).replace("|", "/")))
    w("")
    w("증거 일치 %d / %d" % (same, total))
    w("")

    # ---- 테스트별 결과 ----
    w("## 테스트별 결과")
    w("")
    w("| ID | 구분 | 프로토콜 | 인벤토리 | 시나리오 | 신 | 구 | 비고 |")
    w("|---|---|---|---|---|---|---|---|")
    for i, (mod, name) in enumerate(keys, 1):
        cat, proto = MODULES.get(mod, ("기타", mod))
        sn, mn = new.get((mod, name), ("-", ""))
        sr, mr = ref.get((mod, name), ("-", ""))
        note = (mn or mr).replace("|", "/")
        w("| T%03d | %s | %s | %s | %s | %s | %s | %s |" % (i, cat, proto, INVENTORY.get(mod, "-"), name, sn, sr, note))
    w("")

    # ---- 커버리지 ----
    cov_path = os.path.join(OUT, "coverage.json")
    if os.path.exists(cov_path):
        with open(cov_path, encoding="utf-8") as f:
            cov = json.load(f)
        mods = {}
        for path, e in cov.items():
            p = path.replace("\\", "/")
            key = None
            for k in ("/src/", "/lib/"):
                if k in p:
                    key = k.strip("/") + "/" + p.split(k, 1)[1].split("/")[0]
            m = mods.setdefault(key or "기타", [0, 0])
            m[0] += e["hit"]
            m[1] += e["total"]
        w("## 코드 커버리지 (신 보드, gcov 줄 단위)")
        w("")
        w("전체 protocol 테스트를 계측 빌드로 실행한 결과. 실행되지 않은 영역은 이 체계로 검증되지 않은 코드.")
        w("")
        w("| 모듈 | 실행 줄 | 전체 줄 | 비율 |")
        w("|---|---|---|---|")
        th = tt = 0
        for k, (h, t) in sorted(mods.items()):
            w("| %s | %d | %d | %.1f%% |" % (k, h, t, 100.0 * h / t if t else 0))
            if not k.startswith(("src/util", "src/emon")):
                th += h
                tt += t
        w("| **진단 도구 제외 합계** | %d | %d | %.1f%% |" % (th, tt, 100.0 * th / tt if tt else 0))
        w("")
        w("파일·함수 단위는 `tests/out/coverage.md` 참조.")
        w("")

    # ---- 미검증 ----
    w("## 미검증 영역")
    w("")
    w("| 영역 | 내용 |")
    w("|---|---|")
    for a, b in UNVERIFIED:
        w("| %s | %s |" % (a, b))
    w("")
    import time
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), time.strftime("%Y%m%d%H%M%S") + ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("report:", path)


if __name__ == "__main__":
    main()
