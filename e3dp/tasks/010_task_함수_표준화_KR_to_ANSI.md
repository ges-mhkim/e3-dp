# 010 함수 정의 표준화 (K&R → ANSI 프로토타입)
목표: 레거시 K&R 함수 정의를 ANSI 프로토타입 형식으로 바꿔, 최신 OS(gcc 15 이상, C23 기본 모드) 적용 시 빌드 오류 위험을 없앤다. 동작은 바꾸지 않는다.
상태: 진행중 (2026-11-10 WSL 변환·검증 완료. 장치 빌드·pytest·커밋 대기)
결과 비교표: `010_비교표_함수_표준화.md`

## 선행
- 009 불필요 파일 정리 (완료)

## 사실 (확인된 것만)
- 대상 수 (2026-11-10, WSL `Ubuntu-24.04` gcc 13.3, `-fsyntax-only -Wold-style-definition`, `lib/pdu`의 .c 제외): 소스 101개 파일에서 K&R 정의 **119개**. 파싱 실패 파일 0개.
- 많은 파일: `src/config/config_handler.c` 18개, `src/gather/gather_server.c` 13개, `src/control/control_pe_process.c` 8개, `src/db/ldb_decode.c` 7개, `src/db/ldb_download.c` 5개, `src/control/control_init.c` 5개, `lib/mpu/mpu_util.c` 5개, `lib/com/printmesg.c` 5개.
- 매개변수 타입 분포 (스크립트 파싱): `DrInt` 46, `DrUInt` 37, `int` 7, `DrSocket` 4 (모두 int 계열), 나머지는 포인터 typedef(`DrDBM`, `DrScan`, `EcCommonHeader`, `DrString` 등), `char *`, 배열 매개변수(`DrRtInfoRec rti[]`).
- `float`·`double`·`char`(값) 매개변수 없음. `short` 계열은 6개 매개변수(함수 6개):
  - `EcUDPOpen`, `EcTCPOpen`, `EcTCPConnect` (`DrUShort port_no`, `lib/com`): 호출하는 모든 파일에 `extern ... ( DrUShort port_no );` 프로토타입이 이미 있음. `EcTCPConnect`는 src/lib/include에서 호출 지점 없음.
  - `DrScanGetCompName` (`DrShort compid`, `lib/mpu/config_util.c`): `src/config/config_handler.c:24`에 프로토타입 있음.
  - `DrScan__ao_set` (`unsigned short mr_addr`, `src/config/config_handler.c`, `src/acon_agent/acon_parse.c`): 인자는 상수 0, 1, 6, 11, `USE_RECT_LPORT_TABLE`(0xE3E3 = 58339)로 `unsigned short` 범위 안.
- `DrECM` typedef는 검색에서 찾지 못함. 코드에서 `ecm->ct`로 쓰여 포인터로 보이나 정의는 미확인.
- `make/platform.tools`의 CFLAGS: `-W -Wall -fcommon -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types -Wno-error=int-conversion -Wno-error=return-mismatch -Wno-error=declaration-missing-parameter-type -Wno-error=implicit-int`. 이미 gcc 14 기준으로 일부 오류를 경고로 낮춰 통과 중.
- `e3dp.2.1`은 git 서브모듈 (원격 `git@github.com:ges-mhkim/e3dp.git`). 안쪽 저장소 HEAD `a10979f`. 바깥 저장소가 기록한 서브모듈 커밋은 `62415b8`로 서로 다름 (이전부터 있던 상태).
- WSL `Debian` (Debian 13.5, gcc 14.2.0-19, x86_64): `/home/e3dp/e3dp.2.1 -> /mnt/c/ges/project/08_dp/e3dp/e3dp.2.1` 링크로 컴파일 성공 (사용자 확인). 스킬 `e3dp-build`의 "PC 사전 검증 (WSL Debian)" 참조.
- 009에서 `make HOME_DIR=… OPT_DIR=…`로 경로를 바꿔 빌드한 기록이 있음.

