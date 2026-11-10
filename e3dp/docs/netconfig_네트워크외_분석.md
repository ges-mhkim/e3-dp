# netconfig 네트워크 외 항목 분석 (wire_type · wire_id · 웹 전용 키)

> 대상: `e3dp.2.1` 소스, 경로는 `e3dp.2.1/` 기준. 소스 줄을 직접 확인했고, 기준 장치(10.10.0.220)의 `nelite.conf`·`nelite.db` 사본과 대조했다.
> `netconfig`는 DP가 부팅할 때 `nelite.conf`를 읽어 만드는 공유메모리(182바이트, 키 `0xE3000001`)이다. 이 문서는 그중 **OS 네트워크 설정(IP·게이트웨이·넷마스크·hostname)을 제외한 항목**을 다룬다.
> OS 네트워크 파일(`/etc/network/interfaces`, `/etc/hostname`)과 짝이 있는 항목, 그리고 호스트 통신 주소 흐름은 `netconfig_네트워크관련_분석.md`에서 다룬다.

---

## 1. 핵심 요약

1. **`wire_type`만 동작에 영향을 준다.** 값이 `DrDB->type`으로 복사되어 모국(1)/자국(2) 분기에 쓰인다. 활성 비교가 34곳이고 alarm, scan, gather, control 4개 프로세스에 있다.
2. **`nelite.conf`의 `WIRE_TYPE`은 부팅 직후 값일 뿐이다.** 같은 `DrDB->type`을 `nelite.db` 복원과 DB 다운로드 처리가 덮어쓴다. 다운로드 처리는 값을 항상 1(모국)로 고정한다. 그래서 `WIRE_TYPE=2`로 설정해도 자국 동작이 유지된다는 보장이 없다.
3. **`wire_id`는 진단 출력 전용이다.** 서버 로직이 읽지 않는다. 국 번호는 호스트가 내려주는 DB의 stationid를 쓴다.
4. **웹 설정 화면(`wl.cgi`)의 키 `DEV_TYPE`, `E3GW_SUBNET`, `RECT_SUBNET`은 DP가 읽지 않는다.** 웹 CGI는 DP가 읽는 파일과 다른 경로에 쓴다.

---

## 2. 항목 개요

| 항목 | `nelite.conf` 키 | netconfig 필드 | 서버 로직 영향 | 용도 |
|---|---|---|---|---|
| 통신처리부 구분 | `WIRE_TYPE` (`1` 모국 / `2` 자국) | `wire_type` (1바이트 숫자) | **있음** | `DrDB->type`으로 복사되어 동작 분기 |
| 장치(국) 번호 | `WIRE_ID` (예: `139600`) | `wire_id` (7바이트 문자열, 6자까지) | 없음 | 진단 출력만 |
| 웹 전용 | `DEV_TYPE`, `E3GW_SUBNET`, `RECT_SUBNET` | `e3gw_subnet`, `rect_subnet`은 필드만 있고 값을 채우지 않음 | 없음 | 웹 설정 화면의 입력 항목 |

구조체 정의는 `include/nelite.h:162-186`, 값을 채우는 곳은 `main_server.c`의 `get_network_config()`(`:215-403`)이다. 다른 프로세스는 읽기만 한다.

`HOST_NAME`(`hostname`)은 OS의 `/etc/hostname`과 함께 바뀌는 항목이라 `netconfig_네트워크관련_분석.md`에서 다룬다.

**기준 장치의 값:** `WIRE_ID = 139600`, `WIRE_TYPE = 1`.

### 필드 트리

`[O]` 서버 로직이 사용, `[D]` 진단 출력만, `[X]` 미사용.

