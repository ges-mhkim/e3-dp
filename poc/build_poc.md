# build_poc.sh 구성 및 수동 절차

- 1~7장: build_poc.sh 소스 분석
- 8장: 명령어 입력 방식의 수동 절차
- 작성 범위: 소스 정적 분석. 작성 과정에서 스크립트 실행·부팅 검증 없음

## 1. 목적과 대상 보드

- 목적: WSL2 Ubuntu에서 Debian 13(trixie) armhf 시스템 구성 → microSD 이미지 파일 생성
- 비목적: 보드 OS 설치, SD 카드 직접 기록
- 대상: NanoPi NEO (Allwinner H3)
  - 아키텍처: armhf
  - 장치 트리: `sun8i-h3-nanopi-neo.dtb`
  - 부트로더: `/usr/lib/u-boot/nanopi_neo/u-boot-sunxi-with-spl.bin`
- NanoPi 2, NEO2 등 다른 보드: 아키텍처·DTB·부트로더 별도 확인 필요
- 배포판: `trixie` 고정. 최신 릴리스 자동 검색 없음

## 2. 전체 흐름

```text
WSL2 Ubuntu(root)
  → 호스트 도구 설치
  → debootstrap으로 armhf 최소 파일 시스템 생성
  → QEMU + chroot로 ARM 패키지 초기화
  → 커널·U-Boot·SSH·네트워크·점검 도구·개발 환경 설치
  → 네트워크·RAM 로그·시간·로그인 설정, USB 보정 DTB 생성
  → MBR + ext4 + U-Boot 이미지 조립
  → Windows 폴더로 복사, SHA-256 생성
  → syft 있으면 SBOM 생성
```

- 단계: `### 1` ~ `### 7`, 추가 단계 `### 4b`(개발 환경), `### 4c`(E3DP 패키지)

## 3. 변수와 실행 환경

| 변수 | 기본값 | 역할 |
|---|---|---|
| `WORK` | `/root/dpbuild` | Linux 작업 폴더 |
| `ROOTFS` | `/root/dpbuild/rootfs` | 대상 루트 파일 시스템 |
| `IMG` | `/root/dpbuild/e3dp-poc-debian13-armhf.img` | 조립 중 이미지 |
| `OUT` | `/mnt/c/ges/project/08_dp/poc` | Windows 출력 폴더 |
| `IMG_SIZE_MB` | 빈 값(자동 계산) | 이미지 크기(MiB). 미지정 시 `rootfs 사용량 × 1.2 + 128` |
| `ROOT_PW` | `ges000` | root 비밀번호 |
| `PI_PW` | `ges000` | pi 비밀번호 |
| `MIRROR` | `http://deb.debian.org/debian` | 패키지 저장소 |
| `SBOM_FORMAT` | `cyclonedx-json` | SBOM 형식. `spdx-json` 선택 가능 |
| `SBOM_FULL` | `0` | `1`: 전체 카탈로그, 파일 항목 제거 생략 |
| `SBOM` | `$OUT/e3dp-poc-debian13-armhf_sbom.json` | SBOM 파일 |

- 외부 변경 가능: `OUT`, `IMG_SIZE_MB`, `ROOT_PW`, `PI_PW`, `SBOM_FORMAT`, `SBOM_FULL` (`${변수:-기본값}`)
- 이미지 이름: 크기 변경과 무관하게 동일
- 로그: `SCRIPT_DIR/YYYYMMDD_HHMMSS.log` (KST), `tee -a`로 화면·파일 동시 기록. 스크립트 폴더 쓰기 권한 필요
- 전제: root 권한 WSL2 Ubuntu, 인터넷, Linux·Windows 디스크 여유 공간

## 4. 단계별 구성

### 1단계: 호스트 도구 설치

| 도구 | 목적 |
|---|---|
| `debootstrap` | Debian 기본 시스템 생성 |
| `qemu-user-static`, `binfmt-support` | ARM 실행 파일 실행 |
| `e2fsprogs` | ext4 생성 |
| `fdisk` | `sfdisk`로 파티션 테이블 생성 |
| `debian-archive-keyring` | 저장소 서명 검증 |
| `device-tree-compiler` | `dtc`, `fdtoverlay`로 USB 보정 DTB 생성 |

- `DEBIAN_FRONTEND=noninteractive` 적용
- 호스트 환경 변경됨

### 2단계: debootstrap 1단계

- 기존 마운트 정리 → `/root/dpbuild` 전체 삭제 → 작업 폴더 재생성 (증분 빌드 아님)
- `debootstrap --arch=armhf --foreign --variant=minbase` (`ca-certificates` 포함)
- `/usr/bin/qemu-arm-static`을 대상 루트에 복사

### 3단계: ARM 초기화와 기본 설정

- `chroot "$ROOTFS" /debootstrap/debootstrap --second-stage` 실행
- QEMU·호스트 binfmt 등록에 의존. 스크립트에 등록 상태 검사·복구 코드 없음
- `/proc`, `/sys`, `/dev`, `/dev/pts` 마운트
- `policy-rc.d` 종료 코드 `101`: 빌드 중 서비스 시작 차단

| 설정 | 내용 |
|---|---|
| APT 저장소 | `trixie main`, `trixie-updates main`, `trixie-security main` |
| 호스트 이름 | `E3-DP-POC` |
| `/etc/hosts` | localhost, 장치 호스트 이름 |
| 루트 마운트 | `/dev/mmcblk0p1`, ext4, `defaults,noatime` |
| 최대 절전 복귀 | `RESUME=none` |
| tmpfs | `/var/log` 32 MiB, `/var/tmp` 32 MiB, `/tmp` 64 MiB, `/dev/shm` 64 MiB |
| 로그 디렉터리 | tmpfiles로 `/var/log/apt`, `/var/log/private` 생성 |
| initramfs | 커널 설치 전 `FSTYPE=ext4`, `sunxi-mmc`, `phy-sun4i-usb` 지정 |

- 루트 장치: UUID 대신 `/dev/mmcblk0p1` 고정. SD 카드가 이 이름으로 인식되어야 함