## 체크리스트
- [x] 기준 보관: 변환 전 소스 전체 백업(프로젝트 밖), 변환 전 빌드(WSL Debian, 실제 Makefile)의 오브젝트 108개와 빌드 로그. 대상은 빌드 로그의 K&R 경고 138건 (앞서 단순 검사의 119개는 `lib/pdu` 19개가 빠진 수)
- [x] 모듈별 `-D` 옵션: 파일별 컴파일 대신 실제 Makefile로 빌드해 옵션을 그대로 적용 (`HOME_DIR`, `OPT_DIR`, `BUILD_LOG`만 작업 폴더로 변경)
- [x] 8단계 변환·비교 완료 (1 `lib/com`·`lib/control`, 2 `lib/mpu`, 3 `lib/pdu`, 4 `src/main`·`src/scan`·`src/acon_agent`, 5 `src/alarm`·`src/db`, 6 `src/config`, 7 `src/control`, 8 `src/gather`). 변환 함수 138개, 파일 43개
- [x] `-Wold-style-definition` 경고 0건 (빌드 기준 138→0, 전체 `.c` 108개 스캔 0건)
- [x] WSL 결과: 오류 0건, 경고 514건→514건(저장소 기본 옵션, 직접 측정), 오브젝트 108개 중 106개 동일, 2개는 호출 앞 `mov $0x0,%eax` 1개만 차이, 코드 차이 0개
- [x] 빈 괄호 `f()` 선언 15곳 수정 (2026-11-10): 함수 포인터 타입 `findVar`·`write_method`를 새 헤더 `include/pdu/pdu_callback.h`의 `pdu_find_var_t`·`pdu_write_method_t`로 통일(8개 파일 수정 + 새 헤더 1개). `setCurNo()` → `(void)`, `errno` 선언 2줄 삭제
- [x] C23 검증: gcc 14.2 `-std=gnu23`에서 변환 전 소스는 오류 1건(`lib/pdu/pdu_tree.c:183`, `findVar` 호출 인자 초과), 최종 소스는 오류 0건·`.o` 108개. 전체 스캔에서 K&R 정의·빈 괄호 선언 0건. 최종 오브젝트 비교: 105개 동일, 3개는 호출 앞 `mov $0x0,%eax` 1개만 차이, 코드 차이 0개
- [x] 최신 컴파일러 확인 (2026-11-10): WSL Debian 홈 폴더에 gcc 15.3.0-5, 16.2.0-4를 풀어서(시스템 변경 없음) 빌드. 변환 전 원본은 gcc 15.3에서 오류 1건(`pdu_tree.c:183`)으로 실패, 최종 소스는 gcc 15.3·16.2 모두 오류 0건·`.o` 108개
- [x] `-Wno-error=...` 뒤에 숨은 오류 38건 정리 (선언 누락 31, 타입 생략 3, 포인터·정수 혼용 3, 함수 포인터 불일치 1). 이 옵션을 빼도 gcc 15·16에서 오류 0건. 경고 514→401건, 새 경고 없음. 변환 전 오브젝트 비교: 87 동일, 9 호출부 1명령 차이, 12 코드 차이(원인 모두 확인, 64비트 포인터 절단 해소 등)
- [ ] `src/acon_agent/socket.c:192` `ntohl(addr)` 의도 확인 (포인터를 넘겨 조건이 항상 거짓. 동작 유지하고 주석만 추가함)
- [ ] 남은 경고 401건 검토 (로직 영향 가능: `sequence-point` 12, `stringop-overflow` 6, `uninitialized` 3, `format-overflow` 14, `mismatched-dealloc` 2 등)
- [ ] `-fcommon` 의존 해소 (헤더에 정의된 전역 변수 분리. 제거하면 `multiple definition` 729건)
- [ ] 장치 빌드 (`BUILD_EXIT=0`, `error:` 0건, 경고 건수 변환 전과 비교) — 사용자 실행 필요
- [ ] 기존 pytest 신·구 DP 비교 재실행 — 사용자 실행 필요
- [ ] 커밋 (Claude는 커밋하지 않음. 사용자가 diff 검토 후 서브모듈에서 커밋)

## 결정/미정
- 결정: 동작을 바꾸지 않는 표준화로 한정. 함수 본문 로직과 빌드 옵션(`-Wno-error=...`)은 바꾸지 않는다.
- 결정: 변환 통과 기준은 같은 컴파일러·옵션으로 만든 오브젝트의 `objdump -d` 동일. 다른 함수는 원인을 찾아 해결한다.
- 결정: 변환으로 드러난 인자 타입·개수 불일치를 고치면 동작이 달라지는 경우, 조용히 고치지 않고 따로 보고해 사용자가 판단한다.
- 결정: 비교 기준은 안쪽 저장소의 git(`git show HEAD:<파일>`, `git diff`). 파일 단위 되돌리기는 `git checkout -- <파일>`. 단, `include/drmodule.h`는 `shard_memory` 주석이 커밋되지 않은 상태라 `checkout`으로 되돌리지 않는다.
- 결정: 소스는 바이트를 보존하는 방식으로 수정한다 (한글 주석, cp949 가능성). 한 파일 시험 후 `git diff --stat`으로 전체 파일이 바뀌지 않았는지 확인.
- 미정: 커밋 방식. Claude는 커밋·푸시하지 않고 작업 트리 diff로 남기는 것을 기본으로 한다. 사용자가 맡기면 변경.
- 미정: ARM 크로스 gcc(`arm-linux-gnueabihf-gcc`) 설치. 현재 WSL Debian은 x86_64라 경고 건수가 장치와 다름.
- 결정(2026-11-10): `lib/pdu`는 빌드에 포함되어 있어 이번 대상에 넣어 변환함 (19개).
- 결정(2026-11-10): 빈 괄호 `f()` 선언 15곳도 수정함(위 체크리스트). `write_method`는 호출하는 곳이 없어 `int (*)(void)`로 정의. 실제로 쓰기 함수를 연결할 때 시그니처를 정해야 함.
- 미정: `platform.tools`의 `-Wno-error=...` 옵션 뒤에 남은 코드(WSL x86_64 빌드 집계: `implicit-function-declaration` 31건, `int-conversion` 3건, `implicit-int` 3건, `incompatible-pointer-types` 1건). gcc 14 이상에서 기본 오류인 항목이라 새 OS에서 옵션이 계속 통하지 않으면 빌드가 막힐 수 있음. 정리 여부 결정 필요. 장치(armv7l) 건수는 다를 수 있음.
- 미정: 경고 기준값. 스킬 `e3dp-build`는 405건 이하이나, 009의 정리 후 장치 빌드는 446건. 변환 전 장치 빌드를 먼저 측정해 기준을 정한다.
- 미정: gcc 15의 C23 모드에서 K&R이 오류가 되는지 여부는 확인하지 못했음 (WSL gcc가 13.3, 14.2). 새 OS 이미지에서 빌드로 확인 필요. 임시 대응으로 `CFLAGS`에 `-std=gnu17` 추가 가능.

## 테스트
- 변환 전후 오브젝트 `objdump -d` 비교 (WSL Debian, x86_64).
- `gcc -Wold-style-definition` 경고 0건.
- 장치 빌드: `BUILD_EXIT=0`, `error:` 0건, 경고 건수 변환 전과 비교.
- 기존 pytest 비교 테스트 재실행.

## 참조
- 스킬 `e3dp-build`, `e3dp-test`
- 009 불필요 파일 정리