```
netconfig (182 B) 중 네트워크 외 항목 4개
├─ wire_id        [D] 장치(국) 번호 문자열 (7바이트, 예: "139600")
│                     ※ 국 번호는 이 값이 아니라 서버가 내려준 DB의 stationid를 쓴다
├─ wire_type      [O] 통신처리부 구분 (nelite.conf의 문자 '1','2' → 숫자로 저장)
│   ├─ 1 : 모국 (DR_LOCAL_TYPE)
│   ├─ 2 : 자국 (DR_REMOTE_TYPE)
│   └─ 그 외 : 검증 없이 그대로 저장
│        └─ DrDB->type으로 복사되지만, nelite.db 복원과 DB 다운로드 처리가 덮어쓴다 (4.1절)
├─ e3gw_subnet    [X] 채우는 코드 없음 (항상 0)
└─ rect_subnet    [X] 읽는 코드가 주석 처리됨 (항상 0)
```

- 나머지 9개 필드(`hostname`, IP·넷마스크·게이트웨이 계열)는 `netconfig_네트워크관련_분석.md`의 필드 트리에서 다룬다.

---

## 3. 설정은 어떻게 바꾸나

- `config` 유틸(`src/util/config.c`, root로 실행)이 항목마다 현재 값을 보여주고 새 값을 받아 `/opt/e3dp/conf/nelite.conf`에 쓴다. IP 항목과 같은 방식이다. `WIRE_TYPE`은 1·2만 받는다.
- 서버는 **기동 시 1회만** 읽는다. 값을 바꾼 뒤에는 재부팅하거나 서버 전체를 다시 띄워야 한다.
- `WIRE_ID`, `WIRE_TYPE`은 OS 파일과 짝이 없는 DP 전용 값이라 OS 설정에 반영되지 않는다.
- `config` 유틸은 값을 확인(Y)받은 뒤 `nelite.db`와 `nelite.conf`를 먼저 삭제하고 `nelite.conf`를 새로 쓴다(`config.c:125-128`). `nelite.db`는 상대 경로 `bin/rm`으로 지우므로 현재 디렉터리가 `/`일 때만 삭제된다. 이 동작이 `wire_type`의 최종 값에 영향을 준다(4.1절).
- 수동 편집에는 입력 검증이 없다. 키가 없어도 기동은 멈추지 않고 해당 필드가 빈 값으로 남는다(`main_server.c:232, 246`의 NULL 검사는 `arg`가 배열이라 항상 거짓).
- `WIRE_ID`는 7바이트 필드에 길이 검사 없이 복사된다(`main_server.c:240`). 6자까지는 종료 문자(NUL)가 들어가고, 7자는 종료 문자가 없어지며, 8자부터 다음 필드(`wire_type`)를 덮어쓴다(`include/nelite.h:163-164`).

---

## 4. wire_type

### 4.1 값이 정해지는 경로

서버 로직은 `netconfig->wire_type`이 아니라 **`DrDB->type`** 을 비교한다. `DrDB->type`을 쓰는 곳은 세 군데이다.

```
DrDB->type 이 정해지는 곳
├─ main_server.c:381    get_network_config() 끝에서 netconfig->wire_type 값으로 설정 (기동 직후)
├─ ldb_server.c:494     restore_db(): LOCAL_DB_PATH(/opt/e3dp/conf/nelite.db)의
│                       "* Wire Info" 절 두 번째 값으로 설정
└─ ldb_decode.c:192-196 DB 다운로드 PDU 해석에서 PDU로 받은 값을 곧바로
                        DR_LOCAL_TYPE(1)로 덮어씀. 주석: "Edited by AJS, at 2016.4.29 - Type은 Local로 고정"
```

**기동 순서:**
1. main은 공유메모리를 붙인 뒤 `Dr_Delay(10)`(10ms, `lib/com/conv.c:42`) 후 `get_network_config()`를 호출한다(`main_server.c:73-77`).
2. DB 서버(ldb_server)는 공유메모리를 붙인 뒤 `sleep(1)`을 하고(`ldb_server.c:67-69`), 공유메모리의 DB가 비어 있을 때만(`usedcomps`, `total_ports`, `total_points`, `shelf_count` 중 하나가 0 이하) `restore_db()`를 호출한다(`:261-264`).
3. 호스트가 DB를 내려보내면 `ldb_decode.c:196`이 값을 1로 고정한다.

