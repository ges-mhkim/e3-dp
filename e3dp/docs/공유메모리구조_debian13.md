# E3-DP 공유 메모리 — Debian 13 컴파일 시 필드 검토

> 대상: `e3dp.2.1` 소스의 공유 메모리 구조체 11개(말단 필드 264개)와 `alarm.db` 파일.
> 질문: 구 환경(Ubuntu 16.04)에서 신 환경(Debian 13)으로 컴파일할 때 **크기(bit/byte)나 배치가 바뀌는 필드**가 있는가, 검토가 필요한 필드는 무엇인가.
> 이 문서만으로 이해할 수 있도록 공유 메모리의 구성을 처음에 요약했다. 내용은 소스 읽기와 컴파일로 확인한 사실이다. 아키텍처 규칙에 기대는 부분(ARM의 `char` 부호, little-endian)과 확인하지 못한 것은 8절에 따로 적었다.

---

## 1. 결론

1. **구 환경과 신 환경에서 공유 메모리 구조체의 크기와 필드 오프셋은 하나도 다르지 않다.** 구조체 11개, 말단 필드 264개를 구·신 환경 설정으로 컴파일해 비교한 결과 차이는 0개이다 (3절).
2. 이유: 두 환경 모두 **32비트 ARM(armv7l)** 이라서 `long`, 포인터, `int`의 크기가 같다. 바뀐 것은 `time_t`(4B → 8B)인데, **공유 메모리 구조체에는 `time_t` 필드가 없다** (시간은 `unsigned int`, `unsigned short` 쌍으로 저장한다).
3. 크기가 비트 수에 의존하는 필드는 **1개**이다: `DrAlarmBLOCK.pop_time`(`DrULong` = `unsigned long`). 32비트(현재)에서는 4B로 같고, 64비트(aarch64/x86_64)로 빌드하면 8B가 된다. 이 필드는 소스에서 읽거나 쓰는 곳이 없다.
4. **검토가 필요한 항목은 필드 크기가 아니라 다음 세 가지이다.**
   - 시간에서 파생되는 필드가 64비트 `time_t`에서도 같은 값을 갖는지 (4절): 같다.
   - 필드를 다루는 코드의 컴파일 옵션·선언 문제 (5절): `-fcommon` 필요, `CreateSharedMemory`가 5개 소스에서 선언 없이 호출됨, `acon_agent`의 `time()` 호출.
   - 64비트로 전환할 경우의 위험 (6절).

---

## 2. 환경 차이와 공유 메모리 구성

### 2.1 구 환경과 신 환경

| 항목 | 구 환경 | 신 환경 (Debian 13) | 근거 |
|------|---------|---------------------|------|
| 보드 | NanoPi | Raspberry Pi 3 | `README.md` |
| OS | Ubuntu 16.04.2 | Debian 13 | `.claude/skills/e3dp-ref-device`, `tests/report/20261027080719.md` |
| 커널 | 3.4.39-h3 armv7l | 6.12.111+deb13-armmp armv7l | 같음 |
| 컴파일러 | gcc 5.4 | gcc 14.2.0 | `tasks/003`, `tasks/004` |
| 비트 | 32비트 (armv7l) | 32비트 (armv7l) | `uname -m` 값 |
| `long` / 포인터 | 4B / 4B | 4B / 4B | 32비트이므로 |
| **`time_t`** | **4B** | **8B** | `tasks/004`: "신 툴체인에서 `time_t`는 8바이트" |

바이트 순서는 두 환경 모두 `armv7l`(little-endian)이다.

### 2.2 공유 메모리 구성

서버 프로세스들이 System V 공유 메모리(`shmget`/`shmat`)로 데이터를 주고받는다. 구조체와 크기는 다음과 같다 (3절에서 구/신 환경 값을 비교).

