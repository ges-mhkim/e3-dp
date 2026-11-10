# netconfig (NetworkConfigRec) 분석

> 대상: `e3dp.2.1` 소스. 경로는 `e3dp.2.1/` 기준이다.
> 목적: 공유메모리 `netconfig`의 **필드 구조, 값의 의미, 값을 쓰는 곳과 읽는 곳, 기동·통신 동작**을 트리로 정리한다.
> 확인 방법: 모든 항목은 소스 줄을 직접 읽어 확인했다. 크기·오프셋은 WSL gcc로 컴파일해 `offsetof`/`sizeof`를 출력한 값이다. "참조하는 곳 없음"은 `src`·`lib`·`include`를 grep한 결과이다. 기준 장치(10.10.0.220, 배포본 03.01.14)에서는 설정 파일, 공유메모리 내용, attach 수, 수신 포트를 읽기 전용으로 대조했다(7절). 현장 운영 장치는 확인하지 않았다.
> 이 문서는 단독으로 읽을 수 있게 작성했다.

---

## 1. 한눈에 보기

```
netconfig
├─ 정체       : 장비의 식별 정보와 IP 설정을 담은 공유메모리 (구조체 NetworkConfigRec)
├─ 키         : 0xE3000001 (SHM_NET_CONFIG_KEY, include/nelite.h:111)
├─ 크기       : 182 바이트 (모든 필드가 unsigned char 배열이라 패딩 없음)
├─ 원본       : /opt/e3dp/conf/nelite.conf (CONFIG_FILE_PATH, include/nelite.h:77)
├─ 쓰는 프로세스 : main_server 1개 (기동 시 1회, get_network_config())
└─ 읽는 프로세스 : db, config, control, gather, alarm, main(시각 동기화), emon
```

- 한 줄 요약: **main_server가 기동할 때 `nelite.conf`를 읽어 채우고, 나머지 서버는 이 값으로 통신 상대(Host)와 자기 주소(Self) IP를 정한다.**
- 구조체 정의: `include/nelite.h:162-186` (설명 주석 `:144-161`). 포인터 `netconfig` 선언: `include/nelite.h:188`.

### 1.1 설정을 바꾸면 어디에 적용되는가

| 변경 방법 | OS의 IP·hostname | DP (netconfig) |
|---|---|---|
| `nelite.conf`만 수정 | 적용 안 됨 | DP 재기동(또는 재부팅) 후 적용 |
| `config` 유틸로 수정 | `interfaces`, `hostname`을 함께 기록 → **재부팅 후 적용** | 재부팅 후 적용 |

- IP와 hostname을 장치에 적용하는 것은 OS이고, DP는 `nelite.conf`를 읽어 통신 주소를 만들 뿐이다.
- `nelite.conf`만 고치면 OS와 DP의 값이 어긋난다. 맞추려면 `config` 유틸을 쓴다(상세: 5.2~5.3절).

---

## 2. 필드 트리 (값의 의미 포함)

필드 앞의 `[오프셋/크기]`는 바이트 단위이다. `conf:`는 값을 읽어 오는 `nelite.conf` 키이다.

```
NetworkConfigRec (182 B)
│
├─ [  0/ 7] wire_id            장비(국) 식별번호. 문자열
│   │   conf: WIRE_ID
│   └─ 값 예: "139600" (6자리 + NUL = 7바이트. 기준 장치 설정 파일 값)
│
├─ [  7/ 1] wire_type          통신처리부 구분. 숫자 1바이트 (문자가 아니라 숫자로 저장)
│   │   conf: WIRE_TYPE        저장: netconfig->wire_type = arg[0] - 0x30  (main_server.c:253)
│   ├─ 1 : DR_LOCAL_TYPE   → 모국 통신처리부        (include/drcommon.h:150)
│   ├─ 2 : DR_REMOTE_TYPE  → 자국 통신처리부        (include/drcommon.h:151)
│   └─ 그 외 : 검증 코드 없음 (6.2절 참고)
│        (참고: DR_COMM_TYPE = 3 "모국 통신부"가 정의되어 있으나 netconfig에는 쓰이지 않음)
│
├─ [  8/30] hostname           장비 호스트 이름. 문자열
│   │   conf: HOST_NAME
│   └─ 값 예: "E3-DP"
│
├─ [ 38/16] mih_ip             MIH 네트워크 쪽 **자기 장치 IP**
│   │   conf: MIH_IP
│   ├─ 통신 시 자기 주소(Self_IP)로 사용  → 4.2절
│   └─ main이 4개 숫자로 분해해 DrDB->self_ip[4]에도 저장 (main_server.c:388)
│
├─ [ 54/16] mih_netmask        MIH 서브넷 마스크.  conf: MIH_NETMASK
│   └─ 읽어서 저장만 함. 참조하는 곳 없음
│
├─ [ 70/16] mih_gateway        MIH 게이트웨이.     conf: MIH_GATEWAY
│   └─ 읽어서 저장만 함. 참조하는 곳 없음
│
├─ [ 86/16] private_ip         사설 네트워크 쪽 자기 장치 IP.  conf: PRIVATE_IP
│   ├─ emon이 화면에 출력만 함 (emon.c:309)
│   └─ eth0:1 별칭 설정에 쓰려던 코드는 주석 처리됨 (main_server.c:392-400)
│
├─ [102/16] private_netmask    사설 서브넷 마스크.  conf: PRIVATE_NETMASK
│   └─ 위 주석 처리된 코드에서만 쓰였음. 현재 참조 없음
│
├─ [118/16] private_gateway    사설 게이트웨이.     conf: PRIVATE_GATEWAY
│   └─ 읽어서 저장만 함. 참조하는 곳 없음
│
├─ [134/16] host_ip            **Host(통신 상대) IP**
│   │   conf: HOST_IP
│   ├─ 통신 시 상대 주소(Host_IP)로 사용  → 4.2절
│   └─ main이 4개 숫자로 분해해 DrDB->host_ip[4]에도 저장 (main_server.c:389)
│
├─ [150/16] alarm_host_ip      **알람을 보낼 상대 IP**
│   │   conf: ALARM_HOST_IP
│   └─ alarm_server만 사용 (alarm_sender.c:50, alarm_handler.c:321)
│
├─ [166/ 8] e3gw_subnet        값을 채우는 코드 없음 → 사실상 미사용
│   └─ 참조: emon 출력(emon.c:312), 주석 처리된 블록(main_server.c:393)뿐
│
└─ [174/ 8] rect_subnet        읽어 오는 코드(RECT_SUBNET)가 주석 처리됨 → 사실상 미사용
    └─ 참조: emon 출력(emon.c:313)뿐
```

