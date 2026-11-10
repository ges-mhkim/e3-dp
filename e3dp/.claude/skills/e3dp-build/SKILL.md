---
name: e3dp-build
description: e3dp 소스를 PC에서 수정하고 장치(Raspberry Pi 3, Debian)에서 마운트 확인·컴파일(make clean all)하는 절차. e3dp.2.1 소스 수정, 빌드 오류 디버깅, 장치 동작 확인 시 사용.
---

# e3dp 마운트 / 컴파일

## 작업 흐름
- 소스 수정: PC에서만 (`C:\ges\project\08_dp\e3dp\e3dp.2.1`).
- 최종 컴파일·동작 확인: 장치에서만.
- 사전 검증(구문·오류·경고 확인): PC의 WSL Debian에서 가능 ("PC 사전 검증 (WSL Debian)" 절 참고). 장치 빌드를 대체하지는 않는다.
- 장치에서 소스 직접 편집 금지.

## 폴더 연결 (CIFS 마운트)
| 구분 | 경로 |
|---|---|
| PC | `C:\ges\project\08_dp\e3dp` |
| 공유 | `//10.10.1.20/e3dp` (PC 공유 폴더) |
| 장치 | `/home/e3dp` (e3dp 계정 홈) |

- 장치의 `/home/e3dp` = PC의 `e3dp` 폴더. 소스는 장치의 `/home/e3dp/e3dp.2.1`.
- PC에서 저장한 파일이 장치에 즉시 반영됨 (`actimeo=1`).
- 마운트 확인 (장치): `mount | grep cifs` → `//10.10.1.20/e3dp on /home/e3dp type cifs` 출력되면 정상.
- 마운트 안 된 경우 (장치, root):
  ```
  mount -t cifs //10.10.1.20/e3dp /home/e3dp -o username=<PC계정>,password=<PC비밀번호>,uid=e3dp,gid=e3dp,file_mode=0755,dir_mode=0755,vers=3.0
  ```
  - PC 계정·비밀번호는 사용자에게 받는다. 파일에 기록하지 않는다.
  - PC 공유 폴더가 열려 있고 장치와 같은 망(10.10.1.x)이어야 한다.

## 장치 접속
### 시리얼 (COM71, 115200)
1. serial-monitor MCP: `open_port` (COM71, 115200) → `write_data` → `read_new_lines`.
2. 로그인 상태가 root이면 `su - e3dp`.
3. 프롬프트가 `e3dp@E3-DP-POC:~$`이면 `cd ~/e3dp.2.1`.
4. 사용 후 `close_port`. 다른 터미널 프로그램과 동시 점유 불가.

### SSH
- `ssh e3dp@10.10.1.100` 후 `cd e3dp.2.1`.

## 컴파일
```
cd ~/e3dp.2.1
sudo make clean all > /tmp/build.log 2>&1; echo BUILD_EXIT=$?
grep -c 'error:' /tmp/build.log
grep -c 'warning:' /tmp/build.log
```
- `sudo` 비밀번호는 프롬프트에서 사용자에게 받는다. 명령줄·파일·task에 기록하지 않는다.
- 소요 시간: 약 2분. 시리얼은 출력이 길어 로그를 파일로 돌리고 건수만 확인한다.
- 산출물: `bin/` (프로세스), `web/` (CGI). PC에서도 같은 폴더로 보인다.
- 성공 기준: `BUILD_EXIT=0`, `error:` 0건.

### 기준값 (2026-10-26, 수정 전 원본)
| 항목 | 값 |
|---|---|
| gcc | Debian 14.2.0-19 |
| 아키텍처 | armv7l |
| BUILD_EXIT | 0 |
| `error:` | 0건 |
| `warning:` | 293건 (lib/pdu 제외). lib/pdu 빌드 활성화 후 405건 |

- 수정 후 `warning:` 건수가 기준값보다 늘면 신규 경고 확인.
- 이 gcc는 레거시 코드의 일부 error를 `make/platform.tools`의 `-Wno-error=...` 옵션으로 경고로 낮춰 통과시킨다.

### 작업 완료 시 빌드 기준
- `BUILD_EXIT=0`, `error:` 0건, `warning:` 405건 이하.

## PC 사전 검증 (WSL Debian)
PC의 WSL `Debian`에서 소스를 컴파일해 오류·경고를 장치 빌드 전에 확인한다. 장치나 네트워크, CIFS 마운트가 필요 없다.

### 환경 (2026-11-10 확인)
| 항목 | 값 |
|---|---|
| 배포판 이름 | `Debian` (Debian 13.5) |
| gcc | Debian 14.2.0-19 (장치와 같은 버전) |
| 아키텍처 | x86_64 (장치는 armv7l 32bit) |
| make | 설치됨 |
| ARM 크로스 gcc (`arm-linux-gnueabihf-gcc`) | 미설치 |
| 소스 경로 | `/mnt/c/ges/project/08_dp/e3dp/e3dp.2.1` (마운트 불필요) |