| 세그먼트 | 구조체 | 내용 |
|----------|--------|------|
| `DrDB` | `DrModuleRec` | 구성품·논리포트·포인트 DB (현재값, 경보 상태 등) |
| `DrSI` | `DrSystemRec` | 하위 장비(shelf) 정보와 통신 상태 |
| `shard_m` | `struct shard_memory` | 서버별 생존 카운터·버전 |
| `netconfig` | `NetworkConfigRec` | 장비 IP·ID 설정 |
| `DrPCB`, `PeakDB`, `DcdsDB`, `UpsDB` | `Dr_PCBRec`, `stPeakDBRec`, `stDcdsDBRec`, `stUpsDBRec` | 정시·피크·DCDS·UPS 이력 버퍼 |
| `raw_idx` | `RawIndexRec` | (GW 단위, 포트)별 포인트 인덱스 범위 |
| 플래그 9개 | `char` 1바이트 × 9 | 정전/발전기 판정 |
| `Proc` | `ProcRec` | `acon_agent` 생존 카운터 |
| `DR_ACB` | `DrAlarmRec_ACBRec` | 경보 버퍼. 공유 메모리가 아니라 `/opt/e3dp/conf/alarm.db` 파일을 `mmap` |

구조체는 `#pragma pack(1)` 또는 `PACKED` 속성으로 선언되어 필드 사이에 패딩이 없다 (`shard_memory`만 예외로 패킹되지 않는다).

---

## 3. 구조체 크기와 필드 차이

### 3.1 검증 방법

실제 헤더(`drmodule.h`, `alarm/alarm.h`, `nelite.h`, `scan/period.h`, `scan/peak.h`, `proc_watchdog.h`)를 gcc 13.3으로 컴파일하고 `sizeof`, `offsetof`를 필드마다 뽑아 비교했다. 보드가 아니라 PC(WSL Ubuntu 24.04)에서 환경을 흉내 낸 것이다.

| 설정 | 컴파일 옵션 | 흉내 내는 환경 |
|------|-------------|----------------|
| `OLD32` | `-m32 -funsigned-char` | 구 환경 (32비트, `time_t` 4B, `char` unsigned) |
| `NEW32` | `-m32 -funsigned-char -D_TIME_BITS=64 -D_FILE_OFFSET_BITS=64` | 신 환경 (32비트, `time_t` 8B) |
| `LP64` | (기본) | 참고용 64비트 (aarch64/x86_64) |

한계: x86 32비트와 ARM 32비트는 8바이트 정수의 구조체 내 정렬 규칙이 다르다 (x86: 4B, ARM: 8B). 그러나 **8바이트 이상의 원소를 가진 필드가 공유 메모리 구조체에 하나도 없고** (264개 중 0개), `shard_memory`를 제외한 구조체는 패킹되어 있으며 `shard_memory`는 `int`와 `char`만 가지므로 이 차이는 결과에 영향을 주지 않는다. `char`의 부호는 `-funsigned-char`로 ARM 기본값에 맞췄다.

### 3.2 구조체 크기 (바이트)

| 구조체 | 구 환경 (`OLD32`) | 신 환경 (`NEW32`) | 64비트 (`LP64`) |
|--------|------------------:|------------------:|----------------:|
| `NetworkConfigRec` | 182 | 182 | 182 |
| `struct shard_memory` | 872 | 872 | 872 |
| `DrModuleRec` | 332,237 | 332,237 | 332,237 |
| `DrSystemRec` | 12,005 | 12,005 | 12,005 |
| `Dr_PCBRec` | 61,204 | 61,204 | 61,204 |
| `stPeakDBRec` | 8,722 | 8,722 | 8,722 |
| `stDcdsDBRec` | 14,504 | 14,504 | 14,504 |
| `stUpsDBRec` | 8,704 | 8,704 | 8,704 |
| `RawIndexRec` | 4,400 | 4,400 | 4,400 |
| `ProcRec` | 174 | 174 | 174 |
| `DrAlarmRec_ACBRec` | 144,006 | 144,006 | **156,006** |
| (`DrAlarmBLOCKRec` 1건) | 48 | 48 | **52** |

`struct shard_memory`는 패킹되지 않는 구조체라 소스에서 `drmodule.h`가 `nelite.h`(`#pragma pack(1)`)보다 먼저 포함되면 872B, 나중에 포함되면 870B가 된다. 공유 메모리를 attach하는 서버 소스 16개는 모두 872B이고, 870B가 되는 `upgrade_server.c`는 이 세그먼트를 사용하지 않는다. 이 포함 순서 효과는 구·신 환경에서 동일하다.

