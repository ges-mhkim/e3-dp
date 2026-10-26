#!/bin/bash
# NanoPi NEO (Allwinner H3) 용 Debian 13 (trixie) armhf PoC microSD 이미지 빌드
# WSL2 Ubuntu 에서 root 로 실행. 결과: $OUT/e3dp-poc-debian13-armhf.img
# PoC 전용: 보안보다 시험 편의를 우선함 (root 비밀번호 로그인 허용, 시리얼 자동 로그인, 점검 도구 포함)
set -euo pipefail

# 실행 로그: 화면과 스크립트 폴더에 표준 출력/오류를 함께 기록한다.
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LOG_FILE="$SCRIPT_DIR/$(TZ=Asia/Seoul date +%Y%m%d_%H%M%S).log"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "로그 파일: $LOG_FILE"

WORK=/root/dpbuild
ROOTFS=$WORK/rootfs
IMG=$WORK/e3dp-poc-debian13-armhf.img
OUT=${OUT:-/mnt/c/ges/project/08_dp/poc}
# 비우면 6단계에서 rootfs 크기로 자동 계산한다. 값을 지정하면 그 크기로 고정한다.
IMG_SIZE_MB=${IMG_SIZE_MB:-}
ROOT_PW=${ROOT_PW:-ges000}
PI_PW=${PI_PW:-ges000}
MIRROR=http://deb.debian.org/debian

cleanup() {
  for m in dev/pts dev proc sys; do umount -l "$ROOTFS/$m" 2>/dev/null || true; done
}
trap cleanup EXIT

echo "### 1. host tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq debootstrap qemu-user-static binfmt-support e2fsprogs fdisk debian-archive-keyring device-tree-compiler >/dev/null

echo "### 2. debootstrap stage 1 (armhf, trixie)"
cleanup
rm -rf "$WORK"; mkdir -p "$ROOTFS" "$OUT"
debootstrap --arch=armhf --foreign --variant=minbase \
  --include=ca-certificates \
  trixie "$ROOTFS" "$MIRROR"
cp /usr/bin/qemu-arm-static "$ROOTFS/usr/bin/"

echo "### 3. stage 2 (under qemu-arm)"
chroot "$ROOTFS" /debootstrap/debootstrap --second-stage

mount -t proc proc "$ROOTFS/proc"
mount -t sysfs sys "$ROOTFS/sys"
mount --bind /dev "$ROOTFS/dev"
mount --bind /dev/pts "$ROOTFS/dev/pts"

cat > "$ROOTFS/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
chmod +x "$ROOTFS/usr/sbin/policy-rc.d"

cat > "$ROOTFS/etc/apt/sources.list" <<EOF
deb $MIRROR trixie main
deb $MIRROR trixie-updates main
deb http://deb.debian.org/debian-security trixie-security main
EOF
echo "E3-DP-POC" > "$ROOTFS/etc/hostname"
printf '127.0.0.1\tlocalhost\n127.0.1.1\tE3-DP-POC\n' > "$ROOTFS/etc/hosts"
# microSD + 수시 전원 차단: 쓰기를 최소화한다. 로그/임시 파일은 RAM(tmpfs)에 두고 재부팅하면 버린다.
# 512MB RAM 이므로 tmpfs 상한을 작게 잡는다 (/tmp 기본값은 RAM 의 50%).
# /var/lib (dpkg DB, systemd 상태, expand-rootfs.done) 와 /var/cache 는 디스크에 남긴다.
# (/var/cache 를 tmpfs 로 하면 apt 가 받은 패키지가 RAM 을 점유함)
cat > "$ROOTFS/etc/fstab" <<'EOF'
/dev/mmcblk0p1  /          ext4   defaults,noatime  0 1
tmpfs           /var/log   tmpfs  defaults,noatime,nosuid,nodev,noexec,mode=0755,size=32m   0 0
tmpfs           /var/tmp   tmpfs  defaults,noatime,nosuid,nodev,mode=1777,size=32m          0 0
tmpfs           /tmp       tmpfs  defaults,noatime,nosuid,nodev,mode=1777,size=64m          0 0
EOF
# /var/log 가 tmpfs 로 가려지므로 부팅 때마다 필요한 디렉터리를 만든다.
mkdir -p "$ROOTFS/etc/tmpfiles.d"
cat > "$ROOTFS/etc/tmpfiles.d/var-log-tmpfs.conf" <<'EOF'
d /var/log/apt     0755 root root -
d /var/log/private 0700 root root -
EOF
mkdir -p "$ROOTFS/etc/initramfs-tools/conf.d"
echo "RESUME=none" > "$ROOTFS/etc/initramfs-tools/conf.d/resume"
# initramfs fsck hook 은 빌드 시점(chroot)에 루트 장치가 없어 FSTYPE=auto 로는 fs 종류를 못 찾고 fsck 를 빼 버린다.
# (부팅 시 "fsck not present, so skipping root file system" 경고의 원인) 루트는 ext4 로 고정한다.
echo "FSTYPE=ext4" > "$ROOTFS/etc/initramfs-tools/conf.d/fstype"
# H3 의 SD 호스트(sunxi-mmc)와 USB PHY 는 Debian armmp 커널에서 모듈(=m)이라 initramfs 에 명시해야 한다.
# 빠지면 "/dev/mmcblk0p1 does not exist" 로 루트를 못 찾는다. (linux-image 설치 전에 만들어야 initrd 에 반영됨)
printf 'sunxi-mmc\nphy-sun4i-usb\n' > "$ROOTFS/etc/initramfs-tools/modules"

