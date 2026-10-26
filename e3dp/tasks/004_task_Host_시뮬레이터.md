# 004 Host 시뮬레이터와 프로토콜 테스트
목표: 상위 서버(Host) 역할의 UDP/TCP 클라이언트·수신 서버를 만들고 서버 쪽 통신 전체를 pytest로 검증한다.
상태: 진행중

## 선행
- 001 통신 인벤토리, 003 테스트 기반

## 사실 (확인된 것만)
- Host → DP 요청: 설정 조회·변경, 제어, 실시간 구독, 원시값 조회.
- DP → Host 푸시: 경보(UDP 7704 수신), 정시·피크·충전·UPS 수집(UDP 7062), 실시간 푸시.
- Host 시뮬레이터는 포트 7704 등을 수신해야 하므로 PC가 `HOST_IP`(nelite.conf)로 설정되어야 함.
- 상세 포트·형식은 task 001 결과(`tests/inventory.md`) 참조.

## 소스에서 확정한 Host 프로토콜 (2026-10-26)
- 요청 데이터그램(Host → `main_server` UDP 7999): 44바이트 헤더 + PDU. 헤더의 type(1=EC_REQUEST), size, service, rid, protocol은 모두 빅엔디안, caddr(sockaddr_in) = 응답 받을 주소(family BE 2, port BE, IPv4), 나머지 0. 상세: `tests/sim/ber.py`.
- 본문 PDU: ASN.1 BER 계열. `a3 00`(SET) + 정수 3개(reqid, errstat, errindex) + 변수 바인딩들. 각 바인딩 `30 82 <len16>` + OID(06) + 값. 한계치(409): OID `1.1.6.1.1.5.0.<stationid>.<compid>.<compno>.<portno>.<상한>` = INTEGER 하한(둘 다 float2int 인코딩).
- 응답: DP가 caddr로 UDP 전송(type EC_REQUEST, service = 요청 서비스, 거부 시 0). 일부 서비스(제어 모드 등)는 TCP로 응답.
- DP → Host: 경보(UDP 7704, 정지-대기·rid ACK·5초 재전송), 시각 요청(UDP 37 `What time is it?` → RFC 868 4바이트 응답), 정시수집·실시간(미착수).
- `main_server`는 기동 시 Host의 시각 응답을 받을 때까지 메인 루프(UDP 7999)에 진입하지 않음. Host 시뮬레이터가 응답해야 함. 응답을 받으면 `stime()`으로 시스템 시각을 설정.
- 서비스 라우팅(`_smtable`): 405~416 등 설정 → config_server, 2051 등 룰 → control_server, 403/404 → rt_server, 0x0200xxxx → db_server.

