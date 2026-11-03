# E3-DP 통신 인벤토리와 테스트 대응

| 항목 | 내용 |
|---|---|
| 목적 | DP(E3-DP 장치 프로그램)의 모든 통신을 구분·방향·메시지 단위로 나열하고 각 메시지에 대응하는 테스트와 확인 상태를 기록 |
| 근거 | 소스 `e3dp.2.1` (기준 장치 배포본 03.01.14와 동일), 신 보드·기준 장치 실측 |
| 갱신 | 2026-10-26 |
| 상태 | 작성 중. "미조사"는 소스를 아직 읽지 않은 영역 |

## 1. 용어

| 용어 | 뜻 |
|---|---|
| DP | 현장에서 하위 장치 데이터를 수집·판정·제어하고 상위 서버와 통신하는 장치 프로그램 묶음 (서버 프로세스 약 13개 + 공유메모리) |
| 하위 장치 | DP가 폴링하는 장비. E3-GW(Modbus TCP), 정류기(RECT) |
| Host(서버) | DP의 상위 시스템(모국, 관제). DP에 요청을 보내고 DP의 경보·수집 데이터를 받음 |
| LPORT | 논리 포트. 계측값(AI) 또는 접점(DI) 하나. `컴포넌트명(4자) + 컴포넌트 번호 + 포트 번호`로 식별 (예: ACON 1.1) |
| 포인트 | 하위 장치 채널(GW 번호, 포트, 채널)과 LPORT의 연결 정의. `nelite.db`에 있음 |
| PDU | Host와 DP가 주고받는 ASN.1 BER 계열 본문 (`libPdu`) |
| rid | 요청/경보 식별 번호. 경보는 이 값으로 ACK |
| float2int | 값을 정수로 보내는 방식. 0 이상은 `int(v*1000)`, 음수는 `int(-v*1000) + 1000000000` |

## 2. 하위 장치 통신 (DP가 클라이언트)

### 2.1 E3-GW — Modbus TCP, 포트 1502 (`gw_server`)

| 항목 | 내용 |
|---|---|
| 연결 | 폴링마다 새 TCP 연결, DP가 응답 수신 후 닫음. 연결 타임아웃 500ms, 응답 대기 500ms |
| 대상 | `nelite.db` System Info의 shelf(GW 번호, 포트 번호, IP). 상위 GW(포트 0)가 COMM_NORMAL이어야 폴링 |
| 담당 | `gw_server N`이 shelf N~N+4 담당. `modbus_server`가 GW 5대당 1개 기동 |

| ID | 메시지 | 형식 | 테스트 | 상태 |
|---|---|---|---|---|
| GW-01 | 실시간 요청 | 12바이트 `[txid 2][0 2][6 2][port 1][func 0x03][addr 0][count 120]`, 빅엔디안, txid 증가 | `test_gw_poll` | 신·구 확인 |
| GW-02 | 정상 응답 | 249바이트 `[txid][0][243][port][3][240]` + AI 40 × float32(BE) + DI 40 × uint16(BE). 마지막 바이트 0 = 정상 | `test_gw_poll`, `test_gw_errors` | 신·구 확인 |
| GW-03 | "설정 없음" 응답 | 12바이트 응답. shelf를 COMM_ALARM으로 | `test_gw_errors` | 신·구 확인 |
| GW-04 | 통신 이상 플래그 | 마지막 바이트 ≠ 0 → COMM_ALARM | `test_gw_errors` | 신·구 확인 |
| GW-05 | 잘못된 응답 | 길이 ≠ 249, 응답 port 불일치 → 무시 | `test_gw_errors` | 신·구 확인 |
| GW-06 | 무응답·연결 거부 | 포트당 최대 500ms 후 다음 포트로 | `test_gw_errors` | 신·구 확인 |
| GW-07 | 시각 동기 | func 0x64, port 0, txid 0, 시각 4바이트(LE). 기동 후 첫 루프에서만(이후 21600 사이클) | `test_gw_poll` | 기동 경쟁으로 건너뜀 |
| GW-08 | 제어 쓰기 | func 0x06, addr=채널, count=값. 응답 읽지 않음 | `test_control` | 신 확인 |
| GW-09 | AO 쓰기 | func 0x06 (`check_ao_set`) | 없음 | 미착수 |
| GW-10 | DI 값 반영 | 응답의 DI 40 × uint16 → LPORT 비트 (`update_di_value`, 반전 접점 처리). 비0이면 설정 | `test_gw_di` | 신 확인 (반전 접점은 DB에 없어 미시험) |
| GW-11 | UPS·발전기 해석 | dtype 52 등 장비별 파싱 | 없음 | 미조사 |