echo "### 4. packages (kernel, u-boot, ssh, network)"
chroot "$ROOTFS" /bin/bash -e <<'EOF'
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update -qq
apt-get install -y --no-install-recommends \
  linux-image-armmp u-boot-sunxi initramfs-tools \
  systemd-sysv udev kmod iproute2 iputils-ping \
  openssh-server systemd-resolved nano less e2fsprogs \
  gpiod i2c-tools usbutils ethtool net-tools curl tcpdump strace file fdisk \
  util-linux-extra fake-hwclock systemd-timesyncd wireless-regdb logrotate
ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime
apt-get clean
EOF

echo "### 4b. dev environment (gcc/make/cmake/gdb + Debian 기본 python3)"
# 개발 도구는 Debian 13 저장소의 최신 버전이다 (gcc 14, glibc 2.41, python3 3.13 - 커널 6.12 와 같은 릴리스).
# python 은 Debian 기본 python3 를 그대로 쓴다 (소스 빌드 없음).
chroot "$ROOTFS" /bin/bash -e <<'EOF'
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update -qq
apt-get install -y --no-install-recommends \
  build-essential gdb make cmake ninja-build pkg-config autoconf automake libtool \
  git patch rsync xz-utils wget \
  python3 python3-venv python3-pip python3-dev python-is-python3 \
  libssl-dev zlib1g-dev libffi-dev libbz2-dev libreadline-dev libsqlite3-dev \
  liblzma-dev libncurses-dev libgdbm-dev uuid-dev libzstd-dev libexpat1-dev
apt-get clean
python3 -c "import ssl, sqlite3, zlib, bz2, lzma, ctypes, uuid, readline, sys; print('python', sys.version.split()[0], 'ok')"
gcc --version | head -1
EOF

echo "### 4c. legacy E3DP packages (E3DP_OS_20250901_V030112.img 에 있던 패키지의 Debian 13 최신판)"
# 기존 이미지(Ubuntu 16.04 armhf, dpkg 572개 중 수동 설치분)를 분석해 Debian 13 저장소에 있는 패키지만 골랐다.
# 버전을 고정하지 않으므로 trixie/trixie-updates/trixie-security 의 최신 버전이 설치된다.
# 제외한 것: libc 등 기반 라이브러리/필수 패키지(이미 debootstrap 이 최신으로 설치), 데스크톱/GUI(network-manager-gnome, gnome-keyring 등),
#   Ubuntu 전용(update-manager, ubuntu-*, language-pack-*, update-motd, ssh-import-id, crda), 구형(python2.7, sysv-rc, insserv, initscripts),
#   저장소에 없음(hddtemp, rpimonitor), 네트워크 관리자(network-manager: systemd-networkd 와 충돌하므로 제외).
# 대응 패키지명 변경: fw_printenv/fw_setenv(/usr/local/bin) -> libubootenv-tool, libjpeg-turbo8-dev -> libjpeg-dev.
chroot "$ROOTFS" /bin/bash -e <<'EOF'
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
apt-get update -qq
apt-get install -y --no-install-recommends \
  sudo vim expect telnet telnetd ftp vsftpd openbsd-inetd \
  dnsmasq hostapd wpasupplicant wireless-tools iw rfkill bluez udhcpd ppp fping iptables usb-modeswitch \
  alsa-utils madplay figlet toilet bc busybox cpio psmisc aptitude cron openssl whiptail bzip2 lsb-release fakeroot \
  kbd manpages manpages-dev openssh-sftp-server netbase acl at ncurses-term memtester iperf libubootenv-tool cifs-utils \
  libx264-dev libmp3lame-dev libpulse-dev libv4l-dev libjpeg-dev libasound2-dev libusb-1.0-0-dev libusb-dev libusb-0.1-4