### 3.3 필드 타입 분포 (말단 필드 264개)

| 선언 타입 | 개수 | 구/신 32비트 크기 | 64비트 크기 |
|-----------|-----:|------------------:|------------:|
| `DrUChar` / `unsigned char` | 83 | 1 | 1 |
| `DrUShort` / `unsigned short` | 84 | 2 | 2 |
| `int` / `DrInt` | 39 | 4 | 4 |
| `unsigned int` / `DrUInt` | 18 | 4 | 4 |
| `float` | 12 | 4 | 4 |
| plain `char` / `DrChar` | 25 | 1 | 1 |
| `DrShort` | 2 | 2 | 2 |
| **`DrULong` (`unsigned long`)** | **1** | **4** | **8** |

(합계 264. 배열 필드는 원소 타입 기준이다.) 공유 메모리 구조체에는 비트필드, `enum`, 포인터, `time_t`, `long long`, `double`이 없다.

### 3.4 구 환경과 신 환경의 필드 비교 결과

- 구(`OLD32`) 대 신(`NEW32`): **오프셋·크기·부호가 다른 필드 0개.**
- 신(`NEW32`) 대 64비트(`LP64`): 다른 필드 42개. 내용은 다음 둘뿐이다.
  - `DrAlarmBLOCK.pop_time`의 크기 4B → 8B와 그 뒤 필드들의 오프셋 +4 이동 (4.1절).
  - plain `char` 배열 25개의 부호 (unsigned ↔ signed). 크기와 오프셋은 같다 (4.3).

---

## 4. 검토가 필요한 필드

### 4.1 `DrAlarmBLOCK.pop_time` — 크기가 비트 수에 의존하는 유일한 필드

| 항목 | 값 |
|------|----|
| 선언 | `include/alarm/alarm.h:76` `DrULong pop_time;` (`DrULong` = `unsigned long`, `include/common.h:95`) |
| 32비트 (구/신) | 4B. `DrAlarmRec_ACBRec` 시작에서 `ACB[0].pop_time`의 오프셋 8 (블록 내부 오프셋 2) |
| 64비트 | 8B. 이후 필드가 모두 +4 (`ACB[0]` 기준 오프셋): `relation` 12→16, `lowlimit` 50→54. 블록 48B→52B, ACB 전체 144,006B→156,006B |
| 코드에서의 사용 | `src`, `lib`, `include` 어디에도 읽거나 쓰는 곳이 없다 (선언만 있음). `DrAlarmACBInitialize()`가 블록을 0으로 지울 뿐이다 |

영향:
- 현재(32비트 → 32비트)에서는 변화가 없다. 구 환경(32비트)의 크기도 144,006B이다 (구 장비의 실제 `alarm.db` 파일 크기는 확인하지 않았다).
- `alarm.db`는 기동 시 `get_file_size() != sizeof(DrAlarmRec_ACBRec)`이면 새로 만들고, 어느 경우든 `DrAlarmACBInitialize()`가 ACB 전체를 지운다 (`alarm/init_shm.c`). 따라서 크기가 달라져도 기존 경보는 이미 유지되지 않는다.

### 4.2 시간에서 파생되는 필드 — 64비트 `time_t`에서도 값이 같다

신 환경에서 `time_t`가 8B가 되었으므로 `time_t` 값을 공유 메모리 필드에 넣는 모든 곳을 확인했다.

