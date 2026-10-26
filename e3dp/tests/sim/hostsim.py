#!/usr/bin/env python3
"""Host(상위 서버) 수신 시뮬레이터: DP가 Host로 보내는 UDP 메시지를 받아 기록한다.

DP -> Host 주요 UDP (nelite.conf HOST_IP/ALARM_HOST_IP 가 이 시뮬레이터 주소일 때):
  경보 7704 (alarm_server, EC_ALARM_FRONT_PORT), 정시수집 7062 (gather_server), 실시간 7510 (EC_RT_FRONT_PORT),
  시각 요청 37 ("What time is it?" -> RFC 868 응답, main_server 기동 시 필요. 포트 37은 root 권한 필요),
  정시수집 등 필요 시 추가. 포트는 --ports 로 지정.
제어: 127.0.0.1:<ctl> 에 JSON 한 줄 요청/응답 (op: ping, clear_log, get_log, quit,
  ack_mode {mode: none|echo}). Python 3.5 호환(f-string 미사용).
"""
import argparse
import json
import socket
import struct
import threading
import time


class Sink(object):
    def __init__(self, host, ports, time_offset=0):
        self.time_offset = time_offset
        self.lock = threading.Lock()
        self.log = []
        self.stop = False
        self.ack = "none"
        self.socks = {}
        for p in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, p))
            s.settimeout(0.5)
            self.socks[p] = s
            t = threading.Thread(target=self._loop, args=(p, s))
            t.daemon = True
            t.start()

    def _loop(self, port, s):
        while not self.stop:
            try:
                data, addr = s.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            with self.lock:
                self.log.append({"t": round(time.time(), 3), "port": port, "src": addr[0], "sport": addr[1],
                                 "len": len(data), "hex": "".join("%02x" % b for b in data)})
                mode = self.ack
            if port == 37 and data.startswith(b"What time"):
                # RFC 868 시간 응답: 1900-01-01 기준 초(4바이트 빅엔디안). DP(main_server)가 stime()으로 시스템 시각을 설정한다.
                try:
                    s.sendto(struct.pack(">I", int(time.time()) + self.time_offset + 2208988800), addr)
                except OSError:
                    pass
            elif mode == "echo":
                try:
                    s.sendto(data, addr)
                except OSError:
                    pass
            elif mode == "rid" and len(data) >= 44:
                # EC_RESPONSE 헤더(type 3, size 0, service, rid, rcode 0, protocol 1).
                # 알람 서버는 4번째 정수(rid, 빅엔디안)로 ACB 항목을 삭제한다.
                ack = (b"\x00\x00\x00\x03" + b"\x00\x00\x00\x00" + data[8:12] + data[12:16]
                       + b"\x00\x00\x00\x00" + b"\x01\x00\x00\x00")
                try:
                    s.sendto(ack, (addr[0], addr[1]))
                except OSError:
                    pass

    def handle(self, req):
        op = req.get("op")
        with self.lock:
            if op == "ping":
                return {"ok": True}
            if op == "clear_log":
                self.log = []
                return {"ok": True}
            if op == "get_log":
                return {"ok": True, "log": list(self.log)}
            if op == "ack_mode":
                self.ack = req["mode"]
                return {"ok": True}
        if op == "quit":
            self.stop = True
            return {"ok": True}
        return {"ok": False, "err": "unknown op"}

    def serve_ctl(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(8)
        s.settimeout(0.5)
        while not self.stop:
            try:
                c, _ = s.accept()
            except socket.timeout:
                continue
            try:
                c.settimeout(5.0)
                buf = b""
                while not buf.endswith(b"\n"):
                    ch = c.recv(65536)
                    if not ch:
                        break
                    buf += ch
                try:
                    rsp = self.handle(json.loads(buf.decode()))
                except Exception as e:  # noqa
                    rsp = {"ok": False, "err": repr(e)}
                c.sendall((json.dumps(rsp) + "\n").encode())
            except OSError:
                pass
            finally:
                c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.2")
    ap.add_argument("--ports", default="7704,7510,7062,7000,37")
    ap.add_argument("--time-offset", type=int, default=0)
    ap.add_argument("--ctl", type=int, default=19001)
    a = ap.parse_args()
    sink = Sink(a.host, [int(x) for x in a.ports.split(",") if x], a.time_offset)
    print("hostsim started host=%s ports=%s ctl=%d" % (a.host, a.ports, a.ctl), flush=True)
    sink.serve_ctl(a.ctl)


if __name__ == "__main__":
    main()