## 발견 사항 (2026-10-26)
- 중대(수정 완료): 루트 Makefile이 `lib/pdu`를 빌드하지 않고 구 환경에서 만든 `lib/libPdu.a`(gcc 5.4, `time_t` 4바이트)를 링크했음. 신 툴체인에서 `time_t`는 8바이트라 `struct pdu_info` 레이아웃이 어긋나(`pdu_var_parsed` 17번째 → 25번째 바이트) `config_handler.c` 등 직접 필드를 읽는 코드가 PDU 종료를 인식하지 못하고 무한 루프(CPU 점유). 유효한 Host 요청 한 건으로 `config_server`가 멈추고 `smm`이 정체를 감지하면 장치 재부팅 가능. 조치: 루트 Makefile의 `lib/pdu` 주석 해제(all, clean), `lib/pdu/Makefile` clean이 `lib/libPdu.a`도 삭제. 재빌드 후 정상(파서 하니스 `tests/tools/c/pdutest.c`로 확인).
- 영향 범위(미확인): `pdu_info` 필드를 직접 쓰는 다른 코드(`db_server`의 설정 다운로드 디코드 등)도 같은 증상이었을 가능성이 높음. 설정 다운로드 경로 시험은 후속.
- 중대(확인 필요): **작업 트리와 git HEAD, 그리고 기준 장치 배포본이 서로 다르다.** HEAD는 배포본과 같은 이전 동작이고 작업 트리에는 이식 수정 외에 기능 변경이 섞여 있다.
  - `gather_server.c` (`jhcho 2024.12.27`): 정시 데이터 목적지 포트 `EC_REQUEST_UPORT`(7000) → `DR_UDP_PORT_PERIOD`(7062), `TIMEOUT` 10 → 40초, Peak/Dcds/UPS 공유메모리·초기화 활성화, 저장된 정시 데이터 전송(`#if 0` → `#if 1`) 활성화. 기준 장치 배포본은 이전 동작(로그 `TimeOut : 10Sec`, 포트 7000). 이 변경이 배포 대상 개정인지 확인 필요(신 환경은 변경된 동작을 따름).
  - `config_handler.c`: 디버그 출력(`station`, `compid`, `stationid[0..3]` 등) 추가. `util/sys.c`: 장비 코드 55("7300")·56("2750") 표시 추가.
  - 그 외 `alarm_server.c`(`fclose(alarm_fd)` → `close`), `rtclock.c`(`time_t` 변환), `rect_server.c` 등은 gcc 14/64비트 `time_t` 이식 수정.
- 중대(미해결, 소스 확보 필요): **기준 장치에 배포된 `acon_agent`(2026-03-10, 30464바이트)는 저장소 소스(`src/acon_agent`)와 다른 개정판**이다. 배포본은 ACON당 11워드 블록(`[번호, 설정온도, 현재온도, (미상), 인버터, ON/OFF, 압축기1, 압축기2, 미상 3워드]`)을 응답하고 소스에 있는 디버그 출력이 없다. 저장소 소스(7워드 블록)로 만든 신 환경 빌드는 배포본과 응답 형식이 다르다. 같은 이유로 `emon2`, `kwhm_agent`는 소스가 아예 없다. "소스는 배포본과 동일"이라는 전제가 이 프로그램들에는 성립하지 않는다. 배포본의 실제 소스 또는 요구 형식을 확인해야 한다.
- 낮음(앱 동작): 정시 수집 메시지 헤더의 `protocol`/`priority`/`did`는 설정되지 않아 재사용 버퍼의 이전 내용이 나간다(비결정). `caddr.sin_family`도 경보 메시지(htons)와 달리 호스트(LE) 순서. Host 구현이 이 값들을 쓰지 않아야 정상 동작한다.
- 낮음(앱 결함, 수정 안 함): 본문이 빈 요청(409 등)은 `pdu_parse_header` 실패를 무시하고 초기화되지 않은 `rt_info[10]`로 성공 처리해 응답 송신 후 `nelite.db`를 재저장함 (`test_empty_pdu_body_should_be_rejected` xfail).
- 낮음(앱 결함, 수정 안 함): `realdata_server`는 요청의 `data_cnt`(최대 32767)에 8을 곱한 길이를 1024바이트 스택 버퍼(`tmpBuf`)에 복사함. `data_cnt` > 128이면 스택 오버플로. 시험하지 않음.
- `DrComSendTCPMessage`는 크기 필드의 마지막 바이트를 signed char로 읽어 128 이상이면 길이가 달라짐(char 부호 의존).
- 중간(앱 동작, 수정 안 함): `gw_server`의 첫 폴링 사이클(`tsync_cnt==1`)에서 각 GW의 첫 포트는 시각 동기 프레임을 대신 보내는데, 그보다 먼저 `check_control()`이 제어 플래그를 소비(값 0)한다. 기동 직후 첫 사이클 중에 들어온 제어 명령은 Host에는 `0x0000 0x0000`(성공)으로 응답되고 GW에는 전달되지 않는다. 같은 구조로 `check_ao_set()`의 AO 설정도 유실될 수 있음.
- 낮음(앱 동작): 제어 요청의 wire_id를 검증하지 않음. 명령에 대응하는 포인트가 없어도 성공 응답하고 GW에는 쓰지 않음.
- 제어 응답은 DP가 요청의 caddr(IP:포트)로 **TCP 연결을 맺어** 전송(2건: 초기 확인 44바이트, 최종 `0x<ret2> 0x<ret1> `). Host는 UDP 요청의 출발 포트와 같은 포트에서 TCP 리스너를 열어야 함 (`tests/sim/hostreq.py`). 초기 확인 헤더는 엔디안이 섞여 있음(`00 03 00 00 0f 00 00 00 ...`).