| 필드 | 타입 | 값을 만드는 방법 | 64비트 `time_t`의 영향 |
|------|------|------------------|------------------------|
| `lport[].otime1/otime2`, `rtime1/rtime2`, `shelf[].otime/rtime` | `DrUShort` 쌍 | `alarm_check.c:56-69`: `time(&tval); memcpy(&temp_time[0], &tval, 4);` 후 앞 2바이트→`*1`, 다음 2바이트→`*2` | **없음**. `tval`의 **앞 4바이트**를 복사하는데 little-endian이라 앞 4바이트가 하위 32비트이다. 구 환경의 4B `time_t`와 같은 값이다 |
| `ACB[].otime1/2`, `rtime1/2` | `DrUShort` 쌍 | `alarm_check.c:524-527`(논리포트), `547-550`(shelf)에서 위 `lport[]`/`shelf[]` 시각을 `DrAlarmACBRec`에 복사하고, `alarm_acb.c:109-112`가 ACB에 복사 | 없음 (위와 같은 값) |
| `PCB[].time1/time2` | `unsigned short` 쌍 | `gather_server.c:641-644`, `677-678`: 같은 방식 | 없음 (위와 같음) |
| `PeakDB/DcdsDB/UpsDB .Atime` | `unsigned int` | `gather_server.c:1088, 1159` (`mktime()` 결과 `new_time`), `gw_server.c:936`, `rect_server.c:342` (`time_t at`)를 대입 | 64비트 → 32비트 unsigned로 잘린다. `unsigned int`이므로 2106년 초까지 같은 값이다 (구 환경의 `time_t`는 부호 있는 32비트라 2038년까지) |
| `lport[].occ_time` | `unsigned int` | `scan_check.c:76-87` `getOccurTime()`: `(tv.tv_sec % 10000) * 1000 + tv.tv_usec / 1000` | 없음. 결과가 항상 10,000,000 미만이다 |
| `ACB[].pop_time` | `DrULong` | (사용 안 함, 4.1) | — |

이 방식은 **little-endian에서만** 성립한다. big-endian이면 `memcpy(&tval, 4)`가 상위 4바이트를 복사해 0이 된다. 두 환경 모두 little-endian이므로 문제가 없다.

### 4.3 plain `char` 필드 25개 — 부호가 CPU에 따라 다르다

ARM에서 plain `char`의 기본은 unsigned이고 x86은 signed이다 (아키텍처 ABI 규칙이며 이 PC에서 확인하지 않았다, 8절). 구·신 환경이 모두 ARM이므로 **구→신 변경은 없다.** x86 PC에서 같은 소스를 컴파일하는 테스트 도구·시뮬레이터에서만 달라진다. 크기와 오프셋은 영향이 없다.

| 구조체 | 필드 |
|--------|------|
| `shard_memory` | `ver_main` … `ver_reserv3` (`char[50]` × 15) |
| `ProcRec` | `ver_acon`, `ver_reserv6`, `ver_reserv7` (`char[50]` × 3) |
| `DrModuleRec` | `self_ip[4]`, `host_ip[4]`, `comp[].facilname[3]`, `comp[].compname[5]`, `lport[].reserved0[6]`, `lport[].reserved1[10]` |
| `DrAlarmRec_ACBRec` | `ACB[].compname[5]` |

부호가 결과에 영향을 주는 곳은 개별 바이트를 숫자로 비교·출력하는 코드이다. 확인된 곳:
- `DrDB->self_ip[0..3]`을 `%d`로 출력: `db/ldb_decode.c:909-911`과 `config/config_handler.c:1714-1715` (둘 다 `fprintf(fp, ...)`로 `nelite.db` 헤더 줄에 기록), `emon/emon.c:320-323` (화면 출력). IP 옥텟이 128 이상이면 signed `char`에서는 음수(예: 192 → -64)로 나온다.
- 문자열로만 쓰는 `ver_*`, `compname` 등은 영향이 없다.

### 4.4 자연 정렬에 맞지 않는 2·4바이트 필드 — 변경은 없으나 확인 대상

패킹된 구조체이므로 2·4바이트 필드 중 오프셋이 자기 크기의 배수가 아닌 것이 있다 (**배열 인덱스 0 기준** 55개). 배열 원소 크기가 필드 정렬의 배수가 아니면 인덱스에 따라 정렬 상태가 달라지므로 실제 접근 시 불일치하는 경우는 이보다 많다. 원소 크기: `comp[]` 29B, `lport[]` 103B, `point[]` 22B, `shelf[]` 40B, `PCB[]` 36B, `peak[]`/`dcds[]`/`ups[]` 29B, `ACB[]` 48B(32비트). **구 환경과 배치가 같으므로 신규 문제는 아니다.**