### 4단계: 커널과 운영 도구

- `apt-get install --no-install-recommends` (권장 패키지 제외, 필수 의존성 포함)

| 분류 | 패키지 |
|---|---|
| 커널·부팅 | `linux-image-armmp`, `u-boot-sunxi`, `initramfs-tools` |
| 시스템 관리 | `systemd-sysv`, `udev`, `kmod` |
| 네트워크 | `iproute2`, `iputils-ping`, `systemd-resolved` |
| 원격 접속 | `openssh-server` |
| 편집·파일 시스템 | `nano`, `less`, `e2fsprogs` |
| 파티션 | `fdisk`(`sfdisk` 포함), `util-linux-extra` |
| 시간·로그 | `fake-hwclock`, `systemd-timesyncd`, `logrotate` |
| 무선 규제 | `wireless-regdb` (Wi-Fi 접속 설정 없음) |
| 하드웨어 점검 | `gpiod`, `i2c-tools`, `usbutils`, `ethtool` |
| 통신·분석 | `net-tools`, `curl`, `tcpdump`, `strace`, `file`, `htop`, `lsof`, `tmux`, `traceroute`, `mtr-tiny`, `iftop`, `nload`, `ngrep`, `bind9-dnsutils`, `netcat-openbsd`, `socat`, `arping`, `conntrack` |

- 커널·U-Boot: 소스 빌드 없이 Debian 패키지 바이너리 사용
- 점검 도구 설치 ≠ GPIO/I2C 활성화·핀 설정
- 시간대 `Asia/Seoul`, APT 캐시 정리
- GUI·업무 애플리케이션 설치 없음

### 4b단계: 개발 환경

- 도구: `build-essential`, `gdb`, `make`, `cmake`, `ninja-build`, `pkg-config`, `autoconf`, `automake`, `libtool`, `git`, `patch`, `rsync`, `xz-utils`, `wget`
- Python: Debian `python3`, `python3-venv`, `python3-pip`, `python3-dev`, `python-is-python3` (소스 빌드 없음)
- 라이브러리: SSL, 압축, SQLite, readline 등 개발 패키지
- 마지막에 Python 표준 모듈 import, Python·GCC 버전 출력
- 버전: 빌드 시점 저장소 기준

### 4c단계: 기존 E3DP 패키지 보강

- 기준: `E3DP_OS_20250901_V030112.img`에서 쓰던 도구 중 Debian 13 제공분
- 포함: `sudo`, `vim`, FTP/Telnet, 무선·Bluetooth, 오디오, 시스템 점검, 멀티미디어·USB 개발 라이브러리
- 설치 목록: 8.7 참조
- 제외: Ubuntu 전용, Python 2, GUI, 저장소에 없는 도구, NetworkManager(systemd-networkd 사용)
- 대체: `fw_printenv`/`fw_setenv` → `libubootenv-tool`, JPEG 개발 → `libjpeg-dev`
- 버전 고정 없음
- 기존 이미지의 애플리케이션·설정 복사 없음
- `dnsmasq`: 설치 후 자동 시작 비활성화. 사용 시 DNS/DHCP 역할·포트 충돌 확인 후 활성화

### 5단계: 네트워크, 로그인, 부팅 설정

**유선 네트워크**
- `10-eth0.link`: `Path=platform-1c30000.ethernet` → 내장 EMAC = `eth0`
- `11-eth1.link`: 그 외 이더넷 → `eth1`
- `20-eth0.network`: DHCP
- `21-eth1.network`: `192.168.123.2/24`, `ConfigureWithoutCarrier=yes`
- networkd, resolved, ssh 활성화, DNS stub 링크 생성
- Wi-Fi 접속 설정 없음
- 추가 이더넷이 여러 개면 모두 `eth1`을 요청 → 별도 이름 정책 필요
- 서비스 활성화 명령: `|| true` → 실패해도 빌드 계속

**네트워크 대기 해제**
- `systemd-networkd-wait-online.service` disable: 랜선 없는 환경의 부팅 지연 감소
- networkd(DHCP)는 유지
- 오류 무시(`|| true`)
- disable ≠ mask: 다른 유닛의 명시적 의존성으로는 시작될 수 있음

**로그와 디스크 쓰기**
- tmpfs(`/var/log`, `/var/tmp`, `/tmp`, `/dev/shm`): 재부팅 시 소멸
- `/var/lib`, `/var/cache`: 디스크 유지
- journald: `Storage=volatile` (RAM 전용, 최대 8M, 파일당 1M, 가득 차면 오래된 것부터 삭제)
- logrotate: `/var/log/*.log`, 매시간 검사, `size 1M`, `rotate 10`, `compress`, `delaycompress`, `copytruncate`, 상태 파일 `/run/logrotate.status`
- 루트 ext4는 읽기·쓰기 상태 → 전원 차단 안전성 미보장

**시간과 타이머**
- 활성화: `systemd-timesyncd`, `fake-hwclock` (빌드 시각을 `/etc/fake-hwclock.data`에 저장)
- 비활성화: `apt-daily.timer`, `apt-daily-upgrade.timer`, `dpkg-db-backup.timer`, `e2scrub_all.timer`, `fstrim.timer`
- 유지: `fake-hwclock-save.timer`

**첫 부팅 루트 확장**
- 파일: `/usr/local/sbin/expand-rootfs.sh`, `expand-rootfs.service` (활성화)
- 동작
  1. `findmnt -n -o SOURCE /`로 루트 장치 확인 (`ROOT_PART` 환경변수 우선)
  2. 장치명이 `*p1`일 때만 처리 (예: `/dev/mmcblk0p1` → `/dev/mmcblk0`)
  3. `sfdisk --no-reread -N 1`에 `, +` 입력 → 1번 파티션 확장
  4. `partx -u` → `resize2fs`
  5. 성공 시 `/var/lib/expand-rootfs.done` 생성 → `ConditionPathExists`로 이후 부팅 건너뜀
