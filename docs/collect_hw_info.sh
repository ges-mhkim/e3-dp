#!/bin/bash
# E3-DP 하드웨어/소프트웨어 현황 수집 (읽기 전용, 시스템 변경 없음)
# 사용: root 로 실행 -> bash collect_hw_info.sh > /tmp/dp_info.txt 2>&1
s() { echo; echo "=================== $*"; }

s "OS / KERNEL";      cat /etc/os-release; uname -a; cat /etc/friendlyelec-release 2>/dev/null
s "HW";               cat /proc/cpuinfo | tail -8; free -m; df -h; cat /proc/cmdline
s "BOOT FILES";       ls -l /boot
s "KERNEL MODULES";   lsmod; ls -R /lib/modules/$(uname -r)/extra 2>/dev/null
s "DEVICES";          ls -l /dev | grep -E "gpio|i2c|spi|tty(S|USB|ACM)|video|snd|rtc|watchdog|mtd|mmc"
s "GPIO/I2C/SPI";     ls /sys/class/gpio /sys/class/i2c-adapter /sys/class/spidev 2>/dev/null
s "USB";              lsusb 2>/dev/null; lsusb -t 2>/dev/null
s "NETWORK";          ip -br addr; ip route; ss -tulpn
s "PROCESSES";        ps aux --sort=-rss | head -40
s "SERVICES";         systemctl list-unit-files --state=enabled 2>/dev/null
s "RC/CRON";          cat /etc/rc.local 2>/dev/null; ls /etc/cron* /var/spool/cron* 2>/dev/null; crontab -l 2>/dev/null
s "APP CANDIDATES";   ls -la /home /opt /usr/local/bin /usr/local/lib /root 2>/dev/null
s "PACKAGES (manual)"; apt-mark showmanual 2>/dev/null
s "PACKAGES (all)";   dpkg -l | wc -l; dpkg -l | awk '/^ii/{print $2, $3}' | head -600
s "NON-DISTRO BINS";  find /home /opt /usr/local /root -xdev -type f \( -perm -u+x -o -name "*.so*" -o -name "*.ko" \) 2>/dev/null | head -200
s "LDD OF RUNNING APPS"
for p in $(ps -eo pid,comm --no-headers | awk '{print $1}'); do
  exe=$(readlink -f /proc/$p/exe 2>/dev/null)
  case "$exe" in /home/*|/opt/*|/usr/local/*|/root/*)
    echo "--- $exe"; file "$exe" 2>/dev/null; ldd "$exe" 2>/dev/null ;; esac
done
s "DONE"
