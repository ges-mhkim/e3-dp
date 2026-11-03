# 008 리포트 도구와 커버리지
목표: pytest 결과를 구분별(하위 장치/서버) 표로 리포트하고 gcov 커버리지로 미검증 영역을 드러낸다.
상태: 진행중

## 선행
- 003 테스트 기반 (리포트 뼈대는 003 직후 착수 가능), 001 인벤토리

## 사실 (확인된 것만)
- 보드에 gcc 14.2.0, 기준 장치에 gcov 있음. 보드 gcov 설치 여부 미확인.
- 리포트 표 열: ID, 구분(하위 장치/서버), 프로토콜, 대분류, 조합 입력, 구 환경 결과, 신 환경 결과, 판정(PASS/FAIL/미검증), 기준 출처(캡처/기준 장치/소스 해석).
- 하단: 구분별·프로토콜별 집계, 커버리지.

## 체크리스트
- [x] pytest 결과를 JUnit XML로 저장 (`--junitxml=out/junit_<target>.xml`), 증거는 `out/evidence_<target>.json`
- [x] 테스트 모듈 → 인벤토리 ID 매핑 (`report/make_report.py`의 INVENTORY). 테스트 함수 단위 매핑은 미착수
- [x] `tests/report/make_report.py`: 환경, 요약(구분·프로토콜별), 신·구 증거 비교, 테스트별 결과, 코드 커버리지, 미검증 영역 → `tests/report/<년월일시분초>.md`
- [ ] 인벤토리에 있고 테스트가 없는 항목을 "미검증"으로 자동 표시 (현재는 리포트에 고정 목록)
- [x] 구분별·프로토콜별 집계
- [x] 미검증 영역 고정 목록 표시
- [x] gcov: `tests/tools/coverage.py` (build → install → `COVERAGE=1 pytest` → collect → restore). `/tmp/cov`에 소스 복사본을 계측 빌드, `LD_PRELOAD` 라이브러리로 SIGTERM 종료 시 데이터 기록
- [x] 모듈별·파일별 커버리지 표(`tests/out/coverage.md`), 리포트 통합. 2026-10-26 측정: 진단 도구 제외 28.1% (3454/12286줄)
  - 낮은 모듈: src/rect 3.5%, src/control 5.3%, src/rt 28.6%, src/db 30.9%, src/scan 33.3%, src/gw 37.6%, src/config 39.7%, src/gather 45.2%
  - 높은 모듈: src/realdata 85.1%, src/modbus 80.7%, src/main 76.5%, src/alarm 66.9%
- [ ] 미실행 분기(branch) 단위 분석 (현재는 줄·함수 단위)
- [ ] 리포트 산출 위치 `tests/report/<년월일시분초>.md` (html 은 미정)

## 결정/미정
- 결정: 리포트에는 미검증 항목을 숨기지 않는다.
- 미정: html 포맷 사용 여부(md만으로 충분한지).

## 테스트
- 샘플 JSON 입력으로 리포트 생성 단위 테스트 (`tests/unit/test_report.py`).

## 참조
- 스킬 `e3dp-test`