- 로그: `/var/log/expand-rootfs.log` (재부팅 시 소멸), 완료 파일은 유지
- 실패: 완료 파일 미생성 → 다음 부팅에서 재시도
- 미지원 장치명: 종료 코드 0, 완료 파일 미생성
- 판정: 서비스 상태가 아니라 완료 파일과 용량으로 확인
- `ROOT_PART` 오지정 시 다른 디스크의 1번 파티션 변경 위험 → 일반 사용 시 미설정

**SSH**
- `/etc/ssh/sshd_config.d/10-poc.conf`: `PermitRootLogin yes`, `PasswordAuthentication yes`
- root 비밀번호: `ROOT_PW`

**계정과 빌드 식별자**
- `pi` 계정: 홈 디렉터리, Bash, `sudo`·`dialout` 그룹, 비밀번호 `PI_PW`
- root 비밀번호 변경이 pi에 자동 반영되지 않음
- `/etc/os-release`: 기존 `BUILD_ID` 삭제 → KST `YYYYMMDD_HHMMSS` 기록

**시리얼 콘솔**
- `serial-getty@ttyS0.service` override: root 자동 로그인(비밀번호 없음)
- 커널 콘솔: `ttyS0,115200`
- agetty: 복수 baud rate 지정

**커널 선택**
- `/boot/vmlinuz-*` 버전순 정렬 후 마지막 항목 선택
- 해당 버전의 `sun8i-h3-nanopi-neo.dtb` 사용
- 외부 최신 커널 조회 없음

**initramfs 검증**
- `sunxi-mmc` 없음 또는 검사 파이프라인 실패 → 중단
- `fsck`/`e2fsck` 없음 → 경고만 출력
- `grep -q` 미사용: 조기 종료로 인한 SIGPIPE 방지를 위해 전체 입력 읽음

**USB 보정 DTB**
- 목적: E3-DP 내부망 USB 이더넷(AX88772)용 USB1/USB2 호스트 활성화
- 대상 노드: `/soc/usb@1c1b000`, `1c1b400`, `1c1c000`, `1c1c400` → `status = "okay"`
- `dtc`로 오버레이 컴파일 → `fdtoverlay`로 기본 NEO DTB에 병합
- 결과: `/boot/dtb/sun8i-h3-nanopi-neo-e3dp.dtb`
- 네 노드 적용 검사, 실패 시 중단
- extlinux가 이 DTB를 직접 사용

**extlinux 설정** (`/boot/extlinux/extlinux.conf`)

```text
kernel /boot/vmlinuz-<선택된 커널 버전>
initrd /boot/initrd.img-<선택된 커널 버전>
fdt /boot/dtb/sun8i-h3-nanopi-neo-e3dp.dtb
append root=/dev/mmcblk0p1 rw rootwait console=ttyS0,115200 earlycon
```

- `kernel`: Linux 커널
- `initrd`: 초기 부팅 환경
- `fdt`: 장치 트리
- `rw`: 루트 읽기·쓰기
- `rootwait`: 루트 장치 대기
- `console`, `earlycon`: 시리얼 콘솔, 초기 부팅 로그

**마무리**
- U-Boot 바이너리를 작업 폴더로 복사
- 제거: `policy-rc.d`, `qemu-arm-static`, APT 목록·캐시
- 마운트 정리
- `installed packages`: dpkg 상태 파일의 `Package:` 항목 수 (개별 설치 검증 아님)

### 6단계: microSD 이미지 조립

- 이미지 크기 결정 (`IMG_SIZE_MB` 미지정 시)
  - `ROOT_MB=$(du -sm "$ROOTFS" | cut -f1)`
  - `IMG_SIZE_MB = ROOT_MB × 1.2 + 128` (ext4 메타데이터·저널 여유)
  - 지정 시 그 값으로 고정. 내용물보다 작으면 `mkfs.ext4 -d` 단계에서 실패
- `truncate`: 결정된 크기로 이미지 파일 생성
- `sfdisk`: DOS/MBR, 파티션 1개, 타입 `83`, bootable

```text
이미지 시작
  0 B             MBR 및 파티션 테이블
  8 KiB           U-Boot + SPL 기록 시작
  1 MiB           1번 파티션 시작: ext4 루트
  이미지 끝       1번 파티션 끝
```

- 시작값 `2048` = 512바이트 섹터 기준 1 MiB
- `FS_KB` = 전체 크기 − 1 MiB
- `mkfs.ext4 -d "$ROOTFS" -E offset=1048576`: 이미지 내부에 ext4 생성 및 파일 채움 (loop 장치·이미지 마운트 미사용)
- `dd seek=8 bs=1k conv=notrunc`: 이미지 시작 8 KiB 위치에 U-Boot 기록
- 별도 FAT 부트 파티션 없음. `/boot`는 ext4 루트 안

부팅 흐름 (설계 기준, 실제 성공 여부는 별도 검증):

```text
SoC 부트 ROM → SPL → U-Boot → extlinux 설정
             → 커널 + initramfs + DTB → 루트 ext4 → systemd 서비스
```

- 커널·initramfs·DTB를 작업 폴더에 복사, `sync`
- 이미지를 `OUT`으로 복사, SHA-256 파일 기록

### 7단계: SBOM

- 조건: 호스트에 `syft` 존재
- 대상: `dir:$ROOTFS` (이미지 바이너리 아님), dpkg 카탈로거
- 형식: 기본 CycloneDX JSON, `SBOM_FORMAT=spdx-json` 선택 가능
- `SBOM_FULL=1`: syft 기본 카탈로그, 파일 항목 제거 생략
- 후처리(Python): 기본 모드 + CycloneDX + `python3` 존재 시 파일 타입 component와 dependencies 참조 제거. 그 외 생략
- SBOM = 패키지 목록. 취약점 검사 결과 아님
- `syft` 설치 단계 없음. 없으면 SBOM만 건너뜀
- `syft`·Python 후처리 실패 → `set -e`로 중단. 이미지·체크섬은 이미 생성된 상태일 수 있음

## 5. 결과물

