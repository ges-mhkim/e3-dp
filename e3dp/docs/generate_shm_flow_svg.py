#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E3-DP 공유메모리 데이터 흐름 SVG 생성기
공유메모리구조.md의 '6. 데이터 흐름' Mermaid 다이어그램을 바탕으로
가독성이 뛰어난 고품질 벡터 SVG를 생성합니다.
"""

import html
import os

def generate_svg(output_path):
    width = 1760
    height = 1260

    # 노드 정의 (BT: 아래가 외부, 가운데가 서버 프로세스, 위가 공유 메모리)
    nodes = {
        # === 외부 (EXT) y: 1060 ~ 1140 ===
        "HOST":  {"x": 90,   "y": 1060, "w": 220, "h": 76, "label": "Host 서버", "sub": "상위 관제 시스템", "tag": "UDP 통신", "group": "EXT"},
        "GW":    {"x": 510,  "y": 1060, "w": 180, "h": 76, "label": "E3-GW", "sub": "현장 게이트웨이 (1502)", "tag": "TCP/IP", "group": "EXT"},
        "RECT":  {"x": 800,  "y": 1060, "w": 180, "h": 76, "label": "정류기", "sub": "전원/배터리 장치 (시리얼)", "tag": "RS-232/485", "group": "EXT"},
        "PING":  {"x": 1090, "y": 1060, "w": 200, "h": 76, "label": "하위 장비 (ping)", "sub": "IP 네트워크 핑 감시 대상", "tag": "ICMP", "group": "EXT"},
        "AHOST": {"x": 1440, "y": 1060, "w": 220, "h": 76, "label": "Alarm Host", "sub": "경보 전송 수신 호스트", "tag": "UDP 경보", "group": "EXT"},

        # === 서버 프로세스 (PROC) ===
        # 상단 코어 처리 행 (y: 520)
        "DB":    {"x": 90,   "y": 520,  "w": 150, "h": 66, "label": "db_server", "sub": "구성 DB 복원/다운로드", "group": "PROC"},
        "CFG":   {"x": 270,  "y": 520,  "w": 160, "h": 66, "label": "config_server", "sub": "설정/한계치/AO 제어", "group": "PROC"},
        "CTRL":  {"x": 460,  "y": 520,  "w": 160, "h": 66, "label": "control_server", "sub": "제어 룰/시퀀스 실행", "group": "PROC"},
        "RDS":   {"x": 660,  "y": 520,  "w": 160, "h": 66, "label": "realdata_server", "sub": "실시간 데이터 서비스", "group": "PROC"},
        "SCAN":  {"x": 860,  "y": 520,  "w": 160, "h": 66, "label": "scan_server", "sub": "알람 판정/정전 감시", "group": "PROC"},
        "SMM":   {"x": 1480, "y": 520,  "w": 150, "h": 66, "label": "smm", "sub": "프로세스 생존 감시", "group": "PROC"},

        # 하단 인터페이스 행 (y: 770)
        "MAIN":  {"x": 90,   "y": 770,  "w": 160, "h": 68, "label": "main_server", "sub": "통신/명령 분배 (핵심)", "group": "PROC_MAIN"},
        "RT":    {"x": 290,  "y": 770,  "w": 140, "h": 68, "label": "rt_server", "sub": "실시간 데이터 응답", "group": "PROC"},
        "GWS":   {"x": 510,  "y": 770,  "w": 180, "h": 68, "label": "gw_server", "sub": "GW 계측 데이터 수집", "group": "PROC"},
        "RECTS": {"x": 800,  "y": 770,  "w": 180, "h": 68, "label": "rect_server", "sub": "정류기 계측 수집", "group": "PROC"},
        "NET":   {"x": 1090, "y": 770,  "w": 200, "h": 68, "label": "netcheck_server", "sub": "Ping 감시 및 통신품질", "group": "PROC"},
        "GATH":  {"x": 1330, "y": 770,  "w": 160, "h": 68, "label": "gather_server", "sub": "정시/이력 생성 전송", "group": "PROC"},
        "ALM":   {"x": 1520, "y": 770,  "w": 160, "h": 68, "label": "alarm_server", "sub": "경보 감지/전송/이력", "group": "PROC"},

        # === 공유 메모리 (SHM) y: 190 ~ 340 ===
        "NCFG":  {"x": 90,   "y": 220,  "w": 150, "h": 72, "label": "netconfig", "sub": "네트워크 통신 설정", "group": "SHM"},
        "RAW":   {"x": 270,  "y": 220,  "w": 140, "h": 72, "label": "raw_idx", "sub": "GW 포인트 인덱스 맵", "group": "SHM"},
        "DRSI":  {"x": 440,  "y": 220,  "w": 160, "h": 72, "label": "DrSI 시스템 DB", "sub": "시스템 정보/통신상태", "group": "SHM"},
        "DRDB":  {"x": 630,  "y": 185,  "w": 360, "h": 140, "label": "DrDB 포인트 DB", "sub": "E3-DP 핵심 실시간 계측 데이터베이스", "group": "SHM_CORE"},
        "FLG":   {"x": 1020, "y": 220,  "w": 160, "h": 72, "label": "정전/발전기 플래그", "sub": "MAIN_PE_FLAG 등", "group": "SHM"},
        "HIST":  {"x": 1210, "y": 220,  "w": 170, "h": 72, "label": "PeakDB / DcdsDB\n/ UpsDB", "sub": "각종 이력 DB 버퍼", "group": "SHM"},
        "PCB":   {"x": 1400, "y": 220,  "w": 120, "h": 72, "label": "DrPCB", "sub": "정시 데이터 이력", "group": "SHM"},
        "ACB":   {"x": 1540, "y": 320,  "w": 140, "h": 70, "label": "DR_ACB", "sub": "경보 버퍼 (alarm.db)", "group": "SHM"},
        "SM":    {"x": 1540, "y": 195,  "w": 130, "h": 72, "label": "shard_m", "sub": "서버 생존 슬롯 카운터", "group": "SHM"},
    }

    # 연결선 37개 정의
    connections = [
        # --- 1. 외부 <-> 서버 프로세스 (UDP 및 외부 수집) ---
        {"from": "HOST",  "to": "MAIN",  "type": "udp",   "label": "UDP 요청", "from_pt": (150, 1060), "to_pt": (140, 838), "mid": (110, 950)},
        {"from": "MAIN",  "to": "DB",    "type": "udp",   "label": "UDP 8002 구성 다운로드", "from_pt": (145, 770), "to_pt": (145, 586), "mid": (145, 680)},
        {"from": "MAIN",  "to": "CFG",   "type": "udp",   "label": "UDP 7032 한계/마스크/AO", "from_pt": (195, 770), "to_pt": (330, 586), "mid": (250, 680)},
        {"from": "MAIN",  "to": "CTRL",  "type": "udp",   "label": "UDP 8022 제어", "from_pt": (220, 770), "to_pt": (520, 586), "mid": (360, 690)},
        {"from": "MAIN",  "to": "RT",    "type": "udp",   "label": "UDP 8052 실시간 요청", "from_pt": (250, 804), "to_pt": (290, 804), "mid": (270, 792)},
        {"from": "GW",    "to": "GWS",   "type": "io",    "label": "수집", "from_pt": (600, 1060), "to_pt": (600, 838), "mid": (580, 950)},
        {"from": "RECT",  "to": "RECTS", "type": "io",    "label": "수집", "from_pt": (890, 1060), "to_pt": (890, 838), "mid": (870, 950)},
        {"from": "PING",  "to": "NET",   "type": "io",    "label": "ping", "from_pt": (1190, 1060), "to_pt": (1190, 838), "mid": (1170, 950)},
        {"from": "ALM",   "to": "AHOST", "type": "udp",   "label": "UDP 경보 전송", "from_pt": (1580, 838), "to_pt": (1550, 1060), "mid": (1610, 950)},
        {"from": "GATH",  "to": "HOST",  "type": "udp",   "label": "이력 전송", "from_pt": (1380, 838), "to_pt": (250, 1060), "special": "gath_host"},
        {"from": "RT",    "to": "HOST",  "type": "udp",   "label": "실시간 응답", "from_pt": (340, 838), "to_pt": (200, 1060), "mid": (290, 950)},

        # --- 2. 프로세스 -> 공유 메모리 쓰기 (W) ---
        {"from": "MAIN",  "to": "NCFG",  "type": "write", "from_pt": (110, 770), "to_pt": (120, 292), "special": "main_ncfg"},
        {"from": "DB",    "to": "DRDB",  "type": "write", "from_pt": (210, 520), "to_pt": (660, 325), "mid": (420, 420)},
        {"from": "DB",    "to": "DRSI",  "type": "write", "from_pt": (180, 520), "to_pt": (480, 292), "mid": (320, 380)},
        {"from": "DB",    "to": "RAW",   "type": "write", "from_pt": (150, 520), "to_pt": (330, 292), "mid": (230, 390)},
        {"from": "GWS",   "to": "DRDB",  "type": "write", "from_pt": (580, 770), "to_pt": (710, 325), "mid": (620, 540)},
        {"from": "GWS",   "to": "HIST",  "type": "write", "from_pt": (650, 770), "to_pt": (1240, 292), "mid": (920, 560)},
        {"from": "RECTS", "to": "DRDB",  "type": "write", "from_pt": (870, 770), "to_pt": (810, 325), "mid": (840, 540)},
        {"from": "RECTS", "to": "HIST",  "type": "write", "from_pt": (920, 770), "to_pt": (1270, 292), "mid": (1080, 550)},
        {"from": "NET",   "to": "DRSI",  "type": "write", "from_pt": (1130, 770), "to_pt": (550, 292), "mid": (820, 590)},
        {"from": "NET",   "to": "DRDB",  "type": "write", "from_pt": (1180, 770), "to_pt": (930, 325), "mid": (1040, 530)},
        {"from": "SCAN",  "to": "DRDB",  "type": "write", "from_pt": (890, 520), "to_pt": (870, 325), "mid": (880, 420)},
        {"from": "SCAN",  "to": "FLG",   "type": "write", "from_pt": (980, 520), "to_pt": (1060, 292), "mid": (1020, 400)},
        {"from": "CFG",   "to": "DRDB",  "type": "write", "from_pt": (370, 520), "to_pt": (730, 325), "mid": (540, 420)},
        {"from": "CTRL",  "to": "DRDB",  "type": "write", "from_pt": (550, 520), "to_pt": (770, 325), "mid": (660, 420)},
        {"from": "ALM",   "to": "ACB",   "type": "write", "from_pt": (1610, 770), "to_pt": (1610, 390), "mid": (1630, 580)},
        {"from": "GATH",  "to": "PCB",   "type": "write", "from_pt": (1410, 770), "to_pt": (1450, 292), "mid": (1430, 530)},

        # --- 3. 공유 메모리 -> 프로세스 읽기 (R) ---
        {"from": "RAW",   "to": "GWS",   "type": "read",  "from_pt": (350, 292), "to_pt": (530, 770), "mid": (420, 550)},
        {"from": "DRDB",  "to": "SCAN",  "type": "read",  "from_pt": (890, 325), "to_pt": (930, 520), "mid": (910, 420)},
        {"from": "DRDB",  "to": "ALM",   "type": "read",  "from_pt": (970, 325), "to_pt": (1530, 770), "mid": (1260, 600)},
        {"from": "DRSI",  "to": "ALM",   "type": "read",  "from_pt": (520, 292), "to_pt": (1550, 770), "mid": (1020, 640)},
        {"from": "FLG",   "to": "ALM",   "type": "read",  "from_pt": (1100, 292), "to_pt": (1570, 770), "mid": (1340, 580)},
        {"from": "DRDB",  "to": "RT",    "type": "read",  "from_pt": (650, 325), "to_pt": (370, 770), "mid": (490, 570)},
        {"from": "DRDB",  "to": "RDS",   "type": "read",  "from_pt": (740, 325), "to_pt": (740, 520), "mid": (740, 420)},
        {"from": "DRDB",  "to": "GATH",  "type": "read",  "from_pt": (940, 325), "to_pt": (1350, 770), "mid": (1160, 570)},
        {"from": "HIST",  "to": "GATH",  "type": "read",  "from_pt": (1320, 292), "to_pt": (1430, 770), "mid": (1380, 540)},
        {"from": "SM",    "to": "SMM",   "type": "read",  "from_pt": (1590, 267), "to_pt": (1560, 520), "mid": (1575, 390)},
    ]

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">')
    svg.append('''<defs>
    <!-- 화살표 마커 정의 -->
    <marker id="arr-udp" markerWidth="11" markerHeight="11" refX="9" refY="4.5" orient="auto">
      <polygon points="0 1.5, 9.5 4.5, 0 7.5" fill="#1d4ed8" />
    </marker>
    <marker id="arr-write" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto">
      <polygon points="0 1.5, 8.5 4, 0 6.5" fill="#059669" />
    </marker>
    <marker id="arr-read" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto">
      <polygon points="0 1.5, 8.5 4, 0 6.5" fill="#d97706" />
    </marker>
    <marker id="arr-io" markerWidth="9" markerHeight="9" refX="7" refY="3.5" orient="auto">
      <polygon points="0 1, 7.5 3.5, 0 6" fill="#475569" />
    </marker>

    <!-- 그림자 필터 -->
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.07" />
    </filter>
    <filter id="core-shadow" x="-8%" y="-8%" width="116%" height="120%" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#9333ea" flood-opacity="0.22" />
    </filter>

    <style>
      .title { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 25px; font-weight: 800; fill: #0f172a; }
      .subtitle { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 13.5px; fill: #64748b; }
      .subgroup-title { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 17px; font-weight: 700; }
      .subgroup-desc { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 12px; fill: #64748b; }
      .node-txt-main { font-family: "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif; font-size: 15px; font-weight: 700; text-anchor: middle; }
      .node-txt-sub { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 11px; fill: #64748b; text-anchor: middle; }
      .badge-txt { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 11px; font-weight: 600; text-anchor: middle; }
      .legend-txt { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Malgun Gothic", sans-serif; font-size: 13px; font-weight: 600; fill: #1e293b; }
      .ext-tag { font-family: monospace; font-size: 10px; font-weight: 700; fill: #475569; }
    </style>
  </defs>''')

    # 전체 배경
    svg.append(f'<rect width="{width}" height="{height}" fill="#f8fafc" />')

    # 상단 헤더 영역
    svg.append('''<g transform="translate(50, 42)">
    <text class="title" x="0" y="0">E3-DP 공유 메모리 데이터 흐름도</text>
    <text class="subtitle" x="0" y="24">외부 장비/호스트 ↔ 서버 프로세스 군 ↔ 공유 메모리 세그먼트 상호작용 (Bottom to Top 구조)</text>
  </g>''')

    # 범례 (Legend)
    svg.append('''<g transform="translate(940, 20)">
    <rect x="0" y="0" width="770" height="56" rx="8" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2" filter="url(#shadow)" />
    <!-- UDP -->
    <line x1="20" y1="28" x2="60" y2="28" stroke="#1d4ed8" stroke-width="3.5" marker-end="url(#arr-udp)" />
    <text class="legend-txt" x="70" y="32">UDP 메시지 (명령/응답)</text>
    <!-- 쓰기 -->
    <line x1="235" y1="28" x2="275" y2="28" stroke="#059669" stroke-width="2.2" marker-end="url(#arr-write)" />
    <text class="legend-txt" x="285" y="32">공유메모리 쓰기 (W)</text>
    <!-- 읽기 -->
    <line x1="445" y1="28" x2="485" y2="28" stroke="#d97706" stroke-width="2.2" stroke-dasharray="5,4" marker-end="url(#arr-read)" />
    <text class="legend-txt" x="495" y="32">공유메모리 읽기 (R)</text>
    <!-- I/O -->
    <line x1="645" y1="28" x2="685" y2="28" stroke="#475569" stroke-width="2" marker-end="url(#arr-io)" />
    <text class="legend-txt" x="695" y="32">외부 입출력</text>
  </g>''')

    # 3대 그룹 배경 사각형 (Subgraphs)
    # 1. SHM (공유 메모리 영역)
    svg.append('''<g id="group-shm">
    <rect x="50" y="100" width="1660" height="340" rx="14" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5" filter="url(#shadow)" />
    <path d="M 50 114 Q 50 100 64 100 L 1696 100 Q 1710 100 1710 114 L 1710 140 L 50 140 Z" fill="#faf5ff" />
    <text class="subgroup-title" x="75" y="127" fill="#6d28d9">공유 메모리 (Shared Memory Segments)</text>
    <text class="subgroup-desc" x="430" y="126">커널 상주 메모리 세그먼트 (SysV IPC, 0xE3000000 계열 키) — 잠금(Lock) 없는 고속 공유 데이터 버스</text>
  </g>''')

    # 2. PROC (서버 프로세스 영역)
    svg.append('''<g id="group-proc">
    <rect x="50" y="465" width="1660" height="490" rx="14" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5" filter="url(#shadow)" />
    <path d="M 50 479 Q 50 465 64 465 L 1696 465 Q 1710 465 1710 479 L 1710 505 L 50 505 Z" fill="#eff6ff" />
    <text class="subgroup-title" x="75" y="492" fill="#1d4ed8">서버 프로세스 (Server Processes)</text>
    <text class="subgroup-desc" x="380" y="491">상단: 코어 처리 및 제어/알람 엔진 | 하단: 외부 통신 분배, 현장 계측 수집, 상위 보고 인터페이스</text>
  </g>''')

    # 3. EXT (외부 영역)
    svg.append('''<g id="group-ext">
    <rect x="50" y="980" width="1660" height="210" rx="14" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5" filter="url(#shadow)" />
    <path d="M 50 994 Q 50 980 64 980 L 1696 980 Q 1710 980 1710 994 L 1710 1020 L 50 1020 Z" fill="#f1f5f9" />
    <text class="subgroup-title" x="75" y="1007" fill="#334155">외부 (External Systems &amp; Field Devices)</text>
    <text class="subgroup-desc" x="460" y="1006">상위 관제 호스트 및 현장 하위 계측/통신 장치</text>
  </g>''')

    # 연결선 렌더링
    svg.append('<g id="connections">')
    for conn in connections:
        ctype = conn["type"]
        lbl = conn.get("label")
        p1 = conn["from_pt"]
        p2 = conn["to_pt"]
        special = conn.get("special", "")

        if special == "gath_host":
            # GATH -> HOST (아래 외부 박스 상단 통로를 통해 우회)
            path_str = f"M {p1[0]} {p1[1]} C {p1[0]} {p1[1]+120}, {p2[0]+120} {p2[1]-90}, {p2[0]} {p2[1]}"
            mid_x, mid_y = 750, 965
        elif special == "main_ncfg":
            # MAIN -> NCFG (왼쪽 외곽으로 부드럽게)
            path_str = f"M {p1[0]} {p1[1]} C {p1[0]-40} {p1[1]-150}, {p2[0]-40} {p2[1]+150}, {p2[0]} {p2[1]}"
            mid_x, mid_y = 65, 530
        else:
            mid = conn.get("mid", ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2))
            # 베지어 곡선 제어점 생성
            cx1 = p1[0] + (mid[0] - p1[0]) * 0.5
            cy1 = p1[1] + (mid[1] - p1[1]) * 0.7
            cx2 = p2[0] - (p2[0] - mid[0]) * 0.5
            cy2 = p2[1] - (p2[1] - mid[1]) * 0.7
            path_str = f"M {p1[0]} {p1[1]} C {cx1} {cy1}, {cx2} {cy2}, {p2[0]} {p2[1]}"
            mid_x, mid_y = mid[0], mid[1]

        # 스타일 매핑
        if ctype == "udp":
            s_color = "#1d4ed8"
            s_width = "3.2"
            s_dash = ""
            s_marker = 'marker-end="url(#arr-udp)"'
            opacity = "0.9"
        elif ctype == "write":
            s_color = "#059669"
            s_width = "1.8"
            s_dash = ""
            s_marker = 'marker-end="url(#arr-write)"'
            opacity = "0.75"
        elif ctype == "read":
            s_color = "#d97706"
            s_width = "1.8"
            s_dash = 'stroke-dasharray="5,4"'
            s_marker = 'marker-end="url(#arr-read)"'
            opacity = "0.75"
        else: # io
            s_color = "#475569"
            s_width = "2.0"
            s_dash = ""
            s_marker = 'marker-end="url(#arr-io)"'
            opacity = "0.8"

        dash_attr = f' {s_dash}' if s_dash else ''
        svg.append(f'<path d="{path_str}" fill="none" stroke="{s_color}" stroke-width="{s_width}"{dash_attr} {s_marker} opacity="{opacity}" />')

        # 라벨 배지 렌더링
        if lbl:
            lbl_w = len(lbl) * 7.6 + 18
            svg.append(f'''<g transform="translate({mid_x - lbl_w/2}, {mid_y - 10})">
        <rect x="0" y="0" width="{lbl_w}" height="20" rx="4" fill="#ffffff" stroke="{s_color}" stroke-width="1.2" opacity="0.95" />
        <text class="badge-txt" x="{lbl_w/2}" y="14" fill="{s_color}">{html.escape(lbl)}</text>
      </g>''')
    svg.append('</g>')

    # 노드 렌더링
    svg.append('<g id="nodes">')
    for nid, node in nodes.items():
        x, y, w, h = node["x"], node["y"], node["w"], node["h"]
        lbl = node["label"]
        sub = node.get("sub", "")
        grp = node["group"]
        tag = node.get("tag", "")

        if grp == "SHM_CORE":
            # DrDB 중앙 강조 노드
            svg.append(f'''<g id="node-{nid}" transform="translate({x}, {y})" filter="url(#core-shadow)">
        <rect x="0" y="0" width="{w}" height="{h}" rx="14" fill="#fdf4ff" stroke="#9333ea" stroke-width="2.8" />
        <path d="M 0 14 Q 0 0 14 0 L {w-14} 0 Q {w} 0 {w} 14 L {w} 32 L 0 32 Z" fill="#f5d0fe" />
        <text class="node-txt-main" x="{w/2}" y="22" fill="#701a75" font-size="16px">★ {html.escape(lbl)} ★</text>
        <line x1="0" y1="32" x2="{w}" y2="32" stroke="#e9d5ff" stroke-width="1.2" />
        <text class="node-txt-sub" x="{w/2}" y="56" fill="#581c87" font-weight="700" font-size="12.5px">{html.escape(sub)}</text>
        <text class="node-txt-sub" x="{w/2}" y="78" fill="#4a044e">실시간 계측값(value), 상태(status), 통신상태(com_status) 총괄</text>
        <text class="node-txt-sub" x="{w/2}" y="100" fill="#047857" font-weight="600">쓰기(W): db, gw, rect, net, scan, cfg, ctrl</text>
        <text class="node-txt-sub" x="{w/2}" y="122" fill="#b45309" font-weight="600">읽기(R): scan, alm, rt, rds, gath</text>
      </g>''')
        elif grp == "SHM":
            svg.append(f'''<g id="node-{nid}" transform="translate({x}, {y})" filter="url(#shadow)">
        <rect x="0" y="0" width="{w}" height="{h}" rx="10" fill="#ffffff" stroke="#9333ea" stroke-width="1.8" />
        <path d="M 0 8 Q {w/2} 16 {w} 8 L {w} 0 L 0 0 Z" fill="#f3e8ff" />
        <!-- DB 실린더 아이콘 표시 -->
        <ellipse cx="18" cy="18" rx="8" ry="4" fill="#e9d5ff" stroke="#9333ea" stroke-width="1" />
        <path d="M 10 18 L 10 24 Q 18 28 26 24 L 26 18" fill="none" stroke="#9333ea" stroke-width="1" />
        <text class="node-txt-main" x="{w/2 + 6}" y="{h/2 - 4}" fill="#6b21a8">{html.escape(lbl)}</text>
        <text class="node-txt-sub" x="{w/2}" y="{h/2 + 16}">{html.escape(sub)}</text>
      </g>''')
        elif grp == "PROC_MAIN":
            svg.append(f'''<g id="node-{nid}" transform="translate({x}, {y})" filter="url(#shadow)">
        <rect x="0" y="0" width="{w}" height="{h}" rx="8" fill="#eff6ff" stroke="#1d4ed8" stroke-width="2.6" />
        <text class="node-txt-main" x="{w/2}" y="{h/2 - 5}" fill="#1e3a8a" font-size="16px">{html.escape(lbl)}</text>
        <text class="node-txt-sub" x="{w/2}" y="{h/2 + 16}" fill="#1d4ed8" font-weight="600">{html.escape(sub)}</text>
      </g>''')
        elif grp == "PROC":
            svg.append(f'''<g id="node-{nid}" transform="translate({x}, {y})" filter="url(#shadow)">
        <rect x="0" y="0" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="#2563eb" stroke-width="1.6" />
        <text class="node-txt-main" x="{w/2}" y="{h/2 - 5}" fill="#1e40af">{html.escape(lbl)}</text>
        <text class="node-txt-sub" x="{w/2}" y="{h/2 + 15}">{html.escape(sub)}</text>
      </g>''')
        elif grp == "EXT":
            svg.append(f'''<g id="node-{nid}" transform="translate({x}, {y})" filter="url(#shadow)">
        <rect x="0" y="0" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="#475569" stroke-width="1.8" />
        <rect x="0" y="0" width="8" height="{h}" rx="4" fill="#64748b" />
        <text class="node-txt-main" x="{w/2}" y="{h/2 - 8}" fill="#0f172a">{html.escape(lbl)}</text>
        <text class="node-txt-sub" x="{w/2}" y="{h/2 + 11}">{html.escape(sub)}</text>
        <rect x="{w - 68}" y="6" width="60" height="16" rx="3" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1" />
        <text class="ext-tag" x="{w - 38}" y="18" text-anchor="middle">{html.escape(tag)}</text>
      </g>''')

    svg.append('</g>')

    # 풋터
    svg.append('''<g transform="translate(60, 1225)">
    <text class="subtitle" x="0" y="0">※ e3dp/docs/공유메모리구조.md 제6절 데이터 흐름 다이어그램 (BT: Bottom to Top) 기반 SVG 렌더링</text>
    <text class="subtitle" x="1640" y="0" text-anchor="end">E3-DP Architecture Documentation</text>
  </g>''')

    svg.append('</svg>')

    full_svg = "\n".join(svg)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_svg)
    print(f"SVG successfully written to {output_path}")

if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "공유메모리데이터흐름.svg"
    generate_svg(out)
