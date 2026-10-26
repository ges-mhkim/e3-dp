#!/usr/bin/env python3
"""Host 역할 한 번짜리 요청 도구(보드 안에서 실행, Python 3.5 호환).

DP의 일부 응답(제어, 제어 모드, 실시간 푸시 등)은 DP가 요청의 caddr(IP:포트)로 **TCP 연결을 맺어** 보낸다.
이 도구는 caddr 포트에서 TCP 리스너를 열어 두고, 같은 포트로 UDP 요청(main_server 7999)을 보낸 뒤
수신한 UDP 응답과 TCP 연결별 수신 데이터를 JSON으로 출력한다.

사용: python3 hostreq.py <요청 hex> <대기초> <caddr 포트> [목적지 포트=7999] [중지초 중지hex]
  중지초/중지hex: 첫 TCP 연결에 중지초 후 중지hex 바이트를 보낸다(실시간 구독 해제 404 등)
출력: {"udp": [hex...], "tcp": [[청크 hex...], ...], "tcp_t": [[청크별 수신 시각(요청 후 초)]],
       "closed": [연결이 상대(DP)에 의해 닫혔는지]}
"""
import json
import select
import socket
import sys
import time


def main():
    data = bytes.fromhex(sys.argv[1])
    wait = float(sys.argv[2])
    port = int(sys.argv[3])
    dport = int(sys.argv[4]) if len(sys.argv) > 4 else 7999
    stop_after = float(sys.argv[5]) if len(sys.argv) > 5 else None
    stop_hex = bytes.fromhex(sys.argv[6]) if len(sys.argv) > 6 else b""

    lsn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lsn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsn.bind(("127.0.0.1", port))
    lsn.listen(8)
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(("127.0.0.1", port))
    u.sendto(data, ("127.0.0.1", dport))

    live = {}         # 소켓 -> [청크 hex 목록, 청크 시각 목록]
    done = []         # 닫힌 연결: [청크 hex 목록, 청크 시각 목록, 닫힘 여부]
    udp = []
    t0 = time.time()
    end = t0 + wait
    stopped = False
    first = None
    while time.time() < end:
        r, _, _ = select.select([lsn, u] + list(live), [], [], 0.2)
        for s in r:
            if s is lsn:
                c, _ = lsn.accept()
                live[c] = [[], []]
                if first is None:
                    first = c
            elif s is u:
                d, _ = u.recvfrom(65535)
                udp.append(d.hex())
            else:
                d = s.recv(65535)
                if d:
                    live[s][0].append(d.hex())
                    live[s][1].append(round(time.time() - t0, 2))
                else:
                    done.append(live.pop(s) + [True])
                    s.close()
        if (stop_after is not None and not stopped and first is not None and first in live
                and time.time() - t0 >= stop_after):
            first.sendall(stop_hex)
            stopped = True
    for c, v in live.items():
        done.append(v + [False])
    print(json.dumps({"udp": udp, "tcp": [d[0] for d in done], "tcp_t": [d[1] for d in done],
                      "closed": [d[2] for d in done]}))


if __name__ == "__main__":
    main()