| 위치 | 내용 |
|---|---|
| `C:\ges\project\08_dp\poc` | 기본 출력 폴더 |
| 출력 폴더 | `e3dp-poc-debian13-armhf.img` |
| 출력 폴더 | `e3dp-poc-debian13-armhf.img.sha256` |
| 출력 폴더 | `e3dp-poc-debian13-armhf_sbom.json` (syft 있을 때) |
| `/root/dpbuild` | rootfs, 작업 이미지, U-Boot, 커널, initramfs, 기본 DTB, USB DTS·DTBO·검사용 DTS |
| 스크립트 폴더 | `YYYYMMDD_HHMMSS.log` (KST) |

- SHA-256: 무결성 비교용. 보드 호환성·부팅 성공 미보장
- 미포함: SD 카드 기록, 보드 부팅, 네트워크 접속 검사
- 재빌드: Linux 작업 폴더 삭제, 출력 이미지·체크섬 동일 이름으로 덮어씀

## 6. 오류 처리와 PoC 특성

- `set -euo pipefail`: 명령 실패, 미정의 변수, 파이프라인 실패 시 중단
- 예외: `|| true`가 붙은 마운트 정리·서비스 활성화는 실패 무시
- `trap cleanup EXIT`: 종료 시 `/dev/pts`, `/dev`, `/proc`, `/sys` 마운트 정리(`umount -l`, 지연 해제)
- 롤백 없음: 중단된 빌드의 작업·출력 파일 유지
- PoC 설정 (운영 전환 시 재검토)
  - 기본 root 비밀번호
  - root SSH 비밀번호 로그인
  - 시리얼 root 자동 로그인
- 미구현: 주변 장치별 설정, 애플리케이션 배포, 부팅 시험
- 이미지 크기: rootfs 사용량 기반 자동 계산. 큰 SD 카드에서 확장 서비스 성공 시 루트 공간 증가
- 패키지 버전 미고정 → 실행 시점별 커널·패키지 버전 상이

## 7. 상태 확인 (검토 시점)

- 이미지: 3,221,225,472바이트 (3072 MiB). 고정 크기 방식으로 만든 이전 결과. 자동 계산 방식은 미실행
- `.sha256`: 94바이트
- 최신 로그 `20261014_152522.log`: `### DONE`으로 종료 → 스크립트 실행 완료 상태
- 미검사: 이미지 내용, 체크섬 재계산, 실제 보드 부팅

## 8. 수동 따라하기

- 목적: 자동 스크립트 없이 같은 구성의 이미지 생성
- 아래 명령은 문서 작성 중 실행하지 않음
- 명령 결과를 확인한 뒤 다음 명령 진행
- 명령은 한 줄씩 입력. 화면에서 줄바꿈되어도 한 줄. `\` 입력·중간 Enter 금지

Windows PowerShell에서 배포판 확인 후 Ubuntu를 root로 연다. `Ubuntu`는 실제 배포판 이름으로 변경.

```powershell
wsl --list --verbose
wsl -d Ubuntu -u root
```

**실행 위치**
- 표시 없으면 WSL Ubuntu의 root Bash
- `chroot` 안: `/etc/...` = 제작 중인 Debian의 파일
- `exit` 후 WSL: `$ROOTFS/etc/...`로 접근
- WSL의 `/etc` 직접 수정 금지

**vi 편집 방법**
1. `vi "파일 경로"` 실행
2. 기존 설정 교체 시 `Esc` → `gg` → `dG`로 내용 삭제
3. 들여쓰기가 있는 내용(logrotate, extlinux, Python)은 `:set paste` 입력
4. `i`로 입력 모드 진입 → 파일 내용만 붙여 넣기 (코드 블록 경계·설명 문장 제외)
5. `Esc` → `:wq` → Enter로 저장·종료 (저장 없이 종료: `Esc` → `:q!` → Enter)
6. `cat "파일 경로"`로 확인
- vi에서는 `$변수`가 치환되지 않음 → 안내된 실제 값 입력

### 8.1 WSL 작업 경로 준비

```bash
set -o pipefail
BUILD_TAG=$(TZ=Asia/Seoul date +%Y%m%d-%H%M%S)
WORK="/root/dpbuild-manual-$BUILD_TAG"
ROOTFS="$WORK/rootfs"
IMG="$WORK/e3dp-poc-debian13-armhf.img"
OUT="/mnt/c/ges/project/08_dp/poc/manual-$BUILD_TAG"
MIRROR=http://deb.debian.org/debian
mkdir -p "$ROOTFS" "$OUT"
printf 'WORK=%s\nROOTFS=%s\nIMG=%s\nOUT=%s\n' "$WORK" "$ROOTFS" "$IMG" "$OUT"
whoami
df -h /root /mnt/c
```

- `whoami` = `root` 확인
- 출력된 경로 기록
- 기존 `/root/dpbuild` 미삭제. 별도 폴더·별도 Windows 출력 폴더 사용
- 터미널 재진입 시 재대입: `WORK`, `ROOTFS`, `IMG`, `OUT`, `KVER`, `DTB` (`KVER`, `DTB`는 8.11 첫 두 줄 재실행)
- 새 `BUILD_TAG`로 중간 작업 이어가기 금지
- 자동 정리 함수·trap 없음 → 중단 시에도 8.12 마운트 해제 수행
- 설정 파일 수정 시 해당 절 재수행 후 이미지 재조립

### 8.2 1. host tools

- 수동 편집용 `vim` 추가 설치
- 설치 로그 오류 확인

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y debootstrap qemu-user-static binfmt-support e2fsprogs fdisk debian-archive-keyring device-tree-compiler vim
```

### 8.3 2. debootstrap stage 1 (armhf, trixie)

- 최소 Debian 파일 다운로드, QEMU 복사
- 이 단계의 결과 = 미완성 OS

```bash
debootstrap --arch=armhf --foreign --variant=minbase --include=ca-certificates trixie "$ROOTFS" "$MIRROR"
cp /usr/bin/qemu-arm-static "$ROOTFS/usr/bin/"
```