# dnsmasq 는 설치만 하고 부팅 때 자동 시작하지 않는다 (systemd-resolved 스텁 DNS(53번 포트)와 충돌해 실패하므로 필요할 때 켠다)
systemctl disable dnsmasq >/dev/null 2>&1 || true
apt-get clean
EOF

echo "### 5. config (network, ssh, root pw, extlinux)"
# 인터페이스 이름: 내장 EMAC(platform 1c30000.ethernet) = eth0, 그 외 이더넷(USB 어댑터 등) = eth1
# (기본 predictable 이름 end0/enx... 대신 eth0/eth1 로 고정)
# Driver= 는 netdev 자체에는 드라이버가 없어 매칭되지 않으므로(QEMU 부팅에서 확인) 장치 경로(Path=)로 매칭한다.
cat > "$ROOTFS/etc/systemd/network/10-eth0.link" <<'EOF'
[Match]
Path=platform-1c30000.ethernet

[Link]
Name=eth0
EOF
cat > "$ROOTFS/etc/systemd/network/11-eth1.link" <<'EOF'
[Match]
Type=ether
Path=!platform-1c30000.ethernet

[Link]
Name=eth1
EOF
# eth0: DHCP, eth1: 고정 192.168.123.2/24 (케이블이 없어도 주소를 유지)
cat > "$ROOTFS/etc/systemd/network/20-eth0.network" <<'EOF'
[Match]
Name=eth0

[Network]
DHCP=yes
EOF
cat > "$ROOTFS/etc/systemd/network/21-eth1.network" <<'EOF'
[Match]
Name=eth1

[Network]
Address=192.168.123.2/24
ConfigureWithoutCarrier=yes
EOF
chroot "$ROOTFS" systemctl enable systemd-networkd systemd-resolved ssh >/dev/null 2>&1 || true
# 랜선이 없어도 부팅이 지연되지 않도록 네트워크 대기 서비스는 끔 (DHCP는 연결되는 즉시 동작)
chroot "$ROOTFS" systemctl disable systemd-networkd-wait-online.service >/dev/null 2>&1 || true
ln -sf /run/systemd/resolve/stub-resolv.conf "$ROOTFS/etc/resolv.conf"
mkdir -p "$ROOTFS/etc/ssh/sshd_config.d"
printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' > "$ROOTFS/etc/ssh/sshd_config.d/10-poc.conf"
echo "root:$ROOT_PW" | chroot "$ROOTFS" chpasswd
# 일반 계정 pi (비밀번호는 root 와 동일). sudo/dialout 그룹에 추가한다. (sudo 는 4c 에서 설치됨)
chroot "$ROOTFS" useradd -m -s /bin/bash -G sudo,dialout pi
echo "pi:$PI_PW" | chroot "$ROOTFS" chpasswd

# SSH 클라이언트에 따라 셸이 non-login 이면 /etc/profile 이 읽히지 않아 sshd 기본 PATH(sbin 없음)가 남는다.
# (ifconfig 등이 "command not found") bash.bashrc 는 대화형 셸이면 login 여부와 무관하게 읽히므로 여기서 보정한다.
cat >> "$ROOTFS/etc/bash.bashrc" <<'EOF'

# E3-DP PoC: non-login 셸(일부 SSH 접속)에서도 sbin 이 PATH 에 포함되도록 한다.
case ":$PATH:" in *:/usr/sbin:*) ;; *) PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"; export PATH ;; esac
EOF