| 구조체 | 정렬 불일치 필드 수 |
|--------|--------------------|
| `DrModuleRec` | `float` 6, `DrUShort` 7, `unsigned int` 1 |
| `DrAlarmRec_ACBRec` | `float` 3, `DrUShort` 4 |
| `stPeakDBRec` | `unsigned int` 8, `unsigned short` 6 |
| `stDcdsDBRec`, `stUpsDBRec` | 각각 `unsigned int` 4, `unsigned short` 6 |

`float` 중 정렬이 맞지 않는 것: `lport[].highlimit`(8757), `lowlimit`(8761), `value`(8770), `hpeak`(8790), `lpeak`(8794), `deadband`(8798), `ACB[].peakvalue`(33), `highlimit`(46), `lowlimit`(50). (괄호는 구조체 시작에서의 오프셋, 인덱스 0 기준.)

컴파일러가 구 gcc 5.4에서 gcc 14.2로 바뀌었으므로, 이 필드를 **주소를 취해 포인터로 넘기는 코드**가 있으면 위험하다. 이를 확인했다.
- 서버 소스(`src/` 18개 디렉터리의 Makefile OBJS)를 신 환경 설정(gcc 13.3, `-Waddress-of-packed-member`)으로 구문 검사한 결과 경고가 **0건**이다. 즉 packed 멤버의 주소를 정렬 요구가 더 큰 포인터 형으로 변환하는 코드는 없다. (`void *`로 넘기는 `memcpy` 등은 이 경고의 대상이 아니므로, 모든 접근이 직접 멤버 접근이라는 뜻은 아니다.)

---

## 5. 컴파일 옵션과 선언 문제 (필드 접근에 영향)

### 5.1 `-fcommon`이 필요하다

공유 메모리 포인터가 **헤더 파일에서 정의**된다: `shard_m`(`drmodule.h:81`), `DrDB`(`drmodule.h:260`), `DrSI`(`drmodule.h:336`), `netconfig`(`nelite.h:157`), `raw_idx`(`nelite.h:174`), 플래그 `char *` 9개(`nelite.h:261-269`), `Proc`(`proc_watchdog.h:25`), `DR_ACB`(`alarm/alarm.h:110`), `PeakDB`/`DcdsDB`/`UpsDB`(`scan/peak.h:43, 69, 103`), `DrPCB`(`scan/period.h:113`). 여러 소스가 같은 헤더를 포함하므로 gcc 10 이상의 기본값(`-fno-common`)에서는 링크 시 중복 정의 오류가 난다. 확인:

| 옵션 | 두 소스를 링크한 결과 |
|------|----------------------|
| `-fcommon` | 성공 |
| `-fno-common` (gcc 10 이상 기본값) | `multiple definition of 'shard_m'`, `'DrDB'`, `'DrSI'` … 오류 |

`make/platform.tools`의 `CFLAGS`에 `-fcommon`이 있다. 위 실험처럼 이 옵션을 빼면 같은 헤더를 포함한 소스끼리 링크할 때 중복 정의 오류가 난다 (`make/platform.tools`로 전체 빌드를 `-fcommon` 없이 돌려 보지는 않았다). 같은 `CFLAGS`에는 gcc 14에서 오류로 승격되는 항목을 경고로 낮추는 `-Wno-error=implicit-function-declaration`, `-Wno-error=incompatible-pointer-types`, `-Wno-error=int-conversion` 등도 있다.

### 5.2 `CreateSharedMemory()`를 선언 없이 호출하는 소스

| 소스 | 위치 |
|------|------|
| `src/rt/init_shm.c` | 11행 |
| `src/netcheck/init_shm.c` | 11행 |
| `src/emon/init_shm.c` | 15행 |
| `src/acon_agent/acon_server.c` | 69행 |
| `src/upgrade/upgrade_server.c` | 308행 |

