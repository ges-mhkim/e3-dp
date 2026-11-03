"""보드(신 보드/기준 장치) 원격 제어: ssh 실행, 파일 전송, DP 기동·종료, 시뮬레이터 제어.

접속 정보는 환경 변수로 받는다(코드에 쓰지 않는다).
  신 보드:   BOARD_HOST BOARD_USER BOARD_PW
  기준 장치: REF_HOST   REF_USER   REF_PW

DP는 root로 실행해야 한다(netcheck_server가 raw 소켓 사용). 일반 계정이면 sudo로 실행하며
비밀번호는 stdin으로만 전달한다.
"""
import json
import os
import shlex
import time

import paramiko

SERVERS = ["main_server", "db_server", "config_server", "gather_server", "control_server",
           "modbus_server", "rect_server", "scan_server", "rt_server", "alarm_server",
           "netcheck_server", "realdata_server", "acon_agent"]  # smm의 기동 목록과 같은 순서(realdata_server는 scheck 목록에 없음)
OPT = "/opt/e3dp"
# DB의 GW(shelf 1~6)에 대응하는 시뮬레이터 주소. 실제 GW와 겹치지 않는 대역을 lo 별칭으로 사용.
SIM_IPS = tuple("10.99.0.%d" % n for n in range(11, 17))