두 프로세스 사이에 동기화 장치는 없고 대기 시간(10ms 대 1초)에만 의존한다.

**`nelite.db`의 값:** `store_db()`가 `DrDB->type`을 파일의 "* Wire Info" 절에 기록한다. 같은 이름의 `store_db()`가 두 프로세스에 따로 있다. 하나는 DB 서버(ldb_server)의 `ldb_decode.c:722`(기록 `:775`)로, DB 다운로드 처리 끝에 호출된다(`ldb_handler.c:218`). 다른 하나는 config 서버(config_server)의 `config_handler.c:1477`(기록 `:1508`)로, 상·하한 갱신(`EC_SVC_UPDATE_LIMIT`)이나 경보 마스크 갱신(`EC_SVC_ALARM_MASK`) 뒤에 호출된다(`:389-391`). 둘 다 그 시점의 `DrDB->type`을 기록한다. 기준 장치 사본의 Wire Info 줄은 `139600 1 26 199 245 60`이고, 형식은 `stationid type usedcomps total_ports total_points periodinterval`이다(`ldb_server.c:490-498`). 두 번째 값이 type이며 1이다.

**결론:** 재부팅 후 `nelite.db`가 있으면 type은 그 파일 값이 되고, DB 다운로드가 한 번이라도 일어나면 1이 된다. `nelite.conf`의 `WIRE_TYPE`이 끝까지 유지되는 경우는 `nelite.db`가 없고 다운로드도 없는 상태뿐이다. 기준 장치는 `WIRE_TYPE=1`이라 이 차이가 드러나지 않는다.

**`config` 유틸과의 관계:** `config` 유틸은 값을 바꿀 때 `nelite.db`를 삭제한다(`config.c:125`). 삭제되면 재부팅 후 `restore_db()`가 파일을 열지 못해 FAIL로 끝나고(`ldb_server.c:444-448`), 이때 type은 `nelite.conf`의 `WIRE_TYPE` 값 그대로 남는다. 그러나 이 삭제는 현재 디렉터리가 `/`일 때만 동작하므로, 다른 디렉터리에서 실행하면 이전 `nelite.db`가 남아 그 값이 `WIRE_TYPE`을 덮어쓴다. 삭제가 실제로 일어났는지는 장치에서 확인하지 않았다.

### 4.2 모국/자국에 따라 달라지는 동작

`include/drcommon.h:150-151`: `DR_LOCAL_TYPE = 1`(모국 통신처리부), `DR_REMOTE_TYPE = 2`(자국 통신처리부). 아래는 활성 비교 34곳 전부이다. 이 외에 출력용(`emon.c:322`)과 주석 처리된 곳은 4.3절에 따로 있다.

**alarm (7곳)**

| 위치 | 조건 | 동작 |
|---|---|---|
| `alarm_server.c:100` | 1이면 "LOCAL", 아니면 "REMOTE" | 기동 로그 출력만 (동작 영향 없음) |
| `alarm_check.c:364` | REMOTE | `Data_Filter()`가 즉시 반환 → 경보 필터링을 건너뜀. 주석: "자국은 임시로 제외한다" |
| `alarm_check.c:380`, `:414`, `:446` | LOCAL이고 포트 종류가 HANGEN, BALGEN, COMMON | VCB·발전기 상태(`Dr_VCB_CHECK`, `Dr_GEN_CHECK`)를 확인해 경보를 필터링 |
| `alarm_check.c:629` | LOCAL | `Dr_VCB_CHECK()`: VCB 컴포넌트의 정전/입전 포트로 판정 |
| `alarm_check.c:651` | REMOTE | `Dr_VCB_CHECK()`: RRCP 컴포넌트(compno 1) 포트로 판정 |

**scan (4곳)**

