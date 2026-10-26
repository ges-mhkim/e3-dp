---
name: e3dp-test
description: e3dp 통신 테스트(pytest) 구성·폴더·실행 절차. PC에서 시뮬레이터와 pytest를 돌리고 보드의 DP 프로세스를 검증할 때, 테스트를 추가하거나 실행하거나 리포트를 만들 때 사용.
---

# e3dp 테스트

## 구성
```
PC (pytest + 시뮬레이터 + 리포트)  ──10.10.1.x──  보드 (DP 프로세스 실행)
```

| 위치 | 역할 |
|---|---|
| 보드 | `/opt/e3dp`에 배포해 `scheck init`으로 DP 실행 |
| PC | Host 시뮬레이터(UDP/TCP 클라이언트), GW 시뮬레이터(Modbus TCP 1502 서버), 정류기 시뮬레이터(TCP 2000 서버), pytest, 리포트 |
| PC → 보드 | ssh로 DP 기동·종료, 로그·설정 파일 수집 |

- DP가 GW·정류기에 접속하는 주소는 설정(DB)에 있다. 설정을 PC 시뮬레이터 주소로 두면 DP가 시뮬레이터에 접속한다.
- `netcheck_server`의 ping에는 PC가 응답.
- 보드는 이 프로젝트 폴더와 같은 CIFS 폴더를 보므로 `tests/out/`의 로그를 PC에서 바로 읽는다.

## 방식별 접근
| 구분 | 방법 | 실행 위치 |
|---|---|---|
| 빌드 | `make` 실행, 종료 코드와 error 수 확인 | 보드 (ssh) |
| 단위 | 대상 함수를 공유 라이브러리로 컴파일 후 ctypes로 호출. 또는 작은 C 하니스를 gcc로 빌드해 subprocess 실행 | 개발 PC 또는 보드 |
| 프로토콜 | UDP/TCP/Modbus 패킷 송수신 후 응답 검증 | 개발 PC → 보드 |
| 장치 | 프로세스 기동·종료, 로그, 설정 파일 반영 확인 | 보드 (ssh/시리얼) |
| 기준 비교 | 같은 입력을 기준 장치와 보드에 보내 응답 비교 (`e3dp-ref-device` 스킬) | 개발 PC → 기준 장치, 보드 |

## 현재 구현 (2026-10-26)
| 파일 | 역할 |
|---|---|
| `tests/tools/board.py` | ssh/sftp, sudo(비밀번호 stdin), DP 기동·종료, 공유메모리 정리, lo 별칭, 시뮬레이터 터널 제어, `env_up/env_down`(시험 환경 전체), 기준 장치 백업·복구, 보드 내 UDP 송신(`udp_send`), TCP 터널(`tcp`), Host 요청+TCP 응답(`host_request_tcp`) |
| `tests/sim/gwsim.py` | E3-GW 시뮬레이터(Modbus TCP 1502, 6대, 모드 7종). 보드에서 실행(Python 3.5 호환) |
| `tests/sim/hostsim.py` | Host 수신 시뮬레이터(UDP 7704 경보, 7510, 37 시각 응답). rid ACK 모드 |
| `tests/sim/hostreq.py` | Host 한 번짜리 요청(UDP 7999 송신 + caddr 포트 TCP 리스너로 응답 수신). 보드에서 실행 |
| `tests/sim/hostclient.py` | realdata(TCP 7995) 클라이언트와 float2int |
| `tests/sim/ber.py` | 44바이트 헤더, BER 빌더/파서(경보·설정 요청·응답) |
| `tests/dpapi.py` | `emon sys`/`comp` 출력 파서, DB·conf 변환, Host 보조(`host_request`, `host_alarms`, `drain_alarms`) |
| `tests/conftest.py` | `dp` fixture(모듈 단위 환경 기동), `ref_guard`(기준 장치 백업·복구 검증), `evidence` fixture(신·구 비교 증거 기록) |
| `tests/protocol/` | `test_gw_poll`, `test_gw_errors`, `test_gw_di`, `test_alarm`, `test_realdata`, `test_main_dispatch`, `test_config_limit`, `test_control` |
| `tests/unit/test_ber.py` | PC에서 실행하는 BER 빌더 왕복 검증(샘플 `fixtures/samples/*.hex`) |
| `tests/report/make_report.py`, `tests/tools/compare_evidence.py` | 리포트(`report/<년월일시분초>.md`)와 신·구 증거 비교 |
| `tests/tools/capture_ref.py`, `pcap_summary.py` | 기준 장치 읽기 전용 패킷 캡처·집계 |
| `tests/tools/devenv.py`, `refsession.py` | 환경을 pytest 없이 올리고 내리는 개발용 도구, 기준 장치 실험용 안전 래퍼 |
| `tests/tools/c/*.c` | 보드에서 컴파일하는 진단 도구(PDU 파서 하니스, 자료형 크기) |
| `tests/inventory.md` | 통신 인벤토리와 테스트 대응표 |

