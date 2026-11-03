#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E3-DP 공유메모리 데이터 흐름 DXF 생성기
공유메모리구조.md의 '6. 데이터 흐름'을 AutoCAD 호환 DXF 파일로 변환합니다.
AutoCAD, CADian, ZWCAD, LibreCAD 등에서 바로 열고 DWG로 저장할 수 있습니다.
"""

import sys
import os
import math

def generate_dxf(output_path):
    # generate_shm_flow_svg.py 에서 정의한 데이터 로드
    docs_dir = os.path.dirname(os.path.abspath(__file__))
    svg_gen_path = os.path.join(docs_dir, "generate_shm_flow_svg.py")
    
    # SVG 좌표계: W=1760, H=1260 (좌상단 0,0, 아래로 +Y)
    # CAD 좌표계: W=1760, H=1260 (좌하단 0,0, 위로 +Y)
    canvas_w = 1760
    canvas_h = 1260

    def to_cad_pt(x, y):
        return (round(x, 2), round(canvas_h - y, 2))

    # 노드 및 연결 데이터 추출
    import ast
    with open(svg_gen_path, "r", encoding="utf-8") as f:
        code_text = f.read()

    parsed = ast.parse(code_text)
    nodes = {}
    connections = []
    for node in ast.walk(parsed):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tid = getattr(node.targets[0], 'id', None)
            if tid == 'nodes':
                nodes = ast.literal_eval(node.value)
            elif tid == 'connections':
                connections = ast.literal_eval(node.value)

    dxf = []

    # 1. HEADER SECTION
    dxf.append("0\nSECTION\n2\nHEADER")
    dxf.append("9\n$ACADVER\n1\nAC1015")  # AutoCAD 2000 format
    dxf.append("9\n$DWGCODEPAGE\n3\nANSI_949")
    dxf.append("9\n$INSUNITS\n70\n4")      # Millimeters
    dxf.append("9\n$EXTMIN\n10\n0.0\n20\n0.0\n30\n0.0")
    dxf.append(f"9\n$EXTMAX\n10\n{canvas_w}.0\n20\n{canvas_h}.0\n30\n0.0")
    dxf.append("0\nENDSEC")

    # 2. TABLES SECTION (Linetypes and Layers)
    dxf.append("0\nSECTION\n2\nTABLES")
    
    # Linetype Table
    dxf.append("0\nTABLE\n2\nLTYPE\n70\n2")
    dxf.append("0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid line\n72\n65\n73\n0\n40\n0.0")
    dxf.append("0\nLTYPE\n2\nDASHED\n70\n0\n3\nDash --\n72\n65\n73\n2\n40\n10.0\n49\n7.0\n49\n-3.0")
    dxf.append("0\nENDTAB")

    # Layer Table (ACI Colors: 1=Red, 2=Yellow, 3=Green, 4=Cyan, 5=Blue, 6=Magenta, 7=White/Black, 8=Gray, 30=Orange)
    layers = [
        {"name": "0", "color": 7, "ltype": "CONTINUOUS"},
        {"name": "GROUP_BOXES", "color": 8, "ltype": "CONTINUOUS"},      # 그룹 경계
        {"name": "SHM_NODES", "color": 6, "ltype": "CONTINUOUS"},        # 공유메모리 (자주/보라)
        {"name": "SHM_CORE", "color": 6, "ltype": "CONTINUOUS"},         # DrDB 핵심노드
        {"name": "PROC_NODES", "color": 5, "ltype": "CONTINUOUS"},       # 서버 프로세스 (파랑)
        {"name": "EXT_NODES", "color": 7, "ltype": "CONTINUOUS"},        # 외부 장비 (흰색/검정)
        {"name": "LINE_UDP", "color": 5, "ltype": "CONTINUOUS"},         # UDP 메시지
        {"name": "LINE_WRITE", "color": 3, "ltype": "CONTINUOUS"},       # 공유메모리 쓰기 (초록)
        {"name": "LINE_READ", "color": 30, "ltype": "DASHED"},           # 공유메모리 읽기 (주황/점선)
        {"name": "LINE_IO", "color": 8, "ltype": "CONTINUOUS"},          # 외부 입출력 (회색)
        {"name": "TEXT_LABEL", "color": 7, "ltype": "CONTINUOUS"},       # 텍스트
        {"name": "TEXT_BADGE", "color": 2, "ltype": "CONTINUOUS"},       # 라벨 배지 (노랑)
    ]
    dxf.append(f"0\nTABLE\n2\nLAYER\n70\n{len(layers)}")
    for lay in layers:
        dxf.append(f"0\nLAYER\n2\n{lay['name']}\n70\n0\n62\n{lay['color']}\n6\n{lay['ltype']}")
    dxf.append("0\nENDTAB")
    dxf.append("0\nENDSEC")

    # 3. BLOCKS SECTION
    dxf.append("0\nSECTION\n2\nBLOCKS\n0\nENDSEC")

    # 4. ENTITIES SECTION
    dxf.append("0\nSECTION\n2\nENTITIES")

    # 도우미: LWPOLYLINE 사각형 생성
    def add_rect(layer, x1, y1, w, h, color=None):
        p1 = to_cad_pt(x1, y1)
        p2 = to_cad_pt(x1 + w, y1)
        p3 = to_cad_pt(x1 + w, y1 + h)
        p4 = to_cad_pt(x1, y1 + h)
        res = ["0\nLWPOLYLINE", f"8\n{layer}", "100\nAcDbEntity", "100\nAcDbPolyline", "90\n4", "70\n1"]
        if color is not None:
            res.append(f"62\n{color}")
        for pt in [p1, p2, p3, p4]:
            res.append(f"10\n{pt[0]}\n20\n{pt[1]}")
        dxf.append("\n".join(res))

    # 도우미: TEXT 엔티티 생성
    def add_text(layer, text, x, y, height=14, align="left", color=None):
        pt = to_cad_pt(x, y)
        res = ["0\nTEXT", f"8\n{layer}", "100\nAcDbEntity", "100\nAcDbText"]
        if color is not None:
            res.append(f"62\n{color}")
        res.append(f"10\n{pt[0]}\n20\n{pt[1]}\n30\n0.0")
        res.append(f"40\n{height}")
        res.append(f"1\n{text}")
        if align == "center":
            res.append(f"72\n1\n11\n{pt[0]}\n21\n{pt[1]}\n31\n0.0")
        elif align == "right":
            res.append(f"72\n2\n11\n{pt[0]}\n21\n{pt[1]}\n31\n0.0")
        dxf.append("\n".join(res))

    # 도우미: SOLID 화살표 촉 생성
    def add_arrow(layer, tip_pt, from_pt, size=14, color=None):
        dx = tip_pt[0] - from_pt[0]
        dy = tip_pt[1] - from_pt[1]
        dist = math.hypot(dx, dy)
        if dist < 1e-4: return
        ux = dx / dist
        uy = dy / dist
        vx = -uy
        vy = ux
        p_base = (tip_pt[0] - ux * size, tip_pt[1] - uy * size)
        p_left = (p_base[0] + vx * (size * 0.4), p_base[1] + vy * (size * 0.4))
        p_right = (p_base[0] - vx * (size * 0.4), p_base[1] - vy * (size * 0.4))
        
        res = ["0\nSOLID", f"8\n{layer}", "100\nAcDbEntity", "100\nAcDbTrace"]
        if color is not None:
            res.append(f"62\n{color}")
        res.append(f"10\n{tip_pt[0]}\n20\n{tip_pt[1]}\n30\n0.0")
        res.append(f"11\n{p_left[0]}\n21\n{p_left[1]}\n31\n0.0")
        res.append(f"12\n{p_right[0]}\n21\n{p_right[1]}\n31\n0.0")
        res.append(f"13\n{p_right[0]}\n21\n{p_right[1]}\n31\n0.0")
        dxf.append("\n".join(res))

    # 도우미: 베지어 곡선 폴리라인 생성
    def add_curve(layer, p1_svg, p2_svg, mid_svg=None, num_seg=16, ltype="CONTINUOUS"):
        p1 = p1_svg
        p2 = p2_svg
        if mid_svg is None:
            mid = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
        else:
            mid = mid_svg

        cx1 = p1[0] + (mid[0] - p1[0]) * 0.5
        cy1 = p1[1] + (mid[1] - p1[1]) * 0.7
        cx2 = p2[0] - (p2[0] - mid[0]) * 0.5
        cy2 = p2[1] - (p2[1] - mid[1]) * 0.7

        pts = []
        for i in range(num_seg + 1):
            t = i / num_seg
            x = (1-t)**3 * p1[0] + 3*(1-t)**2*t * cx1 + 3*(1-t)*t**2 * cx2 + t**3 * p2[0]
            y = (1-t)**3 * p1[1] + 3*(1-t)**2*t * cy1 + 3*(1-t)*t**2 * cy2 + t**3 * p2[1]
            pts.append(to_cad_pt(x, y))

        res = ["0\nLWPOLYLINE", f"8\n{layer}", "100\nAcDbEntity", "100\nAcDbPolyline", f"90\n{len(pts)}", "70\n0"]
        if ltype != "CONTINUOUS":
            res.append(f"6\n{ltype}")
        for pt in pts:
            res.append(f"10\n{pt[0]}\n20\n{pt[1]}")
        dxf.append("\n".join(res))
        
        # 마지막 끝점과 직전 점 반환 (화살표 방향용)
        return pts[-1], pts[-2]

    # --- 타이틀 및 그룹 배경 그리기 ---
    add_text("TEXT_LABEL", "E3-DP 공유 메모리 데이터 흐름도 (AutoCAD DXF)", 50, 42, height=22)
    add_text("TEXT_LABEL", "외부(EXT) ↔ 서버 프로세스(PROC) ↔ 공유 메모리(SHM) 상호작용 (Bottom to Top 구조)", 50, 68, height=12)

    # 범례 박스
    add_rect("GROUP_BOXES", 940, 20, 770, 56)
    add_text("TEXT_LABEL", "[범례] 파랑: UDP 메시지 | 초록: 공유메모리 쓰기(W) | 주황(점선): 공유메모리 읽기(R) | 회색: 외부 입출력", 960, 52, height=11)

    # 3대 그룹 경계 사각형
    add_rect("GROUP_BOXES", 50, 100, 1660, 340, color=6)
    add_text("SHM_NODES", "[공유 메모리] Shared Memory Segments (0xE3000000 계열 키)", 75, 126, height=16)

    add_rect("GROUP_BOXES", 50, 465, 1660, 490, color=5)
    add_text("PROC_NODES", "[서버 프로세스] Server Processes (상단: 코어 처리/감시 | 하단: 수집/분배/보고)", 75, 492, height=16)

    add_rect("GROUP_BOXES", 50, 980, 1660, 210, color=7)
    add_text("EXT_NODES", "[외부] External Systems & Field Devices (상위 호스트 및 현장 설비)", 75, 1008, height=16)

    # --- 노드 그리기 ---
    for nid, node in nodes.items():
        x, y, w, h = node["x"], node["y"], node["w"], node["h"]
        lbl = node["label"].replace("\n", " ")
        sub = node.get("sub", "")
        grp = node["group"]

        if grp == "SHM_CORE":
            lay = "SHM_CORE"
            add_rect(lay, x, y, w, h, color=6)
            add_rect(lay, x+4, y+4, w-8, h-8, color=6) # 더블 보더
            add_text(lay, f"★ {lbl} ★", x + w/2, y + 26, height=15, align="center")
            add_text(lay, sub, x + w/2, y + 54, height=11, align="center")
            add_text(lay, "실시간 계측값(value), 상태(status), 통신상태(com_status) 총괄", x + w/2, y + 76, height=10, align="center")
            add_text(lay, "W: db, gw, rect, net, scan, cfg, ctrl | R: scan, alm, rt, rds, gath", x + w/2, y + 98, height=9, align="center")
        elif grp == "SHM":
            lay = "SHM_NODES"
            add_rect(lay, x, y, w, h, color=6)
            add_text(lay, lbl, x + w/2, y + h/2 - 4, height=13, align="center")
            add_text(lay, sub, x + w/2, y + h/2 + 16, height=9.5, align="center")
        elif grp in ("PROC", "PROC_MAIN"):
            lay = "PROC_NODES"
            color = 5 if grp == "PROC" else 4
            add_rect(lay, x, y, w, h, color=color)
            add_text(lay, lbl, x + w/2, y + h/2 - 4, height=13, align="center")
            add_text(lay, sub, x + w/2, y + h/2 + 15, height=9.5, align="center")
        elif grp == "EXT":
            lay = "EXT_NODES"
            add_rect(lay, x, y, w, h, color=7)
            tag = node.get("tag", "")
            add_text(lay, lbl, x + w/2, y + h/2 - 6, height=13, align="center")
            add_text(lay, sub, x + w/2, y + h/2 + 12, height=9.5, align="center")
            if tag:
                add_text(lay, f"[{tag}]", x + w/2, y + h/2 + 25, height=8.5, align="center")

    # --- 연결선 및 화살표 그리기 ---
    for conn in connections:
        ctype = conn["type"]
        lbl = conn.get("label")
        p1 = conn["from_pt"]
        p2 = conn["to_pt"]
        special = conn.get("special", "")

        if special == "gath_host":
            lay = "LINE_UDP"
            tip, prev = add_curve(lay, p1, p2, mid_svg=(750, 965), num_seg=24)
            add_arrow(lay, tip, prev, size=15)
            add_text("TEXT_BADGE", f"[{lbl}]", 750, 965, height=11, align="center")
        elif special == "main_ncfg":
            lay = "LINE_WRITE"
            tip, prev = add_curve(lay, p1, p2, mid_svg=(65, 530), num_seg=20)
            add_arrow(lay, tip, prev, size=12)
        else:
            mid = conn.get("mid", ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2))
            if ctype == "udp":
                lay = "LINE_UDP"
                ltype = "CONTINUOUS"
                arr_sz = 14
            elif ctype == "write":
                lay = "LINE_WRITE"
                ltype = "CONTINUOUS"
                arr_sz = 12
            elif ctype == "read":
                lay = "LINE_READ"
                ltype = "DASHED"
                arr_sz = 12
            else: # io
                lay = "LINE_IO"
                ltype = "CONTINUOUS"
                arr_sz = 11

            tip, prev = add_curve(lay, p1, p2, mid_svg=mid, num_seg=16, ltype=ltype)
            add_arrow(lay, tip, prev, size=arr_sz)
            if lbl:
                add_text("TEXT_BADGE", f"[{lbl}]", mid[0], mid[1], height=10, align="center")

    dxf.append("0\nENDSEC")
    dxf.append("0\nEOF")

    full_dxf = "\n".join(dxf)
    with open(output_path, "w", encoding="cp949", errors="replace") as f:
        f.write(full_dxf)

    # UTF-8 버전도 동시에 생성 (AutoCAD 최신판 및 웹 뷰어 완벽 호환)
    utf8_path = output_path.replace(".dxf", "_utf8.dxf")
    with open(utf8_path, "w", encoding="utf-8") as f:
        f.write(full_dxf)

    print(f"DXF created at: {output_path} (CP949) and {utf8_path} (UTF-8)")

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "공유메모리데이터흐름.dxf"
    generate_dxf(out)

