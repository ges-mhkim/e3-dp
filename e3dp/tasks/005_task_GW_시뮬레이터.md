# 005 GW 시뮬레이터 (Modbus TCP)
목표: E3-GW 역할의 Modbus TCP 서버를 만들어 gw_server 통신과 netcheck 동작을 pytest로 검증한다.
상태: 보류

## 선행
- 001 통신 인벤토리, 003 테스트 기반, (비교 기준) 002 캡처

## 사실 (확인된 것만)
- `gw_server`는 담당 GW 5대를 순회하며 TCP 1502로 Modbus 읽기(AI 40워드, DI 40워드). 응답 249바이트 검증. 제어·AO 쓰기 수행.
- 응답을 `update_ai_value`/`update_di_value`로 LPORT/POINT에 매핑. 통신 실패 시 `DrSI->shelf[].status = COMM_ALARM`.
- `modbus_server`가 GW 5대당 `gw_server` 1개를 기동. GW 수에 따라 프로세스 수 변화 (예: 1~5대=1개, 6~10대=2개).
- `netcheck_server`가 ICMP ping으로 GW 통신 상태(`com_status`) 갱신. PC는 ping에 응답해야 함.
- 기준 장치의 GW: 192.168.123.11, .12.

## 소스에서 확정한 GW 프로토콜 (gw_server.c, nelite.h)
- 요청 12바이트(big-endian): `[txid 2][proto 0][len 6][port 1][func 1][addr 2][count 2]`. 연결은 폴링마다 새로 맺고 DP가 닫음.
  - func 0x03: addr 0, count 120(= AI 40 × 2 + DI 40). txid는 요청마다 1씩 증가(0xFFFF 다음 1).
  - func 0x06: 제어/AO 쓰기. addr=채널, count=값. 응답 읽지 않음.
  - func 0x64: 시각 동기. port 0, txid 0, 본문 time_t 하위 4바이트(little-endian). 응답 읽지 않음.
- 정상 응답 249바이트: `[txid][proto][len 243][port][func 3][bytecnt 240]` + AI 40 × float32(big-endian) + DI 40 × uint16(big-endian).
  - 마지막 바이트(DI 40번의 하위 바이트)가 통신 상태. 0이면 정상, 아니면 COMM_ALARM.
- 응답 판정 순서: ① 응답의 port(EquipID) 불일치 → 무시 ② 12바이트 → "설정 없음", 해당 shelf COMM_ALARM ③ 249바이트 아님 → 무시 ④ 마지막 바이트 ≠ 0 → COMM_ALARM ⑤ 정상 → 값 반영.
- 값 매핑: 포인트 테이블(nelite.db)에서 (shelfno=GW 번호, boardno=port, channelno)로 LPORT를 찾아 AI는 `value`, DI는 비트로 반영.
- 응답 대기 500ms(poll). 연결 타임아웃 500ms.
- 폴링 조건: 상위 GW(shelf의 compid 0)가 COMM_NORMAL이어야 함. 이 상태는 `netcheck_server`가 ping으로 설정.
- GW 주소는 `nelite.db`의 System Info(shelf)에서 옴. `gw_server N`은 shelf N~N+4 담당.

## 발견 사항 (신 보드 실측)
- 연결 거부(리스너 없음)도 포트당 약 0.5초 소요. GW 6대 중 2대만 시뮬레이션하면 한 사이클 6.8초. 전체 GW를 띄우면 2~3초.
- `netcheck_server`의 ping 판정은 raw 소켓에서 처음 읽은 패킷의 출발지를 대상 IP와 비교. 127.0.0.x로 ping하면 처음 읽히는 패킷이 자기 요청(출발지 127.0.0.1)이라 실패. 보드에 할당된 별칭 주소로 보내면 출발지가 그 주소가 되어 성공.
- 시각 동기는 `gw_server` 기동 후 첫 루프에서만 전송(이후 21600 사이클마다). 첫 루프 시점에 상위 GW 상태가 아직 COMM_ALARM이면 건너뛰고 수 시간 뒤에 전송됨(기동 경쟁). 실측에서 전송되는 경우와 안 되는 경우가 모두 나타남.
- 신 보드(Debian 13)는 time_t가 64비트. 시각 동기는 하위 4바이트만 보내므로 2038년 이후 값이 달라질 수 있음(현재는 영향 없음).

## 체크리스트
- [x] `tests/sim/gwsim.py`: Modbus TCP 서버(1502), GW 6대(10.99.0.11~16), 모드(normal, noconfig, silent, badsize, wrongport, commfail, slow), JSON 제어. 보드에서 실행(Python 3.5 호환)
- [x] 값 주입 API: `set_ai`, `set_di` (제어 포트로 JSON 요청)
- [x] 정상 응답 테스트: `comp ACON 1 1` 출력으로 LPORT 값·상태 확인 (`tests/protocol/test_gw_poll.py`, 신 보드 통과)
- [ ] 판정 연계 테스트: 값 변화 → scan_server 상/하한 판정 → alarm 송신 (Host 시뮬레이터 연동, task 004)
- [x] 연결 거부·무응답 테스트: DP 프로세스 유지, 다른 port 폴링 계속 (`test_gw_errors.py`, 신 보드 통과)
- [x] 이상 응답 테스트: 249바이트 아님, port 불일치, 12바이트(설정 없음), 마지막 바이트 ≠ 0 (신 보드 통과). 기능 코드 오류 응답은 미작성
- [ ] 쓰기 테스트: 제어 출력, AO 설정이 GW에 올바르게 전달됨 (시뮬레이터가 수신 프레임 기록)
- [ ] GW 수 변화 테스트: 5대 경계(5, 6대)에서 `gw_server` 프로세스 수
- [ ] ping 응답 테스트: `com_status` RT/READY 전이
- [x] 캡처(task 002)와 요청 프레임 구조 일치 확인: 12바이트, count 120, unit별 연속 txid. 응답은 캡처에 12바이트(설정 없음)만 있어 일치 확인(`noconfig` 모드)

## 결정/미정
- 결정: 값 확인은 읽기 전용 덤프 방식을 우선. 로그 파싱은 보조.
- 미정: 보드가 하나이므로 GW 여러 대를 PC 하나에서 흉내 내는 방식(IP 별칭 / 포트 분리). DP가 GW 포트를 1502 고정으로 쓰는지 소스 확인 필요.
- 미정: 공유메모리 값을 외부에서 읽는 방법(`emon` 출력 파싱 vs trace 덤프 추가). trace는 `#ifdef E3DP_TEST_TRACE` 사용.

## 테스트
- 위치: `tests/protocol/test_gw_*.py`
- 실행: `pytest tests/protocol -m device -k gw`

## 참조
- 스킬 `e3dp-test`
- 소스: `e3dp.2.1/src/gw/gw_server.c`, `e3dp.2.1/src/modbus/modbus_server.c`, `e3dp.2.1/src/netcheck/`