| 위치 | 조건 | 동작 |
|---|---|---|
| `scan_check.c:864` | 1도 2도 아님 | 정전/입전 체크 함수가 즉시 반환 |
| `scan_check.c:889` | LOCAL | 모국형 정전/입전 체크: VCB 컴포넌트 포트를 확인 |
| `scan_check.c:1083` | REMOTE | 자국형 정전/입전 체크: ATS 컴포넌트를 확인 (소스 주석: 자국에는 ATS가 1개라 전압 이상이면 정전, 회복이면 입전) |
| `scan_check.c:1156` | LOCAL | `Dr_Filter_driver()`(`:182`에서 호출): VCB 정전 감지 루프 |

`scan_check.c:884-885, 1080-1081`의 소스 주석은 "자국 장치를 LAN으로 수용한 경우 Type이 LOCAL로 설정되어 있어도 자국 기준으로 처리한다"고 적고 있다.

**gather (3곳)**

| 위치 | 조건 | 동작 |
|---|---|---|
| `gather_server.c:1216`, `:1339`, `:1463` | LOCAL | 수집 데이터(피크, 충전기, UPS)를 모아 20건(`cnt > 20`)마다 호스트로 송신 |
| 같은 위치의 else | LOCAL이 아님 | 10건(`cnt > 10`, `:1241`, `:1364`, `:1488`)마다 송신 |

**control (20곳)**

| 위치 | 조건 | 동작 |
|---|---|---|
| `control_init.c:59` | LOCAL | `DrCtClientAdd()`가 TCP 연결(`DrCt__tcp_connect`)을 맺음. LOCAL이 아니면 연결 없이 `evc_client` 필드만 채움 |
| `control_pt_process.c:50` | REMOTE | 지연 5초 추가. 주석: 일부 자국에서 Reset으로 예열하므로 지연 필요 |
| `control_auto.c:135` | LOCAL이면 "Vcb", 아니면 "Ats" | 자동제어 점검 로그의 문구만 달라짐 |
| `control_auto.c:162` | LOCAL | 정전 자동제어 조건 판단(모국: 한전 정전 + 발전기·VCB 상태) |
| `control_auto.c:208` | REMOTE | 같은 판단을 자국 규칙으로 수행(`:162`의 else if) |
| `control_auto.c:846`, `:916` | LOCAL | VCB 컴포넌트 포트를 읽어 메인 VCB 상태·정전/입전 데이터를 확인 |
| `control_auto.c:1029` | REMOTE이고 `dcd_status != 0x02` | "DCD Status is OFF-LINE … Message Cancelled" 출력 후 메시지 송신 취소 |
| `control_auto.c:1058` | LOCAL | 메시지를 7111 포트의 `dr_control_udp_handler()`로 직접 전달하고 반환 |
| `control_auto.c:1088` | REMOTE | 값 `0x799`를 반환하고 가상 디멘드 전력 확인을 건너뜀 |
| `control_auto.c:1120` | REMOTE | 값 `0x199`를 반환하고 가상 디멘드 전력 확인을 건너뜀 |
| `control_auto.c:1154` | REMOTE | `demand_flag`(0)를 반환하고 가상 디멘드 전력 확인을 건너뜀 |
| `control_pg_process.c:51` | REMOTE이고 DGCP 모드 포트가 미정의 | `gen_mode = 0x01`로 고정 (그 외에는 포트 값을 읽음) |
| `control_pg_process.c:256`, `:589` | LOCAL | "출력전압,주파수,동작상태를 체크하는 중입니다" 안내 메시지와 지연(`:256` 5초, `:589` 6초 × 2회)을 거쳐 점검 단계를 수행 |
| `control_pg_process.c:296` | LOCAL이고 전압·주파수 포트 상태가 정상 | 정상 기동 메시지 처리 |
| `control_pg_process.c:323`, `:686` | LOCAL이고 전압 포트 상태 이상 | "출력전압이상으로 발전기 기동을 실패" 처리 후 441 반환 |
| `control_pg_process.c:334`, `:697` | LOCAL이고 주파수 포트 상태 이상 | "출력주파수이상으로 발전기 기동을 실패" 처리 후 441 반환 |