- 다음 단계에서 `Exec format error` 발생 시
  1. `update-binfmts --display qemu-arm`으로 등록 상태 확인
  2. `update-binfmts --enable qemu-arm`으로 활성화
  3. 실패한 명령부터 재실행

### 8.4 3. stage 2 (under qemu-arm)

- 2단계 초기화 성공 후 가상 파일 시스템 마운트
- `policy-rc.d`: 빌드 중 서비스 시작 차단
- initramfs 설정: 커널 설치 전에 작성

```bash
chroot "$ROOTFS" /debootstrap/debootstrap --second-stage

mount -t proc proc "$ROOTFS/proc"
mount -t sysfs sys "$ROOTFS/sys"
mount --bind /dev "$ROOTFS/dev"
mount --bind /dev/pts "$ROOTFS/dev/pts"
```

```bash
vi "$ROOTFS/usr/sbin/policy-rc.d"
```

파일 내용:

```text
#!/bin/sh
exit 101
```

```bash
chmod +x "$ROOTFS/usr/sbin/policy-rc.d"
```

```bash
vi "$ROOTFS/etc/apt/sources.list"
```

파일 내용:

```text
deb http://deb.debian.org/debian trixie main
deb http://deb.debian.org/debian trixie-updates main
deb http://deb.debian.org/debian-security trixie-security main
```

```bash
vi "$ROOTFS/etc/hostname"
```

파일 내용:

```text
E3-DP-POC
```

```bash
vi "$ROOTFS/etc/hosts"
```

파일 내용:

```text
127.0.0.1	localhost
127.0.1.1	E3-DP-POC
```

```bash
vi "$ROOTFS/etc/fstab"
```

파일 내용:

```text
/dev/mmcblk0p1  /          ext4   defaults,noatime  0 1
tmpfs           /var/log   tmpfs  defaults,noatime,nosuid,nodev,noexec,mode=0755,size=32m   0 0
tmpfs           /var/tmp   tmpfs  defaults,noatime,nosuid,nodev,mode=1777,size=32m          0 0
tmpfs           /tmp       tmpfs  defaults,noatime,nosuid,nodev,mode=1777,size=64m          0 0
tmpfs           /dev/shm   tmpfs  defaults,nosuid,nodev,noexec,mode=1777,size=64m           0 0
```

```bash
mkdir -p "$ROOTFS/etc/tmpfiles.d"
```

```bash
vi "$ROOTFS/etc/tmpfiles.d/var-log-tmpfs.conf"
```

파일 내용:

```text
d /var/log/apt     0755 root root -
d /var/log/private 0700 root root -
```

```bash
mkdir -p "$ROOTFS/etc/initramfs-tools/conf.d"
```

```bash
vi "$ROOTFS/etc/initramfs-tools/conf.d/resume"
```

파일 내용:

```text
RESUME=none
```

```bash
vi "$ROOTFS/etc/initramfs-tools/conf.d/fstype"
```

파일 내용:

```text
FSTYPE=ext4
```

```bash
vi "$ROOTFS/etc/initramfs-tools/modules"
```

파일 내용:

```text
sunxi-mmc
phy-sun4i-usb
```

### 8.5 4. packages (kernel, u-boot, ssh, network)

- `chroot`로 대상 Debian에 진입해 패키지 설치, 성공 후 `exit`
- chroot에서 서비스 실제 시작 없음

```bash
chroot "$ROOTFS" /bin/bash
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update
apt-get install -y --no-install-recommends linux-image-armmp u-boot-sunxi initramfs-tools systemd-sysv udev kmod iproute2 iputils-ping openssh-server systemd-resolved nano less e2fsprogs gpiod i2c-tools usbutils ethtool net-tools curl tcpdump strace file fdisk htop lsof tmux traceroute mtr-tiny iftop nload ngrep bind9-dnsutils netcat-openbsd socat arping conntrack util-linux-extra fake-hwclock systemd-timesyncd wireless-regdb logrotate
ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime
apt-get clean
exit
```

- `chroot` ~ `exit` 사이: 대상 Debian 안에서 입력
- `exit` 후: WSL 작업 변수 재사용 가능

### 8.6 4b. dev environment (gcc/make/cmake/gdb + Debian 기본 python3)

- 대상 Debian에 재진입해 컴파일러·Python 개발 환경 설치
- Python 모듈 검사에서 `ok` 출력 확인

```bash
chroot "$ROOTFS" /bin/bash
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update
apt-get install -y --no-install-recommends build-essential gdb make cmake ninja-build pkg-config autoconf automake libtool git patch rsync xz-utils wget python3 python3-venv python3-pip python3-dev python-is-python3 libssl-dev zlib1g-dev libffi-dev libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev libncurses-dev libgdbm-dev uuid-dev libzstd-dev libexpat1-dev
apt-get clean
python3 -c "import ssl, sqlite3, zlib, bz2, lzma, ctypes, uuid, readline, sys; print('python', sys.version.split()[0], 'ok')"
gcc --version | head -1
exit
```

### 8.7 4c. legacy E3DP packages (E3DP_OS_20250901_V030112.img 에 있던 패키지의 Debian 13 최신판)

- 기존 E3DP 도구 추가
- `dnsmasq` 자동 시작 비활성화, 필요 시 별도 설정

```bash
chroot "$ROOTFS" /bin/bash
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update
apt-get install -y --no-install-recommends sudo vim expect telnet telnetd ftp vsftpd openbsd-inetd dnsmasq hostapd wpasupplicant wireless-tools iw rfkill bluez udhcpd ppp fping iptables usb-modeswitch alsa-utils madplay figlet toilet bc busybox cpio psmisc aptitude cron openssl whiptail bzip2 lsb-release fakeroot kbd manpages manpages-dev openssh-sftp-server netbase acl at ncurses-term memtester iperf iperf3 libubootenv-tool cifs-utils libx264-dev libmp3lame-dev libpulse-dev libv4l-dev libjpeg-dev libasound2-dev libusb-1.0-0-dev libusb-dev libusb-0.1-4
systemctl disable dnsmasq
apt-get clean
exit
```

