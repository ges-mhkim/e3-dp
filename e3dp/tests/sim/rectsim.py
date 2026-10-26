#!/usr/bin/env python3
"""정류기(Dongah RECT) 시뮬레이터: Modbus ASCII over TCP 2000. DP(rect_server)가 접속하는 정류기 역할.

명세 출처: e3dp.2.1/src/rect/rect_server.c (process_rt_request, SendRecvManager, RectUpdate, make_LRC),
          src/rect/rect.h (st_DA_RectRequestRec, st_DA_RectResRec), include/nelite.h
  요청 17바이트 ASCII: ':' + id(2) + func(2) + addr(4) + val(4) + LRC(2) + CR LF   (id=01, func=04 읽기, addr=0100, val=004B=75레지스터)
      func 06 = 단일 레지스터 쓰기(AO·접점 제어): addr, val 이 레지스터 번지와 값
  LRC = (id,func,addr,val 12자를 16진 쌍으로 합산한 값의 2의 보수) 의 2자리 대문자 16진
  응답: ':' + id(2) + func(2) + 바이트수(4자리 16진, 0x96=150) + 레지스터 75개 x 4자리 대문자 16진 + LRC(2) + CR LF
      (DP는 응답의 9번째 문자부터 레지스터로 해석하고 LRC는 검사하지 않는다)
레지스터 순서는 rect.h 구조체 순서(주소 주석은 일부 중복·누락이라 순서를 따른다).
제어: 127.0.0.1:<ctl> JSON 한 줄. Python 3.5 호환.
"""
import argparse
import json
import socket
import threading
import time

REG_NAMES = [
    "ac_v_R", "ac_v_S", "ac_v_T", "ac_a_R", "ac_a_S", "ac_a_T", "temp", "rack1_ac_fail", "rack2_ac_fail",
    "rack3_ac_fail", "rack4_ac_fail", "rack5_ac_fail", "dcds_dc_v", "dcds_dc_a", "dcds_batt_a", "disch_set_v",
    "rect_rom_ver1", "rect_rom_ver2", "lcd_rom_ver1", "lcd_rom_ver2", "temp_cell_v", "temp_cell_cnt",
    "temp_comp_low", "temp_comp_high", "temp_set", "temp_comp_state", "temp_comp_select", "agm_batt_charge",
    "output_v_set", "output_a_set", "charger_mode", "run_mode", "battTestendStat", "LED_alarm_display",
    "ER_comm_fail", "batt_test_state", "rack1_output_a", "rack1_output_temp", "rack1_output_v", "rack1_batt_a",
    "rack2_output_a", "rack2_output_temp", "rack2_output_v", "rack2_batt_a", "rack3_output_a", "rack3_output_temp",
    "rack3_output_v", "rack3_batt_a", "rack4_output_a", "rack4_output_temp", "rack4_output_v", "rack4_batt_a",
    "rack5_output_a", "rack5_output_temp", "rack5_output_v", "rack5_batt_a", "mr_module_fail", "er1_module_fail",
    "er2_module_fail", "er3_module_fail", "er4_module_fail", "mr_fail", "er1_fail", "er2_fail", "er3_fail",
    "er4_fail", "DoD_capacity", "disch_time_set", "batt_disch_amp", "batt_disch_set", "batt_low_volt_rel",
    "batt_capacity", "amg_batt_retry_cnt", "batt_disch_end", "disch_range"]
N_REGS = len(REG_NAMES)


def lrc_ascii(chars):
    s = 0
    for i in range(0, len(chars), 2):
        s += int(chars[i:i + 2], 16)
    return "%02X" % ((-s) & 0xFF)


class Rect(object):
    def __init__(self, ip, port=2000):
        self.ip, self.port = ip, port
        self.regs = [0] * N_REGS
        self.mode = "normal"      # normal | silent | short | badframe
        self.up = False
        self.sock = None
        self.writes = []


class Sim(object):
    def __init__(self, ips, port=2000):
        self.lock = threading.Lock()
        self.log = []
        self.rects = dict((ip, Rect(ip, port)) for ip in ips)
        self.stop = False

    def start_all(self):
        for ip in self.rects:
            self.ip_up(ip)

    def ip_up(self, ip):
        r = self.rects[ip]
        if r.up:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((r.ip, r.port))
        s.listen(8)
        s.settimeout(0.5)
        r.sock, r.up = s, True
        t = threading.Thread(target=self._accept, args=(r, s))
        t.daemon = True
        t.start()

    def ip_down(self, ip):
        r = self.rects[ip]
        r.up = False
        if r.sock:
            try:
                r.sock.close()
            except OSError:
                pass
            r.sock = None

    def _accept(self, r, s):
        while r.up and not self.stop:
            try:
                c, _ = s.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            t = threading.Thread(target=self._serve, args=(r, c))
            t.daemon = True
            t.start()

    def _serve(self, r, c):
        try:
            c.settimeout(2.0)
            data = b""
            while len(data) < 17:
                d = c.recv(64)
                if not d:
                    break
                data += d
            txt = data.decode("ascii", errors="replace")
            ev = {"t": round(time.time(), 3), "ip": r.ip, "req": txt, "mode": r.mode}
            ok = len(txt) >= 17 and txt[0] == ":"
            if ok:
                body = txt[1:13]
                ev.update(func=txt[3:5], addr=txt[5:9], val=txt[9:13], lrc=txt[13:15],
                          lrc_ok=(lrc_ascii(body) == txt[13:15]))
            with self.lock:
                self.log.append(ev)
                mode = r.mode
                regs = list(r.regs)
            if not ok or mode == "silent":
                time.sleep(1.5)
                return
            if ev["func"] == "06":
                with self.lock:
                    r.writes.append((ev["addr"], ev["val"]))
                reply = txt[:17]
            else:
                payload = "".join("%04X" % (v & 0xFFFF) for v in regs)
                if mode == "short":
                    payload = payload[:40]
                inner = txt[1:3] + txt[3:5] + "%04X" % (len(payload) // 2) + payload
                reply = ":" + inner + lrc_ascii(inner) + "\r\n"
                if mode == "badframe":
                    reply = "garbage"
            c.sendall(reply.encode("ascii"))
            time.sleep(0.05)
        except (OSError, socket.timeout):
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass

    def handle(self, req):
        op = req.get("op")
        with self.lock:
            if op == "ping":
                return {"ok": True}
            if op == "clear_log":
                self.log = []
                for r in self.rects.values():
                    r.writes = []
                return {"ok": True}
            if op == "get_log":
                return {"ok": True, "log": list(self.log),
                        "writes": dict((ip, list(r.writes)) for ip, r in self.rects.items())}
            if op == "set_reg":
                r = self.rects[req["ip"]]
                idx = REG_NAMES.index(req["name"]) if "name" in req else int(req["idx"])
                r.regs[idx] = int(req["value"]) & 0xFFFF
                return {"ok": True}
            if op == "mode":
                self.rects[req["ip"]].mode = req["mode"]
                return {"ok": True}
        if op in ("ip_up", "ip_down"):
            getattr(self, op)(req["ip"])
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
    ap.add_argument("--ips", default="10.99.0.17")
    ap.add_argument("--ctl", type=int, default=19002)
    ap.add_argument("--port", type=int, default=2000)
    a = ap.parse_args()
    sim = Sim([x for x in a.ips.split(",") if x], a.port)
    sim.start_all()
    print("rectsim started ips=%s ctl=%d" % (a.ips, a.ctl), flush=True)
    sim.serve_ctl(a.ctl)


if __name__ == "__main__":
    main()