### 2.1 필드 사용 요약표

| 필드 | conf 키 | 쓰는 곳 | 읽는 곳 | 상태 |
|---|---|---|---|---|
| `wire_id` | WIRE_ID | main_server.c:239-240 | emon 출력 | 서버 로직에서는 미사용 |
| `wire_type` | WIRE_TYPE | main_server.c:253 | main_server.c:381(DrDB로 복사), emon 출력 | 4.3절 참고 |
| `hostname` | HOST_NAME | main_server.c:264-265 | emon 출력 | 서버 로직에서는 미사용 |
| `mih_ip` | MIH_IP | main_server.c:276-277 | 서버 6종 + main 시각 동기화 | **핵심** |
| `mih_netmask` | MIH_NETMASK | main_server.c:298-299 | 없음 | 저장만 (파일 값은 OS 설정에 사용, 5.2절) |
| `mih_gateway` | MIH_GATEWAY | main_server.c:288-289 | 없음 | 저장만 (파일 값은 OS 설정에 사용, 5.2절) |
| `private_ip` | PRIVATE_IP | main_server.c:308-309 | emon 출력 | 출력만 (파일 값은 OS 설정에 사용) |
| `private_netmask` | PRIVATE_NETMASK | main_server.c:332-333 | 없음(주석 처리된 코드만) | 저장만 (파일 값은 OS 설정에 사용) |
| `private_gateway` | PRIVATE_GATEWAY | main_server.c:320-321 | 없음 | 저장만 (파일 값은 OS 설정에 사용) |
| `host_ip` | HOST_IP | main_server.c:344-345 | 서버 5종 + main 시각 동기화 | **핵심** |
| `alarm_host_ip` | ALARM_HOST_IP | main_server.c:357-358 | alarm_server | **핵심(알람 전용)** |
| `e3gw_subnet` | — | 없음 | emon 출력 | 미사용 |
| `rect_subnet` | — | 없음(주석 처리) | emon 출력 | 미사용 |

---

## 3. 프로세스 트리

### 3.1 netconfig에 붙는(attach) 프로세스

공통 attach 함수는 `CreateSharedMemory(SHM_NET_CONFIG_KEY, sizeof(NetworkConfigRec))`이다.

```
attach 하는 프로세스 (실행 파일)
├─ init_shm.c 에서 attach  (각 서버 시작 시 init_shm("이름") 호출)
│   ├─ main_server     src/main/init_shm.c:20
│   ├─ db_server       src/db/init_shm.c:16
│   ├─ control_server  src/control/init_shm.c:16
│   ├─ alarm_server    src/alarm/init_shm.c:22
│   ├─ emon            src/emon/init_shm.c:18
│   ├─ gw_server       src/gw/init_shm.c:16
│   ├─ modbus_server   src/modbus/init_shm.c:16
│   ├─ netcheck_server src/netcheck/init_shm.c:14
│   ├─ rect_server     src/rect/init_shm.c:16
│   ├─ rt_server       src/rt/init_shm.c:14
│   └─ scan_server     src/scan/init_shm.c:25
└─ 서버 본문에서 직접 attach
    ├─ config_server   src/config/config_server.c:76
    ├─ gather_server   src/gather/gather_server.c:144   (attach 전에 sleep(1), :135)
    └─ acon_agent      src/acon_agent/acon_server.c:75

attach 하지 않음: realdata_server (netconfig 참조 없음)
```

- **attach만 하고 필드를 읽지 않는 프로세스**: gw, modbus, netcheck, rect, rt, scan, acon_agent. `netconfig->`로 필드에 접근하는 코드가 없다.
- **필드를 실제로 읽는 프로세스**: main(쓰기 포함), db, config, control, gather, alarm, emon. 아래 3.2절.

### 3.2 필드를 사용하는 프로세스·함수·위치

```
main_server
├─ main()                         main_server.c:41
│   ├─ init_shm("MAIN")           :73   → netconfig attach
│   ├─ Dr_Delay(10)               :75
│   ├─ get_network_config()       :77   → ★ netconfig를 채우는 유일한 함수 (정의 :215-403)
│   └─ Clock_sync()               :93 / :96   → 시각 동기화 (main_tsync.c)
│       └─ Clock_sync()           main_tsync.c:49
│           ├─ Host_IP ← host_ip  :65
│           ├─ Self_IP ← mih_ip   :66
│           └─ Dr__tsync_request() (:257) 안에서 Host_IP로 시각 요청 전송 (sendto, :293-311)
│              (Clock_sync는 main_dispatch.c:148에서도 호출됨: 요청 서비스가
│               EVR_DB_SYSTEM_UPDATE일 때. 호출될 때마다 host_ip/mih_ip를 다시 복사함)
│
db_server
└─ DrDbm__wire_address_set()      ldb_server.c:401   (호출 :142)
    ├─ Host_IP ← host_ip          :413   → wire_remote(상대) 주소로 사용 (:428)
    └─ Self_IP ← mih_ip           :414   → self_addr(자기) 주소로 사용 (:422)

config_server
└─ DrScan__wire_address_set()     config_server.c:227  (호출 :112)
    ├─ Host_IP ← host_ip          :241   → wire_remote 주소 (:253)
    └─ Self_IP ← mih_ip           :242   → self_addr 주소 (:247)

control_server
└─ DrCt__wire_address_set()       control_init.c:140   (호출 control_server.c:138)
    ├─ cip, rip ← host_ip         :158, :159   → wire_center, wire_remote 주소
    └─ sip ← mih_ip               :160         → self_addr 주소

gather_server
└─ DrPeriod__comm_init()          gather_server.c:338  (호출 :157)
    ├─ Host_IP ← host_ip          :348   → remote_addr (:419)
    └─ Self_IP ← mih_ip           :349   → self_addr (:430)

alarm_server
├─ DrAlarmSender__comm_init()     alarm_sender.c:35    (호출 alarm_server.c:122)
│   ├─ Host_IP ← alarm_host_ip    :50    → tm_addr (알람 수신 측) 주소 (:121)
│   └─ Self_IP ← mih_ip           :51    → self_addr (:129)
└─ AlarmSendTimeOutCheck()        alarm_handler.c:304  (호출 alarm_server.c:203)
    └─ 알람 응답 시간 초과 시 alarm_host_ip를 로그로 출력 (:320-321)

emon (진단 도구)
└─ list_shm()                     emon.c:298
    └─ wire_id, wire_type, hostname, mih_ip, private_ip, host_ip,
       alarm_host_ip, e3gw_subnet, rect_subnet 을 화면에 출력 (:305-313)
       (mih_netmask, mih_gateway, private_netmask, private_gateway는 출력하지 않음)
```

