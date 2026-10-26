"""capture_ref.py가 만든 pcap을 (인터페이스, 프로토콜, 송신IP:포트 -> 수신IP:포트)별로 집계한다.

사용: python pcap_summary.py <파일.pcap> [샘플 출력 수]
"""
import collections
import struct
import sys


def read_pcap(path):
    with open(path, "rb") as f:
        f.read(24)
        while True:
            h = f.read(16)
            if len(h) < 16:
                return
            sec, usec, cl, _ = struct.unpack("<IIII", h)
            yield sec + usec / 1e6, f.read(cl)


def parse(frame):
    """Ethernet/IPv4 TCP·UDP·ICMP 프레임 -> (proto, src, sport, dst, dport, payload)"""
    if len(frame) < 34 or frame[12:14] != b"\x08\x00":
        return None
    ihl = (frame[14] & 15) * 4
    proto = frame[23]
    src = ".".join(str(b) for b in frame[26:30])
    dst = ".".join(str(b) for b in frame[30:34])
    o = 14 + ihl
    if proto == 6 and len(frame) >= o + 20:
        sp, dp = struct.unpack("!HH", frame[o:o + 4])
        off = (frame[o + 12] >> 4) * 4
        return "TCP", src, sp, dst, dp, frame[o + off:]
    if proto == 17 and len(frame) >= o + 8:
        sp, dp = struct.unpack("!HH", frame[o:o + 4])
        return "UDP", src, sp, dst, dp, frame[o + 8:]
    if proto == 1:
        return "ICMP", src, 0, dst, 0, frame[o:]
    return None


def main():
    path = sys.argv[1]
    try:
        names = [l.split()[1] for l in open(path + ".ifaces")]
    except OSError:
        names = []
    cnt = collections.Counter()
    size = collections.Counter()
    sample = {}
    for i, (ts, fr) in enumerate(read_pcap(path)):
        p = parse(fr)
        iface = names[i] if i < len(names) else "?"
        if not p:
            cnt[(iface, "other", "", "")] += 1
            continue
        proto, s, sp, d, dp, pl = p
        # 낮은 포트를 서비스 포트로 간주
        svc = min(sp, dp) if proto != "ICMP" else 0
        key = (iface, proto, "%s:%d" % (s, sp), "%s:%d" % (d, dp))
        cnt[key] += 1
        size[key] += len(pl)
        if pl and key not in sample:
            sample[key] = pl[:48].hex()
    for k, v in cnt.most_common():
        print("%-5s %-4s %-24s -> %-24s n=%-6d bytes=%-8d %s" % (
            k[0], k[1], k[2], k[3], v, size[k], sample.get(k, "")))


if __name__ == "__main__":
    main()
