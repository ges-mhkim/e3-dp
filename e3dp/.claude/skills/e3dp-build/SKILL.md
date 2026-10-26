---
name: e3dp-build
description: e3dp 소스를 PC에서 수정하고 장치(Raspberry Pi 3, Debian)에서 마운트 확인·컴파일(make clean all)하는 절차. e3dp.2.1 소스 수정, 빌드 오류 디버깅, 장치 동작 확인 시 사용.
---

# e3dp 마운트 / 컴파일

## 작업 흐름
- 소스 수정: PC에서만 (`C:\ges\project\08_dp\e3dp\e3dp.2.1`).
- 컴파일·동작 확인: 장치에서만.
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

## 오류 디버깅
1. `grep -n 'error:' /tmp/build.log | head`로 첫 error부터 해결 (`lib/com`부터 빌드됨).
2. 레거시 K&R 코드(32bit 가정). 최신 gcc의 `-Wint-conversion` 등이 error로 승격될 수 있음.
3. PC에서 수정 → 장치에서 `make` 재실행. 부분 빌드: `make -C src/<모듈>`.