`control_pg_process.c`의 소스 주석은 "자국(ROME3)의 경우에는 전압 및 주파수 검사 무시"라고 적고 있지만, 해당 조건은 `DR_LOCAL_TYPE`이다. 주석의 용어와 조건이 서로 반대로 읽히며, 어느 쪽이 의도인지는 소스만으로 판단하지 않았다.

**요약:** 모국(1)은 VCB 기반 정전/입전 판정, 발전기 전압·주파수 점검, 제어 TCP 연결, 20건 단위 송신을 수행한다. 자국(2)은 ATS/RRCP 기반 판정, 가상 디멘드 확인 생략, 경보 필터링 생략, 10건 단위 송신을 수행한다.

**1·2가 아닌 값(예: 0)의 동작은 분기마다 다르다.** 정전/입전 체크는 `scan_check.c:864`에서 중단된다. 수집은 LOCAL이 아니므로 10건 단위로 송신한다. 제어의 REMOTE 전용 분기(`control_auto.c:1088, 1120, 1154` 등)는 REMOTE가 아니므로 건너뛰어 모국과 같은 코드로 진행하고, LOCAL 전용 분기(제어 TCP 연결 등)는 실행되지 않는다. 일관된 동작이 아니므로 사용하면 안 되는 값이다.

### 4.3 영향이 없는 곳

| 위치 | 상태 |
|---|---|
| `main_tsync.c:180, 303` | 주석 블록 안이라 실행되지 않음 (시각 동기화는 type과 무관) |
| `config_handler.c:1364` | 주석 처리됨 |
| `ldb_download.c:75, 125` | 주석 처리됨 |
| `sys.c:102` | 주석 처리됨 |
| `emon.c:322` | 진단 화면에 값만 출력 |

gw, modbus, netcheck, rect, rt, acon_agent는 `DrDB->type`을 비교하지 않는다(`e3dp.2.1` 전체 `.c`·`.h` 검색에서 해당 파일 없음).

---

## 5. wire_id

- `netconfig->wire_id`를 읽는 곳은 **`emon.c:305`(진단 화면)뿐**이다. main이 기동 시 값을 출력한다(`main_server.c:242`).
- 국 번호(stationid)는 호스트가 내려주는 DB에서 온다: `ldb_decode.c:189-190`(다운로드), `ldb_server.c:493`(`nelite.db` 복원). 예전에 `wire_id`로 stationid를 계산하던 코드는 삭제되어 주석만 남아 있다(`main_server.c:383-385`, "2018.07.02 DSK Deleted").
- `control_store.c`의 `wire_id`는 제어 메시지 구조체의 별도 필드이고 `netconfig`를 참조하지 않는다.
- 기준 장치에서는 `WIRE_ID`(139600)와 `nelite.db`의 stationid(139600)가 같다. 둘이 같아야 한다는 검증 코드는 없다.
- 웹 설정 화면(`wl.c:1258`)이 `WIRE_ID`를 읽어 보여준다.

---

## 6. 웹 설정 화면의 키

웹 CGI `cgi-bin/wl.c`(`wl.cgi`)는 설정 항목 14개를 다룬다(`wl.c:7-22`).

```
DEV_TYPE(1:GI-GW / 2:E3GW), WIRE_ID, WIRE_TYPE, HOST_NAME,
MIH_IP, MIH_GATEWAY, MIH_NETMASK, PRIVATE_IP, PRIVATE_GATEWAY, PRIVATE_NETMASK,
HOST_IP, ALARM_HOST_IP, E3GW_SUBNET, RECT_SUBNET
```