`CreateSharedMemory`를 호출하는 소스 23개(서버 16개, `src/util` 7개)를 모두 신 환경 설정으로 컴파일해 확인한 결과, 위 5개에서 `implicit declaration of function 'CreateSharedMemory'` 경고가 나온다. 이 파일들은 `extern void *CreateSharedMemory(...)` 선언이 없어 컴파일러가 반환형을 `int`로 간주하고, 반환값을 `(void *)`로 캐스트해 공유 메모리 포인터에 대입한다. 나머지 15개는 선언이 있다. (`src/util`의 `alm_tst.c`, `e3_test.c`, `vcb_test/vcb_test.c`도 같은 경고가 나오지만, `util/Makefile`의 기본 빌드 대상 `TARGET = port config station comp sys`에는 없다. `smm`과 `acagent_checker`가 쓰는 `createShardMemory()`는 선언되어 있다.)

- **32비트(현재)**: `int`와 포인터가 둘 다 4B라 정상 동작한다.
- **64비트**: 반환된 포인터가 `int`(32비트)로 잘리고 `(void *)`로 캐스트될 때 부호 확장되므로, 주소가 2GB 이상이면 원래 주소와 달라진다 (6절).
- gcc 14는 암묵적 선언을 기본으로 오류 처리하지만 `-Wno-error=implicit-function-declaration` 때문에 경고로 통과한다.

### 5.3 `acon_agent`의 `time()` 호출과 `Proc.cnt_acon`

| 항목 | 내용 |
|------|------|
| 코드 | `src/acon_agent/acon_server.c:57-58` `time_t at; time_t rtime;`, `113` `time(&rtime);`, `119` `time(&at);`, `121` `if((at - rtime) > 2)` 이면 `Proc->cnt_acon++` (`123-124`) |
| 선언 | 이 소스는 `<time.h>`를 포함하지 않아 `time()`이 암묵적으로 선언된다 (컴파일 경고 `implicit declaration of function 'time'`로 확인). glibc `time.h`는 64비트 `time_t`일 때 `time()`을 `__time64`로 연결한다 (이 PC의 Ubuntu 24.04 glibc 2.39 `time.h` 기준: 86행 `__REDIRECT_NTH (time, ..., __time64)`, 그렇지 않으면 76행의 일반 선언). 헤더가 없으면 이 연결이 적용되지 않는다 |
| 신 환경 `time_t` | 8B (`tasks/004`) |

문제 가능성: 선언 없이 호출한 `time(&at)`에는 위의 `__time64` 연결이 적용되지 않는다. 일반 `time` 심볼이 32비트 `time_t`용 함수로 연결되면 8바이트 변수 `at`, `rtime`의 **하위 4바이트만** 갱신되고 상위 4바이트는 초기화되지 않은 지역 변수의 값이 남을 수 있다. 그러면 `at - rtime` 비교와 `cnt_acon` 증가가 의도와 다르게 동작한다.
**이 PC에는 armhf glibc가 없어 실제 동작은 확인하지 못했다.** 보드에서 `acon_agent` 기동 후 `Proc->cnt_acon`이 약 2초마다 증가하는지, `acagent_checker`가 20초마다 `acon_agent`를 재기동하지 않는지로 확인해야 한다 (8절).

### 5.4 참고: `#pragma pack(1)`이 시스템 구조체에 미치는 영향 (x86 32비트 흉내 기준)

`nelite.h`의 `#pragma pack(1)`은 이후에 포함되는 헤더에도 적용된다. `nelite.h`가 자기 시스템 헤더는 모두 그 앞에서 포함하지만, 소스가 `nelite.h` **뒤에** 시스템 헤더를 포함하면 그 헤더의 구조체가 패킹된다. x86 32비트 흉내로 확인한 결과, `struct dirent`, `struct termios`는 패킹 시 크기가 달라진다 (예: `termios` 57B ↔ 60B). 조사한 시스템 구조체 21종 중 구 환경과 신 환경 설정에서 **같은 구조체(`dirent`, `termios`)가 같은 방식으로** 달라졌으므로, 이 조사 범위에서는 `time_t` 64비트화로 새로 생긴 크기 불일치가 없다. ARM에서의 정확한 값은 확인하지 못했다. 공유 메모리 필드와는 무관하다.

---

