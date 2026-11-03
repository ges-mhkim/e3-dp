#!/usr/bin/env bash
# FOSSLight 소스 스캔 -> CycloneDX json
#
# 사용법:
#   ./sbom_src.sh          # e3dp.2.1/src 만 스캔 (루트 sbom-info.yaml 중 src/ 항목만 임시 적용)
#   ./sbom_src.sh full     # e3dp.2.1 전체 스캔 (e3dp.2.1/sbom-info.yaml 전체 적용)
#
# 환경변수:
#   OUT=<dir>   결과 출력 폴더 (기본: 모드에 따라 sbom_out_src / sbom_out_full)
#
# 메모:
#  - sbom-info.yaml 은 스캔 폴더(-p) 최상위에서만 읽히고, 경로 존재 확인은 '현재 디렉터리' 기준이다.
#  - 그래서 src 모드는 루트 yaml 에서 src/ 항목만 뽑아 src/sbom-info.yaml 을 임시로 만들고,
#    스캔 후 삭제한다 (yaml 원본은 e3dp.2.1/sbom-info.yaml 하나만 관리).

set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV=/mnt/c/ges/venvs/sbom-wsl
MODE="${1:-src}"

# shellcheck disable=SC1091
source "$VENV/bin/activate"

case "$MODE" in
  src)
    OUT="${OUT:-$HERE/sbom_out_src}"
    mkdir -p "$OUT"
    SRC="$HERE/e3dp.2.1/src"
    python - "$HERE/e3dp.2.1/sbom-info.yaml" "$TMPYAML" <<'PY'
import sys, yaml
src, dst = sys.argv[1:3]
doc = yaml.safe_load(open(src, encoding="utf-8"))
out = {}
for name, items in doc.items():
    kept = []
    for it in items:
        sp = it.get("source path")
        paths = sp if isinstance(sp, list) else ([sp] if sp else [])
        paths = [p[4:] for p in paths if p.startswith("src/")]
        if paths:
            it = dict(it); it["source path"] = paths; kept.append(it)
    if kept:
        out[name] = kept
yaml.safe_dump(out, open(dst, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
print(f"src 용 sbom-info.yaml 임시 생성: {len(out)} 항목")
PY
    cd "$SRC"
    fosslight source -p . -f cyclonedx-json --no_merge -o "$OUT"
    ;;
  full)
    OUT="${OUT:-$HERE/sbom_out_full}"
    mkdir -p "$OUT"
    cd "$HERE/e3dp.2.1"
    fosslight source -p . -f cyclonedx-json --no_merge \
      -e "NOTICE" "REUSE.toml" "LICENSES/" "DPTester/" -o "$OUT"
    ;;
  *)
    echo "사용법: $0 [src|full]" >&2
    exit 1
    ;;
esac

echo "결과 폴더: $OUT"
ls -la "$OUT"
