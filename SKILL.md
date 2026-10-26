---
name: e3dp-build
description: e3dp 소스 수정 및 보드(10.10.1.100) 컴파일 확인 절차. e3dp.2.1 소스를 수정하거나 빌드/컴파일 오류를 디버깅할 때 사용.
---

# e3dp 빌드 / 디버깅

## 소스 수정
- 위치: `C:\ges\project\08_dp\e3dp\e3dp.2.1`
- 이 폴더는 보드의 `/home/e3dp/e3dp.2.1` 과 CIFS 마운트(`//10.10.1.20/e3dp`)로 공유된다.

## 컴파일 확인 (보드, ARMv7 Debian, gcc)
```
ssh e3dp@10.10.1.100        # pwd: ges000
cd e3dp.2.1 && make
```
비대화형 실행 예: `ssh e3dp@10.10.1.100 'cd e3dp.2.1 && make 2>&1 | tail -40'`
(비밀번호 입력이 필요하면 sshpass 또는 사용자에게 입력 요청)

## 시리얼 콘솔 (COM71, 115200)
- E3-DP 장치에 시리얼로 연결된 포트: `COM71`, 115200 baud.
- 이 포트로 접속(serial-monitor MCP: `open_port` → `write_data` → `read_lines`/`read_new_lines`)하여
  장치의 Linux Debian 명령을 직접 수행할 수 있다. (SSH 불가/네트워크 설정 변경/부팅 로그 확인 시 유용)
- 사용 후에는 `close_port` 로 포트를 닫는다 (다른 터미널 프로그램과 동시 점유 불가).

## 디버깅 순서
1. make 실행 후 첫 번째 error 부터 해결 (`lib/com` 부터 빌드됨).
2. 코드는 K&R 스타일(32bit 가정) 레거시. 최신 gcc의 `-Wint-conversion` 등이 error 로 승격됨.
3. 수정은 로컬 소스에서만 하고, 보드에서 make 재실행으로 검증.