## 6. 64비트(aarch64, x86_64)로 빌드할 경우 확인된 위험

현재 대상은 32비트라 해당하지 않으나, 64비트 전환 시 소스에서 확인된 위치이다. **실제 오동작 위험**과 **확인했으나 문제없는 곳**을 구분했다.

### 6.1 실제 오동작 위험

| 위치 | 내용 |
|------|------|
| `DrAlarmBLOCK.pop_time` (4.1) | 8B로 커져 ACB 블록 52B, `alarm.db` 156,006B. 필드 자체는 사용하지 않는다 |
| `CreateSharedMemory` 암묵적 선언 5개 소스 (5.2) | 반환 포인터가 `int`로 잘림 |
| `alarm_handler.c:79, 194-196, 209-211` | `DrUInt otime, rtime`(4B)를 `memcpy`로 채운 뒤 `pdu_mesg_add(..., sizeof(DrULong), &otime)`로 전달한다 (`186-193`, `200-207`의 같은 형태 코드는 주석 처리됨). 32비트에서는 `sizeof(DrULong)`이 4B라 일치하지만 64비트에서는 길이 인자가 8이 되어 4B 변수 뒤를 읽고 Host로 가는 TIMETICKS 항목의 길이도 달라진다 |

### 6.2 확인했으나 값에는 문제가 없는 곳

| 위치 | 내용 |
|------|------|
| `alarm_check.c:59, 67, 582, 590`, `gather_server.c:631, 642` | `DrULong long_time`에 `memcpy(..., 4)`로 4바이트만 복사하지만 이후 사용하는 코드가 없다 |
| `gather_server.c:725, 751-758` | 같은 방식으로 `long_time`을 채운 뒤 `DrPeriod__append_pdu_message()`에 전달한다. 이 함수의 매개변수(`gather_server.c:812-815`)는 모두 `DrInt`(4B)라 하위 32비트만 쓰이므로 little-endian에서 값은 맞다 |
| `db/ldb_decode.c:915` | `%d`에 `unsigned long stationid`를 전달한다 (컴파일 경고 `-Wformat`). 32비트 설정에서도 같은 경고가 나온다 |
| `db/ldb_server.c:462, 514-516` | `unsigned long i1`에 `sscanf("%ld")` 후 `memcpy(&DrDB->stationid[0], &i1, 4)`. 4바이트 복사라 little-endian에서는 값이 맞다 |

---

## 7. 검토 항목 요약

| # | 대상 | 구→신(Debian 13) 변경 | 조치 |
|---|------|----------------------|------|
| 1 | 구조체 11개 전체 크기·필드 오프셋 | **없음** (264개 필드 비교) | 없음. 보드에서 8절의 점검 프로그램으로 한 번 확인 권장 |
| 2 | `ACB.pop_time` (`DrULong`) | 없음 (32비트). 64비트에서만 4→8 | 64비트 전환 시에만 재검토 |
| 3 | 시간 파생 필드 (`otime/rtime`, `PCB.time`, `Atime`, `occ_time`) | 값 동일 (little-endian, 하위 32비트) | 없음 |
| 4 | plain `char` 25개 | 없음 (둘 다 ARM). x86 호스트에서만 부호 다름 | x86 테스트 호스트에서 `self_ip` 출력 비교 시 주의 |
| 5 | 정렬 불일치 `float`·`short`·`int` 55개 (인덱스 0 기준) | 없음 | 주소 취득 경고 0건. 보드에서 정렬 트랩 수 확인 권장 |
| 6 | 전역 공유 포인터의 헤더 정의 | 링크 시 `-fcommon` 필요 (gcc 10+) | `CFLAGS`의 `-fcommon` 유지 |
| 7 | `CreateSharedMemory` 암묵적 선언 5개 소스 (23개 호출 소스 전수 확인) | 32비트라 동작은 같음 | 선언 추가 권장 |
| 8 | `acon_agent`의 `time()` 암묵적 선언 + 8B `time_t` | **확인 필요** | 보드에서 `cnt_acon` 증가 확인, `<time.h>` 포함 권장 |

---

## 8. 확인하지 못한 것 / 보드에서 확인할 것