---

## 4. 동작 설명

### 4.1 기동 시 값이 채워지는 순서

```
main_server 기동
├─ (1) init_shm("MAIN")
│       └─ CreateSharedMemory(0xE3000001, 182)  → shmget(IPC_CREAT|0666) + shmat   (e3lib.c:350-)
│          (먼저 붙는 프로세스가 세그먼트를 만든다. 새로 만든 SysV 세그먼트는 0으로 채워져 있다)
├─ (2) Dr_Delay(10)
├─ (3) get_network_config()
│       ├─ 항목별로 반복:  memset(arg) → get_arg1(nelite.conf, 키, arg) → netconfig 필드에 한 글자씩 복사
│       │     WIRE_ID → WIRE_TYPE → HOST_NAME → MIH_IP → MIH_GATEWAY → MIH_NETMASK
│       │     → PRIVATE_IP → PRIVATE_GATEWAY → PRIVATE_NETMASK → HOST_IP → ALARM_HOST_IP
│       │     (RECT_SUBNET은 주석 처리, E3GW 서브넷은 읽는 코드 자체가 없음)
│       └─ 후처리 (:381-390)
│            ├─ DrDB->type = netconfig->wire_type
│            └─ DrDB->self_ip[0..3] = ip_token(mih_ip, 1..4)
│               DrDB->host_ip[0..3] = ip_token(host_ip, 1..4)
└─ (4) Clock_sync()  → 채워진 host_ip/mih_ip로 Host에 시각 요청
```

### 4.2 Host_IP / Self_IP 사용 패턴

각 서버는 같은 패턴으로 netconfig를 읽는다. 지역 변수 `Host_IP[16]`, `Self_IP[16]`에 문자열을 복사한 뒤 `inet_addr()`로 소켓 주소를 만든다.

```
통신 주소 구성
├─ Self_IP = netconfig->mih_ip        → 자기 쪽 소켓 주소 (self_addr)
├─ Host_IP = netconfig->host_ip       → 상대 쪽 소켓 주소 (wire_remote / remote_addr / wire_center)
│    └─ 사용 서버: db, config, control, gather, main(시각 동기화)
└─ Host_IP = netconfig->alarm_host_ip → 알람 상대 주소 (tm_addr)
     └─ 사용 서버: alarm
```

- 상대 주소의 포트는 서버마다 코드 상수로 정한다(예: `EC_REQUEST_UPORT`, `DR_UDP_PORT_PERIOD`, `EC_ALARM_FRONT_PORT`). netconfig에는 포트가 없다.
- 주의: db, config, control이 만든 주소 구조체는 이후 참조되지 않는다(6.8절). 실제로 쓰이는 것은 gather와 alarm의 주소, main의 시각 동기화 주소이다.
- db, config, control, gather, alarm의 주소 구성은 **서버 기동 직후 1회** 실행되는 초기화 함수 안에 있다. 이후 `netconfig`가 바뀌어도 이미 만들어진 소켓 주소에는 반영되지 않는다.
- 예외는 main의 `Clock_sync()`이다. 시각 동기화를 요청할 때마다 `netconfig`에서 다시 복사한다(4.1절 (4), 3.2절 main 항목).

### 4.3 wire_type 값에 따른 동작

> 이 절은 일부 위치만 정리한 것이다. 활성 비교 34곳 전체(scan, gather, control 포함)와 값이 덮어써지는 순서는 `netconfig_네트워크외_분석.md` 4절에 있다.

`wire_type`은 main이 `DrDB->type`으로 복사하고(`main_server.c:381`), 서버 로직은 `netconfig->wire_type`이 아니라 **`DrDB->type`** 을 본다.

```
netconfig->wire_type
└─ DrDB->type 으로 복사 (main_server.c:381)
    ├─ 1 : LOCAL(모국)
    │    ├─ alarm_check.c:629   정전/입전 상태 확인 루프 실행 (LOCAL일 때만)
    │    ├─ alarm_check.c:380, 414, 446   LOCAL 조건 분기
    │    ├─ control_pg_process.c:256, 296, 323   LOCAL 조건 분기 (포트 상태 확인 등)
    │    └─ alarm_server.c:100   기동 로그에 "LOCAL" 표시
    └─ 2 : REMOTE(자국)
         ├─ alarm_check.c:364   함수 시작에서 REMOTE면 즉시 반환 ("자국은 임시로 제외한다" 주석)
         ├─ alarm_check.c:651   REMOTE 분기
         ├─ control_pg_process.c:51   REMOTE이면서 지정 포트가 없을 때 gen_mode = 0x01
         └─ alarm_server.c:100   기동 로그에 "REMOTE" 표시
```

**중요: `DrDB->type`은 이후 덮어써진다.** wire_type의 영향은 main 기동 직후에만 유효하다.

