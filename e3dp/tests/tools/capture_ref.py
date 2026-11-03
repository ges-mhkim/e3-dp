"""기준 장치 읽기 전용 패킷 캡처.

원격 장치에 파일을 쓰지 않고, 원격 python3(3.5 호환)의 AF_PACKET 소켓으로 읽은 프레임을
ssh 채널로 받아 PC에 pcap(Ethernet)으로 저장한다.

사용: REF_PW=<비밀번호> python capture_ref.py [초] [출력.pcap] [인터페이스...]
기본: 300초, tests/fixtures/ref_220/capture_<시각>.pcap, eth0 eth1
"""
import os
import struct
import sys
import time

import paramiko

HOST = os.environ.get("REF_HOST", "10.10.0.220")
USER = os.environ.get("REF_USER", "root")

REMOTE = r'''
import os, select, socket, struct, sys, time
dur = float(sys.argv[1]); ifs = sys.argv[2:]
try:
    os.nice(19)
except Exception:
    pass
socks = []
for n in ifs:
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    s.bind((n, 0)); s.setblocking(False); socks.append((s, n))
out = sys.stdout.buffer
end = time.time() + dur
def skip(f):
    # skip ssh(22) over IPv4 TCP
    if len(f) > 38 and f[12:14] == b"\x08\x00" and f[23] == 6:
        ihl = (f[14] & 15) * 4
        o = 14 + ihl
        sp = (f[o] << 8) | f[o + 1]; dp = (f[o + 2] << 8) | f[o + 3]
        return sp == 22 or dp == 22
    return False
while time.time() < end:
    r, _, _ = select.select([x[0] for x in socks], [], [], 1.0)
    for s in r:
        name = [n for (k, n) in socks if k is s][0]
        for _ in range(64):
            try:
                f = s.recv(2048)
            except BlockingIOError:
                break
            if skip(f):
                continue
            nb = name.encode()
            out.write(struct.pack("!dBHB", time.time(), len(nb), len(f), 0) + nb + f)
    out.flush()
'''


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 300
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(here, "..", "fixtures", "ref_220",
                           "capture_%s.pcap" % time.strftime("%Y%m%d_%H%M%S"))
    path = sys.argv[2] if len(sys.argv) > 2 else default
    ifs = sys.argv[3:] or ["eth0", "eth1"]

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=os.environ["REF_PW"], timeout=10,
              allow_agent=False, look_for_keys=False)
    cmd = "nice -n 19 python3 -u - %s %s" % (dur, " ".join(ifs))
    stdin, stdout, stderr = c.exec_command(cmd)
    stdin.write(REMOTE)
    stdin.channel.shutdown_write()

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    hdr = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    n = 0
    with open(path, "wb") as fo, open(path + ".ifaces", "w") as fi:
        fo.write(hdr)
        buf = b""
        ch = stdout.channel
        deadline = time.time() + dur + 30
        while time.time() < deadline:
            if ch.recv_ready():
                buf += ch.recv(65536)
            elif ch.exit_status_ready():
                break
            else:
                time.sleep(0.05)
            while len(buf) >= 12:
                ts, nl, fl, _ = struct.unpack("!dBHB", buf[:12])
                if len(buf) < 12 + nl + fl:
                    break
                name = buf[12:12 + nl].decode()
                frame = buf[12 + nl:12 + nl + fl]
                buf = buf[12 + nl + fl:]
                sec = int(ts)
                fo.write(struct.pack("<IIII", sec, int((ts - sec) * 1e6), fl, fl) + frame)
                fi.write("%d %s\n" % (n, name))
                n += 1
    err = stderr.read().decode(errors="replace")
    c.close()
    print("frames=%d file=%s" % (n, os.path.abspath(path)))
    if err.strip():
        print("remote stderr:", err[:500])


if __name__ == "__main__":
    main()