# 빌드 일시를 /etc/os-release 의 BUILD_ID 에 기록한다. (KST, 확인: grep BUILD_ID /etc/os-release)
sed -i '/^BUILD_ID=/d' "$ROOTFS/etc/os-release"
echo "BUILD_ID=$(TZ=Asia/Seoul date +%Y%m%d_%H%M%S)" >> "$ROOTFS/etc/os-release"

# 저널은 디스크(/var/log/journal)에 저장하지 않고 RAM(/run/log/journal)에만 둔다.
# 전원을 갑자기 끊어도 "journal corrupted or uncleanly shut down" 이 생기지 않고 SD 카드 쓰기도 줄어든다. (재부팅하면 로그는 사라짐)
mkdir -p "$ROOTFS/etc/systemd/journald.conf.d"
# 저널 크기: 파일 1MB 에서 순환, 최대 10개(=10MB). (순환된 저널 파일을 따로 gzip 하는 기능은 journald 에 없다.)
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=10M\nRuntimeMaxFileSize=1M\nRuntimeMaxFiles=10\n' > "$ROOTFS/etc/systemd/journald.conf.d/10-volatile.conf"
rm -rf "$ROOTFS/var/log/journal"

# 그 외 /var/log/*.log: 1MB 를 넘으면 순환, 10개 보관, 오래된 것은 gzip 압축.
cat > "$ROOTFS/etc/logrotate.d/poc-logs" <<'EOF'
/var/log/*.log {
    size 1M
    rotate 10
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF
# 크기 기준 순환이므로 매일이 아니라 매시간 점검한다. 상태 파일은 디스크(/var/lib/logrotate)가 아니라 RAM(/run)에 둔다.
mkdir -p "$ROOTFS/etc/systemd/system/logrotate.timer.d" "$ROOTFS/etc/systemd/system/logrotate.service.d"
printf '[Timer]\nOnCalendar=\nOnCalendar=hourly\n' > "$ROOTFS/etc/systemd/system/logrotate.timer.d/hourly.conf"
printf '[Service]\nExecStart=\nExecStart=/usr/sbin/logrotate -s /run/logrotate.status /etc/logrotate.conf\n' > "$ROOTFS/etc/systemd/system/logrotate.service.d/status-in-ram.conf"

# 시험 편의: 첫 부팅 때 루트 파티션을 카드 전체 크기로 자동 확장
cat > "$ROOTFS/usr/local/sbin/expand-rootfs.sh" <<'EOF'
#!/bin/sh
# 루트 파티션(1번)을 카드 끝까지 늘리고 파일시스템을 확장한다. 성공하면 다시 실행하지 않는다.
# 시험용으로 ROOT_PART 환경변수로 대상 장치를 지정할 수 있다.
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
EOF
chmod +x "$ROOTFS/usr/local/sbin/expand-rootfs.sh"
cat > "$ROOTFS/etc/systemd/system/expand-rootfs.service" <<'EOF'
[Unit]
Description=Expand root filesystem to fill the SD card (first boot)
ConditionPathExists=!/var/lib/expand-rootfs.done
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/expand-rootfs.sh

[Install]
WantedBy=multi-user.target
EOF
chroot "$ROOTFS" systemctl enable expand-rootfs.service >/dev/null

# 시험 편의: 시리얼 콘솔(ttyS0)은 비밀번호 없이 root 자동 로그인
mkdir -p "$ROOTFS/etc/systemd/system/serial-getty@ttyS0.service.d"
cat > "$ROOTFS/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf" <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear --keep-baud 115200,57600,38400,9600 %I $TERM
EOF

KVER=$(basename "$(ls "$ROOTFS"/boot/vmlinuz-* | sort -V | tail -1)" | sed 's/vmlinuz-//')
DTB=$(ls "$ROOTFS"/usr/lib/linux-image-$KVER/sun8i-h3-nanopi-neo.dtb)
echo "kernel=$KVER dtb=$DTB"
# initrd 에 SD 호스트 드라이버가 들어갔는지 검증 (없으면 부팅 불가이므로 빌드 중단)
# grep -q 는 조기 종료로 lsinitramfs 에 SIGPIPE(141)를 발생시켜 pipefail 에서 오판할 수 있다.
# 전체 목록을 읽고 출력을 버려 생산자와 검색 명령의 실패를 모두 검증한다.
chroot "$ROOTFS" lsinitramfs "/boot/initrd.img-$KVER" | grep -E '/sunxi[-_]mmc\.ko(\.(xz|gz|zst))?$' >/dev/null \
  || { echo "ERROR: initrd 에 sunxi-mmc 없음 -> 부팅 불가"; exit 1; }
# fsck 가 initrd 에 들어갔는지 확인 (없으면 부팅 시 "fsck not present" 경고)
# 경고만 내고 빌드는 계속한다 (PoC 는 비정상 종료가 잦아 fsck 가 있으면 유리함).
chroot "$ROOTFS" lsinitramfs "/boot/initrd.img-$KVER" | grep -E '(^|/)(fsck|e2fsck)$' >/dev/null \
  || echo "WARNING: initrd 에 fsck/e2fsck 없음"
chroot "$ROOTFS" systemctl enable systemd-timesyncd fake-hwclock >/dev/null 2>&1 || true
# 쓰기 최소화: 주기적으로 디스크에 쓰는 타이머를 끈다 (apt 자동 갱신, dpkg DB 백업, ext4 점검, fstrim).
# fake-hwclock-save.timer(1시간마다 20바이트)는 NTP 가 없는 내부망에서 시계를 유지하기 위해 남겨 둔다.
chroot "$ROOTFS" systemctl disable apt-daily.timer apt-daily-upgrade.timer dpkg-db-backup.timer e2scrub_all.timer fstrim.timer >/dev/null 2>&1 || true
# RTC 가 없어 첫 부팅 시각이 과거(커널 빌드 시각)가 되면 apt 서명 검증이 "Not live until" 로 실패한다.
# 빌드 시점의 현재 시각을 저장해 두면 fake-hwclock 이 부팅 때 그 시각 이후로 복원한다 (이후 NTP 가 보정).
chroot "$ROOTFS" fake-hwclock save
cat "$ROOTFS/etc/fake-hwclock.data"
# E3-DP 보드: 내부망 USB 이더넷(AX88772)이 H3 의 USB1/USB2(헤더 USB-DP1/DM1, DP2/DM2)에 연결되어 있다.
# Debian 의 NanoPi NEO DT 는 이 두 호스트(ehci/ohci 1c1b000, 1c1c000)를 disabled 로 두므로 오버레이로 켠다.
cat > "$WORK/e3dp-usb.dts" <<'DTS'
/dts-v1/;
/plugin/;
/ {
	fragment@0 { target-path = "/soc/usb@1c1b000"; __overlay__ { status = "okay"; }; };
	fragment@1 { target-path = "/soc/usb@1c1b400"; __overlay__ { status = "okay"; }; };
	fragment@2 { target-path = "/soc/usb@1c1c000"; __overlay__ { status = "okay"; }; };
	fragment@3 { target-path = "/soc/usb@1c1c400"; __overlay__ { status = "okay"; }; };
};
DTS
dtc -@ -I dts -O dtb -o "$WORK/e3dp-usb.dtbo" "$WORK/e3dp-usb.dts"
mkdir -p "$ROOTFS/boot/dtb"
E3DP_DTB=/boot/dtb/sun8i-h3-nanopi-neo-e3dp.dtb
fdtoverlay -i "$DTB" -o "$ROOTFS$E3DP_DTB" "$WORK/e3dp-usb.dtbo"
# 적용 결과 검증: 1c1b000/1c1c000 가 okay 인지 확인 (아니면 빌드 중단)
dtc -I dtb -O dts -o "$WORK/e3dp-check.dts" "$ROOTFS$E3DP_DTB" 2>/dev/null
for n in usb@1c1b000 usb@1c1b400 usb@1c1c000 usb@1c1c400; do
  sed -n "/^\t\t$n {/,/^\t\t};/p" "$WORK/e3dp-check.dts" | grep -q '"okay"' \
    || { echo "ERROR: DT 오버레이 적용 실패 ($n)"; exit 1; }
done
mkdir -p "$ROOTFS/boot/extlinux"
cat > "$ROOTFS/boot/extlinux/extlinux.conf" <<EOF
default debian
timeout 20
label debian
  menu label Debian 13 (PoC)
  kernel /boot/vmlinuz-$KVER
  initrd /boot/initrd.img-$KVER
  fdt $E3DP_DTB
  append root=/dev/mmcblk0p1 rw rootwait console=ttyS0,115200 earlycon
EOF

UBOOT=$ROOTFS/usr/lib/u-boot/nanopi_neo/u-boot-sunxi-with-spl.bin
ls -l "$UBOOT"
cp "$UBOOT" "$WORK/"

rm -f "$ROOTFS/usr/sbin/policy-rc.d" "$ROOTFS/usr/bin/qemu-arm-static"
rm -rf "$ROOTFS/var/lib/apt/lists/"* "$ROOTFS/var/cache/apt/"*
chroot_dpkg_count=$(grep -c '^Package:' "$ROOTFS/var/lib/dpkg/status")
echo "installed packages: $chroot_dpkg_count"
cleanup

echo "### 6. image assembly"
# 이미지 크기 = rootfs 사용량 x 1.2 + 128 MiB (ext4 메타데이터·저널 여유). 더 큰 SD 카드는 첫 부팅에 expand-rootfs 가 확장한다.
if [ -z "$IMG_SIZE_MB" ]; then
  ROOT_MB=$(du -sm "$ROOTFS" | cut -f1)
  IMG_SIZE_MB=$(( ROOT_MB * 12 / 10 + 128 ))
  echo "image size: ${IMG_SIZE_MB} MiB (rootfs ${ROOT_MB} MiB, 자동 계산)"
else
  echo "image size: ${IMG_SIZE_MB} MiB (지정값)"
fi
truncate -s ${IMG_SIZE_MB}M "$IMG"
echo 'label: dos
start=2048, type=83, bootable' | sfdisk "$IMG" >/dev/null
FS_KB=$(( (IMG_SIZE_MB*1024) - 1024 ))
mkfs.ext4 -F -q -L rootfs -d "$ROOTFS" -E offset=1048576 "$IMG" ${FS_KB}k
dd if="$WORK/u-boot-sunxi-with-spl.bin" of="$IMG" bs=1k seek=8 conv=notrunc status=none

cp "$ROOTFS/boot/vmlinuz-$KVER" "$ROOTFS/boot/initrd.img-$KVER" "$WORK/"
cp "$DTB" "$WORK/"
sync
cp "$IMG" "$OUT/"
( cd "$OUT" && sha256sum "$(basename "$IMG")" > "$(basename "$IMG").sha256" )
echo "### 7. SBOM (이미지명_sbom.json)"
# 이미지에 들어간 OS 패키지 목록을 CycloneDX JSON으로 생성한다. syft 가 없으면 건너뛴다.
# 형식 변경: SBOM_FORMAT=spdx-json bash build_poc.sh
SBOM_FORMAT=${SBOM_FORMAT:-cyclonedx-json}
SBOM="$OUT/$(basename "$IMG" .img)_sbom.json"
if command -v syft >/dev/null 2>&1; then
  # 기본: OS 패키지(dpkg)만 담는다 (파일 단위 항목은 용량만 커져 제외).
  # 파일 단위까지 전부 담으려면: SBOM_FULL=1 bash build_poc.sh  (용량이 수십 배로 커짐)
  if [ "${SBOM_FULL:-0}" = "1" ]; then
    syft "dir:$ROOTFS" -o "$SBOM_FORMAT=$SBOM" -q
  else
    syft "dir:$ROOTFS" --select-catalogers dpkg -o "$SBOM_FORMAT=$SBOM" -q
  fi
  if [ "${SBOM_FULL:-0}" != "1" ] && [ "$SBOM_FORMAT" = "cyclonedx-json" ] && command -v python3 >/dev/null 2>&1; then
    python3 - "$SBOM" <<'PY'
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
PY
  fi
  echo "SBOM: $SBOM"
else
  echo "syft 가 없어 SBOM 생성을 건너뜀 (설치: https://github.com/anchore/syft/releases)"
fi

echo "### DONE: $OUT/$(basename "$IMG")"
