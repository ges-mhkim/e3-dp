#!/usr/bin/env python3
"""E3-GW 시뮬레이터 (Modbus TCP, 포트 1502). DP(gw_server)가 접속하는 GW 역할.

명세 출처: e3dp.2.1/src/gw/gw_server.c, include/nelite.h
  요청(12바이트): [txid 2][proto 2=0][len 2=6][port 1][func 1][addr 2][count 2]  (모두 big-endian)
    func 0x03 : 실시간 요청 (addr 0, count 120)
    func 0x06 : 제어/AO 쓰기 (addr=채널, count=값). 응답 없음, DP가 바로 연결 종료
    func 0x64 : 시각 동기 (port=0, txid=0, 본문 시각 4바이트). 응답 없음
  정상 응답(249바이트): [txid][proto][len=243][port][func=3][bytecnt=240] + AI 40 x float32(BE)
    + DI 40 x uint16(BE). 마지막 바이트(DI40 하위)가 통신 상태(0=정상).
  설정 없음 응답(12바이트): DP는 "No Configuration"으로 처리(shelf status = COMM_ALARM).

주의: 프로세스 이름/경로에 'gw_server'를 넣지 않는다. modbus_server가 `kil gw_server`로 죽인다.
제어: 127.0.0.1:<ctl>에 JSON 한 줄 요청, JSON 한 줄 응답. Python 3.5 호환(f-string 미사용).
"""
import argparse
import json
import socket
import struct
import threading
import time

AI_MAX = 40
DI_MAX = 40
RT_SIZE = 249
NOCONF_SIZE = 12

MODES = ("normal", "noconfig", "silent", "badsize", "wrongport", "commfail", "slow")


class PortCfg(object):
    def __init__(self):
        self.mode = "normal"
        self.ai = [0.0] * AI_MAX
        self.di = [0] * DI_MAX
        self.delay = 0.0
        self.func_override = None


class Gw(object):
    def __init__(self, ip, port=1502):
        self.ip = ip
        self.tcp_port = port
        self.ports = {}
        self.sock = None
        self.up = False
        self.thread = None

    def cfg(self, p):
        if p not in self.ports:
            self.ports[p] = PortCfg()
        return self.ports[p]


class Sim(object):
    def __init__(self, ips, tcp_port=1502, ports=(1, 2, 3, 4, 5)):
        self.lock = threading.Lock()
        self.log = []
        self.gws = {}
        for ip in ips:
            g = Gw(ip, tcp_port)
            for p in ports:
                g.cfg(p)
            self.gws[ip] = g
        self.stop = False

    # ---- 서버 ----
    def start_all(self):
        for g in self.gws.values():
            self.ip_up(g.ip)

    def ip_up(self, ip):
        g = self.gws[ip]
        if g.up:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((g.ip, g.tcp_port))
        s.listen(16)
        s.settimeout(0.5)
        g.sock = s
        g.up = True
        g.thread = threading.Thread(target=self._accept, args=(g, s))
        g.thread.daemon = True
        g.thread.start()

    def ip_down(self, ip):
        g = self.gws[ip]
        g.up = False
        if g.sock:
            try:
                g.sock.close()
            except OSError:
                pass
            g.sock = None

    def _accept(self, g, s):
        while g.up and not self.stop:
            try:
                c, _ = s.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            t = threading.Thread(target=self._serve, args=(g, c))
            t.daemon = True
            t.start()

    def _serve(self, g, c):
        try:
            c.settimeout(2.0)
            data = b""
            while len(data) < 12:
                chunk = c.recv(64)
                if not chunk:
                    break
                data += chunk
            if len(data) < 12:
                self._rec(g, data, "short", None)
                return
            txid, proto, ln, port, func, addr, cnt = struct.unpack("!HHHBBHH", data[:12])
            with self.lock:
                cfg = g.cfg(port)
                mode, delay = cfg.mode, cfg.delay
            ev = "req"
            reply = None
            if func == 0x03:
                reply = self._build(g, cfg, mode, txid, port, data)
                if mode == "silent":
                    ev = "silent"
                    time.sleep(1.0)
                    return
                if mode == "slow":
                    time.sleep(delay)
            elif func == 0x06:
                ev = "write"
            elif func == 0x64:
                ev = "tsync"
            self._rec(g, data, ev, mode)
            if reply:
                c.sendall(reply)
                time.sleep(0.05)
        except (OSError, socket.timeout):
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass

    def _build(self, g, cfg, mode, txid, port, req):
        if mode == "noconfig":
            return req[:7] + b"\x84" + req[8:12]
        if mode == "badsize":
            return struct.pack("!HHHBBB", txid, 0, 100, port, 3, 94) + b"\x00" * 94
        pid = port + 1 if mode == "wrongport" else port
        body = b"".join(struct.pack("!f", v) for v in cfg.ai)
        di = list(cfg.di)
        if mode == "commfail":
            di[DI_MAX - 1] = (di[DI_MAX - 1] & 0xFF00) | 1
        else:
            di[DI_MAX - 1] = di[DI_MAX - 1] & 0xFF00
        body += b"".join(struct.pack("!H", v & 0xFFFF) for v in di)
        hdr = struct.pack("!HHHBBB", txid, 0, 3 + len(body), pid, 3, len(body))
        out = hdr + body
        assert len(out) == RT_SIZE
        return out

    def _rec(self, g, data, ev, mode):
        item = {"t": round(time.time(), 3), "ip": g.ip, "ev": ev, "mode": mode,
                "hex": data.hex() if hasattr(data, "hex") else "".join("%02x" % b for b in data)}
        if len(data) >= 12:
            txid, proto, ln, port, func, addr, cnt = struct.unpack("!HHHBBHH", data[:12])
            item.update(txid=txid, port=port, func=func, addr=addr, cnt=cnt)
        with self.lock:
            self.log.append(item)
            if len(self.log) > 20000:
                del self.log[:10000]

    # ---- 제어 ----
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
            if op == "state":
                return {"ok": True, "ips": {ip: {"up": g.up, "ports": {str(p): c.mode for p, c in g.ports.items()}}
                                              for ip, g in self.gws.items()}}
        if op in ("ip_up", "ip_down"):
            getattr(self, op)(req["ip"])
            return {"ok": True}
        if op == "mode":
            ips = [req["ip"]] if "ip" in req else list(self.gws)
            for ip in ips:
                g = self.gws[ip]
                for p in ([req["port"]] if "port" in req else list(g.ports)):
                    if req["mode"] not in MODES:
                        return {"ok": False, "err": "bad mode"}
                    with self.lock:
                        g.cfg(p).mode = req["mode"]
                        if "delay" in req:
                            g.cfg(p).delay = float(req["delay"])
            return {"ok": True}
        if op == "set_ai":
            with self.lock:
                self.gws[req["ip"]].cfg(req["port"]).ai[req["ch"] - 1] = float(req["value"])
            return {"ok": True}
        if op == "set_di":
            with self.lock:
                self.gws[req["ip"]].cfg(req["port"]).di[req["ch"] - 1] = int(req["value"])
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
    ap.add_argument("--ips", default=",".join("10.99.0.%d" % n for n in range(11, 17)))
    ap.add_argument("--ctl", type=int, default=19000)
    ap.add_argument("--port", type=int, default=1502)
    a = ap.parse_args()
    sim = Sim([x for x in a.ips.split(",") if x], a.port)
    sim.start_all()
    print("gwsim started ips=%s ctl=%d" % (a.ips, a.ctl), flush=True)
    sim.serve_ctl(a.ctl)


if __name__ == "__main__":
    main()