| 항목 | 사유 |
|------|------|
| ARM 32비트 컴파일러가 만든 실제 `sizeof`/`offsetof` | 보드 접속에 비밀번호(환경변수 `BOARD_PW`)가 필요해 접속하지 않았고, 이 PC에는 ARM 컴파일러가 없다. 대신 x86 32비트(`-m32`)로 흉내 냈다 (3.1절의 한계 참조) |
| ARM에서 plain `char`가 unsigned인지 | 아키텍처 ABI 규칙에 따른 것이며 이 PC에서 확인하지 않았다. 아래 점검 프로그램이 `plain_char_signed`를 출력한다 |
| 선언 없는 `time()`이 armhf glibc에서 32비트 `time_t`용 함수에 연결되는지 (5.3) | armhf glibc가 없다 |
| 신 환경에서 `time_t`가 8B가 되는 이유 (Debian이 `_TIME_BITS=64`를 기본으로 하는지) | `tasks/004`의 관찰 결과만 사용했다. 위 흉내에서는 `-D_TIME_BITS=64`를 직접 지정했다 |
| 정렬 불일치 필드 접근 시 커널 정렬 트랩 | 보드에서 확인 필요: `cat /proc/cpu/alignment` (커널 설정에 따라 파일이 없을 수 있음) |

### 보드에서 값을 확인하는 점검 프로그램

`e3dp.2.1`에서 다음 파일을 컴파일해 실행하면 이 문서의 3.2절, 4.1절 값과 직접 대조할 수 있다 (PC에서 64비트로 컴파일해 실행까지 확인한 코드이며, 32비트 값은 위 표가 기대값이다). 구 장치에서도 같은 파일로 실행해 비교할 수 있다.

```c
/* shmcheck.c: gcc -fcommon -I include shmcheck.c -o shmcheck && ./shmcheck */
#include <stdio.h>
#include <stddef.h>
#include <time.h>
#include <drmodule.h>
#include <alarm/alarm.h>
#include <nelite.h>
#include <scan/period.h>
#include <scan/peak.h>
#include <proc_watchdog.h>

#define SZ(t)   printf("sizeof(%-20s) = %lu\n", #t, (unsigned long)sizeof(t))
#define OF(t,f) printf("offsetof(%s, %s) = %lu\n", #t, #f, (unsigned long)offsetof(t, f))

int main(void)
{
	printf("long=%d ptr=%d time_t=%d plain_char_signed=%d\n",
	       (int)sizeof(long), (int)sizeof(void *), (int)sizeof(time_t), (char)-1 < 0);
	SZ(NetworkConfigRec); SZ(struct shard_memory); SZ(DrModuleRec); SZ(DrSystemRec);
	SZ(Dr_PCBRec); SZ(stPeakDBRec); SZ(stDcdsDBRec); SZ(stUpsDBRec); SZ(RawIndexRec);
	SZ(ProcRec); SZ(DrAlarmRec_ACBRec); SZ(DrAlarmBLOCKRec);
	OF(DrAlarmRec_ACBRec, ACB[0].pop_time);
	OF(DrAlarmRec_ACBRec, ACB[0].relation);
	OF(DrAlarmRec_ACBRec, ACB[0].lowlimit);
	OF(DrModuleRec, lport[0].value);
	OF(DrModuleRec, lport[0].highlimit);
	OF(DrModuleRec, init_modbus);
	OF(DrSystemRec, shelf[0].status);
	OF(stPeakDBRec, peak[0].Atime);
	return 0;
}
```

기대값 (구·신 32비트 동일): `long=4 ptr=4 time_t=8(신)/4(구)`, `shard_memory=872`, `DrModuleRec=332237`, `DrAlarmRec_ACBRec=144006`, `DrAlarmBLOCKRec=48`, `ACB[0].pop_time=8`, `ACB[0].relation=12`, `ACB[0].lowlimit=50`, `lport[0].value=8770`, `lport[0].highlimit=8757`, `init_modbus=332232`, `shelf[0].status=32`, `peak[0].Atime=45`. `plain_char_signed`는 ARM이면 0이어야 한다.
