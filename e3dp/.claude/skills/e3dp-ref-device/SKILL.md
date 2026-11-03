---
name: e3dp-ref-device
description: 구 환경 기준 장치(10.10.0.220, Ubuntu 16.04 NanoPi)에 읽기 전용으로 접속해 상태·설정 파일을 확인하고 신 환경과 동작을 비교하는 절차. 기준 장치 접속, 설정 복사, 동작 비교 시 사용.
---

# 기준 장치 (구 환경)

## 정보
| 항목 | 값 |
|---|---|
| IP | 10.10.0.220 (eth0), 192.168.123.2 (eth1, 하위 장치 망) |
| 접속 | ssh, 계정 root, 비밀번호 ges000 |
| OS | Ubuntu 16.04.2, Linux 3.4.39-h3 armv7l (NanoPi) |
| 배포 버전 | 03.01.14 (`/opt/e3dp/bin/VERSION`) |
| 상태 | 연구소 보관 장치(현장 운영 장치 아님, 사용자 확인 2026-10-26). 가동 185일, 서버 프로세스 13개, `gw_server` 2개 실행 중 |
| 하위 장치 | `/opt/e3dp/conf/gw_list`: 192.168.123.11, 192.168.123.12 |
| 상위 서버 | `nelite.conf`: HOST_IP·ALARM_HOST_IP 10.10.0.144 |
| 도구 | python3, gcov 있음. tcpdump, gdb 없음 |

## 용도
- 기준 DP 실행체: 소스와 같은 바이너리가 구 OS에서 동작. 같은 입력에 대한 응답을 신 환경과 비교하는 기준.
- 설정 파일(`nelite.conf`, `nelite.db` 등) 복사.
- 실제 현장 통신 기록은 기대하지 않는다. 연결된 GW 9종 중 4종만 12바이트 응답(함수 0x84), 5종 무응답(2026-10-26 캡처). 시뮬레이터의 기준은 소스.

## 허용 / 금지
- 현재 허용 범위는 읽기 전용. 설정 변경·프로세스 재기동은 사용자 승인 후에만(연구소 장치이므로 승인 시 가능).
- 허용: 파일 읽기, `ps`, 로그 조회 등 읽기 전용 명령.
- 금지: 프로세스 종료·재기동, 파일 수정·삭제, 재부팅, 패키지 변경. 필요하면 사용자 확인 후 수행.
- 가동 중인 DP가 있으므로 부하가 큰 명령(전체 파일 검색 등)을 피한다.

## 접속 (Python, paramiko)
```
import paramiko, os
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('10.10.0.220', username='root', password=os.environ['REF_PW'],
          timeout=10, allow_agent=False, look_for_keys=False)
stdin, stdout, stderr = c.exec_command('ps -eo pid,etime,args | grep _server', timeout=15)
```
- 비밀번호는 환경 변수 `REF_PW`로 전달. 테스트 코드·task에 쓰지 않는다.
- PC에 sshpass 없음. 일반 ssh 대신 paramiko 사용.
- 파일 복사는 `c.open_sftp().get(원격, 로컬)`.

## 설정 복사
- 대상: `/opt/e3dp/conf/{nelite.conf, nelite.db, gw_list, acon_config.json}`
- 저장 위치: `tests/fixtures/ref_220/` (2026-10-26 복사 완료)
- `alarm.db`는 운영 중 갱신되는 mmap 파일이라 복사하지 않는다.

## 동작 비교 절차
1. 비교 시나리오의 입력(패킷)을 소스 기반 시뮬레이터로 생성. 시뮬레이터는 "입력 생성기"이고, 기대값은 기준 장치 DP의 실제 응답.
2. 기준 장치와 신 환경 보드에 같은 입력을 전송. (GW·정류기 시뮬레이터를 기준 장치에 연결하려면 기준 장치의 `gw_list`/`nelite.db` 변경이 필요하므로 사용자 승인 필요)
3. 응답 바이트·필드를 저장해 비교. 차이는 FAIL로 리포트.
4. 상태를 바꾸는 요청(제어, 설정 변경)과 설정 변경은 사용자 승인 후에만 기준 장치에 수행하고, 끝나면 백업한 설정으로 원복.
- 테스트 마커: `@pytest.mark.ref`.

## 소스와 배포본의 관계
- `e3dp.2.1` 소스 = 기준 장치 배포본(03.01.14)의 소스. 최신 소스에 수정 이력 없음(사용자 확인, 2026-10-26).
- 기존에는 버전 관리를 하지 않았고 이후 git으로 관리 시작. 따라서 구 장치와 신 환경의 동작 차이는 소스 차이가 아닌 환경(컴파일러, libc, 커널, 보드) 차이로 본다.

## 기준 장치에서 테스트 실행 (DP 교체와 복구)
- 운영 기동 방식: `/etc/init.d/e3dp`가 `wan_led`와 `smm`을 기동. `smm`이 서버 12개를 기동·감시하고, 정체 시 `reboot -f`. `acon_agent`는 별도 기동.
- 테스트 시 `smm`을 먼저 종료하고 서버를 종료해야 함(순서 반대면 `smm`이 재기동하거나 장치를 재부팅).
- 자동 처리: `conftest.py`의 `ref_guard` fixture(세션 단위). 시작 시 `Board.ref_save()`가 `nelite.conf`, `nelite.db`, `gw_list`, `acon_config.json`, `alarm.db`를 `tests/out/ref_backup_<시각>/`에 백업(원격과 크기 비교 검증). 종료 시 `Board.ref_restore()`가 한 번만 복구하고 프로세스 목록이 백업 시점과 같은지 검증, 다르면 테스트 실패.
- 복구 내용: 테스트 DP·시뮬레이터 종료, 공유메모리 정리, 백업 복원, `/opt/e3dp/bin/smm`·`acon_agent`를 절대 경로와 `setsid`로 재기동(`wan_led`는 건드리지 않음).
- 실험용 스크립트는 `tests/tools/refsession.py`의 `ref_session()` 컨텍스트로 감싼다(같은 백업·복구 적용).
- 복구 확인은 프로세스 이름으로 한다. 상대 경로(`./smm`)로 기동하면 `ps` 인자가 달라 `/opt/e3dp/bin` 검색에 안 잡힌다.
- 기준 프로세스 목록 17개: `tests/out_ref_procs_before.txt`.
- 실행 명령: `cd tests && DP_TARGET=ref REF_PW=<비번> python -m pytest protocol -m device -p no:cacheprovider` (약 1.5분, 이 시간 동안 구 장치의 운영 DP가 중단됨).
- 사용자 승인: "복구 가능하면 어떠한 테스트도 진행해도 된다"(2026-10-26).