### 소스 링크 (WSL Debian, 2026-11-10 확인)
```
/home/e3dp/e3dp.2.1 -> /mnt/c/ges/project/08_dp/e3dp/e3dp.2.1
```
- 이 링크 덕분에 WSL Debian에서 장치와 같은 경로(`/home/e3dp/e3dp.2.1`)로 `make`를 실행할 수 있다. 컴파일이 성공했음을 사용자가 확인했다.
- 링크가 없으면 (root) 다음으로 만든다: `mkdir -p /home/e3dp && ln -s /mnt/c/ges/project/08_dp/e3dp/e3dp.2.1 /home/e3dp/e3dp.2.1`
- 빌드 (PowerShell, `$?`가 PowerShell에서 먼저 해석되지 않도록 작은따옴표 사용): `wsl -d Debian bash -c 'cd /home/e3dp/e3dp.2.1 && make clean all > build_wsl.log 2>&1; echo BUILD_EXIT=$?'`
  - 산출물(`bin/`, `web/`)이 소스 폴더에 생성되므로 장치용 산출물과 섞이지 않게 주의한다. x86_64 산출물은 장치에서 실행되지 않는다.
  - 소스 폴더를 건드리지 않는 방법 (2026-11-10 사용, 약 6초): 소스를 WSL 홈의 별도 폴더로 복사해 `make clean all HOME_DIR=<복사본> OPT_DIR=<임의 폴더> BUILD_LOG=<로그>`로 빌드한다. 고정 경로는 `make/platform.tools`의 `HOME_DIR`, `OPT_DIR` 두 곳뿐이라 두 값을 덮어쓰면 `/home/e3dp`, `/opt/e3dp`에 쓰지 않는다. `CC="gcc -Wold-style-definition"`처럼 `CC`로 옵션을 추가할 수 있다 (`CFLAGS`를 덮어쓰면 Makefile의 `+=`가 무시된다).
  - 변경 전후 비교: 변경 전·후 소스를 각각 빌드해 `objdump -dr`(주소 정규화)로 `.o`를 비교하면 동작이 바뀌지 않았음을 확인할 수 있다.
  - 최신 gcc 시험 (2026-11-10): Debian trixie에는 gcc 14.2뿐이지만 sid에 gcc 15.3, 16.2가 있다. `sudo` 없이 `apt-get download`(전용 apt 상태 폴더 `-o Dir::State=...`, `-o Dir::Etc::sourcelist=...` 지정)로 `gcc-15-base cpp-15 cpp-15-x86-64-linux-gnu gcc-15 gcc-15-x86-64-linux-gnu libgcc-15-dev`를 받아 `dpkg -x`로 `~/gcc15/root`에 풀면 `~/gcc15/root/usr/bin/x86_64-linux-gnu-gcc-15`로 쓸 수 있다 (gcc 16도 같은 방식, `~/gcc16`). 시스템 apt 설정과 설치된 gcc는 바뀌지 않으며 폴더를 지우면 원상 복구된다. 빌드는 `make -C <모듈> CC=<절대경로>/x86_64-linux-gnu-gcc-15`.
  - 두 버전 모두 기본 표준 모드는 C23이다. `make/platform.tools`의 `-Wno-error=...` 옵션을 뺀 작업 복사본으로 빌드하면 새 컴파일러가 기본으로 오류 처리하는 항목이 드러난다 (원본 파일은 수정하지 않는다). `-fcommon`은 아직 필요하다 (제거하면 링크 실패).
  - `make clean all`은 기존 `bin/`, `web/`의 산출물을 지울 수 있다. 장치용 산출물이 필요하면 실행 전에 백업한다 (동작은 미확인).

### 실행 방법
- 기본 배포판이 `Ubuntu-24.04`(gcc 13.3)이므로 반드시 `wsl -d Debian`으로 지정한다.
- 개별 파일 구문 확인 예:
  ```
  wsl -d Debian bash -c "cd /mnt/c/ges/project/08_dp/e3dp/e3dp.2.1 && gcc -fsyntax-only -fcommon -I include -I include/gi_gw -I src/control src/control/control_pg_process.c"
  ```
- 여러 명령은 스크립트 파일로 만들어 `wsl -d Debian bash <파일>`로 실행한다. 경로는 `/mnt/c/...` 형식으로 쓴다.
- Git Bash에서 `wsl ... /mnt/c/...`를 실행하면 경로가 `C:/Program Files/Git/mnt/c/...`로 바뀌어 실패한다. PowerShell에서 실행하거나 스크립트 파일 방식을 쓴다.
- WSL의 `/tmp`는 `wsl` 호출 간에 유지되지 않았다. 결과 파일은 `/mnt/c/...` 아래에 저장한다.

### 한계
- x86_64(64bit)라서 `int`·`long`·포인터 크기가 장치와 다르다. 이 코드는 32bit 가정이므로 경고 종류와 건수가 장치와 다르게 나온다. 위 "기준값"(293건/405건)과 직접 비교할 수 없다.
- 같은 환경에서 수정 전·후를 비교하는 용도(예: 오브젝트 `objdump -d` 비교, 경고 증감)로 사용한다.
- `make/platform.tools`의 `HOME_DIR`이 `/home/e3dp/e3dp.2.1`로 고정되어 있어, WSL에 같은 경로의 링크를 만들어 두었다 (아래 "소스 링크").
- `gcc -m32`는 단순 파일(헤더 없음)만 확인했다. 실제 소스의 헤더(`<stdio.h>` 등)에 필요한 32bit 개발 패키지 설치 여부는 확인하지 않았다.
- 최종 확인은 항상 장치 빌드의 `BUILD_EXIT=0`, `error:` 0건, `warning:` 405건 이하로 한다.

## 오류 디버깅
1. `grep -n 'error:' /tmp/build.log | head`로 첫 error부터 해결 (`lib/com`부터 빌드됨).
2. 레거시 K&R 코드(32bit 가정). 최신 gcc의 `-Wint-conversion` 등이 error로 승격될 수 있음.
3. PC에서 수정 → 장치에서 `make` 재실행. 부분 빌드: `make -C src/<모듈>`.
