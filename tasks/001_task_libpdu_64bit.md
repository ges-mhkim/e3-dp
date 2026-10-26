# 001 libPdu 소스 편입 및 32/64bit 호환
목표: lib/pdu를 빌드에 편입하고 ASN.1 정수 처리를 32bit 고정으로 변경
상태: 진행중

## 사실 (확인된 것만)
- `lib/pdu`에 소스 7개(.c)+Makefile 있음. 최상위 Makefile에서 `lib/pdu` 주석 처리됨.
- `lib/libPdu.a`는 2022-06-23 프리빌드, 32bit ARM. `-lPdu` 링크 서버: main, db, config, alarm, scan, gather, rt, netcheck 외.
- WSL(Ubuntu 24.04, gcc 13, x86-64)에서 lib/pdu 소스 빌드 성공(에러 0, 경고만). 경고는 대부분 `pdu/misc.h` 미include(반환형 int, 무해)와 디버그용 포인터 캐스트.
- `pdu_asn.c:47,104,162,221`: `intsize != sizeof(long)`이면 NULL 반환.
- 64bit 실측: `asn_build_int/unsigned_int`에 intsize=4 → NULL. intsize=8 → 정상. 인코딩 바이트는 32bit와 동일(`02 01 fb`, `43 04 12 34 56 78`).
- `pdu_mesg_add`가 `(long*)`/`(u_long*)`로 읽음(`pdu_build.c` ASN_INTEGER, TIMETICKS 등). 호출부는 4바이트 변수를 `sizeof(DrInt)`/`sizeof(DrULong)`로 전달.
- 호출 수: `pdu_mesg_add` — `alarm_handler.c` 14, `config_handler.c` 6, `util/acon_ctrl/config_handler.c` 6.
- 파싱: `ldb_decode.c`의 `long pdu_val_integer` + `pdu_var.val.integer`(long).
- `DrULong`=`unsigned long`(`include/common.h:95`, `comm.h`). `alarm_handler.c:187-211`의 `otime/rtime`은 `DrUInt`(4B)인데 크기 인자는 `sizeof(DrULong)`.
- 주의: `DrULong`만 `uint32_t`로 바꾸면 ASN 크기 검사 때문에 PDU 전부 실패. ASN 쪽을 먼저 수정해야 함.
- 보드: `10.10.1.100` ARMv7 Debian, 빌드 절차는 `SKILL.md`. 소스는 CIFS로 공유(`/home/e3dp/e3dp.2.1`).
- 이 PC에 `-m32`, ARM 크로스 툴체인, qemu 없음.

## 체크리스트
- [x] lib/pdu 소스·Makefile 존재 확인
- [x] 64bit 소스 빌드 가능 확인 (WSL)
- [x] 64bit에서 intsize=4 → NULL 재현
- [ ] 작업 방식 결정 (git 브랜치 `e3dp.2.1` / 백업 복사)
- [ ] 보드에서 현행 `lib/pdu` 소스 빌드, 기존 `libPdu.a`와 `nm` 심볼 비교 (소스=바이너리 일치 확인)
- [ ] 최상위 `Makefile`의 `#	make -C lib/pdu` 주석 해제 (all, clean 둘 다)
- [ ] 경고 정리: `module_vars.c`, `pdu_build.c`, `pdu_debug.c`, `pdu_tree.c`에 `#include <pdu/misc.h>` 추가
- [ ] `pdu_asn.c`: asn_build_int/unsigned_int, asn_parse_int/unsigned_int를 `int32_t`/`uint32_t` 기준으로 변경, intsize==4 허용 (32bit 값 4바이트 접근)
- [ ] `include/pdu/asn1.h` 시그니처 동기화
- [ ] `pdu_build.c`/`pdu_parse.c`: `(long *)`, `(u_long *)` 캐스트를 `int32_t*`/`uint32_t*`로 변경, `variable_node.val.integer` 타입 확인(`include/pdu/pdu_impl.h:211,241`)
- [ ] `ldb_decode.c` 등 `long pdu_val_integer` 사용처 점검
- [ ] 보드에서 전체 `make` — PDU 송신/수신(alarm, db 다운로드, config) 동작 확인
- [ ] 골든 테스트: 보드(32bit)에서 PDU 바이트 덤프 → 64bit 빌드 출력과 비교
- [ ] `DrLong/DrULong` → `int32_t/uint32_t` 변경 (`include/common.h`, `comm.h`) — ASN 수정 이후에만
- [ ] `alarm.db` 호환: `DrAlarmBLOCK.pop_time` 크기 고정 여부 결정 (크기 불일치 시 `init_shm.c:87`이 파일 재생성 → 경보 이력 소실)
- [ ] 시각동기 수신 변수 `uint32_t`로 변경 (`main_tsync.c:178`, `ldb_tsync.c:151`)
- [ ] 완료 시 파일명 `_done.md`로 변경

## 결정/미정
- 미정: 작업 방식(브랜치 vs 백업).
- 미정: 64bit 이식 최종 목표 여부. 보드는 현재 ARMv7(32bit). 목표가 32bit 유지면 `DrULong` 변경은 보류하고 ASN 수정만.

## 참조
- 분석: `docs/E3-DP_소스_아키텍처.md`
- 소스: `e3dp/e3dp.2.1/lib/pdu`, `include/pdu`, `src/alarm/alarm_handler.c`, `src/db/ldb_decode.c`
- 64bit 검증 하네스(스크래치, 소멸 가능): WSL에서 `gcc -fcommon -I include -I include/pdu t.c libPdu64.a` 후 `asn_build_int(buf,&len,0x02,&v,sizeof(int))` 호출
