"""신 보드와 기준 장치(구 환경)의 증거 파일을 비교해 표(markdown)로 출력한다.

사용: python compare_evidence.py [new.json] [ref.json]
기본: tests/out/evidence_new.json, evidence_ref.json
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def diff(a, b, path=""):
    """두 값의 차이 목록 (경로, 신, 구)"""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append((path + "/" + k, "<없음>", b[k]))
            elif k not in b:
                out.append((path + "/" + k, a[k], "<없음>"))
            else:
                out += diff(a[k], b[k], path + "/" + k)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff(x, y, "%s[%d]" % (path, i))
        return out
    return [] if a == b else [(path or "/", a, b)]


def compare(new, ref):
    rows = []
    for test in sorted(set(new) | set(ref)):
        n, r = new.get(test), ref.get(test)
        if n is None or r is None:
            rows.append((test, "-", "-", "한쪽만 실행 (%s)" % ("신 없음" if n is None else "구 없음")))
            continue
        for key in sorted(set(n) | set(r)):
            d = diff(n.get(key), r.get(key))
            rows.append((test, key, "일치" if not d else "차이 %d건" % len(d), "; ".join(
                "%s: 신=%s 구=%s" % (p, str(x)[:60], str(y)[:60]) for p, x, y in d[:3])))
    return rows


def main():
    new_p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "evidence_new.json")
    ref_p = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "out", "evidence_ref.json")
    rows = compare(load(new_p), load(ref_p))
    print("| 테스트 | 증거 | 신/구 | 차이 |")
    print("|---|---|---|---|")
    for t, k, st, d in rows:
        print("| %s | %s | %s | %s |" % (t.split("::", 1)[-1], k, st, d.replace("|", "/")))
    same = sum(1 for r in rows if r[2] == "일치")
    print("\n일치 %d / 전체 %d" % (same, len(rows)))
    return 0 if same == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