### 2.2 netcheck_server — ICMP ping

| ID | 메시지 | 내용 | 테스트 | 상태 |
|---|---|---|---|---|
| NET-01 | ping | 상위 GW(shelf 포트 0)마다 raw ICMP echo. 처음 수신한 패킷의 출발지가 대상 IP와 같으면 성공. 6회 연속 실패 시 COMM_ALARM | 환경 구성에서 간접 확인 | DP는 root 필요 |

### 2.3 정류기 (`rect_server`) — TCP 2000, ASCII + LRC

| ID | 메시지 | 상태 |
|---|---|---|
| RECT-01 | 폴링 요청 | DP -> 정류기 TCP 2000. 17바이트 ASCII `:` 01 04 0100 004B LRC CRLF (LRC = 12자 16진 합의 2의 보수) | `test_rect` | 신·구 확인 |
| RECT-02 | 응답 해석 | 응답 9번째 문자부터 레지스터 75개(각 4자리 16진, rect.h 순서). ACDS 301 포트 1~7·22, DCDS 302 포트 1~3(부호: MSB 1 이면 -(~v&0x7FFF)), RECT 303 channel 1 포트 1~4. 짧은 응답·깨진 응답에도 프로세스 유지 | `test_rect` | 신·구 확인 |
| RECT-03 | 통신 이상 | 연속 51회 초과 실패 시 셸프 통신 이상(3), LPORT 상태 22. 복구 시 정상 | `test_rect` | 신·구 확인 |

## 3. Host(서버) 통신

### 3.1 Host → DP 요청 (UDP 7999, `main_server`)

공통 형식: 44바이트 헤더 + PDU. 헤더(type=1, size, service, rid, protocol은 빅엔디안, caddr = 응답 받을 주소). 상세는 `sim/ber.py`.

| ID | 서비스 | 대상 서버 | 동작 | 테스트 | 상태 |
|---|---|---|---|---|---|
| HOST-01 | 409 한계치 설정 | config_server | LPORT 상·하한 변경, 응답 송신, `nelite.db` 저장. 상한 < 하한이면 거부(응답 service 0) | `test_config_limit` | 신 확인 |
| HOST-02 | 407 경보 마스크 | config_server | AI 마스크(value 최하위 비트), 상태 정상화·경보 억제 | `test_config_limit` | 신 확인 |
| HOST-03 | 405·406·408·410~416 기타 설정 | config_server | 상/하한 개별, 전력량 초기값, DC 전압·전류, 방전, 온도보상, AO 값, 배터리 방전기 | 없음 | 미착수 |
| HOST-04 | 2051·2061 등 정전/입전/디멘드/ADR 룰 | control_server | 룰 저장 | 라우팅만 `test_main_dispatch` | 신 확인(라우팅) |
| HOST-05 | 수동 제어 CM_RUN `0x01000101` (RM/A/AN은 같은 경로) | control_server | 본문 ASCII `<wire_id> <구성품> <번호> <명령>`. 출력 LPORT(포트 28) 값 설정 → gw_server가 다음 폴링에서 GW에 func 0x06 쓰기(addr=채널, count=명령). 응답은 DP가 caddr로 TCP 연결해 2건 전송(`0x0000 0x0000` 성공, 구성품 없음 `0x0552 0x0000`) | `test_control` | 신 확인. 첫 폴링 사이클 중 명령은 유실(앱 동작) |
| HOST-06 | 제어 모드 조회·설정 (`EVR_CTRL_MODE_*`) | config_server | TCP 응답 | 없음 | 미착수 |
| HOST-07 | 403·404 실시간 구독·해제 | rt_server | 구독 클라이언트 관리, 푸시 (RT-01~03) | `test_rt_push`, 라우팅 `test_main_dispatch` | 신 확인 |
| HOST-08 | 0x0200xxxx 설정 다운로드 (START `0x02000001` → SHELF `0x02000111` → MODULE `0x02000501` → EQUIP `0x02000507` → LPORT `0x0200050A` → POINT `0x0200050D` → END `0x02000002`) | db_server | 레코드당 변수 1개(이름 `1.1.5.<테이블>.<필드>.0.<인덱스들>`, 값 마지막 필드, shelf IP는 호스트 순서 정수). 메시지마다 DP가 caddr로 TCP 연결해 1024바이트 응답. END 후 DB 저장·서버 재구성. 상세 `sim/dbdl.py` | `test_download` | 신 확인 (재전송 DB와 저장 DB 행 단위 일치) |
| HOST-09 | 0x02000103 시각 갱신 | main_server | `Clock_sync` 실행 | 없음 | 미착수 (시스템 시각 변경) |
| HOST-10 | 알 수 없는 서비스, 크기 > 2048, 잘린 패킷, 깨진 본문, 빈 본문 | main_server, config_server | 로그 후 폐기. 빈 본문은 결함(xfail) | `test_main_dispatch` | 신 확인 |