```
DrDB->type 이 바뀌는 지점
├─ main_server.c:381     netconfig->wire_type 값으로 설정 (기동 시)
├─ ldb_server.c:494      restore_db(): nelite.db "* Wire Info" 줄의 두 번째 값으로 설정
└─ ldb_decode.c:196      DrDbmModulePduDecode()(DB 다운로드 PDU 해석)에서 DR_LOCAL_TYPE(1)로 **고정**
                         (바로 위 :192에서 받은 값을 곧바로 덮어씀. 주석: "2016.4.29 Type은 Local로 고정")
```

- 따라서 DB 다운로드가 한 번이라도 일어나면 `DrDB->type`은 `nelite.conf`의 WIRE_TYPE과 무관하게 1이 된다.
- `main_tsync.c:303`의 `DrDB->type == DR_REMOTE_TYPE` 분기는 주석 블록 안에 있어 실행되지 않는다.

---

## 5. 소스 설명 (netconfig를 만드는 함수)

```
관련 함수
├─ get_network_config()    main_server.c:215-403
│   ├─ 입력: 파일 /opt/e3dp/conf/nelite.conf
│   ├─ 출력: netconfig 전 필드(미사용 2개 제외) + DrDB->type/self_ip/host_ip
│   └─ 특징: 항목당 "memset → get_arg1 → for 루프 복사" 반복. 키가 없어도 종료하지 않음 (6.1절)
│
├─ get_arg1(path, key, result)    lib/e3/e3lib.c:154-210
│   ├─ 파일을 열어 존재만 확인하고 닫음 (없으면 0 반환)
│   ├─ 셸 명령 실행:  grep <키> <파일> | grep -v '^#' | tr -d '"'      (popen, :169-176)
│   ├─ 출력의 **첫 줄만** 읽고 (fgets), '=' 뒤쪽에서 공백 이하 문자를 제거해 값을 만듦 (:183-200)
│   ├─ memcpy로 result에 복사 (NUL은 호출 측이 미리 memset 한 0에 의존, :205)
│   └─ 반환: 성공 1 / 파일 없음·값 없음 0
│
├─ ip_token(addr, pos)    lib/e3/e3lib.c:306-329
│   ├─ "a.b.c.d"에서 pos(1~4)번째 숫자를 반환
│   ├─ 셸 명령 실행:  echo <addr> | awk -F. '{ print $<pos> }'   (popen, :317-323)
│   └─ 문자열 길이 7 미만이거나 pos > 4면 0xFF 반환
│
└─ CreateSharedMemory(key, size)    lib/e3/e3lib.c:350-
    ├─ shmget(key, size, IPC_CREAT | 0666) → shmat
    └─ 실패 시 메시지를 출력하고 NULL 반환 (호출 측은 NULL을 검사하지 않음)
```

### 5.1 nelite.conf 파일 형식과 쓰는 쪽

```
/opt/e3dp/conf/nelite.conf
├─ 형식    : "키 = 값" 한 줄에 하나. '#'로 시작하는 줄은 주석 (기준 장치 샘플: tests/fixtures/ref_220/nelite.conf)
├─ 읽는 쪽 : main_server get_network_config(), util/station.c:47, util/config.c:60
└─ 쓰는 쪽 : util/config.c write_configuration_file() (:144, 파일을 "w"로 열어 새로 씀)
              └─ 항목 순서: WIRE_ID, WIRE_TYPE, HOST_NAME, MIH_IP, MIH_GATEWAY, MIH_NETMASK,
                            PRIVATE_IP, PRIVATE_GATEWAY, PRIVATE_NETMASK, HOST_IP, ALARM_HOST_IP  (config.c:28-30)
```

- netconfig는 **공유메모리 값이 바뀌어도 파일에 반영되지 않는다.** 방향은 파일 → 공유메모리 한쪽뿐이다.
- 파일을 고쳐도 공유메모리는 main_server가 다시 기동하기 전까지 갱신되지 않는다(`get_network_config()` 호출 지점은 `main_server.c:77` 하나).

### 5.2 nelite.conf의 IP 설정은 실제 장치에 어떻게 적용되는가

`nelite.conf`에는 두 가지 소비 경로가 있다. **DP 프로세스는 IP를 직접 설정하지 않는다.** 장치의 실제 IP는 OS가 `/etc/network/interfaces`를 읽어 적용한다.

```
nelite.conf (/opt/e3dp/conf)
├─ (A) 읽기 : DP 앱 내부용  — main_server가 부팅 시 netconfig로 로드 (5절)
│     └─ DP가 통신 주소를 구성하는 데만 쓴다. OS의 IP는 바꾸지 않는다.
│
└─ (B) 쓰기 : config 유틸 (src/util/config.c, 실행 파일 /opt/e3dp/bin/config)  — 사람이 수동 실행
      ├─ 대화형으로 11개 항목을 입력받는다 (입력 검증: 숫자/IP 형식 등, is_ip() :221)
      ├─ 확인(Yes) 후 순서대로 실행 (:125-140)
      │    ├─ ① system("bin/rm -f /opt/e3dp/conf/nelite.db")   ← 로컬 DB 삭제 의도. 상대 경로 "bin/rm"이라
      │    │      현재 디렉터리가 "/"일 때만 /bin/rm이 실행됨 (아래 "실행 위치 주의" 참고)
      │    ├─ ② system("bin/rm -f .../nelite.conf") → write_configuration_file() (:144)
      │    │    ├─ nelite.conf 새로 씀                       (:151-172)
      │    │    ├─ /etc/network/interfaces 새로 씀           (:177-199)
      │    │    │    ├─ eth0 static : address=MIH_IP, gateway=MIH_GATEWAY, netmask=MIH_NETMASK
      │    │    │    └─ eth1 static : address=PRIVATE_IP, gateway=PRIVATE_GATEWAY, netmask=PRIVATE_NETMASK
      │    │    └─ /etc/hostname 새로 씀 (HOST_NAME)         (:204-212)
      │    └─ ③ 재부팅 여부를 묻고 Yes면 sync 후 shutdown -r now (:131-140)
      └─ 즉시 적용하지 않는다. ifconfig/ifup 호출이 없고, 재부팅 후 OS가 interfaces를 적용한다.

wl.c (웹 CGI)  — nelite.conf를 읽고 쓰는 코드가 있으나 경로가 /home/pi/e3gw/conf/nelite.conf (cgi-bin/common.h:141)
      └─ DP의 /opt/e3dp/conf/nelite.conf와 다른 경로이고, interfaces를 쓰는 코드는 없다. 기준 장치에서 lighttpd/CGI 프로세스는 실행 중이 아니다.
```

