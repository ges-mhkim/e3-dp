#!/usr/bin/env python3
"""빌드된 ELF 실행파일 기준 CycloneDX 1.5 SBOM 생성 (제출 통과본과 동일 구조).

사용법 (e3dp 폴더에서):
    python sbom_gen.py                    # sbom_out_bom/ 에 생성
    python sbom_gen.py --out DIR          # 출력 폴더 지정
    python sbom_gen.py --with-oss         # sbom-info.yaml 의 외부(비 Proprietary) 코드도 컴포넌트로 추가

설정: sbom_product.json (제품명/버전/제품코드/스캔 폴더)
참고: 실행파일은 git 에 없고 빌드 산출물이다. 먼저 빌드(make)해서 bin/ 등에 ELF 가 있어야 한다.
목록은 sbom_manifest.json 으로 검증한다(필수 누락 시 실패).
소스 헤더의 SPDX-License-Identifier 가 제품 라이선스와 다르면 실패한다(--no-license-check 로 생략).
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {".git", "__pycache__"}


def elf_kind(path):
    """ELF 실행파일(ET_EXEC/ET_DYN)이면 True. .o/.a/.so 및 비ELF 는 False."""
    if path.endswith((".o", ".a", ".so")) or ".so." in path:
        return False
    try:
        with open(path, "rb") as f:
            h = f.read(20)
    except OSError:
        return False
    if len(h) < 18 or h[:4] != b"\x7fELF":
        return False
    e_type = int.from_bytes(h[16:18], "little" if h[5] == 1 else "big")
    return e_type in (2, 3)


def sha256(path):
    d = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            d.update(chunk)
    return d.hexdigest()


def find_elfs(root, scan_dirs):
    found = []
    for sd in scan_dirs:
        base = os.path.join(root, sd)
        if not os.path.isdir(base):
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                p = os.path.join(dp, fn)
                if os.path.isfile(p) and not os.path.islink(p) and elf_kind(p):
                    found.append(p)
    return sorted(found)


SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.\-+]+)")


def load_declared(root):
    """sbom-info.yaml 에 (라이선스 값과 무관하게) 선언된 파일 경로 집합 = 검토된 파일."""
    path = os.path.join(root, "sbom-info.yaml")
    if not os.path.isfile(path):
        return set(), "sbom-info.yaml 없음"
    try:
        import yaml
    except ImportError:
        return set(), "yaml 모듈 없음(venv 활성화 필요)"
    doc = yaml.safe_load(open(path, encoding="utf-8")) or {}
    out = set()
    for items in doc.values():
        for it in items or []:
            sp = it.get("source path")
            out.update(sp if isinstance(sp, list) else ([sp] if sp else []))
    return out, None


def check_licenses(root, manifest, cfg):
    """모듈 소스 헤더의 SPDX 라이선스를 제품 라이선스와 대조. (mismatch, undeclared) 반환."""
    expected = cfg.get("spdx_license", "LicenseRef-Proprietary")
    dirs = sorted({r["module"] for r in manifest.get("required", []) if r.get("module")}) + ["lib", "include"]
    declared, note = load_declared(root)
    mismatch, undeclared = [], []
    print(f"[라이선스 검증] 기대값 SPDX={expected}" + (f" ({note})" if note else ""))
    for d in dirs:
        tot = ok = dec = 0
        base = os.path.join(root, d)
        for dp, dns, fns in os.walk(base):
            dns[:] = [x for x in dns if x not in SKIP_DIRS]
            for fn in sorted(fns):
                if not fn.endswith((".c", ".h")):
                    continue
                rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
                with open(os.path.join(dp, fn), "rb") as f:
                    head = "\n".join(f.read().decode("utf-8", "replace").splitlines()[:40])
                m = SPDX_RE.search(head)
                tot += 1
                if m and m.group(1) == expected:
                    ok += 1
                elif m:
                    mismatch.append((rel, m.group(1)))
                elif rel in declared:
                    dec += 1
                else:
                    undeclared.append(rel)
        print(f"  {d}: {tot}개 | SPDX 일치 {ok} | yaml 선언 {dec} | 기타 {tot - ok - dec}")
    for rel, v in mismatch:
        print(f"[오류] 라이선스 불일치: {rel} -> {v} (기대 {expected})", file=sys.stderr)
    for rel in undeclared:
        print(f"[경고] 라이선스 선언 없음: {rel}", file=sys.stderr)
    return mismatch, undeclared


def check_stale(root, manifest):
    """필수 바이너리가 해당 모듈 소스(.c/.h)보다 오래됐으면 경고 (빌드 누락/구 바이너리 탐지)."""
    stale = []
    for r in manifest.get("required", []):
        mod = r.get("module")
        bp = os.path.join(root, r["path"])
        if not mod or not os.path.isfile(bp):
            continue
        newest = 0.0
        for dp, dns, fns in os.walk(os.path.join(root, mod)):
            dns[:] = [x for x in dns if x not in SKIP_DIRS]
            for fn in fns:
                if fn.endswith((".c", ".h")):
                    newest = max(newest, os.path.getmtime(os.path.join(dp, fn)))
        if os.path.getmtime(bp) < newest:
            bt = datetime.datetime.fromtimestamp(os.path.getmtime(bp)).strftime("%F")
            st = datetime.datetime.fromtimestamp(newest).strftime("%F")
            stale.append(r["path"])
            print(f"[경고] 바이너리가 소스보다 오래됨: {r['path']} ({bt}) < {mod} 소스 ({st}) - 다시 빌드했는지 확인",
                  file=sys.stderr)
    return stale


def apply_manifest(found_rel, manifest):
    """found_rel: 발견된 ELF 상대경로 목록 -> (포함할 목록, 누락된 필수, 목록에 없는 ELF)"""
    required = [r["path"] for r in manifest.get("required", [])]
    optional = manifest.get("optional", [])
    missing = [r for r in required if r not in found_rel]
    keep, unlisted = [], []
    for rel in found_rel:
        if rel in required or any(fnmatch.fnmatch(rel, pat) for pat in optional):
            keep.append(rel)
        else:
            unlisted.append(rel)
    return keep, missing, unlisted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "sbom_product.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "sbom_out_bom"))
    ap.add_argument("--manifest", default=os.path.join(HERE, "sbom_manifest.json"))
    ap.add_argument("--no-manifest", action="store_true", help="목록 검증 없이 발견된 ELF 전부 포함")
    ap.add_argument("--allow-missing", action="store_true", help="필수 실행파일이 없어도 계속 진행")
    ap.add_argument("--no-license-check", action="store_true", help="소스 헤더 라이선스 검증 생략")
    ap.add_argument("--allow-license-mismatch", action="store_true", help="SPDX 불일치가 있어도 계속 진행")
    ap.add_argument("--with-oss", action="store_true")
    a = ap.parse_args()

    cfg = json.load(open(a.config, encoding="utf-8"))
    root = os.path.join(HERE, cfg["source_root"])
    ver, name = cfg["version"], cfg["device_name"]
    slug = name.lower()
    lic = [{"license": {"name": cfg["license"]}}]
    sup = {"name": cfg["company"]}

    # 1) ELF 수집, SHA-256 기준으로 같은 바이너리 경로를 묶는다
    found = [os.path.relpath(p, root).replace(os.sep, "/") for p in find_elfs(root, cfg["scan_dirs"])]
    if not a.no_manifest:
        manifest = json.load(open(a.manifest, encoding="utf-8"))
        found, missing, unlisted = apply_manifest(found, manifest)
        for u in unlisted:
            print(f"[경고] manifest 에 없는 ELF 제외: {u}", file=sys.stderr)
        for m in missing:
            print(f"[오류] 필수 실행파일 없음(빌드 확인): {m}", file=sys.stderr)
        if missing and not a.allow_missing:
            sys.exit(2)
        check_stale(root, manifest)
        if not a.no_license_check:
            mismatch, undeclared = check_licenses(root, manifest, cfg)
            if mismatch and not a.allow_license_mismatch:
                sys.exit(3)
    by_hash = {}
    for rel in found:
        by_hash.setdefault(sha256(os.path.join(root, rel)), []).append(rel)
    if not by_hash:
        sys.exit("ELF 실행파일이 없다. 먼저 빌드하고 scan_dirs 를 확인할 것.")

    # 2) 이름 결정: 같은 이름에 해시가 다르면 뒤의 것에 -<해시8> 을 붙인다
    entries, used = [], set()
    for h, paths in sorted(by_hash.items(), key=lambda kv: (os.path.basename(kv[1][0]), kv[1][0])):
        base = os.path.splitext(os.path.basename(paths[0]))[0] if paths[0].endswith(".cgi") else os.path.basename(paths[0])
        nm = base if base not in used else f"{base}-{h[:8]}"
        used.add(nm)
        entries.append((nm, h, sorted(paths)))
    entries.sort(key=lambda e: e[0].lower())

    comps = []
    for nm, h, paths in entries:
        ref = f"pkg:generic/{slug}-{nm.split('-' + h[:8])[0]}-{h[:8]}@{ver}"
        comps.append({
            "bom-ref": ref,
            "hashes": [{"alg": "SHA-256", "content": h}],
            "licenses": lic,
            "name": nm,
            "properties": [
                {"name": "ges:binary:paths", "value": json.dumps(paths, ensure_ascii=False)},
                {"name": "ges:component:from", "value": "SRC"},
                {"name": "ges:elf:type", "value": "EXEC"},
                {"name": "ges:license-basis", "value": "product_info.license"},
                {"name": "ges:version-basis", "value": f"Firmware release {ver}"},
            ],
            "purl": ref,
            "scope": "required",
            "supplier": sup,
            "type": "application",
            "version": ver,
        })

    # 3) (선택) 외부 코드: sbom-info.yaml 에서 Proprietary 가 아닌 항목
    if a.with_oss:
        import yaml
        doc = yaml.safe_load(open(os.path.join(root, "sbom-info.yaml"), encoding="utf-8"))
        for oname, items in doc.items():
            for it in items:
                if str(it.get("license", "")).strip() in ("", "Proprietary"):
                    continue
                v = str(it.get("version", "") or "")
                ref = f"pkg:generic/{oname.lower().replace(' ', '-')}" + (f"@{v}" if v else "")
                c = {"bom-ref": ref, "name": oname, "type": "library", "purl": ref,
                     "licenses": [{"license": {"name": str(it["license"])}}],
                     "properties": [{"name": "ges:component:from", "value": "OSS"}]}
                if v:
                    c["version"] = v
                if it.get("copyright"):
                    c["copyright"] = it["copyright"]
                comps.append(c)

    root_ref = f"pkg:generic/{slug}@{ver}"
    now = datetime.datetime.now(datetime.timezone.utc)
    bom = {
        "metadata": {
            "component": {
                "bom-ref": root_ref, "group": "", "licenses": lic, "name": name,
                "properties": [
                    {"name": "arch", "value": cfg["arch"]},
                    {"name": "ges:k9-code", "value": cfg["product_code"]},
                    {"name": "ges:source-root", "value": os.path.relpath(root, HERE)},
                    {"name": "ges:target", "value": "product_source"},
                ],
                "purl": root_ref, "supplier": sup, "type": cfg["component_type"], "version": ver,
            },
            "supplier": sup,
            "timestamp": now.isoformat(),
            "tools": {"components": [{"name": "sbom_gen.py", "type": "application", "version": "1.0"}]},
        },
        "components": comps,
        "dependencies": [{"ref": c["bom-ref"]} for c in comps]
                        + [{"ref": root_ref, "dependsOn": [c["bom-ref"] for c in comps]}],
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
    }

    os.makedirs(a.out, exist_ok=True)
    fn = os.path.join(a.out, f"GES_{name}_sbom_{now.astimezone().strftime('%Y%m%d_%H%M%S')}.cdx.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(bom, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"컴포넌트 {len(comps)}개 (ELF {len(entries)}개) -> {fn}")


if __name__ == "__main__":
    main()