### 3.2 Host → DP 조회 (TCP 7995, `realdata_server`)

| ID | 메시지 | 형식 | 테스트 | 상태 |
|---|---|---|---|---|
| RD-01 | 전체·DI·AI 원시값 조회 | 헤더 15바이트(`wire_id[6] svc[2] data_len data_cnt next_yn result[2]`) + 본문 `data_cnt*8`. 응답 레코드 22바이트(`index_id[8] value min max status`), 최대 90건씩, 마지막 `next_yn='N'` | `test_realdata` | 신·구 확인 |
| RD-02 | 잘못된 요청 | wire_id 불일치, data_cnt 0 → 빈 응답 result "01" 후 연결 종료 | `test_realdata` | 신·구 확인 |
| RD-03 | AI 값 인코딩 | float2int (0, 12.5, -3.25, 35.999, 0.0004, 1234.567) | `test_realdata` | 신·구 확인 |

### 3.3 DP → Host 송신

| ID | 메시지 | 내용 | 테스트 | 상태 |
|---|---|---|---|---|
| ALM-01 | 경보 UDP 7704 | 헤더 44바이트(type 1, service 201, caddr = DP 주소:7042) + PDU 11개 변수(stationid, equip, compno, portno, value, status, peak, otime 또는 rtime, type, 상한, 하한). 상태 0 정상 · 1 하한 · 2 상한 · 3 디지털 · 21 GW 설정 없음 · 22 통신 이상 | `test_alarm` | 신·구 바이트 일치 |
| ALM-02 | 경보 ACK | Host가 DP의 7042로 응답 헤더(rid 포함) 전송 → DP가 ACB 항목 삭제 후 다음 건. 정지-대기 | `test_alarm` | 신·구 확인 |
| ALM-03 | 경보 재전송 | ACK 없으면 5초 후 같은 항목 재전송 | `test_alarm` | 신·구 확인 |
| TS-01 | 시각 요청 UDP 37 | `What time is it?` 16바이트 → Host가 RFC 868 4바이트 응답 → `stime()`. 응답 없으면 계속 재요청, 7999 미개방 | `test_main_dispatch` | 신 확인 |
| GAT-01 | 정시 수집 UDP 7062 (DP→Host) | 주기(10/60/120분)의 경계에서 AI·RMM LPORT를 SET 요청 PDU로 송신. 메시지당 변수 20개, 변수 이름 `1.1.3.5.1.6.1.<국번>.<compid>.<번호>.<포트>.<상태>.<시각>.<type>.<min>.<max>` = 현재값(float2int). 헤더 type·size·service는 BE, rid(1000+n)·caddr.family는 LE(호스트 순서), protocol은 미설정. Host는 헤더 rid를 응답 헤더로 돌려줘 ACK | `test_gather` | 신 확인 (Host 시각 오프셋으로 경계를 앞당겨 시험) |
| RT-01 | 실시간 구독 (Host→DP) | UDP 7999(→rt_server 8052)로 44바이트 헤더 + ASCII `403` + 개수(4자리) + 항목(국번6+구성품4+번호2+포트2, 14자). DP가 요청 caddr로 TCP 연결 | `test_rt_push` | 신 확인 |
| RT-02 | 실시간 푸시 (DP→Host, TCP) | 44바이트 헤더(size만) + ASCII 28자: AI `%06d%4s%02d%02d%10.3f%04d`, DI·특수 포트 `%10d`. 첫 값과 값·상태가 바뀔 때만 송신(`SEND_COUNT`는 재시도 횟수). 구독 목록에 없는 항목은 무시 | `test_rt_push` | 신 확인 |
| RT-03 | 구독 해제 | Host가 TCP로 헤더 44바이트 + `404` 전송 → DP가 연결을 닫음 | `test_rt_push` | 신 확인 |