- `DEV_TYPE`, `E3GW_SUBNET`, `RECT_SUBNET`은 **DP가 읽지 않는다.** `get_network_config()`에 읽는 코드가 없거나 주석 처리되어 있다(`main_server.c:364-377`, `smm_new.c:240`). 기준 장치의 `nelite.conf`에도 이 키가 없다.
- `E3GW_SUBNET` 값에 따라 `ifconfig eth0:1`을 실행하던 코드는 주석 블록 안에 있어 실행되지 않는다(`main_server.c:392-400`).
- **웹 CGI는 DP와 다른 경로에 쓴다.** `wl.c`는 `NELITE_NET_CONF` = `/home/pi/e3gw/conf/nelite.conf`(`cgi-bin/common.h:141`)에 저장하고, DP는 `CONFIG_FILE_PATH` = `/opt/e3dp/conf/nelite.conf`(`include/nelite.h:77`)를 읽는다. 따라서 웹 화면의 저장 결과는 경로만 보면 DP에 반영되지 않는다.
- 웹 화면(`web/mainctl_info_wl.html`)에는 입력란이 13개이고 `WIRE_TYPE` 입력란은 없다. 저장(`mainctl_save`)은 `WIRE_TYPE`을 항상 `"1"`로 기록한다(`wl.c:1441`). `wl.c`가 파일에 쓰는 키는 14개이다.
- 웹 저장은 `nelite.conf`만 쓰고 `/etc/network/interfaces`·`/etc/hostname`은 바꾸지 않는다. 이 점이 `config` 유틸과 다르다.
- `wl.c`가 쓰는 파일의 머리글은 `N-ELITE E3-GW Standard Configuration File`(`wl.c:1434-1438`)이고, `config` 유틸이 쓰는 파일은 `N-ELITE E3-DP Standard Configuration File`(`config.c:161-167`)이다. 웹 코드(`cgi-bin`, `web`)의 경로도 `/home/pi/e3gw`라서 E3-GW 계열 코드로 보이나, 이는 이름에서 본 추정이다.
- **기준 장치(10.10.0.220, 설치 버전 03.01.14) 확인 결과, 웹 설정 화면은 배포되어 있지 않다.**
  - `/opt/e3dp` 설치 트리(`bin`, `conf`, `download`, `etc`, `log`, `periodic`)에 cgi·web 파일이 없다.
  - 웹 서버(lighttpd)가 기동되어 있지 않고 설정 포트(`web/lighttpd.conf`의 `server.port = 10080`)도 열려 있지 않다. lighttpd 패키지도 없다.
  - 문서 루트 `/home/pi/e3gw`가 없다.
  - 장치 안의 소스 사본(`/home/e3dp/e3dp.2.1/cgi-bin`)에도 `wl.c`가 없고, `web/`에는 `wl.cgi`가 없다.
  - 기준 장치는 현장과 거의 비슷한 환경이므로, 웹 설정 화면은 E3-DP에서 쓰이지 않는 것으로 본다. 현장 장치 자체는 확인하지 않았다.

---

## 7. 알아둘 점

- **`WIRE_TYPE`을 2로 바꾸는 것만으로는 자국 동작이 보장되지 않는다.** `nelite.db`의 Wire Info 값과 DB 다운로드(항상 1로 고정)가 `DrDB->type`을 덮어쓴다. 자국 장치가 실제로 어떤 경로로 type 2를 유지하는지는 이 소스만으로 확인되지 않았다.
- **type이 1·2가 아니면 분기마다 다르게 동작한다**(4.2절 요약). `config` 유틸은 1·2만 받지만 수동 편집에는 검증이 없다. `main_server.c:253`은 첫 글자에서 `0x30`을 빼서 저장하므로 `WIRE_TYPE = 12`는 1이 되고, 숫자가 아닌 문자는 의미 없는 값이 된다.
- **`wire_id`를 바꿔도 동작은 달라지지 않는다.** 기록과 진단 화면의 표시만 바뀐다.
- **기준 장치에서는 모든 값이 1·모국 기준이다.** 자국(2) 동작은 기준 장치로 대조하지 못했다. 시뮬레이터로 확인하려면 `WIRE_TYPE=2`와 `nelite.db` 값을 함께 조정해야 한다.
