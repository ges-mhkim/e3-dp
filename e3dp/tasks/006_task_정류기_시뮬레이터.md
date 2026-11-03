# 006 정류기 시뮬레이터 (TCP 2000, ASCII/LRC)
목표: 정류기(RECT) 역할의 TCP 서버를 만들어 rect_server 통신을 pytest로 검증한다.
상태: 진행 (MR-RECT 완료, 대용량 정류기 남음)

## 선행
- 001 통신 인벤토리, 003 테스트 기반, (비교 기준) 002 캡처

## 사실 (확인된 것만)
- `rect_server`는 정류기에 TCP 2000으로 접속해 ASCII + LRC 프레임으로 폴링. 정류기 종류별로 값 파싱 후 LPORT 갱신.
- `rect.lport` 테이블 사용. 대용량 정류기는 `large_rect.c`에서 처리.
- 프레임 형식·종류는 task 001에서 소스 기반으로 확정.

## 체크리스트
- [x] 정류기 종류와 프레임 형식 목록화 (inventory RECT-01~03, 소스 rect.h·rect_server.c 기준)
- [x] `tests/sim/rectsim.py`: TCP 서버(2000), 75레지스터 응답, LRC 계산, 모드(silent/short/badframe), 제어 19002 (DB 변형: `dpapi.make_db_rect`, 셸프 7 = 10.99.0.17)
- [x] 정상 응답 테스트: ACDS·DCDS·RECT(rack1) 값 반영 (신·구 13개 통과)
- [x] 통신 실패 테스트: 연결 거부(ip_down) -> 51회 초과 시 통신 이상, 복구 확인. 무응답(silent) 모드는 시뮬레이터에 있으나 시험은 미작성
- [~] 이상 응답 테스트: 짧은 응답·깨진 응답에 프로세스 유지 확인. LRC 불일치는 DP가 검사하지 않음(소스 확인)이라 시험 대상 아님
- [ ] 대용량 정류기 테스트 (`large_rect.c` 경로)
- [~] 포트 매핑 테스트: 사용 포트만 검증. ACDS 8·DCDS 4~8·20·51~58·RECT 2~5 rack·22·24 등은 미검증
- [ ] 캡처(task 002)와 시뮬레이터 응답의 프레임 구조 비교 테스트

## 결정/미정
- 미정: 기준 장치가 실제 정류기를 사용 중인지(캡처에 정류기 통신이 있는지). 없으면 기준은 소스 해석만.

## 테스트
- 위치: `tests/protocol/test_rect_*.py`
- 실행: `pytest tests/protocol -m device -k rect`

## 참조
- 소스: `e3dp.2.1/src/rect/rect_server.c`, `large_rect.c`
- 스킬 `e3dp-test`