### 3.4 외부 클라이언트가 DP 값을 읽는 Modbus TCP 서버 (포트 9785, `acon_agent`)

현장 ACON 장치(기준 장치에서 192.168.123.150/157 등 다수 연결)와 외부 시스템이 DP에 접속해 ACON 값을 읽는다.

| ID | 메시지 | 형식 | 테스트 | 상태 |
|---|---|---|---|---|
| ACON-01 | 읽기 | 요청 12바이트 `[txid][0][6][unit][0x04][addr][count]` (count ≤ 125). 응답 레지스터: stationid 2워드 + ACON(번호순)마다 7워드 `[번호, 설정온도*10(n.3), 현재온도*10(n.1), 인버터(n.18), ON/OFF(n.20), 압축기1/2(n.23 bit1/2)]` | `test_acon_agent` | 신 확인, 구는 최종 실행에 포함 |
| ACON-02 | 오류 | 범위 초과·count > 125·미지원 func → func\|0x80 응답. 12바이트 미만 요청 → 0x90 | `test_acon_agent` | 신 확인 |
| ACON-03 | 쓰기(func 0x10) | `do_Acon` → 제어 LPORT 설정 | 없음 | 미착수 |

### 3.5 DP 내부·기타 포트

| 포트 | 서버 | 용도 | 상태 |
|---|---|---|---|
| TCP 7031, 7041, 8001, 8021 | config, alarm, db, control | 각 서버의 TCP 리스너 (응답·다운로드 경로) | 열림만 확인 |
| UDP 7032, 7042, 7062, 8002, 8022, 8052 | config, alarm, gather, db, control, rt | `main_server`가 중계하는 내부 UDP | 일부 확인 |

## 4. 미검증 영역 (이 체계의 한계)

| 영역 | 이유 |
|---|---|
| 하드웨어(GPIO, LED, 시리얼, 이더넷 드라이버, RTC) | 보드가 달라 시뮬레이터로 대체 불가 |
| 현장 장비의 실제 응답과 Host의 실제 요청 | 시뮬레이터는 소스 해석 기반. 연구소 기준 장치에 현장 통신 없음 |
| 타이밍·장시간 동작 | 주기·누수·파일 증가는 짧은 시험으로 확인되지 않음 |
| 부팅·`smm` 감시·재부팅 경로 | 시험은 서버를 직접 기동. `smm` 경로는 재부팅 위험으로 보류 |

## 5. 발견 사항 요약

| 구분 | 내용 | 위치 |
|---|---|---|
| 이식 결함(수정) | `lib/libPdu.a`가 구 환경에서 만든 것으로 `time_t` 크기가 달라 `struct pdu_info` 레이아웃 불일치 → PDU 파싱 루프 무한 반복 | task 004, `수정이력.txt` |
| 이식 요구 | DP는 root로 실행해야 함(`netcheck_server` raw 소켓) | task 003 |
| 앱 결함(기록) | 빈 본문 요청 성공 처리, `realdata_server` 스택 버퍼 길이 검증 없음, `DrComSendTCPMessage` char 부호 의존 | task 004 |
| 소스 불일치 | ① 기준 장치에 배포된 `acon_agent`(2026-03-10)는 저장소 소스와 다른 개정판(ACON당 11워드). `emon2`, `kwhm_agent`는 소스 없음. ② 작업 트리의 `gather_server.c`는 HEAD·배포본과 달리 정시 데이터를 7062로 보내고 TIMEOUT이 40초(`jhcho 2024.12.27`) | task 004 |
| 동작 특성 | 시각 동기 1회성(기동 경쟁), 연결 거부도 포트당 0.5초, `main_server`는 Host 시각 응답 전까지 요청 불가 | task 005 |