### 8.8 5. config (network, ssh, root pw, extlinux)

- 네트워크·계정·RAM 로그·첫 부팅 확장·부팅 파일 설정
- vi 편집은 모두 WSL에서 수행
- 내장 이더넷 = eth0 DHCP, 그 외 이더넷 = eth1 고정 주소

```bash
vi "$ROOTFS/etc/systemd/network/10-eth0.link"
```

파일 내용:

```text
[Match]
Path=platform-1c30000.ethernet

[Link]
Name=eth0
```

```bash
vi "$ROOTFS/etc/systemd/network/11-eth1.link"
```

파일 내용:

```text
[Match]
Type=ether
Path=!platform-1c30000.ethernet

[Link]
Name=eth1
```

```bash
vi "$ROOTFS/etc/systemd/network/20-eth0.network"
```

파일 내용:

```text
[Match]
Name=eth0

[Network]
DHCP=yes
```

```bash
vi "$ROOTFS/etc/systemd/network/21-eth1.network"
```

파일 내용:

```text
[Match]
Name=eth1

[Network]
Address=192.168.123.2/24
ConfigureWithoutCarrier=yes
```

```bash
chroot "$ROOTFS" systemctl enable systemd-networkd systemd-resolved ssh
chroot "$ROOTFS" systemctl disable systemd-networkd-wait-online.service
ln -sf /run/systemd/resolve/stub-resolv.conf "$ROOTFS/etc/resolv.conf"
mkdir -p "$ROOTFS/etc/ssh/sshd_config.d"
```

```bash
vi "$ROOTFS/etc/ssh/sshd_config.d/10-poc.conf"
```

파일 내용:

```text
PermitRootLogin yes
PasswordAuthentication yes
```

- root·pi 비밀번호: 각각 2회 입력
- 자동 스크립트 기본값: 모두 `ges000` (변경 가능)
- 입력 문자가 화면에 표시되지 않는 것은 정상

```bash
chroot "$ROOTFS" passwd root
chroot "$ROOTFS" useradd -m -s /bin/bash -G sudo,dialout pi
chroot "$ROOTFS" passwd pi

sed -i '/^BUILD_ID=/d' "$ROOTFS/etc/os-release"
echo "BUILD_ID=$(TZ=Asia/Seoul date +%Y%m%d_%H%M%S)" >> "$ROOTFS/etc/os-release"

mkdir -p "$ROOTFS/etc/systemd/journald.conf.d"
```

### 8.9 RAM 로그와 순환 설정

- `/var/log`, `/var/tmp`, `/tmp`, `/dev/shm`: 8.4의 tmpfs. 재부팅 시 소멸
- journald: RAM 전용 (`Storage=volatile`, `/run/log/journal`). 디스크 I/O 없음, 최대 8 MiB, 가득 차면 오래된 것부터 삭제(순환). 재부팅 시 소멸
- `logs` 래퍼(`/usr/local/bin/logs`): docker logs 와 같은 사용법. `logs 서비스`, `logs 서비스 -f`, `logs 서비스 -n 100`, `logs -f`(전체)
- 일반 로그: 1 MiB 초과 시 매시간 검사에서 순환
- `/var/lib`, `/var/cache`: 디스크 유지

```bash
vi "$ROOTFS/etc/systemd/journald.conf.d/10-volatile.conf"
```

파일 내용:

```text
[Journal]
Storage=volatile
RuntimeMaxUse=8M
RuntimeMaxFileSize=1M
ForwardToSyslog=no
ForwardToKMsg=no
ForwardToConsole=no
ForwardToWall=no
```

```bash
rm -rf "$ROOTFS/var/log/journal"
```

`logs` 래퍼 (`/usr/local/bin/logs`, 실행 권한 필요):

```bash
vi "$ROOTFS/usr/local/bin/logs"
chmod +x "$ROOTFS/usr/local/bin/logs"
```

파일 내용:

```sh
#!/bin/sh
UNIT=
case "${1:-}" in -*|"") ;; *) UNIT="-u $1"; shift ;; esac
FOLLOW=
for a in "$@"; do [ "$a" = "-f" ] && FOLLOW=1; done
if [ -n "$FOLLOW" ] && ! echo " $* " | grep -q ' -n '; then set -- "$@" -n 200; fi
exec journalctl $UNIT --no-pager -o short-iso "$@"
```

```bash
vi "$ROOTFS/etc/logrotate.d/poc-logs"
```

파일 내용:

```text
/var/log/*.log {
    size 1M
    rotate 10
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

```bash
mkdir -p "$ROOTFS/etc/systemd/system/logrotate.timer.d" "$ROOTFS/etc/systemd/system/logrotate.service.d"
```

```bash
vi "$ROOTFS/etc/systemd/system/logrotate.timer.d/hourly.conf"
```

파일 내용:

```text
[Timer]
OnCalendar=
OnCalendar=hourly
```

```bash
vi "$ROOTFS/etc/systemd/system/logrotate.service.d/status-in-ram.conf"
```

파일 내용:

```text
[Service]
ExecStart=
ExecStart=/usr/sbin/logrotate -s /run/logrotate.status /etc/logrotate.conf
```

### 8.10 첫 부팅 루트 파일 시스템 확장

- 카드가 이미지보다 클 때 첫 부팅에서 파티션·ext4를 카드 끝까지 확장
- 아래 파일은 보드 첫 부팅에 실행되는 파일 (이미지 제작용 아님)

```bash
vi "$ROOTFS/usr/local/sbin/expand-rootfs.sh"
```

파일 내용:

```text
#!/bin/sh
LOG=/var/log/expand-rootfs.log
exec >>"$LOG" 2>&1
echo "=== $(date) expand-rootfs start"
ROOT_PART=${ROOT_PART:-$(findmnt -n -o SOURCE /)}
case "$ROOT_PART" in
  *p1) DISK=${ROOT_PART%p1} ;;
  *) echo "unsupported root device: $ROOT_PART"; exit 0 ;;