**netconfig 필드와 OS 설정의 대응**

| nelite.conf 키 | DP 프로세스(netconfig) | OS 설정(config 유틸이 기록) |
|---|---|---|
| MIH_IP / MIH_GATEWAY / MIH_NETMASK | `mih_ip`만 사용 | eth0 address / gateway / netmask |
| PRIVATE_IP / PRIVATE_GATEWAY / PRIVATE_NETMASK | 참조 없음(`private_ip`는 emon 출력만) | eth1 address / gateway / netmask |
| HOST_NAME | emon 출력만 | `/etc/hostname` |
| HOST_IP / ALARM_HOST_IP | 사용 | 없음 (DP 전용) |
| WIRE_ID / WIRE_TYPE | `wire_type`만 사용 | 없음 (DP 전용) |

- 따라서 `mih_netmask`, `mih_gateway`, `private_*`가 **DP 프로세스에서는 참조되지 않아도 설정 값으로서는 의미가 있다.** 이 값들은 OS 네트워크 설정을 만드는 입력이다. 7절 정리의 "저장만 하고 참조 없음 4개"는 "공유메모리 기준"이라는 뜻이다.
- `util/config.c:83-85` 주석에는 "E3-GW Subnet, Rectifier Subnet"(값 1 또는 2 검증)이 있다. 그러나 항목 배열은 11개이고(`MAX_ITEM`, :17) 루프가 `i < 11`이라 `case 11, 12`에는 도달하지 못한다. `rect_subnet`의 RECT는 Rectifier(정류기)로 읽는 것이 맞다.
- `station` 유틸(`util/station.c:47`)은 `nelite.conf`를 읽어 화면에 보여주기만 한다.

**기준 장치(10.10.0.220)에서 확인한 결과 (읽기 전용)**

```
기준 장치 대조
├─ /etc/network/interfaces : eth0 10.10.0.220 / gw 10.10.0.1 / 255.255.255.0
│                            eth1 192.168.123.2 / gw 192.168.123.1 / 255.255.255.0   → nelite.conf와 값 일치
├─ /etc/hostname           : E3-DP                                                    → HOST_NAME과 일치
├─ ip addr                 : eth0 10.10.0.220/24, eth1 192.168.123.2/24               → 실제 적용값이 위와 일치
├─ ip route                : default via 10.10.0.1 dev eth0 (1개). eth1의 gateway 192.168.123.1은 기본 경로로 반영되지 않음
├─ 파일 시각               : interfaces, hostname = 2026-01-08 12:39 (nelite.conf 머리말 "Created at 2026.01.08"과 같은 날)
│                            → config 유틸이 같은 시점에 만들었다는 정황. 직접 증거는 아님
└─ 기동                    : /etc/rc2.d/S05e3dp → init.d/e3dp → smm.  IP 설정 코드는 없음 (OS 네트워크는 별도로 기동)
```

**주의**
- 설정이 **두 곳(nelite.conf와 interfaces/hostname)에 따로 저장**되고 자동 동기화되지 않는다. `config` 유틸을 거치지 않고 한쪽만 고치면 DP가 쓰는 IP(netconfig)와 OS의 실제 IP가 어긋날 수 있다.
- `config` 유틸은 `nelite.db` 삭제를 시도한다(`config.c:125`). 상대 경로 `bin/rm`이라 **현재 디렉터리가 `/`일 때만** 실제로 삭제된다. 기준 장치에서 root의 로그인 디렉터리는 `/root`이고 `/root/bin/rm`, `/opt/e3dp/bin/bin/rm`은 없으므로, 그 위치에서 실행하면 삭제는 실패하고 오류도 표시되지 않는다(반환값을 확인하지 않음). `nelite.conf`는 삭제가 실패해도 이어서 `fopen("w")`로 덮어쓴다. 삭제되면 DB를 다시 내려받아야 하고, 삭제되지 않으면 기존 `nelite.db`가 남는다.

### 5.3 수동 변경 절차 (config 유틸을 쓰는 방법)

`config`는 `/opt/e3dp/bin`이 PATH에 있어 아무 위치에서나 실행되는 대화형 명령이다(기준 장치에서 `type config` 확인). root 권한이 필요하다(`/etc` 파일을 쓴다).

```
config 실행 (인자 없음)
├─ 항목마다 현재 값을 보여주며 입력을 받음   "* MIH IP : [10.10.0.220]"   (config.c:56-108)
│    ├─ 현재 값 = nelite.conf에서 읽은 값 (get_arg1, :60). 파일에 키가 없으면 소스에 박힌 기본값
│    ├─ 그냥 Enter → 현재 값 유지,  새 값 입력 → 형식 검증 후 교체 (검증 실패 시 다시 입력)
│    └─ 검증 : WIRE_ID 숫자>0 / WIRE_TYPE 1 또는 2 / IP·마스크 형식(is_ip) / HOST_NAME 무조건 통과
├─ 전체 값을 출력하고  "Are You Sure ? (Yes/No) : [N]"   (N이면 아무것도 쓰지 않고 종료, :116-123)
├─ Y → nelite.db 삭제 시도 → nelite.conf, /etc/network/interfaces, /etc/hostname 기록      (:125-128)
└─ "Reboot Now ? (Yes/No) : [N]"   Y → sync 후 shutdown -r now,  N → 파일만 바뀐 채 종료    (:131-140)

config init
└─ 입력 단계를 건너뛰고 **소스에 박힌 기본값**(WIRE_ID 100100, MIH_IP 10.0.10.10, HOST_IP 10.240.34.103 …,
   config.c:32-34)으로 확인 후 그대로 기록한다. 현재 nelite.conf 값은 읽지 않는다.
```