## 체크리스트
- [x] `tests/sim/hostclient.py`(realdata TCP), `tests/sim/ber.py`(44바이트 헤더, BER 빌더/파서, 샘플 왕복 검증 `tests/unit/test_ber.py`), `tests/dpapi.py`(`host_request`)
- [x] `tests/sim/hostsim.py`: 보드에서 실행하는 UDP 수신기(7704, 7510, 37). 시각 응답, rid ACK 모드(none/echo/rid)
- [ ] `tests/sim/host.py`: TCP 클라이언트(제어 8021, 원시값 7995)
- [x] 보드 안에서 Host 시뮬레이터를 실행하고 `nelite.conf`의 HOST_IP·ALARM_HOST_IP를 127.0.0.1로 설정 (`dpapi.make_conf`)
- [x] main_server 중계 테스트 일부: 409→config, 2051→control, 403→rt, 알 수 없는 서비스, 크기 초과, 잘린 데이터그램 (`protocol/test_main_dispatch.py`). DB 서비스(0x0200xxxx)는 DB를 비울 수 있어 미시험
- [x] config_server 한계치(409)·경보 마스크(407) 테스트 (`protocol/test_config_limit.py`), 원복 포함. AO·DC 전압 등 나머지 서비스는 미착수
- [x] control_server 수동 제어 테스트 (`protocol/test_control.py`: 응답 2건, GW 쓰기 프레임, 구성품 없음 0x0552, 포인트 없는 명령, wire_id 미검증). 자동 제어 룰 저장·실행은 미착수
- [x] rt_server 구독(UDP→DP가 caddr로 TCP 연결)·푸시 형식·변화 시에만 전송·구독 해제 404 (`protocol/test_rt_push.py`). 푸시 주기(10ms 간격)와 다수 클라이언트는 미착수
- [x] alarm_server 테스트 (상한/하한/복구 경보, rid ACK, 5초 재전송) (`protocol/test_alarm.py`). ACB 영속화(alarm.db)는 미착수
- [x] gather_server 정시 수집 전송 (`protocol/test_gather.py`: 경계 시각, 20개 단위 분할, 변수 이름·값, rid). 피크·충전·UPS 수집과 `/opt/e3dp/periodic` 파일 생성은 미착수
- [x] realdata_server 테스트 (ALL/DI/AI, 90건 분할, 오류 응답, float2int) (`protocol/test_realdata.py`)
- [x] 이상 입력 테스트: 길이 초과, 알 수 없는 서비스, 잘린 패킷, 깨진 본문, 빈 본문(xfail)
- [ ] 각 테스트에 인벤토리 ID 부여 (task 001 인벤토리 완성 후)

## 결정/미정
- 결정: 설정 변경 테스트는 fixture에서 원본을 백업하고 종료 시 복원.
- 미정: 설정 다운로드(ASN.1 PDU) 테스트 포함 여부. 보드의 `libPdu` 의존 때문에 PDU 생성 도구를 보드에서 빌드하는 방안 검토.

## 테스트
- 위치: `tests/protocol/`
- 실행: `pytest tests/protocol -m device`

## 참조
- 스킬 `e3dp-test`
- `tests/inventory.md` (task 001 산출)