esac
echo "root=$ROOT_PART disk=$DISK"
echo ", +" | sfdisk --no-reread -N 1 "$DISK" || { echo "sfdisk failed"; exit 1; }
partx -u "$DISK" || { echo "partx failed"; exit 1; }
resize2fs "$ROOT_PART" || { echo "resize2fs failed"; exit 1; }
mkdir -p /var/lib && touch /var/lib/expand-rootfs.done
echo "done: $(lsblk -n -o SIZE "$ROOT_PART" 2>/dev/null)"
```

```bash
chmod +x "$ROOTFS/usr/local/sbin/expand-rootfs.sh"
```

```bash
vi "$ROOTFS/etc/systemd/system/expand-rootfs.service"
```

파일 내용:

```text
[Unit]
Description=Expand root filesystem to fill the SD card (first boot)
ConditionPathExists=!/var/lib/expand-rootfs.done
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/expand-rootfs.sh

[Install]
WantedBy=multi-user.target
```

```bash
chroot "$ROOTFS" systemctl enable expand-rootfs.service

mkdir -p "$ROOTFS/etc/systemd/system/serial-getty@ttyS0.service.d"
```

```bash
vi "$ROOTFS/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf"
```

파일 내용:

```text
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 115200,57600,38400,9600 %I $TERM
```

### 8.11 커널 확인, USB 보정 DTB와 extlinux

- 설치된 커널 중 버전순 마지막 파일 선택
- initramfs의 SD 드라이버 확인
- USB1/USB2 네 노드를 활성화한 DTB 생성

```bash
KVER=$(basename "$(ls "$ROOTFS"/boot/vmlinuz-* | sort -V | tail -1)" | sed 's/vmlinuz-//')
DTB=$(ls "$ROOTFS"/usr/lib/linux-image-$KVER/sun8i-h3-nanopi-neo.dtb)
echo "kernel=$KVER dtb=$DTB"
chroot "$ROOTFS" lsinitramfs "/boot/initrd.img-$KVER" | grep -E '/sunxi[-_]mmc\.ko(\.(xz|gz|zst))?$' || echo "ERROR: initrd 에 sunxi-mmc 없음 -> 부팅 불가"
chroot "$ROOTFS" lsinitramfs "/boot/initrd.img-$KVER" | grep -E '(^|/)(fsck|e2fsck)$' || echo "WARNING: initrd 에 fsck/e2fsck 없음"
chroot "$ROOTFS" systemctl enable systemd-timesyncd fake-hwclock
chroot "$ROOTFS" systemctl disable apt-daily.timer apt-daily-upgrade.timer dpkg-db-backup.timer e2scrub_all.timer fstrim.timer
chroot "$ROOTFS" fake-hwclock save
cat "$ROOTFS/etc/fake-hwclock.data"
```

```bash
vi "$WORK/e3dp-usb.dts"
```

파일 내용:

```text
/dts-v1/;
/plugin/;
/ {
	fragment@0 { target-path = "/soc/usb@1c1b000"; __overlay__ { status = "okay"; }; };
	fragment@1 { target-path = "/soc/usb@1c1b400"; __overlay__ { status = "okay"; }; };
	fragment@2 { target-path = "/soc/usb@1c1c000"; __overlay__ { status = "okay"; }; };
	fragment@3 { target-path = "/soc/usb@1c1c400"; __overlay__ { status = "okay"; }; };
};
```

```bash
dtc -@ -I dts -O dtb -o "$WORK/e3dp-usb.dtbo" "$WORK/e3dp-usb.dts"
mkdir -p "$ROOTFS/boot/dtb"
E3DP_DTB=/boot/dtb/sun8i-h3-nanopi-neo-e3dp.dtb
fdtoverlay -i "$DTB" -o "$ROOTFS$E3DP_DTB" "$WORK/e3dp-usb.dtbo"
dtc -I dtb -O dts -o "$WORK/e3dp-check.dts" "$ROOTFS$E3DP_DTB" 2>/dev/null
fdtget -t s "$ROOTFS$E3DP_DTB" /soc/usb@1c1b000 status
fdtget -t s "$ROOTFS$E3DP_DTB" /soc/usb@1c1b400 status
fdtget -t s "$ROOTFS$E3DP_DTB" /soc/usb@1c1c000 status
fdtget -t s "$ROOTFS$E3DP_DTB" /soc/usb@1c1c400 status
mkdir -p "$ROOTFS/boot/extlinux"
```

- `kernel=` 출력값 확인 → 아래 `<실제 커널 버전>` 두 곳에 입력 (꺾쇠 제거)

```bash
vi "$ROOTFS/boot/extlinux/extlinux.conf"
```

파일 내용:

```text
default debian
timeout 20
label debian
  menu label Debian 13 (PoC)
  kernel /boot/vmlinuz-<실제 커널 버전>
  initrd /boot/initrd.img-<실제 커널 버전>
  fdt /boot/dtb/sun8i-h3-nanopi-neo-e3dp.dtb
  append root=/dev/mmcblk0p1 rw rootwait console=ttyS0,115200 earlycon
```

```bash
UBOOT=$ROOTFS/usr/lib/u-boot/nanopi_neo/u-boot-sunxi-with-spl.bin
ls -l "$UBOOT"
cp "$UBOOT" "$WORK/"

