<map version="1.0.1">
<!-- E3-DP 공유 메모리 구조 마인드맵. FreeMind / Freeplane 에서 열 수 있음. 원본 문서: 공유메모리구조.md -->
<node ID="ID_1" TEXT="E3-DP 공유 메모리 (소스 e3dp.2.1 기준)" COLOR="#000000">
  <node ID="ID_2" TEXT="개요" POSITION="right" COLOR="#1f4e79">
    <node ID="ID_3" TEXT="통신 수단 2가지">
      <node ID="ID_4" TEXT="공유 메모리(SysV shmget/shmat): 데이터(현재값·상태·설정) 공유"/>
      <node ID="ID_5" TEXT="UDP 소켓: Host 요청을 main_server가 서비스별 서버로 전달"/>
    </node>
    <node ID="ID_6" TEXT="ACB(경보 버퍼)만 예외: alarm.db 파일 mmap"/>
    <node ID="ID_7" TEXT="락(세마포어/뮤텍스/flock) 없음 (src, lib 전체)">
      <icon BUILTIN="messagebox_warning"/>
    </node>
    <node ID="ID_8" TEXT="모든 세그먼트 권한 0666 + IPC_CREAT, 먼저 기동한 프로세스가 생성"/>
    <node ID="ID_9" TEXT="attach 함수: lib/e3/e3lib.c CreateSharedMemory (실패 시 NULL, 호출측 검사 없음)"/>
  </node>
  <node ID="ID_10" TEXT="[A] 시스템·설정" POSITION="right" COLOR="#1f4e79">
    <node ID="ID_11" TEXT="netconfig  key 0xE3000001  182 B">
      <node ID="ID_12" TEXT="NetworkConfigRec"/>
      <node ID="ID_13" TEXT="wire_id, wire_type, hostname, MIH/Private/Host/경보호스트 IP, 넷마스크, 게이트웨이, 서브넷"/>
      <node ID="ID_14" TEXT="쓰기: main_server만 (nelite.conf 로드)"/>
    </node>
    <node ID="ID_15" TEXT="shard_m  key 0xE3000002  872 B">
      <node ID="ID_16" TEXT="struct shard_memory (패킹 안 됨: 870 + 패딩 2)"/>
      <node ID="ID_17" TEXT="슬롯 15개: main, db, config, scan, gather, real(rt), alarm, alarm_h, control, modbus, rect, netcheck, realdata, reserv2, reserv3"/>
      <node ID="ID_18" TEXT="미사용 슬롯: alarm_h, reserv2, reserv3 / gw_server는 슬롯 없음"/>
      <node ID="ID_19" TEXT="cnt_xxx: 서버가 3초마다 +1 (100 이상이면 0)"/>
      <node ID="ID_20" TEXT="kill_xxx: 9이면 서버 종료. 9를 쓰는 코드는 소스에 없음">
        <icon BUILTIN="messagebox_warning"/>
      </node>
      <node ID="ID_21" TEXT="ver_xxx[50]: 기동 시 VERSION 기록"/>
      <node ID="ID_22" TEXT="smm 감시: 120초마다 비교, 같으면 ProcessKilled 후 bin/서버 재실행 (12개 서버)"/>
    </node>
    <node ID="ID_23" TEXT="Proc  key 0xE000002  174 B">
      <node ID="ID_24" TEXT="ProcRec: cnt_acon, kill_acon, ver_acon + 예약"/>
      <node ID="ID_25" TEXT="acagent_checker가 생성·0 초기화, 20초마다 cnt_acon 비교, 같으면 acon_agent 재실행"/>
      <node ID="ID_26" TEXT="acon_agent: cnt_acon 65000까지 증가 후 0"/>
      <node ID="ID_27" TEXT="키가 0xE3…이 아님 (코드 전체 일관)"/>
    </node>
  </node>
  <node ID="ID_28" TEXT="[B] 실시간 DB (핵심)" POSITION="right" COLOR="#1f4e79">
    <node ID="ID_29" TEXT="DrDB  key 0xE3000003  332,237 B">
      <node ID="ID_30" TEXT="DrModuleRec (PACKED)"/>
      <node ID="ID_31" TEXT="헤더 32 B">
        <node ID="ID_32" TEXT="stationid[4], type (1 Local / 2 Remote / 3 Comm)"/>
        <node ID="ID_33" TEXT="self_ip, host_ip: main_server가 netconfig에서 변환"/>
        <node ID="ID_34" TEXT="periodinterval, period_flag(gather)"/>
        <node ID="ID_35" TEXT="isdownload">
          <node ID="ID_36" TEXT="0: 다운로드 데이터 수신 중 (DrDB 전체가 0으로 초기화됨)"/>
          <node ID="ID_37" TEXT="2 READY: db_server 기동"/>
          <node ID="ID_38" TEXT="3 START: 순간값 (직후 0으로 지워짐)"/>
          <node ID="ID_39" TEXT="4 STOP: 수신 종료, 후처리 중 (실패 아님)"/>
          <node ID="ID_40" TEXT="5 SUCCESS: 정상 운영"/>
          <node ID="ID_41" TEXT="1 DR_SYSTEM_CONFIRM: 비교만 함"/>
        </node>
        <node ID="ID_42" TEXT="iscontrol, control_user, control_mode, control_pre_mode: control_server"/>
        <node ID="ID_43" TEXT="usedcomps, total_ports, total_points, point_count, lport_count, comp_count: db_server"/>
      </node>
      <node ID="ID_44" TEXT="comp[300]  29 B x 300: 구성품 정보">
        <node ID="ID_45" TEXT="facilname, compname(5), compno, usedlports ..."/>
      </node>
      <node ID="ID_46" TEXT="lport[2500]  103 B x 2500: 논리포트">
        <node ID="ID_47" TEXT="식별: compid, compno, compname, portno, type"/>
        <node ID="ID_48" TEXT="value (float): 현재 계측/상태값">
          <node ID="ID_49" TEXT="쓰기: gw, rect, control, scan, modbus, db, gather(VCB_ 1번 포트 19), emon"/>
        </node>
        <node ID="ID_50" TEXT="status: 경보 상태">
          <node ID="ID_51" TEXT="0 정상 / 1 하한 / 2 상한 / 3 디지털 / 5 없음"/>
          <node ID="ID_52" TEXT="20 Invalid / 21 GW 설정 없음 / 22 통신이상 / 23 한전·발전 마스킹"/>
          <node ID="ID_53" TEXT="쓰기: scan, gw, netcheck, rect, db(다운로드 시 22), emon"/>
          <node ID="ID_54" TEXT="alarm: 디지털 포트에서 value&amp;alarmmask가 pvalue와 달라지면 DIGITAL/NORMAL (alarm_check.c:299-333)"/>
        </node>
        <node ID="ID_55" TEXT="com_status: 통신 상태">
          <node ID="ID_56" TEXT="0x11 FAIL 0x22 ERROR 0x33 READY 0x44 NORMAL"/>
          <node ID="ID_57" TEXT="0x55 LPORT_DOWN 0x66 POINT_DOWN 0x77 RT(수신 중) 0x88 PING"/>
          <node ID="ID_58" TEXT="쓰기: gw, rect, netcheck, scan, gather(0x77), db(다운로드 시 0x33)"/>
          <node ID="ID_59" TEXT="alarm의 set_lport_com_status()는 호출부가 주석 처리되어 미실행"/>
        </node>
        <node ID="ID_60" TEXT="highlimit, lowlimit, alarmmask: config_server (초기값 db)"/>
        <node ID="ID_61" TEXT="deadband: db_server만 / dband: config가 쓰지만 읽는 곳 없음"/>
        <node ID="ID_62" TEXT="peakvalue: alarm, emon / pvalue: alarm(디지털 포트 직전 value&amp;alarmmask)"/>
        <node ID="ID_63" TEXT="pstatus: alarm (db가 0으로 초기화) / hpeak, lpeak: alarm, gather"/>
        <node ID="ID_64" TEXT="otime1/2, rtime1/2: alarm"/>
        <node ID="ID_65" TEXT="occ_time: scan"/>
        <node ID="ID_66" TEXT="tree_port: 1 한전 / 2 발전 / 3 한전&amp;발전 / 4 발전&amp;발전 (쓰기 db)"/>
        <node ID="ID_67" TEXT="tree: 어느 서버도 읽거나 쓰지 않음"/>
        <node ID="ID_68" TEXT="rtvalue: 쓰는 코드가 없음 (읽기: gw, rect, large_rect)">
          <icon BUILTIN="messagebox_warning"/>
        </node>
        <node ID="ID_69" TEXT="rackno, shelfno, slotno, channelno: 물리 위치 (db_server)"/>
        <node ID="ID_70" TEXT="AO 명령 전달 (power_reset, high_flag, low_flag)">
          <node ID="ID_71" TEXT="1. config_server/acon_agent가 power_reset=0xAF, high_flag=주소, low_flag=값 기록"/>
          <node ID="ID_72" TEXT="high_flag = channelno x 1000 + shelfno x 10 + boardno (compid 302 DCDS는 mr_addr)"/>
          <node ID="ID_73" TEXT="2. gw_server check_ao_set()이 읽어 GW로 전송 후 3개 필드 0으로 클리어"/>
          <node ID="ID_74" TEXT="3. 정류기는 rect_server가 high_flag=레지스터 주소, low_flag=값으로 전송 후 클리어 (기동 시 주소 사전 설정)"/>
          <node ID="ID_75" TEXT="power_reset 0x33, 0x34~0x37 (DC 설정): 읽는 쪽 확인 못 함"/>
        </node>
      </node>
      <node ID="ID_76" TEXT="point[3000]  22 B x 3000: 물리 포인트 (GW 포트·채널 매핑)"/>
      <node ID="ID_77" TEXT="init_modbus / init_rect / init_alarm / init_rt / init_periodic  (5 B)">
        <node ID="ID_78" TEXT="db_server가 다운로드 완료 시 모두 INIT_NEED(1)"/>
        <node ID="ID_79" TEXT="init_modbus: modbus_server가 읽고 재적용 후 0으로 내림"/>
        <node ID="ID_80" TEXT="init_rect: rect가 기동 시 1로 두지만 확인 코드는 #if 0"/>
        <node ID="ID_81" TEXT="init_rect, init_alarm, init_rt, init_periodic: 활성 코드에서 읽는 서버 없음 (emon 출력만)">
          <icon BUILTIN="messagebox_warning"/>
        </node>
      </node>
    </node>
    <node ID="ID_82" TEXT="DrSI  key 0xE3000004  12,005 B">
      <node ID="ID_83" TEXT="DrSystemRec: 헤더 5 B + shelf[300] x 40 B"/>
      <node ID="ID_84" TEXT="shelf = 하위 장비 1대">
        <node ID="ID_85" TEXT="rackno(DP 번호), shelfno(GW 번호)"/>
        <node ID="ID_86" TEXT="compno: 1 DP / 2 GW / 3 정류기 / 4 ACON / 41~50 계측기·UPS 등"/>
        <node ID="ID_87" TEXT="usedslots: IP 끝자리 (db_server만 씀. modbus의 적용 코드는 주석 처리)"/>
        <node ID="ID_88" TEXT="compid: Modbus 번호 (1~4, 9)"/>
        <node ID="ID_89" TEXT="ipaddr[20]"/>
        <node ID="ID_90" TEXT="status/pstatus: 0 정상 / 3 통신이상 / 99 설정 없음"/>
        <node ID="ID_91" TEXT="com_fail_cnt: netcheck, rect (db 초기화) / flag: netcheck (db 초기화)"/>
        <node ID="ID_92" TEXT="otime/rtime: alarm_server"/>
      </node>
    </node>
    <node ID="ID_93" TEXT="raw_idx  key 0xE3000010  4,400 B">
      <node ID="ID_94" TEXT="begin/end[100][11]: (GW 단위, 포트) -&gt; DrDB.point[] 범위"/>
      <node ID="ID_95" TEXT="쓰기: db_server / 읽기: gw_server"/>
    </node>
  </node>
  <node ID="ID_96" TEXT="[C] 이력 버퍼" POSITION="right" COLOR="#1f4e79">
    <node ID="ID_97" TEXT="DrPCB  key 0xE3000005  61,204 B">
      <node ID="ID_98" TEXT="정시 데이터 1700건 x 36 B"/>
      <node ID="ID_99" TEXT="gather_server 쓰고 읽음 (20건씩 파일 저장 후 Host 전송)"/>
    </node>
    <node ID="ID_100" TEXT="PeakDB  key 0xE3000006  8,722 B">
      <node ID="ID_101" TEXT="피크 300건 x 29 B + 전력값 4개 (pre/now/old/calc_data)"/>
      <node ID="ID_102" TEXT="gw_server: now_data, calc_data / gather_server: 피크 항목"/>
    </node>
    <node ID="ID_103" TEXT="DcdsDB  key 0xE3000007  14,504 B">
      <node ID="ID_104" TEXT="항목 500건"/>
      <node ID="ID_105" TEXT="rect_server가 생성 (attach 없음!) / gather_server가 소비">
        <icon BUILTIN="messagebox_warning"/>
      </node>
      <node ID="ID_106" TEXT="호출 조건: (int)value != 0 이고 lport 인덱스 i == 0 (rtvalue를 쓰는 코드가 없어 항상 0)"/>
    </node>
    <node ID="ID_107" TEXT="UpsDB  key 0xE3000008  8,704 B">
      <node ID="ID_108" TEXT="항목 300건"/>
      <node ID="ID_109" TEXT="gw_server가 생성 (attach 없음!) / gather_server가 소비">
        <icon BUILTIN="messagebox_warning"/>
      </node>
      <node ID="ID_110" TEXT="호출 조건: (value&amp;1)==0 이고 (rtvalue&amp;1)!=0 인데 rtvalue를 쓰는 코드가 없어 참이 될 수 없음"/>
    </node>
    <node ID="ID_111" TEXT="항목 관리: Used(사용 중) + Rid(Host 요청 ID), 응답 rid 일치 시 처리"/>
  </node>
  <node ID="ID_112" TEXT="[D] 정전/발전기 플래그 (1 B x 9, scan_server만 씀)" POSITION="right" COLOR="#1f4e79">
    <node ID="ID_113" TEXT="MAIN_ON_OFF_FLAG  0xE3000011: 입전 확정 1 / 정전·복구 대기 0"/>
    <node ID="ID_114" TEXT="VCB_FLAG  0xE3000012: VCB OFF 또는 전압이상(UV)이면 1"/>
    <node ID="ID_115" TEXT="MAIN_VCB_FLAG  0xE3000013: 서버 로직 미사용 (emon 출력만)"/>
    <node ID="ID_116" TEXT="MAIN_VCB_FLAG_COUNT  0xE3000014: 정전 시 8, 입전 조건마다 1초 대기 후 -1, 0이면 입전 확정"/>
    <node ID="ID_117" TEXT="MAIN_GEN_FLAG  0xE3000015: 발전기 1~4 중 하나라도 RUN이면 1"/>
    <node ID="ID_118" TEXT="MAIN_GEN_FLAG1~4  0xE3000016~19: 발전기 #1~#4 RUN 여부 (FLAG4는 scan, gw만 attach)"/>
    <node ID="ID_119" TEXT="읽는 곳: alarm_server가 MAIN_GEN_FLAG만 읽음">
      <node ID="ID_120" TEXT="tree_port=한전: 정전이면 경보 생략"/>
      <node ID="ID_121" TEXT="tree_port=발전: 발전기 RUN 아니면 생략"/>
      <node ID="ID_122" TEXT="tree_port=공통: 발전기 STOP이고 정전이면 생략"/>
      <node ID="ID_123" TEXT="정전 판정(Dr_VCB_CHECK)은 공유 플래그가 아니라 DrDB 포트 값을 직접 읽음"/>
    </node>
    <node ID="ID_124" TEXT="판정 상태 변화: 입전 -&gt; 정전 -&gt; 복구대기(COUNT 감소) -&gt; 입전"/>
  </node>
  <node ID="ID_125" TEXT="[E] 경보 버퍼 (alarm.db mmap)" POSITION="left" COLOR="#1f4e79">
    <node ID="ID_126" TEXT="DrAlarmRec_ACBRec: flag, req_id, ACB[3000]"/>
    <node ID="ID_127" TEXT="크기: 156,006 B (64비트, 컴파일 확인) / 144,006 B (32비트, 계산값)"/>
    <node ID="ID_128" TEXT="경보 발생 -&gt; ACB 기록 -&gt; Host 전송 -&gt; 응답 rid 수신 시 삭제"/>
    <node ID="ID_129" TEXT="ACB 전체 초기화(DrAlarmACBInitialize) 시점">
      <node ID="ID_130" TEXT="alarm_server 기동 때마다 (alarm/init_shm.c:113)"/>
      <node ID="ID_131" TEXT="구성 다운로드 완료 후 3초 대기 뒤 (alarm_server.c:167)"/>
      <node ID="ID_132" TEXT="실행 인자 init (alarm_server.c:105)"/>
      <node ID="ID_133" TEXT="=&gt; 재기동 시 기존 ACB 유지되지 않음 (README 설명과 다름)">
        <icon BUILTIN="messagebox_warning"/>
      </node>
    </node>
    <node ID="ID_134" TEXT="emon: 같은 파일을 읽기/쓰기 mmap, 새 파일 생성 시 또는 alarm init 명령으로 초기화"/>
  </node>
  <node ID="ID_135" TEXT="프로세스별 공유 메모리 접근" POSITION="left" COLOR="#1f4e79">
    <node ID="ID_136" TEXT="main_server (src/main)">
      <node ID="ID_137" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~18"/>
      <node ID="ID_138" TEXT="쓰기: netconfig 전체, DrDB.type/self_ip/host_ip"/>
      <node ID="ID_139" TEXT="UDP: Host 요청을 서비스 테이블로 분배"/>
    </node>
    <node ID="ID_140" TEXT="db_server (src/db)">
      <node ID="ID_141" TEXT="attach: netconfig, shard_m, DrDB, DrSI, DrPCB, PeakDB, DcdsDB, raw_idx, 플래그 11~18"/>
      <node ID="ID_142" TEXT="쓰기: DrDB 구성, DrSI 구성, raw_idx, isdownload, init_* 5개, lport 초기값"/>
      <node ID="ID_143" TEXT="UDP 8002, nelite.db 저장·복원"/>
    </node>
    <node ID="ID_144" TEXT="config_server (src/config)">
      <node ID="ID_145" TEXT="attach: netconfig, shard_m, DrDB, DrSI"/>
      <node ID="ID_146" TEXT="쓰기: 상하한·마스크·dband, AO 명령(power_reset/high_flag/low_flag), control_* 일부"/>
      <node ID="ID_147" TEXT="UDP 7032"/>
    </node>
    <node ID="ID_148" TEXT="scan_server (src/scan)">
      <node ID="ID_149" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~19"/>
      <node ID="ID_150" TEXT="쓰기: lport.status/com_status/value(가상포인트)/occ_time, 플래그 전부"/>
    </node>
    <node ID="ID_151" TEXT="gw_server (src/gw)">
      <node ID="ID_152" TEXT="attach: netconfig, shard_m, DrDB, DrSI, PeakDB, raw_idx, 플래그 11~19"/>
      <node ID="ID_153" TEXT="쓰기: lport.value/com_status/status, DrSI.shelf.status, PeakDB 전력값, UpsDB(attach 없음)"/>
      <node ID="ID_154" TEXT="읽기: raw_idx, AO 명령"/>
    </node>
    <node ID="ID_155" TEXT="modbus_server (src/modbus)">
      <node ID="ID_156" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~18"/>
      <node ID="ID_157" TEXT="쓰기: init_modbus, lport.value 초기화, power_reset/high_flag/low_flag 클리어"/>
      <node ID="ID_158" TEXT="README의 usedslots 적용 코드는 주석 처리 (db_server로 이동)"/>
      <node ID="ID_159" TEXT="GW 5대당 gw_server 1개 기동"/>
    </node>
    <node ID="ID_160" TEXT="rect_server (src/rect)">
      <node ID="ID_161" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~18"/>
      <node ID="ID_162" TEXT="쓰기: lport.value/com_status/status, AO 주소(high_flag), init_rect(기동 시), DrSI.shelf.status/com_fail_cnt, DcdsDB(attach 없음)"/>
    </node>
    <node ID="ID_163" TEXT="netcheck_server (src/netcheck)">
      <node ID="ID_164" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~18"/>
      <node ID="ID_165" TEXT="쓰기: DrSI.shelf.status/flag/com_fail_cnt, lport.status=22/com_status"/>
    </node>
    <node ID="ID_166" TEXT="control_server (src/control)">
      <node ID="ID_167" TEXT="attach: netconfig, shard_m, DrDB, DrSI, PeakDB, DcdsDB, 플래그 11~18"/>
      <node ID="ID_168" TEXT="쓰기: 제어 포인트 lport.value, iscontrol/control_*"/>
      <node ID="ID_169" TEXT="UDP 8022"/>
    </node>
    <node ID="ID_170" TEXT="alarm_server (src/alarm)">
      <node ID="ID_171" TEXT="attach: netconfig, shard_m, DrDB, DrSI, DrPCB, PeakDB, DcdsDB, UpsDB, 플래그 11~18, DR_ACB"/>
      <node ID="ID_172" TEXT="쓰기: DR_ACB, lport 피크·시각·pvalue, 디지털 포트 status, DrSI.shelf.pstatus/시각"/>
      <node ID="ID_173" TEXT="읽기: MAIN_GEN_FLAG"/>
    </node>
    <node ID="ID_174" TEXT="gather_server (src/gather)">
      <node ID="ID_175" TEXT="attach: netconfig, shard_m, DrDB, DrPCB, PeakDB, DcdsDB, UpsDB"/>
      <node ID="ID_176" TEXT="쓰기: DrPCB, PeakDB 항목, DcdsDB/UpsDB 해제·ID, period_flag, lport.hpeak/lpeak, VCB_ 1번 포트 19 value/com_status"/>
    </node>
    <node ID="ID_177" TEXT="rt_server (src/rt)">
      <node ID="ID_178" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~18"/>
      <node ID="ID_179" TEXT="읽기: DrDB / UDP 8052, 값·상태 변할 때 응답"/>
    </node>
    <node ID="ID_180" TEXT="realdata_server (src/realdata)">
      <node ID="ID_181" TEXT="attach: shard_m, DrDB"/>
      <node ID="ID_182" TEXT="읽기: DrDB / TCP 7995, 최대 30 클라이언트"/>
    </node>
    <node ID="ID_183" TEXT="smm (src/smm)">
      <node ID="ID_184" TEXT="shard_m 읽기, 멈춘 서버 재기동"/>
    </node>
    <node ID="ID_185" TEXT="emon (src/emon)">
      <node ID="ID_186" TEXT="attach: netconfig, shard_m, DrDB, DrSI, 플래그 11~18, DR_ACB"/>
      <node ID="ID_187" TEXT="점검 CLI: shm/sys/smm/flag/comp/lport/raw/point/alarm 출력, 값·통신상태 수동 설정"/>
    </node>
    <node ID="ID_188" TEXT="acon_agent / acagent_checker">
      <node ID="ID_189" TEXT="acon_agent attach: netconfig, shard_m, DrDB, DrSI, Proc / TCP 9785"/>
      <node ID="ID_190" TEXT="AO 설정: lport.high_flag/low_flag/power_reset=0xAF 기록"/>
      <node ID="ID_191" TEXT="acagent_checker: Proc 생성, 20초마다 감시"/>
    </node>
    <node ID="ID_192" TEXT="upgrade_server (src/upgrade, 루트 Makefile 빌드 대상 아님)">
      <node ID="ID_193" TEXT="attach: netconfig, DrDB, DrSI"/>
      <node ID="ID_194" TEXT="읽기: DrSI.shelf 중 GW(compno==2) 목록 순회"/>
    </node>
  </node>
  <node ID="ID_195" TEXT="Host 요청 분배 (main_server UDP)" POSITION="left" COLOR="#1f4e79">
    <node ID="ID_196" TEXT="EVR_DB_* (구성 다운로드·저장) -&gt; db_server  UDP 8002"/>
    <node ID="ID_197" TEXT="한계/마스크/AO/kWh 초기화, 제어모드 -&gt; config_server  UDP 7032"/>
    <node ID="ID_198" TEXT="제어 스크립트·룰 -&gt; control_server  UDP 8022"/>
    <node ID="ID_199" TEXT="실시간 요청 설정/해제 -&gt; rt_server  UDP 8052"/>
    <node ID="ID_200" TEXT="EVR_DB_SYSTEM_UPDATE: 전달 없이 main_server가 시각 동기화"/>
  </node>
  <node ID="ID_201" TEXT="소스 점검에서 확인된 사항" POSITION="left" COLOR="#1f4e79">
    <node ID="ID_202" TEXT="rect_server: DcdsDB를 attach 없이 사용 (rect_server.c:624, large_rect.c:199)">
      <icon BUILTIN="messagebox_warning"/>
    </node>
    <node ID="ID_203" TEXT="gw_server: UpsDB를 attach 없이 사용 (gw_server.c:739)">
      <icon BUILTIN="messagebox_warning"/>
    </node>
    <node ID="ID_204" TEXT="rtvalue를 쓰는 코드가 src/lib/include/cgi-bin 어디에도 없음 -&gt; 위 호출 조건이 거의/전혀 충족되지 않음"/>
    <node ID="ID_205" TEXT="README와 코드 불일치: alarm 재기동 시 ACB 유지(README) vs 기동마다 초기화(코드), modbus의 GW IP 적용(README) vs 주석 처리(db로 이동)"/>
    <node ID="ID_206" TEXT="control_auto.c: SRAM 절대주소 0xd7000026 사용, 호출부 주석 처리로 미실행"/>
    <node ID="ID_207" TEXT="다운로드 시작 시 DrDB를 구조체 끝보다 13 B 넘게 0으로 씀 (ldb_download.c:48-52)"/>
    <node ID="ID_208" TEXT="SHM_DR_ACB_KEY 0xE3000009: 정의만 있고 attach 주석 처리"/>
    <node ID="ID_209" TEXT="emon/common.h SHM_KEY_NUM 9527: 오래된 키, 현재 키는 0xE3000002"/>
    <node ID="ID_210" TEXT="shmget 크기 불일치(기존보다 큰 크기 요청)는 EINVAL: 구조체 크기 변경 시 기존 세그먼트 정리 필요"/>
  </node>
  <node ID="ID_211" TEXT="검증 기준" POSITION="left" COLOR="#1f4e79">
    <node ID="ID_212" TEXT="구조체 크기: 실제 헤더를 gcc 13.3(x86_64)로 컴파일해 sizeof 확인"/>
    <node ID="ID_213" TEXT="attach 목록: gcc -E 전처리 결과 기준 (#if 0, 주석 제외)"/>
    <node ID="ID_214" TEXT="값의 의미·동작: 소스 줄 직접 확인"/>
    <node ID="ID_215" TEXT="소스 트리 기준이며 장비 배포본과 일치 여부는 미확인"/>
  </node>
</node>
</map>
