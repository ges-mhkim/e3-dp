# 001 통신 인벤토리
목표: 소스에서 DP의 모든 통신(포트, 방향, 메시지, 필드)을 추출해 테스트 체크리스트의 기준 문서로 만든다.
상태: 진행중

## 사실 (확인된 것만)
- 아키텍처 문서(`docs/E3-DP_소스_아키텍처.md`) 기준 포트 후보

| 서버 | 포트 | 상대 |
|---|---|---|
| main_server | UDP 7999 | Host 요청 진입점, 서비스 코드로 타 서버에 중계 |
| db_server | UDP 8002 | Host 설정 다운로드 (ASN.1 PDU) |
| config_server | UDP 7032 | Host 설정 get/set |
| control_server | UDP 8022 / TCP 8021 | Host 제어 |
| rt_server | UDP 8052 | Host 실시간 구독, 푸시 |
| alarm_server | UDP 7042 → Host UDP 7704 | 경보 송신, 응답 대기 재전송 |
| gather_server | UDP 7062 | Host로 정시·피크·충전·UPS 데이터 송신 |
| realdata_server | TCP 7995 | 외부 클라이언트 원시값 조회 |
| gw_server | → E3-GW TCP 1502 | Modbus TCP 폴링, 제어/AO 쓰기 |
| rect_server | → 정류기 TCP 2000 | ASCII + LRC 프레임 폴링 |
| netcheck_server | ICMP | GW/장치 ping |
| acon_agent | TCP 9785 (기준 장치 실측. 문서 기재 13120은 불일치) | ACON 장치 연동 (최상위 Makefile 미포함, 기준 장치에서 실행 중) |

- 위 표는 문서 기반이며 소스로 재확인 전.
- 날짜·접미사 보관 폴더는 2026-10-26 삭제됨(task 009).
- 소스는 기준 장치 배포본(03.01.14)과 동일.

## 확인된 포트 정의 (소스 `include/`)
| 정의 | 값 | 위치 |
|---|---|---|
| DR_TCP_PORT_DBM / DR_UDP_PORT_DBM | 8001 / 8002 | drcommon.h |
| DR_UDP_PORT_VTM (main_server) | 7999 (8011 TCP 정의 있음) | drcommon.h |
| DR_TCP_PORT_ECM / DR_UDP_PORT_ECM (control) | 8021 / 8022 | drcommon.h |
| DR_TCP_PORT_SCAN / DR_UDP_PORT_SCAN (config) | 7031 / 7032 | drcommon.h |
| DR_TCP_PORT_ALARM / DR_UDP_PORT_ALARM | 7041 / 7042 | drcommon.h |
| DR_TCP_PORT_RT / DR_UDP_PORT_RT | 8051 / 8052 | drcommon.h |
| DR_TCP_PORT_PERIOD / DR_UDP_PORT_PERIOD (gather) | 7061 / 7062 | drcommon.h |
| EC_ALARM_FRONT_PORT (Host 경보 수신) | 7704 | drcommon.h |
| EC_RT_FRONT_PORT | 7510 | drcommon.h |
| EC_REQUEST_UPORT | 7000 | drcommon.h |
| TSYNC_SELF_PORT / DR_UDP_PORT_TSYNC / TSYNC_SERVICE_PORT | 7700 / 7800 / 37 | drcommon.h |
| E3_GW_TCP_PORT | 1502 | nelite.h, misc.h |
| DONGAH_RECT_PORT | 2000 | nelite.h, misc.h |
| 기타 UDP | 8071~8074 (FO_MUX, IMAGE, S_MUX, 155M) | drcommon.h |
| 기타 | 9001, 9002, 9004, 9010, 9020, 9030, 9101 | misc.h (사용 여부 미확인) |

- 기준 장치 listen TCP(실측): 7031, 7041, 7995, 8001, 8021, 9785(acon_agent). UDP listen은 `ss -ulnp`에서 확인되지 않음(확인 방법 재검토 필요).
- `main_server`는 `main_dispatch.c`의 `_smtable`로 서비스 코드(`EC_SVC_*`, `EVR_*`)를 목적 서버로 중계: SCAN(7032)은 한계치·마스크·AO·제어모드, COT(8022)는 제어 스크립트·룰, DB(8002)는 설정 다운로드·저장, RT(8052)는 실시간 설정·해제. `EVR_DB_SYSTEM_UPDATE`는 시각 동기로 `main_server`가 직접 처리. 요청 크기 2048 초과 시 폐기.
- 소스 인코딩이 EUC-KR 계열이라 주석이 UTF-8 뷰어에서 깨져 보임. 변환 금지(README 코딩 규칙).

## 체크리스트
- [x] 포트 정의 추출: `include/drcommon.h`, `include/nelite.h`, `include/misc.h` (아래 "확인된 포트 정의"). `bind`/`connect` 사용처 대조는 미완
- [ ] 서비스 코드 표 추출: `src/main/main_dispatch.c`의 `_smtable`(약 45개)을 코드값(`include/service.h` 등)까지 풀어 표로 저장 (구조 파악은 완료)
- [ ] Host → DP 메시지별 요청/응답 형식 정리 (헤더, 필드, 길이, 바이트 순서)
- [ ] DP → Host 푸시 메시지별 형식 정리 (경보, 정시수집, 실시간)
- [ ] DP → GW Modbus 요청/응답 형식 정리 (AI 40워드, DI 40워드, 응답 249B 검증, 쓰기)
- [ ] DP → 정류기 프레임 형식 정리 (ASCII, LRC, 정류기 종류별 차이)
- [ ] 메시지별 입력 필드의 분기 조건과 대표값(정상, 경계, 초과, 미달) 정리
- [ ] 메시지별 이상 입력 후보 정리 (길이 오류, LRC 불일치, 타임아웃, 끊김)
- [ ] 결과를 `tests/inventory.md`로 저장. 문서 단독으로 이해 가능하게 작성 (용어, 메시지 형식을 본문에 기재)
- [ ] 구분 열 추가: 하위 장치(GW/정류기/ping) / 서버(Host)

## 결정/미정
- 결정: 인벤토리의 행 하나가 테스트 ID 하나의 기준이 된다. 리포트 표의 ID와 일치시킨다.
- 미정: ASN.1 PDU(`libPdu`) 메시지의 상세 분해 범위. 다운로드는 `nelite.db` 복원으로 우회하는 경로(task 003)를 기본으로 하고 다운로드 자체는 후순위.

## 테스트
- 해당 없음 (문서 산출). 산출물이 task 004~006의 입력.

## 참조
- `docs/E3-DP_소스_아키텍처.md` (§3 전체 구조, §4 모듈별 책임)
- 소스: `e3dp.2.1/src/*`, `e3dp.2.1/include/`, `e3dp.2.1/lib/com`, `e3dp.2.1/lib/pdu`