**"적용된다"의 기준**
```
시점별 상태
├─ config 종료 직후 (재부팅 N)  : 파일 3개만 바뀜.  실행 중인 OS의 IP, DP의 netconfig는 그대로
├─ 재부팅 후                    : OS가 새 interfaces로 IP 설정 + main_server가 새 nelite.conf를 netconfig로 로드 → 적용 완료
└─ (참고) 재부팅 없이 적용하려면 : OS 네트워크 재시작 + DP(smm) 재기동이 각각 필요하다. config 유틸은 이를 하지 않는다.
```

**손으로 직접 편집하는 경우**
| 방법 | 결과 |
|---|---|
| `vi`로 `nelite.conf`만 수정 후 DP 재기동 | DP의 netconfig만 바뀜. **OS의 IP·hostname은 그대로**(interfaces는 안 바뀜) |
| `vi`로 `nelite.conf` 수정 → `config` 실행, 전 항목 Enter | 수정한 값이 기본값으로 표시되므로 그대로 유지되며 **interfaces와 hostname이 같은 값으로 다시 생성**됨. 두 곳을 맞추는 방법 |
| `vi`로 `interfaces`만 수정 후 재부팅 | OS의 IP만 바뀜. **DP의 netconfig(mih_ip 등)는 그대로** → 둘이 어긋남 |
- 신 환경(Debian)에서 `/etc/network/interfaces` 방식이 실제 IP를 적용하는지는 확인하지 않았다(OS 네트워크 관리자가 다르면 `config` 유틸의 결과가 반영되지 않을 수 있다).

### 5.4 서버(호스트)에서 IP·네트워크 설정이 내려오는가

**없다.** 소스 전체(`src`, `lib`, `cgi-bin`)에서 확인한 결과이다.

```
설정이 바뀌는 경로 (전부)
├─ netconfig(공유메모리)를 쓰는 코드     : get_network_config() 하나 (main_server.c:215). 호스트 메시지로는 바뀌지 않음
├─ nelite.conf / interfaces / hostname 을 쓰는 코드 : config 유틸 하나 (util/config.c). 수동 실행
└─ 호스트가 DP로 내려보내는 서비스 (config_server 등)
    ├─ config_handler.c:185-210  실시간 설정/해제(EC_SVC_REALTIME_SET/RESET), 상·하한(EC_SVC_UPDATE_LIMIT),
    │                           경보 마스크(EC_SVC_ALARM_MASK), kWh 초기값, DC 전압/전류, 방전 설정, 온도 메뉴,
    │                           AO 값, 제어 모드/스크립트 실행(EVR_CTRL_*)
    ├─ DB 다운로드 (db_server)   장비 구성: stationid, type, usedcomps, total_ports, total_points, periodinterval
    │                           (ldb_decode.c:189-199). IP는 포함되지 않음
    └─ 시각 동기화 (main_tsync)   Host_IP의 TSYNC_SERVICE_PORT(37)로 시각 요청 → 시스템 시각만 갱신
```

- 서버 프로세스(main, db, config, control, scan, gather, rt, alarm, realdata, acon_agent)의 `system()`/`popen()`/`exec` 호출을 grep한 결과, 네트워크 설정을 바꾸는 명령은 `main_server.c:398`의 `system(ifconfig eth0:1 ...)` 하나이고, 이것도 주석 블록 안이라 실행되지 않는다. (`lib`의 `get_arg1`/`ip_token`은 값을 읽기 위해 grep/awk를 `popen`으로 실행할 뿐이다.)
- `config` 유틸은 **netconfig(공유메모리)를 읽지 않는다.** 공유메모리를 attach하는 코드가 없고, 입력은 키보드와 `nelite.conf` 파일(`get_arg1`)이다. 따라서 "netconfig를 읽어 OS에 쓴다"가 아니라 아래와 같다.

```
데이터 흐름 (단방향)
nelite.conf ──(부팅, main_server)──▶ netconfig ──▶ DP 서버들(통신 주소)
    ▲
    └──(수동, config 유틸: 키보드 입력 + 기존 파일 값)──▶ nelite.conf + interfaces + hostname ──(재부팅)──▶ OS가 IP 적용
```

- 장치 식별도 같다. 국 번호는 `netconfig->wire_id`가 아니라 **서버가 내려준 DB의 `DrDB->stationid`** 를 쓴다(`ldb_decode.c:189-190`, `control_auto.c:1051`). `wire_id`로 stationid를 만드는 코드는 `main_server.c:383-385`에서 주석 처리됐다("2018.07.02 DSK Deleted").

**netconfig를 거치지 않는 Host IP 경로가 하나 남아 있다 (소스 확인, 장치 실행 여부는 미확인)**

```
control_server
└─ control_auto.c:1060  dr_control_udp_handler(7111, 메시지)   ← 자동 메시지 전송 (DrDB->type == LOCAL일 때)
    └─ control_client.c:27  DrGetHostIP(Host_IP)               ← netconfig가 아니라 별도 함수
        └─ lib/com/ipaddr.c:19, 42  get_arg1("/opt/conf/nelite.config", "HOST_IP", host)
            ├─ 파일 이름·경로가 다르다 (/opt/conf/nelite.config ≠ /opt/e3dp/conf/nelite.conf)
            ├─ 기준 장치에는 /opt/conf 디렉터리가 없다 → get_arg1이 0 반환, host는 빈 문자열
            └─ DrGetHostIP는 DrDB->host_ip[0..3]도 다시 채운다 (ipaddr.c:44-53)
```

- 이 경로가 실제로 실행되면 빈 주소로 `sendto`가 호출되고, main이 채운 `DrDB->host_ip`가 덮어써질 수 있다. 실행 조건(`control_auto.c`의 자동 메시지 발생)이 기준 장치에서 일어나는지는 확인하지 않았다.
- 다른 서버는 같은 호출(`DrGetHostIP`)을 주석 처리하고 `netconfig->host_ip`로 바꿨는데(예: `gather_server.c:346-349`), `control_client.c`만 바뀌지 않은 채 남아 있다.

