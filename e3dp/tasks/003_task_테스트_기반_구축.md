# 003 테스트 기반 구축
목표: PC의 pytest가 보드의 DP를 기동·정리하고 UDP 7999 응답 1건을 확인하는 end-to-end 한 줄을 만든다.
상태: 진행중

## 사실 (확인된 것만)
- 보드: Raspberry Pi 3, Debian, gcc 14.2.0, armv7l. 호스트명 E3-DP-POC. 접속·마운트 절차는 스킬 `e3dp-build`.
- 소스 빌드는 보드에서 성공함 (`error:` 0건, `warning:` 293건).
- DP 기동은 `bin/scheck init`, 배포 경로 `/opt/e3dp/{bin,conf,periodic,download,log}`.
- `smm`은 프로세스 정체 시 `reboot -f` 실행.
- 설정은 Host 다운로드 또는 `/opt/e3dp/conf/nelite.db` 복원으로 채워짐. 기준 장치 설정 복사본 `tests/fixtures/ref_220/`.
- PC에 Python 3.12, paramiko 5.0.0, pytest 9.1.1 설치됨.
- 신 보드: Debian 13, 커널 6.12.111, Python 3.13.5, gcov·tcpdump 있음. 계정 e3dp는 sudo 필요(비밀번호 요구).
- DP는 root로 실행해야 함: `netcheck_server`가 raw 소켓(ICMP)을 사용. 일반 계정이면 `socket open error`가 반복되고 모든 GW가 COMM_ALARM으로 남아 `gw_server`가 폴링하지 않음. 구 장치는 전부 root로 실행됨.
- 공유메모리(키 0xe30000xx)가 남아 있으면 새 DB가 반영되지 않음. 기동 전 `ipcrm` 필요(`rmshm` 스크립트와 동일).
- 운영 기동 경로는 `smm`이 서버 12개를 기동·감시(죽으면 재기동, 정체 시 reboot -f). 현재 테스트는 `smm` 없이 `scheck`의 목록 순서로 직접 기동.
- 테스트 하네스 결함(수정 완료): `dp_stop`의 `pkill -9 -f gwsim.py`가 자기 자신의 `bash -c`(스크립트 문자열에 같은 이름 포함)를 종료시켜 뒤의 `ipcrm`이 실행되지 않았음. 공유메모리가 남아 시험 DB가 반영되지 않고 구 장치에서는 실제 GW(192.168.123.11)에 연결하기까지 했음. `pkill -f '[g]wsim[.]py'` 형태로 변경. 종료 후 shm 18 → 0 확인.
- 시뮬레이터 주소는 `lo` 별칭 10.99.0.11~16. 127.0.0.x는 ping 판정이 실패하므로 사용 불가(task 005 참조).

## 체크리스트
- [x] PC에 pytest 설치 확인 (9.1.1)
- [x] 보드에 `/opt/e3dp` 배포 상태 확인: `bin`만 있었음(make가 복사). conf, log, periodic, download, etc는 테스트 준비 단계(`Board.prepare`)에서 생성
- [x] 보드 `/opt/e3dp/conf`에 기준 장치 `nelite.conf`·`nelite.db`를 변환해 설치 (GW 주소 10.99.0.1N, 상위 서버 127.0.0.1, 자기 주소 보드 IP). 사용자가 보드 테스트를 허용(2026-10-26)
- [x] `tests/conftest.py` (환경 변수 BOARD_PW/REF_PW, `DP_TARGET=new|ref`, `dp` fixture), `tests/tools/board.py` (ssh, sudo, DP 기동·종료·공유메모리 정리, 시뮬레이터 터널 제어), `tests/dpapi.py` (emon/comp 출력 파서)
- [x] `pytest.ini`: 마커 등록(`device`, `ref`, `slow`)
- [x] DP 기동 방식: `smm` 제외하고 `E3DP_L_LIST` 순서로 직접 기동 가능 확인. `smm` 포함 기동은 별도 테스트로 남김
- [ ] `tests/device/test_boot.py`: DP 기동 후 프로세스 확인(서버 11개 + gw_server N개), `smm` 포함 기동과 서버 재기동 감시
- [ ] `tests/protocol/test_main_server.py`: UDP 7999에 요청 1건 전송, 응답 수신 확인 (task 004에서 수행)
- [ ] gcov 빌드 확인: 보드에서 `CFLAGS`에 `--coverage` 추가해 빌드 가능 여부, `.gcda` 생성 위치 확인
- [ ] `tests/tools/run_tests.ps1` 또는 `Makefile`: 실행 명령 단순화
- [ ] 스킬 `e3dp-test` 폴더 구조·명령을 실제와 일치하게 갱신

## 결정/미정
- 결정: pytest는 PC에서 실행. 보드 제어는 ssh(paramiko).
- 미정: 보드의 기존 `/opt/e3dp` 설정을 덮어써도 되는지.
- 미정: 보드 IP·계정. 환경 변수로 받음. 스킬 `e3dp-build` 기준 10.10.1.100.

## 테스트
- 추가: `tests/device/test_boot.py`, `tests/protocol/test_main_server.py`
- 실행: `pytest tests -m device`

## 참조
- 스킬 `e3dp-build`, `e3dp-test`
- `e3dp.2.1/bin/scheck`, `e3dp.2.1/dp_tar`