rm -f "$ROOTFS/usr/sbin/policy-rc.d" "$ROOTFS/usr/bin/qemu-arm-static"
rm -rf "$ROOTFS/var/lib/apt/lists/"* "$ROOTFS/var/cache/apt/"*
chroot_dpkg_count=$(grep -c '^Package:' "$ROOTFS/var/lib/dpkg/status")
echo "installed packages: $chroot_dpkg_count"
```

확인 사항:
- `BUILD_ID`: `grep BUILD_ID "$ROOTFS/etc/os-release"`
- initramfs 검사 `ERROR` 출력 시 진행 중단. 대화형 셸의 `exit`는 세션·변수를 모두 삭제하므로 `exit 1` 미사용
- `fsck` `WARNING`: 별도 확인
- `fdtget` 네 결과: 모두 `okay`
- 서비스 명령: 오류를 숨기지 않음 → 실패 시 원인 확인

### 8.12 마운트 해제

- 이미지에 호스트 `/dev`, `/proc` 등이 섞이지 않도록 순서대로 해제
- 열려 있는 chroot 셸은 먼저 `exit`
- 작업 중단 시에도 동일 명령 사용

```bash
umount "$ROOTFS/dev/pts"
umount "$ROOTFS/dev"
umount "$ROOTFS/proc"
umount "$ROOTFS/sys"
findmnt -R "$ROOTFS"
```

- `findmnt`: 작업 폴더 아래 마운트 없어야 함 (목록 없음 + 종료 코드 1 = 정상)
- `target is busy`: 사용 중인 셸·프로세스 종료 후 재해제
- 해제 실패 상태에서 조립 금지

### 8.13 MBR·ext4·U-Boot 이미지 조립

```bash
vi "$WORK/partition.layout"
```

파일 내용:

```text
label: dos
start=2048, type=83, bootable
```

- 이미지 크기: `rootfs 사용량 × 1.2 + 128 MiB` 자동 계산 (`du -sm`)
- `truncate`: 계산된 크기의 파일 생성
- `sfdisk`: MBR·파티션 생성
- `mkfs.ext4`: 1 MiB 위치부터 ext4 생성 + rootfs 복사
- `dd`: SPL 포함 U-Boot를 8 KiB 위치에 기록
- 대상: 물리 디스크 아님, `$IMG` 파일

```bash
ROOT_MB=$(du -sm "$ROOTFS" | cut -f1)
IMG_SIZE_MB=$(( ROOT_MB * 12 / 10 + 128 ))
echo "rootfs=${ROOT_MB}MiB image=${IMG_SIZE_MB}MiB"
truncate -s "${IMG_SIZE_MB}M" "$IMG"
sfdisk "$IMG" < "$WORK/partition.layout"
FS_KB=$((IMG_SIZE_MB * 1024 - 1024))
mkfs.ext4 -F -L rootfs -d "$ROOTFS" -E offset=1048576 "$IMG" "${FS_KB}k"
dd if="$WORK/u-boot-sunxi-with-spl.bin" of="$IMG" bs=1k seek=8 conv=notrunc status=progress
cp "$ROOTFS/boot/vmlinuz-$KVER" "$ROOTFS/boot/initrd.img-$KVER" "$WORK/"
cp "$DTB" "$WORK/"
sync
cp "$IMG" "$OUT/"
cd "$OUT"
sha256sum e3dp-poc-debian13-armhf.img > e3dp-poc-debian13-armhf.img.sha256
sha256sum -c e3dp-poc-debian13-armhf.img.sha256
```

- 체크섬 검사 결과 `OK` 확인
- 이미지 앞 1 MiB: MBR + U-Boot. `/boot`는 ext4 안. 별도 FAT 파티션 없음

### 8.14 선택: OS 패키지 SBOM

- `command -v syft`로 설치 여부 확인
- 없으면 생략 (이미지·체크섬은 완성 상태)

```bash
SBOM="$OUT/e3dp-poc-debian13-armhf_sbom.json"
syft "dir:$ROOTFS" --select-catalogers dpkg -o "cyclonedx-json=$SBOM"
ls -lh "$SBOM"
```

- SPDX: `-o "spdx-json=$SBOM"`
- 전체 파일 카탈로그: `--select-catalogers dpkg` 제거
- 자동 스크립트와 동일한 후처리(파일 component·관련 dependencies 제거)가 필요하면 아래 파일 작성

```bash
vi "$WORK/trim_sbom.py"
```

파일 내용:

```python
import json, sys
p = sys.argv[1]
j = json.load(open(p, encoding="utf-8"))
files = {c.get("bom-ref") for c in j.get("components", []) if c.get("type") == "file"}
j["components"] = [c for c in j.get("components", []) if c.get("type") != "file"]
if "dependencies" in j:
    j["dependencies"] = [
        {**d, "dependsOn": [r for r in d.get("dependsOn", []) if r not in files]}
        for d in j["dependencies"] if d.get("ref") not in files
    ]
json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
```

```bash
python3 "$WORK/trim_sbom.py" "$SBOM"
python3 -m json.tool "$SBOM" > /dev/null
```

- 후처리 적용 대상: CycloneDX 기본 패키지 결과. SPDX·전체 카탈로그 제외

### 8.15 결과 확인과 보드 첫 부팅 점검

```bash
stat -c '%n : %s bytes' "$OUT/e3dp-poc-debian13-armhf.img"
sfdisk --dump "$IMG"
ls -lh "$OUT"
```

- 이미지 크기: 위 `image=` 출력값(MiB × 1,048,576바이트)과 일치
- 파티션: `start=2048`, `type=83`
- Windows 결과 폴더: `C:\ges\project\08_dp\poc\manual-<BUILD_TAG>`
- 이미지 생성·체크섬 확인 ≠ 보드 부팅 확인

이미지를 microSD에 기록하고 부팅한 뒤, **보드의 root 콘솔**에서 실행:

```bash
cat /etc/os-release
grep BUILD_ID /etc/os-release
id pi
systemctl status expand-rootfs.service --no-pager
cat /var/log/expand-rootfs.log
ls -l /var/lib/expand-rootfs.done
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
df -h /
ip -br address
timedatectl
systemctl is-enabled systemd-networkd systemd-resolved ssh systemd-timesyncd fake-hwclock
systemctl is-enabled dnsmasq
```

- 확장 로그: 첫 부팅 직후 확인 (재부팅 시 소멸, 완료 파일은 유지)
- 확장 판정: oneshot 서비스 inactive 표시가 아니라 완료 파일과 실제 용량으로 확인
- 확인 항목: eth0 DHCP 주소, eth1 `192.168.123.2/24`, pi의 sudo/dialout 그룹, BUILD_ID
- `dnsmasq`: `disabled`가 의도한 결과. 조회 명령의 종료 코드는 0이 아닐 수 있음