class Board(object):
    def __init__(self, host, user, pw, name="board"):
        self.name = name
        self.host, self.user, self.pw = host, user, pw
        self.c = paramiko.SSHClient()
        self.c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.c.connect(host, username=user, password=pw, timeout=15,
                       allow_agent=False, look_for_keys=False)
        self.sftp = self.c.open_sftp()

    @classmethod
    def new(cls):
        return cls(os.environ.get("BOARD_HOST", "10.10.1.100"), os.environ.get("BOARD_USER", "e3dp"),
                   os.environ["BOARD_PW"], "new")

    @classmethod
    def ref(cls):
        return cls(os.environ.get("REF_HOST", "10.10.0.220"), os.environ.get("REF_USER", "root"),
                   os.environ["REF_PW"], "ref")

    # ---- 실행 ----
    def run(self, cmd, timeout=60):
        _, o, e = self.c.exec_command(cmd, timeout=timeout)
        out = o.read().decode(errors="replace")
        err = e.read().decode(errors="replace")
        return o.channel.recv_exit_status(), out, err

    def sh(self, cmd, timeout=60):
        rc, out, err = self.run(cmd, timeout)
        return out + err

    def root(self, script, timeout=120):
        """스크립트 전체를 root로 한 번에 실행한다."""
        if self.user == "root":
            return self.run("bash -c " + shlex.quote(script), timeout)
        i, o, e = self.c.exec_command("sudo -S -p '' bash -c " + shlex.quote(script), timeout=timeout)
        i.write(self.pw + "\n")
        i.flush()
        out = o.read().decode(errors="replace")
        err = e.read().decode(errors="replace")
        return o.channel.recv_exit_status(), out, err

    # ---- 파일 (연결이 끊기면 재연결 후 재시도) ----
    def reconnect(self):
        try:
            self.c.close()
        except Exception:
            pass
        self.c = paramiko.SSHClient()
        self.c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.c.connect(self.host, username=self.user, password=self.pw, timeout=15,
                       allow_agent=False, look_for_keys=False)
        self.sftp = self.c.open_sftp()

    def _retry(self, fn, tries=5):
        last = None
        for i in range(tries):
            try:
                return fn()
            except (paramiko.SSHException, EOFError, OSError) as e:
                last = e
                time.sleep(3)
                try:
                    self.reconnect()
                except Exception:
                    pass
        raise last

    def put_text(self, text, remote, mode=0o644):
        def go():
            with self.sftp.open(remote, "wb") as f:
                f.write(text.encode("utf-8") if isinstance(text, str) else text)
            self.sftp.chmod(remote, mode)
        self._retry(go)

    def put(self, local, remote, mode=None):
        def go():
            self.sftp.put(local, remote)
            if mode:
                self.sftp.chmod(remote, mode)
        self._retry(go)

    def get_file(self, remote, local):
        """원격 파일을 임시 파일로 받은 뒤 이름을 바꾼다(실패 시 기존 로컬 파일을 건드리지 않는다)."""
        tmp = local + ".part"
        self._retry(lambda: self.sftp.get(remote, tmp))
        os.replace(tmp, local)

    def get_text(self, remote):
        with self.sftp.open(remote, "rb") as f:
            return f.read().decode("utf-8", errors="replace")

    # ---- DP ----
    def prepare(self, db_text, conf_text):
        """/opt/e3dp 디렉터리 구성과 설정 파일 설치. 바이너리는 make가 /opt/e3dp/bin에 복사해 둔 것을 사용."""
        self.root("mkdir -p {o}/conf {o}/log {o}/periodic {o}/download {o}/etc {o}/bin; "
                  "chown -R {u} {o}".format(o=OPT, u=self.user))
        self.put_text(db_text, OPT + "/conf/nelite.db")
        self.put_text(conf_text, OPT + "/conf/nelite.conf")

    def env_up(self, tests_dir, period=None, boundary_in=None, rect=False):
        """시험 환경 전체 기동: 정리 -> 별칭 -> 설정 설치 -> GW/Host 시뮬레이터 -> DP. GW(1)가 정상이 될 때까지 대기.
        period: 정시 수집 주기(분). boundary_in: 초. 지정하면 Host 시각 응답에 오프셋을 줘서 보드 시계가
        다음 10분 경계 boundary_in 초 전이 되게 한다(정시 수집 시험용; env_down에서 시각을 되돌린다).
        rect=True: 정류기 셸프(10.99.0.17)를 DB에 추가하고 rectsim(제어 19002)을 기동한다."""
        import dpapi
        src = os.path.join(tests_dir, dpapi.FIXTURE)
        db = dpapi.make_db(open(src + "nelite.db", encoding="utf-8", errors="replace").read(), period=period)
        if rect:
            db = dpapi.make_db_rect(db)
        conf = dpapi.make_conf(open(src + "nelite.conf", encoding="utf-8").read(), self.host)
        self.dp_stop()
        self.alias_add(SIM_IPS + (dpapi.RECT_SIM_IP,))
        self.prepare(db, conf)
        self.sim_start(os.path.join(tests_dir, "sim", "gwsim.py"))
        if rect:
            self.rectsim_start(os.path.join(tests_dir, "sim", "rectsim.py"))
        offset = 0
        if boundary_in is not None:
            # NTP 동기화 서비스가 시계 변경을 감지해 되돌리므로 시험 동안 멈춘다(env_down에서 다시 시작)
            self.root("systemctl stop systemd-timesyncd 2>/dev/null; systemctl stop ntp 2>/dev/null; true")
            now = int(self.sh("date +%s").strip())
            nb = (now // 600 + 1) * 600
            if nb - now < boundary_in + 30:
                nb += 600
            offset = (nb - boundary_in) - now
            self.clock_shifted = True
        self.hostsim_start(os.path.join(tests_dir, "sim", "hostsim.py"), time_offset=offset)
        self.dp_start()
        ok = dpapi.wait_for(lambda: dpapi.shelves(self).get((1, 0)) == 0, timeout=60)
        assert ok, "DP가 GW(1)를 정상으로 인식하지 못함: " + self.procs()
        self.wait_ready()
        if boundary_in is None:
            self.wait_first_poll_pass()

    def wait_first_poll_pass(self, timeout=120):
        """gw_server의 첫 폴링 사이클이 끝날 때까지 기다린다(첫 GW 첫 포트가 2번 폴링될 때).
        첫 사이클(tsync_cnt==1)에는 각 GW의 첫 포트가 시각 동기 프레임을 대신 보내면서 제어·AO 플래그를 소비해 버린다."""
        import dpapi

        def polled_twice():
            log = self.sim({"op": "get_log"})["log"]
            return sum(1 for x in log if x["ip"] == SIM_IPS[0] and x.get("port") == 1 and x.get("func") == 3) >= 2
        ok = dpapi.wait_for(polled_twice, timeout=timeout, step=1.0)
        assert ok, "gw_server 첫 폴링 사이클이 끝나지 않음"

    READY_LOGS = ("alarm_server", "config_server", "control_server", "db_server", "gather_server", "main_server")

    def wait_ready(self, timeout=120):
        """각 서버가 'Running Now'를 출력할 때까지 기다린다. 이전에 보낸 UDP 요청은 서버가 준비되기 전이면 유실된다."""
        import dpapi
        cmd = "cd %s/log && grep -l 'Running Now' %s 2>/dev/null | wc -l" % (
            OPT, " ".join(n + ".out" for n in self.READY_LOGS))
        ok = dpapi.wait_for(lambda: self.sh(cmd).strip() == str(len(self.READY_LOGS)), timeout=timeout, step=1.0)
        assert ok, "서버 기동 완료 로그가 모두 나타나지 않음: " + self.sh("cd %s/log && grep -c 'Running Now' *.out" % OPT).replace(chr(10), " ")

    def env_down(self):
        self.dp_stop()
        self.alias_del(SIM_IPS + ("10.99.0.17",))
        self.root("pkill -9 -f '[r]ectsim[.]py'; rm -f /tmp/gwsim.py /tmp/gwsim.out /tmp/hostsim.py /tmp/hostsim.out /tmp/rectsim.py /tmp/rectsim.out")
        if getattr(self, "clock_shifted", False):
            self.set_clock()
            self.root("systemctl start systemd-timesyncd 2>/dev/null; systemctl start ntp 2>/dev/null; true")
            self.clock_shifted = False

    def set_clock(self):
        """보드 시계를 PC 시각으로 맞춘다(Host 시각 오프셋 시험 뒤 복구)."""
        self.root("date -s @%d" % int(time.time()))

    def alias_add(self, ips):
        """시뮬레이터 주소를 lo 별칭으로 추가. 로컬 주소로 ping하면 요청 패킷의 출발지가 그 주소가 되어
        netcheck_server(첫 수신 패킷 출발지로 판정)가 성공으로 본다. 127.0.0.x는 출발지가 127.0.0.1이라 실패."""
        self.root("; ".join("ip addr show dev lo | grep -q ' %s/' || ip addr add %s/32 dev lo" % (i, i) for i in ips))

    def alias_del(self, ips):
        self.root("; ".join("ip addr del %s/32 dev lo 2>/dev/null" % i for i in ips) + "; true")

    def dp_stop(self):
        names = " ".join(["smm"] + SERVERS + ["gw_server"])
        pre = ""
        if os.environ.get("COVERAGE"):
            # 계측 빌드는 정상 종료(exit)해야 gcov 데이터(.gcda)가 기록된다: SIGTERM 먼저, 남은 것만 SIGKILL
            pre = "for n in %s; do pkill -TERM -x $n; done; sleep 4; " % names
        self.root(pre + "for n in %s; do pkill -9 -x $n; done; pkill -9 -f '[g]wsim[.]py'; pkill -9 -f '[h]ostsim[.]py'; "
                  "for id in $(ipcs -m | grep 0xe30000 | awk '{print $2}'); do ipcrm -m $id; done; true" % names)
        time.sleep(1)

    # ---- 기준 장치(운영 방식 DP) 보존/복구 ----
    REF_FILES = ("nelite.conf", "nelite.db", "gw_list", "acon_config.json", "alarm.db")

    def ref_save(self, local_dir):
        """기준 장치의 설정·경보 DB를 PC에 백업하고 크기를 검증한다. 기준 프로세스 목록도 저장한다."""
        os.makedirs(local_dir, exist_ok=True)
        for f in self.REF_FILES:
            dst = os.path.join(local_dir, f)
            self.get_file(OPT + "/conf/" + f, dst)
            rsize = self._retry(lambda: self.sftp.stat(OPT + "/conf/" + f).st_size)
            if os.path.getsize(dst) != rsize or rsize == 0:
                raise RuntimeError("백업 검증 실패: %s (원격 %d, 로컬 %d)" % (f, rsize, os.path.getsize(dst)))
        procs = self.sh("ps -eo args | grep -E '/opt/e3dp/bin' | grep -v grep | sort")
        with open(os.path.join(local_dir, "procs_before.txt"), "w") as fo:
            fo.write(procs)
        return procs

    def ref_restore(self, local_dir):
        """테스트 DP·시뮬레이터를 내리고 백업한 설정을 되돌린 뒤 운영 방식(smm, acon_agent)으로 재기동한다.
        smm이 서버 12개를 기동·감시한다. 절대 경로와 setsid로 세션에서 분리해 기동한다.
        반환: 복구 후 프로세스 목록이 백업 시점과 같은지 (bool, 현재 목록)"""
        self.dp_stop()
        for f in self.REF_FILES:
            self.put(os.path.join(local_dir, f), OPT + "/conf/" + f)
        self.root("rm -f %s/log/*.out /tmp/gwsim.py /tmp/gwsim.out /tmp/hostsim.py /tmp/hostsim.out /tmp/hostreq.py" % OPT)
        self.set_clock()
        self.root("pkill -9 -x smm; pkill -9 -x acon_agent; sleep 1; "
                  "setsid nohup %s/bin/smm </dev/null >/dev/null 2>&1 & sleep 1; "
                  "setsid nohup %s/bin/acon_agent </dev/null >/dev/null 2>&1 & sleep 2" % (OPT, OPT))
        base = open(os.path.join(local_dir, "procs_before.txt")).read()
        now = base
        for _ in range(12):
            time.sleep(5)
            now = self.sh("ps -eo args | grep -E '/opt/e3dp/bin' | grep -v grep | sort")
            if now == base:
                return True, now
        return False, now

    def dp_start(self, with_smm=False, delay=3):
        """서버를 root로 기동한다. 출력은 /opt/e3dp/log/*.out"""
        lines = ["cd %s/bin" % OPT, "export PATH=%s/bin:$PATH" % OPT, "rm -f %s/log/*.out" % OPT]
        if os.environ.get("COVERAGE"):
            lines.append("export LD_PRELOAD=/tmp/gcovflush.so")        # 종료 시 gcov 데이터 기록(tools/coverage.py)
        for s in SERVERS:
            lines.append("nohup stdbuf -oL -eL ./%s > %s/log/%s.out 2>&1 &" % (s, OPT, s))
            if s == "main_server":
                lines.append("sleep %d" % delay)
        if with_smm:
            lines.append("nohup stdbuf -oL -eL ./smm > %s/log/smm.out 2>&1 &" % OPT)
        lines.append("sleep 1")
        self.root("\n".join(lines), timeout=90)

    def procs(self):
        return self.sh("ps -eo pid,etime,args | grep -E '_server|smm|gwsim' | grep -v grep")

    def tool(self, cmdline):
        """DP 상태 조회 도구(emon, comp, station, sys 등) 실행"""
        return self.sh("cd %s/bin; ./%s 2>&1" % (OPT, cmdline))

    # ---- 시뮬레이터 제어 (보드의 127.0.0.1:ctl 로 ssh 터널) ----
    def sim_start(self, local_py, ips=SIM_IPS, ctl=19000):
        remote = "/tmp/gwsim.py"
        self.put(local_py, remote, 0o755)
        self.run("pkill -9 -f '[g]wsim[.]py'; true")
        self.run("nohup python3 -u %s --ips %s --ctl %d > /tmp/gwsim.out 2>&1 &" % (remote, ",".join(ips), ctl))
        for _ in range(40):
            time.sleep(0.25)
            try:
                if self.sim({"op": "ping"}, ctl).get("ok"):
                    return
            except Exception:
                pass
        raise RuntimeError("gwsim start failed: " + self.sh("cat /tmp/gwsim.out"))

    def rectsim_start(self, local_py, ip="10.99.0.17", ctl=19002):
        remote = "/tmp/rectsim.py"
        self.put(local_py, remote, 0o755)
        self.run("pkill -9 -f '[r]ectsim[.]py'; true")
        self.run("nohup python3 -u %s --ips %s --ctl %d > /tmp/rectsim.out 2>&1 &" % (remote, ip, ctl))
        for _ in range(40):
            time.sleep(0.25)
            try:
                if self.sim({"op": "ping"}, ctl).get("ok"):
                    return
            except Exception:
                pass
        raise RuntimeError("rectsim start failed: " + self.sh("cat /tmp/rectsim.out"))

    def hostsim_start(self, local_py, ports=(7704, 7510, 7062, 7000, 37), ctl=19001, time_offset=0, host="127.0.0.2"):
        remote = "/tmp/hostsim.py"
        self.put(local_py, remote, 0o755)
        self.root("pkill -9 -f '[h]ostsim[.]py'; true")   # 기동 명령과 같은 스크립트에 넣으면 자기 자신도 종료됨
        # 포트 37(시각 서비스) 바인딩에 root 필요
        self.root("setsid nohup python3 -u %s --host %s --ports %s --ctl %d --time-offset %d </dev/null > /tmp/hostsim.out 2>&1 & sleep 1" % (
            remote, host, ",".join(str(p) for p in ports), ctl, time_offset))
        for _ in range(40):
            time.sleep(0.25)
            try:
                if self.sim({"op": "ping"}, ctl).get("ok"):
                    return
            except Exception:
                pass
        raise RuntimeError("hostsim start failed: " + self.sh("cat /tmp/hostsim.out"))

    def sim(self, req, ctl=19000):
        ch = self.c.get_transport().open_channel("direct-tcpip", ("127.0.0.1", ctl), ("127.0.0.1", 0))
        ch.settimeout(10)
        ch.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            d = ch.recv(65536)
            if not d:
                break
            buf += d
        ch.close()
        return json.loads(buf.decode())

    def udp_send(self, port, data, host="127.0.0.1", src_port=0, wait=0.0):
        """보드 안에서 UDP 데이터그램을 보낸다(Python 3.5 호환 스크립트를 ssh로 실행).
        wait>0 이면 그 시간 동안 같은 소켓으로 수신한 데이터(hex 목록)를 돌려준다."""
        code = """import socket,sys,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.bind(('127.0.0.1',%d))
s.sendto(bytes.fromhex(sys.argv[1]),(sys.argv[2],%d))
s.settimeout(0.3)
end=time.time()+%f
while time.time()<end:
    try:
        d,a=s.recvfrom(65535)
        print(d.hex())
    except socket.timeout:
        pass
""" % (src_port, port, wait)
        rc, out, err = self.run("python3 -c %s %s %s" % (shlex.quote(code), data.hex(), host), timeout=int(wait) + 20)
        if rc != 0:
            raise RuntimeError("udp_send 실패: " + err)
        return [l for l in out.split() if l]

    def host_request_tcp(self, local_py, datagram, port=40100, wait=8.0, stop_after=None, stop_data=b""):
        """UDP 요청을 보내고, DP가 caddr로 TCP 연결을 맺어 보내는 응답까지 받는다(sim/hostreq.py 사용).
        반환: {"udp": [hex], "tcp": [[hex 청크...], ...]}"""
        import json
        remote = "/tmp/hostreq.py"
        self.put(local_py, remote, 0o755)
        extra = "" if stop_after is None else " 7999 %s %s" % (stop_after, stop_data.hex())
        rc, out, err = self.run("python3 %s %s %s %d%s" % (remote, datagram.hex(), wait, port, extra), timeout=int(wait) + 30)
        if rc != 0:
            raise RuntimeError("hostreq 실패: " + err)
        return json.loads(out.strip().splitlines()[-1])

    def tcp(self, port, host="127.0.0.1", timeout=10):
        """보드 안의 host:port 에 대한 TCP 연결(ssh 터널). socket과 같은 sendall/recv 인터페이스."""
        ch = self.c.get_transport().open_channel("direct-tcpip", (host, port), ("127.0.0.1", 0))
        ch.settimeout(timeout)
        return ch

    def close(self):
        try:
            self.sftp.close()
            self.c.close()
        except Exception:
            pass
