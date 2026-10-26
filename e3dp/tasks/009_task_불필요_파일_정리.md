# 009 불필요 파일·죽은 코드 정리
목표: 빌드·배포에 쓰이지 않는 보관본과 낡은 사본을 제거해 시뮬레이터 작성 시 혼동을 없앤다.
상태: 진행중

## 사실 (확인된 것만)
- 판정 근거 3가지: (1) 루트 Makefile과 하위 Makefile 대상, (2) 장치에서 `make clean all` 후 생성된 `.o`, (3) 기준 장치(10.10.0.220) 실행 프로세스·배포 바이너리·기동 스크립트.
- 기준 장치 실행 프로세스: smm, main_server, db_server, config_server, scan_server, gather_server, rt_server, alarm_server, control_server, modbus_server, rect_server, netcheck_server, realdata_server, acon_agent, gw_server(N), wan_led. `acagent_checker`는 `/etc/rc.local`에서 기동.
- 기준 장치 `/opt/e3dp/bin` 배포 바이너리: 위 목록 + comp, config, port, station, sys(`src/util`), emon, emon2, kwhm_agent, acagent_checker. `emon2`, `kwhm_agent`는 `e3dp.2.1`에 소스 없음.
- 기준 장치에 `upgrade`, `proc_check` 바이너리 없음. 웹 서버(lighttpd 등)와 CGI 없음.
- 기준 장치 기동 경로: `/etc/init.d/e3dp` → `scheck`, `/opt/e3dp/run.sh`(`wan_led`, `smm`), `/etc/rc.local`(`acagent_checker`).
- 기준 장치 listen TCP: 7031(config), 7041(alarm), 7995(realdata), 8001(db), 8021(control), 9785(acon_agent), 21(vsftpd), 22, 23.
- 삭제 전 백업: `C:\ges\project\08_dp\_backup\e3dp.2.1_before_cleanup_20261026` (미추적 파일 포함 전체 복사, 13MB).
- 삭제 후 장치 빌드: `BUILD_EXIT=0`, `error:` 0건, `warning:` 293건. 삭제 전과 동일.

## 체크리스트
- [x] 백업 생성 (프로젝트 폴더 밖)
- [x] 루트 Makefile 대상, `.o` 생성 여부, 기준 장치 프로세스로 사용 목록 작성
- [x] 보관 폴더 삭제: `src/control.20221012`, `src/gather.240411`, `src/gather.org20240405`, `src/netcheck.240124`, `src/netcheck.old`, `src/scan.20230213`
- [x] 폴더 내 낡은 사본 삭제: `src/gather/gather_server.c_org`, `src/gw/gw_server_171205.c`, `src/rect/rect_server.c.old`, `src/smm/smm.c`(Makefile은 `smm_new.c` 사용), `lib/gi_gw/Makefile.org`, `cgi-bin/Makefile.org`, `src/proc_check/Makefile.org`
- [x] 장치 `sudo make clean all`로 삭제 후 빌드 확인
- [ ] 사용자 결정 필요 항목 정리 (아래 "결정/미정")
- [ ] 빌드되지만 호출되지 않는 `.c`(`src/db/ldb_tsync.c`, `src/config/config_init.c`, `src/realdata/realdata_util.c`) 처리: 링크에 불필요함을 확인했으나 헤더·주석 참조 여부 추가 확인 후 삭제
- [ ] 파일 내부의 죽은 코드(`#if 0`, 주석 처리된 블록) 목록화. 삭제는 task 별도 생성
- [ ] README의 "보관 폴더 수정·삭제 금지" 규칙을 현재 상태에 맞게 수정 (완료 시 체크)

## 결정/미정
- 결정: 삭제 대상은 "어떤 Makefile에도 없고 기준 장치에 배포되지 않은" 보관본·낡은 사본으로 한정.
- 결정: 삭제 전 항상 프로젝트 밖에 백업.
- 미정(삭제하지 않음, 사용자 판단 필요)

| 대상 | 현황 | 판단 근거 |
|---|---|---|
| `src/upgrade` | 루트 Makefile 미포함, 기준 장치에 없음. FTP 기반 업그레이드 서버 | OS 업그레이드 시스템 검토와 관련 가능 |
| `src/proc_check` | 루트 Makefile 미포함, 기준 장치에 없음 | 프로세스 감시. `smm`과 기능 중복 가능 |
| `cgi-bin/`, `web/` | 루트 Makefile 미포함, 기준 장치에 웹 서버·CGI 없음 | 개발 장치에서만 존재. 현장 미사용 가능성 높음 |
| `DPTester/` | NanoPi 하드웨어 검수 도구(libfahw 의존). 바이너리 미추적 | 신 보드(Raspberry Pi)에서 사용 불가 |
| `lib/pdu` | Makefile에서 주석 처리, 사전 빌드 `libPdu.a` 사용 | 소스 보존 필요 여부 |
| `src/util`의 미빌드 소스 | `alm_tst.c`, `compmon.c`, `e3_test.c`, `gw_upgrade.c`, `pb_test.c`, `ppp.c`, `tsync.c`, `udpsend.c` | Makefile에 수동 대상으로만 존재 |
| `src/util/{acon_ctrl,mb_test,modbus_test,real_test,vcb_test}` | git 미추적 하위 폴더, 시험용 | |
| `bin/acon_server`, `bin/acon_test` | git 미추적 바이너리, 기준 장치 미배포 | |
| `src/acon_agent`, `src/acagent_checker`, `src/wan_led` | 루트 Makefile 미포함이나 기준 장치에서 실행 중 | 삭제 금지. 사용 중 |

## 테스트
- 해당 없음. 장치 빌드로 검증.

## 참조
- 백업: `C:\ges\project\08_dp\_backup\e3dp.2.1_before_cleanup_20261026`
- 스킬 `e3dp-ref-device`, `e3dp-build`