---

## 6. 주의·발견 사항 (소스로 확인된 것)

### 6.1 키가 없어도 기동이 멈추지 않는다

`get_network_config()`는 `arg`를 `char arg[50]` 배열로 선언하고 `if (arg == (char *)NULL)`로 실패를 검사한다(`main_server.c:219, 232`). 배열의 주소는 NULL이 될 수 없어 **이 검사는 항상 거짓**이고, 실패 시 `exit(1)`하는 경로는 실행되지 않는다. 키가 없으면 `get_arg1`이 0을 반환하고 `arg`는 빈 문자열이므로 해당 필드가 빈 문자열로 남는다.

```
키 누락 시 결과
├─ 문자열 필드 : 빈 문자열 (IP가 비면 inet_addr("") = 실패값, 통신 주소가 잘못 구성됨)
└─ wire_type   : arg[0]=0 → 0 - 0x30 = -48 → unsigned char 로 208 저장
```

### 6.2 wire_type은 값 범위를 검사하지 않는다

`'1'`, `'2'` 외 문자가 와도 `arg[0] - 0x30`을 그대로 저장한다. 예: `'3'` → 3, `'a'` → 49. 서버 로직의 분기는 1(LOCAL)과 2(REMOTE)만 비교한다.

### 6.3 길이 검사가 없다

값은 `arg[50]`에 담긴 뒤 `for(i < strlen(arg))`로 필드에 복사된다. 필드 크기보다 긴 값이 오면 다음 필드를 덮어쓴다.

```
필드 크기와 안전한 최대 문자 수 (NUL 1바이트 제외)
├─ wire_id    7  → 6자
├─ hostname  30  → 29자
└─ IP 계열   16  → 15자 ("255.255.255.255")
```

### 6.4 `HOST_IP` 키는 `ALARM_HOST_IP` 줄과도 일치한다

`get_arg1`은 `grep <키>`로 **부분 문자열 일치**를 쓰고 첫 줄만 읽는다. `HOST_IP`로 검색하면 `ALARM_HOST_IP = ...` 줄도 걸린다.

- `nelite.conf`에서 `HOST_IP` 줄이 `ALARM_HOST_IP` 줄보다 **앞에 있으면 정상**이다. 기준 장치 샘플과 `util/config.c`가 쓰는 항목 순서(`config.c:28-30`)가 모두 이 순서이다.
- 순서가 뒤바뀌면 `host_ip`에 알람 호스트 주소가 들어간다.
- 같은 이유로 `grep HOST_NAME`, `grep MIH_IP` 등은 다른 키와 겹치지 않는다(키 이름 확인 결과).

### 6.5 셸 호출로 값을 처리한다

`get_arg1`과 `ip_token`은 `popen()`으로 셸(grep, tr, echo, awk)을 실행한다. `ip_token`은 `echo <addr>`에 문자열을 그대로 붙여 넣으므로, 파일 값에 셸 특수문자가 있으면 그대로 해석된다. 기동 시 필드당 1회 실행되는 초기화 경로이며 운영 중 반복 호출되지는 않는다.

### 6.6 문서 간 줄 번호 불일치

기존 `공유메모리구조.md`와 `메모리_파일_소스연계.md`의 일부 줄 번호는 현재 소스와 다르다.

| 문서 | 문서의 기재 | 현재 소스 |
|---|---|---|
| 공유메모리구조.md (type 설명) | `main_server.c:523` | `main_server.c:381` |
| 공유메모리구조.md (self_ip/host_ip) | `main_server.c:530-531` | `main_server.c:388-389` |
| 메모리_파일_소스연계.md (netconfig 행) | `main/init_shm.c:12`, `main_server.c:228-354` | `main/init_shm.c:20`, `main_server.c:215-403` |
| 메모리_파일_소스연계.md | `nelite.conf` = `nelite.h:74` | `nelite.h:77` |

이 문서의 줄 번호는 현재 소스 기준이다. 기존 두 문서의 보정은 별도 작업으로 남긴다.

### 6.7 기동 순서: main이 채우기 전에 읽는 경합이 있는가

서버 기동은 `smm`이 맡는다. `smm`은 `main_server`를 가장 먼저 실행하고, 이어서 db, config, scan, gather, rt, alarm, control 등을 차례로 실행한다. 서버 사이 간격은 `usleep(10000)`(10ms)이다(`smm_new.c:267-278`, 실행 함수 `:204-206`).

```
기동 직후 타임라인 (smm_new.c)
├─ main_server   : init_shm → Dr_Delay(10) = 10ms (Dr_Delay의 단위는 ms, lib/com/conv.c:42)
│                  → get_network_config() → netconfig 채움
│                  (항목마다 popen 셸 실행: get_arg1 11회 + ip_token 8회)
└─ netconfig를 읽는 서버는 모두 읽기 전에 sleep(1)을 둔다
    ├─ db_server      init_shm 후 sleep(1) (ldb_server.c:67-69)  → 주소 구성 :142
    ├─ config_server  sleep(1) :69, attach :76, sleep(1) :78     → 주소 구성 :112
    ├─ control_server sleep(1) :84, init_shm :86, sleep(1) :104  → 주소 구성 :138
    ├─ alarm_server   sleep(1) :49, init_shm :72                 → 주소 구성 :122
    └─ gather_server  sleep(1) :135, attach :144                 → 주소 구성 :157
```

- 결론: 읽는 쪽이 모두 **최소 1초** 기다린 뒤 읽는다. main이 채우는 데 필요한 시간(셸 19회 실행)은 이보다 짧을 것으로 보이나 **측정하지는 않았다.** 동기화 장치(락, 플래그)는 없고 **대기 시간에만 의존**한다. 부하가 큰 상태에서 `popen`이 1초 넘게 걸리면 읽는 쪽이 빈 값을 보게 된다.
- 예외: `main_server`의 `Clock_sync()`는 같은 프로세스에서 채운 직후 읽으므로 경합이 없다.