### 전체 실행과 리포트
```
cd tests
EVIDENCE_RESET=1 BOARD_PW=<비번> python -m pytest protocol -p no:cacheprovider --junitxml=out/junit_new.xml          # 신 보드 (약 12분)
EVIDENCE_RESET=1 DP_TARGET=ref REF_PW=<비번> python -m pytest protocol -p no:cacheprovider --junitxml=out/junit_ref.xml   # 기준 장치 (약 12분, 운영 DP 중단·복구)
python report/make_report.py                                                                                           # report/<년월일시분초>.md
python -m pytest unit -q                                                                                               # PC 단위 테스트
```
- 대상 선택: `DP_TARGET=new`(기본, `BOARD_PW`) / `DP_TARGET=ref`(`REF_PW`).
- 기준 장치 실행은 `ref_guard`가 백업·복구·프로세스 일치 검증을 한다. 실행 중에는 구 장치의 운영 DP가 중단된다.

### 시험 환경 구성 요점
- 시뮬레이터 이름·경로에 `gw_server`를 넣지 않는다(`modbus_server`가 `kil gw_server`로 프로세스를 종료함).
- DP는 root로 실행해야 함(`netcheck_server` raw 소켓). GW 주소는 `lo` 별칭 10.99.0.11~16(127.0.0.x는 ping 판정 실패).
- Host 시뮬레이터가 UDP 37에 시각 응답을 해야 `main_server`가 UDP 7999를 연다. `stime()`으로 보드 시각이 PC 시각으로 설정됨.
- `pkill -f` 패턴은 같은 스크립트 안의 명령줄과 매칭되어 자기 자신을 종료시킨다. `[x]yz` 형태 패턴을 쓰고 종료·기동을 다른 호출로 나눈다.
- 서버 준비는 `Running Now` 로그와 gw_server 첫 폴링 사이클 종료로 판단한다(그 전 UDP 요청은 유실, 첫 사이클의 제어 명령은 소비됨).
- 구 장치의 `ss -u`는 UDP 리스너를 표시하지 않는다 → `/proc/net/udp` 사용.
- 파일 작성 시 `\` 이스케이프가 한 단계 줄어드는 경우가 있어 제어 문자가 섞이지 않았는지 검사한다(`tests` 아래 .py를 바이트 단위로 확인).

## 폴더
```
tests/
  conftest.py     # 보드 주소, ssh, 기동/정리 fixture
  sim/            # host.py, gw.py, rect.py (시뮬레이터)
  unit/           # 함수 단위
  build/          # 빌드 확인
  protocol/       # 포트별 시나리오
  device/         # 기동·감시·재시작
  report/         # pytest 결과 → 표(md/html) 변환
  fixtures/       # nelite.db 등 입력 자료 (ref_220/ = 기준 장치 설정 복사본)
  out/            # 로그, 리포트 (git 제외)
```
- 이 구조는 초안. 파일 추가 시 이 스킬에 반영.

## 실행
```
pytest tests -m "not device and not ref"   # 보드·기준 장치 없이
pytest tests -m device                     # 보드 필요
pytest tests -m ref                        # 기준 장치 필요 (읽기 전용)
pytest tests/unit/test_xxx.py -k 이름
```
- 환경 변수: 보드 주소, 기준 장치 비밀번호(`REF_PW`)는 환경 변수 또는 `tests/local.env`.

## 마커
| 마커 | 의미 |
|---|---|
| `device` | 보드 필요 |
| `ref` | 기준 장치 필요 (읽기 전용 명령만) |
| `slow` | 장시간 |

## 테스트 설계
- 입력 분류: 소스 분기 조건에서 대표값(정상, 경계, 초과, 미달)을 뽑는다.
- 열거형은 전체를 한 번씩, 조합은 pairwise로 줄이고 위험 조합은 직접 추가.
- 이상 입력: 길이 오류, LRC 불일치, 타임아웃, 연결 끊김, 중복, 순서 뒤바뀜, 범위 초과.
- 커버리지: 보드에서 `gcc --coverage`로 빌드하고 gcov로 미실행 분기를 확인해 시나리오 보충.

## DP 기동 시 주의
- 설정이 필요: 기준 장치에서 복사한 `nelite.db`를 복원해 다운로드 단계를 우회. 다운로드 경로는 별도 테스트.
- `smm`이 정체를 감지하면 `reboot -f`로 보드를 재부팅. 테스트 모드에서는 `smm`을 기동하지 않고, `smm` 시험은 `slow`로 분리.
- 테스트 전후로 프로세스 종료와 공유메모리 정리(`ipcrm`).

## 리포트 표
- 열: ID, 구분(하위 장치/서버), 프로토콜, 대분류, 조합 입력, 구 환경 결과, 신 환경 결과, 판정(PASS/FAIL/미검증), 기준 출처(캡처/기준 장치/소스 해석).
- 하단: 구분별·프로토콜별 집계, 커버리지.

## 디버그 출력
- 소스에 추가할 때 `#ifdef E3DP_TEST_TRACE`로 감싸 기본 빌드에서는 끈다.
- 로그 출력보다 읽기 전용 덤프(공유메모리 값·상태 플래그를 파일로 기록)를 우선. 기존 `emon`으로 조회 가능한지 먼저 확인.
- 동작 로직은 건드리지 않는다. 타이밍 의존 시나리오는 trace 빌드와 일반 빌드 양쪽에서 확인.