### 6.8 포트 상수 `0x411f`, `0x581b`

`ldb_server.c:423, 429`와 `config_server.c:248, 254`는 `htons(0x411f)`, `htons(0x581b)`를 쓰고 주석은 각각 8001, 7000이다. 0x411f는 16671, 0x581b는 22555이고, 8001은 0x1f41, 7000은 0x1b58이므로 주석과 값의 바이트 순서가 반대다. 같은 목적의 다른 코드는 `htons(EC_REQUEST_UPORT)`처럼 상수를 쓴다(`control_init.c:164-165, 180, 186`; `EC_REQUEST_UPORT` = 7000, `drcommon.h:44`).

**실제 영향은 없다.** 소스 전체(`lib`, `src`, `include`)에서 이 주소를 설정하는 코드 외에는 참조가 없다.

```
주소 구조체를 설정만 하고 쓰지 않는 곳
├─ db_server      dbm->self_addr, dbm->wire_remote     (ldb_server.c:419-429)
├─ config_server  scan->self_addr, scan->wire_remote   (config_server.c:244-254, 화면 출력만 :259, :262)
└─ control_server ecm->self_addr, wire_center, wire_remote (control_init.c:170-186)

실제로 쓰이는 곳
├─ gather_server  period->self_addr  (gather_server.c:875, 1560, 1674)
└─ alarm_server   as->self_addr      (alarm_handler.c:240)
```

- 기준 장치의 UDP 수신 포트에도 16671(0x411f), 22555(0x581b)는 없다(7절 참고).
- 따라서 db·config·control의 "Host_IP/Self_IP 주소 구성"은 현재 코드에서 **통신에 반영되지 않는다.** 4.2절 표의 이 세 서버는 "netconfig를 읽어 구조체에 담지만 이후 사용하지 않음"으로 읽어야 한다. 호스트와 실제로 통신하는 서버는 gather(`remote_addr`/`self_addr`), alarm(`tm_addr`/`self_addr`), main(시각 동기화)이다. gather의 `remote_addr` 사용처까지는 추적하지 않았다.

---

## 7. 기준 장치(10.10.0.220) 확인 결과

2026-11-09, 읽기 전용(`cat`, `ps`, `ipcs`, `/proc/net/*`, 공유메모리 읽기 전용 attach)으로 확인했다. 장치는 Ubuntu 16.04, armv7l, 배포 버전 03.01.14, 가동 199일이다. 프로세스 시작 시각은 2026-10-26 20:44이다.

```
기준 장치 확인 항목
├─ nelite.conf → 공유메모리 일치
│   ├─ 설정 파일 : WIRE_ID=139600, WIRE_TYPE=1, HOST_NAME=E3-DP, MIH_IP=10.10.0.220,
│   │             MIH_GATEWAY=10.10.0.1, MIH_NETMASK=255.255.255.0,
│   │             PRIVATE_IP=192.168.123.2, PRIVATE_GATEWAY=192.168.123.1, PRIVATE_NETMASK=255.255.255.0,
│   │             HOST_IP=ALARM_HOST_IP=10.10.0.144
│   └─ 0xE3000001 세그먼트(182바이트)를 읽은 결과 : 위 값이 2절의 오프셋 그대로 들어 있음
│       ├─ wire_type  = 1 (숫자 1바이트. 문자 '1'이 아님)
│       ├─ 문자열 필드 = NUL로 끝나고 나머지는 0 (memset 후 복사한 결과와 일치)
│       └─ e3gw_subnet, rect_subnet = 전부 0 (채우는 코드가 없다는 분석과 일치)
│
├─ attach 프로세스 수 : ipcs 의 nattch = 14 = 소스 분석과 일치
│   ├─ main, db, control, alarm, config, gather, acon_agent      → 7
│   ├─ gw_server 2개(인자 1, 6)                                   → 2
│   └─ scan, rt, modbus, rect, netcheck                          → 5
│      (emon은 대화형 도구라 미실행, realdata_server와 smm은 attach하지 않음 → 3.1절과 일치)
│
├─ 수신 소켓 (/proc/net)
│   ├─ UDP : 7700, 8002, 8022, 8052, 7032, 7062   → 16671, 22555 없음
│   └─ TCP LISTEN 8개 : 22, 23, 7031, 7041, 7995, 8001, 8021, 9785 → 16671, 22555 없음
│
└─ 기동 방식 : PID 순서가 smm 기동 순서(main, db, config, scan, gather, rt, alarm, control, …)와 일치
               (시작 시각은 모두 같은 초라 시각으로는 순서를 구분할 수 없음)
```

- `alarm_server`의 UDP 포트 7042는 수신 소켓 목록에 없다. `AlarmSendTimeOutCheck()`가 응답 시간 초과 시 `udp_sockfd`를 닫기 때문일 수 있으나(`alarm_handler.c:317`) 원인은 확인하지 않았다. netconfig와는 무관하다.
- 현장 운영 장치의 값은 확인하지 못했다. 이 장치는 연구소 보관 장치이다.

---

## 7. 정리 (이 구조체에서 의미 있는 것과 없는 것)

```
netconfig 13개 필드
├─ 서버 동작에 영향 (4)  : mih_ip, host_ip, alarm_host_ip, wire_type(→DrDB->type, 이후 덮어써짐)
├─ 표시·진단용 (3)       : wire_id, hostname, private_ip  (emon 출력만)
├─ 저장만 하고 참조 없음 (4) : mih_netmask, mih_gateway, private_netmask, private_gateway
│                            (공유메모리 기준. nelite.conf 값은 config 유틸이 OS 설정 생성에 사용 → 5.2절)
└─ 미사용 (2)            : e3gw_subnet, rect_subnet
```

- 신·구 DP를 비교할 때 netconfig 쪽에서 반드시 일치시켜야 할 입력은 `nelite.conf`의 `MIH_IP`, `HOST_IP`, `ALARM_HOST_IP`, `WIRE_TYPE` 4개이다.
