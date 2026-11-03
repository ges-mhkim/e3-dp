#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E3-DP 공유메모리 데이터 흐름 Visio (VDX & VSDX) 생성기
공유메모리구조.md의 '6. 데이터 흐름'을 Microsoft Visio에서 바로 열고
각 요소를 자유롭게 편집할 수 있는 정식 Visio 다이어그램 파일로 생성합니다.
"""

import sys
import os
import ast
import math
import html
import zipfile

def generate_visio_files(out_vdx_path, out_vsdx_path=None):
    docs_dir = os.path.dirname(os.path.abspath(__file__))
    svg_gen_path = os.path.join(docs_dir, "generate_shm_flow_svg.py")

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

    # 캔버스 및 좌표 변환 설정
    # SVG: W=1760, H=1260
    # Visio: W=18.0 in, H=13.0 in, 1 in = 100 px
    page_w = 18.0
    page_h = 13.0
    scale = 100.0

    def to_vx(x_svg):
        return round(x_svg / scale, 4)

    def to_vy(y_svg):
        return round((1260.0 - y_svg) / scale, 4)

    # ==========================================
    # 1. VDX (Visio XML Drawing) 생성
    # ==========================================
    vdx = []
    vdx.append('<?xml version="1.0" encoding="utf-8"?>')
    vdx.append('<VisioDocument xmlns="http://schemas.microsoft.com/visio/2003/core" xmlns:vx="http://schemas.microsoft.com/visio/2003/core" xml:space="preserve">')
    vdx.append('  <DocumentProperties>')
    vdx.append('    <Title>E3-DP 공유 메모리 데이터 흐름도</Title>')
    vdx.append('    <Subject>E3-DP Architecture Data Flow</Subject>')
    vdx.append('    <Creator>Antigravity</Creator>')
    vdx.append('  </DocumentProperties>')
    vdx.append('  <DocumentSettings TopPage="0" DefaultTextStyle="0" DefaultLineStyle="0" DefaultFillStyle="0"/>')
    vdx.append('  <Pages>')
    vdx.append(f'    <Page ID="0" NameU="Page-1">')
    vdx.append('      <PageSheet>')
    vdx.append('        <PageProps>')
    vdx.append(f'          <PageWidth Unit="IN">{page_w}</PageWidth>')
    vdx.append(f'          <PageHeight Unit="IN">{page_h}</PageHeight>')
    vdx.append('        </PageProps>')
    vdx.append('      </PageSheet>')
    vdx.append('      <Shapes>')

    shape_id = 1

    # 도우미: VDX 사각형 박스
    def add_vdx_box(x, y, w, h, fill_color, line_color, line_weight, title, subtitle="", is_core=False, rounding=0.08):
        nonlocal shape_id
        pw = to_vx(w)
        ph = to_vx(h)
        cx = to_vx(x + w/2)
        cy = to_vy(y + h/2)

        txt = html.escape(title)
        if subtitle:
            txt += "&#xA;" + html.escape(subtitle)

        # 라운딩
        r_str = f'<Rounding Unit="IN">{rounding}</Rounding>' if rounding > 0 else ''

        vdx.append(f'''        <Shape ID="{shape_id}" Type="Shape">
          <XForm>
            <PinX Unit="IN">{cx}</PinX>
            <PinY Unit="IN">{cy}</PinY>
            <Width Unit="IN">{pw}</Width>
            <Height Unit="IN">{ph}</Height>
            <LocPinX F="Width*0.5">{round(pw/2, 4)}</LocPinX>
            <LocPinY F="Height*0.5">{round(ph/2, 4)}</LocPinY>
          </XForm>
          <Line>
            <LineColor>{line_color}</LineColor>
            <LineWeight Unit="PT">{line_weight}</LineWeight>
            {r_str}
          </Line>
          <Fill>
            <FillForegnd>{fill_color}</FillForegnd>
            <FillPattern>1</FillPattern>
          </Fill>
          <TextBlock>
            <VerticalAlign>1</VerticalAlign>
          </TextBlock>
          <Text><cp IX="0"/>{txt}</Text>
          <Geom IX="0">
            <NoFill>0</NoFill>
            <NoLine>0</NoLine>
            <MoveTo IX="1"><X F="Width*0">0</X><Y F="Height*0">0</Y></MoveTo>
            <LineTo IX="2"><X F="Width*1">{pw}</X><Y F="Height*0">0</Y></LineTo>
            <LineTo IX="3"><X F="Width*1">{pw}</X><Y F="Height*1">{ph}</Y></LineTo>
            <LineTo IX="4"><X F="Width*0">0</X><Y F="Height*1">{ph}</Y></LineTo>
            <LineTo IX="5"><X F="Geometry1.X1">0</X><Y F="Geometry1.Y1">0</Y></LineTo>
          </Geom>
        </Shape>''')
        shape_id += 1

    # 도우미: VDX 연결선
    def add_vdx_connector(p1_svg, p2_svg, mid_svg, line_color, line_weight, arrow, dashed, label=""):
        nonlocal shape_id
        x1 = to_vx(p1_svg[0])
        y1 = to_vy(p1_svg[1])
        x2 = to_vx(p2_svg[0])
        y2 = to_vy(p2_svg[1])

        # 중점 (엘보우)
        if mid_svg:
            xm = to_vx(mid_svg[0])
            ym = to_vy(mid_svg[1])
        else:
            xm = round((x1 + x2)/2, 4)
            ym = round((y1 + y2)/2, 4)

        # 3점 폴리라인으로 경로 표현
        min_x = min(x1, xm, x2)
        min_y = min(y1, ym, y2)
        cw = max(abs(x2 - x1), 0.05)
        ch = max(abs(y2 - y1), 0.05)
        c_pinx = round((x1 + x2)/2, 4)
        c_piny = round((y1 + y2)/2, 4)

        pattern = 2 if dashed else 1
        arrow_code = 4 if arrow else 0

        # 로컬 좌표계
        lx1 = round(x1 - c_pinx + cw/2, 4)
        ly1 = round(y1 - c_piny + ch/2, 4)
        lxm = round(xm - c_pinx + cw/2, 4)
        lym = round(ym - c_piny + ch/2, 4)
        lx2 = round(x2 - c_pinx + cw/2, 4)
        ly2 = round(y2 - c_piny + ch/2, 4)

        lbl_txt = f'<Text><cp IX="0"/>{html.escape(label)}</Text>' if label else ''

        vdx.append(f'''        <Shape ID="{shape_id}" Type="Shape">
          <XForm>
            <PinX Unit="IN">{c_pinx}</PinX>
            <PinY Unit="IN">{c_piny}</PinY>
            <Width Unit="IN">{cw}</Width>
            <Height Unit="IN">{ch}</Height>
            <LocPinX F="Width*0.5">{round(cw/2, 4)}</LocPinX>
            <LocPinY F="Height*0.5">{round(ch/2, 4)}</LocPinY>
          </XForm>
          <Line>
            <LineColor>{line_color}</LineColor>
            <LineWeight Unit="PT">{line_weight}</LineWeight>
            <LinePattern>{pattern}</LinePattern>
            <EndArrow>{arrow_code}</EndArrow>
          </Line>
          {lbl_txt}
          <Geom IX="0">
            <NoFill>1</NoFill>
            <NoLine>0</NoLine>
            <MoveTo IX="1"><X>{lx1}</X><Y>{ly1}</Y></MoveTo>
            <LineTo IX="2"><X>{lxm}</X><Y>{lym}</Y></LineTo>
            <LineTo IX="3"><X>{lx2}</X><Y>{ly2}</Y></LineTo>
          </Geom>
        </Shape>''')
        shape_id += 1

    # --- 1) 3대 그룹 배경 박스 추가 ---
    # SHM
    add_vdx_box(50, 100, 1660, 340, "#FAF5FF", "#9333EA", 1.8, "공유 메모리 (Shared Memory Segments)", "커널 상주 메모리 세그먼트 (0xE3000000 계열 키)", rounding=0.15)
    # PROC
    add_vdx_box(50, 465, 1660, 490, "#EFF6FF", "#2563EB", 1.8, "서버 프로세스 (Server Processes)", "상단: 코어 처리 및 제어/알람 엔진 | 하단: 수집/분배/보고 인터페이스", rounding=0.15)
    # EXT
    add_vdx_box(50, 980, 1660, 210, "#F8FAFC", "#475569", 1.8, "외부 (External Systems & Field Devices)", "상위 관제 호스트 및 현장 하위 계측/통신 장치", rounding=0.15)

    # 타이틀
    add_vdx_box(50, 20, 600, 60, "#FFFFFF", "#CBD5E1", 1.0, "E3-DP 공유 메모리 데이터 흐름도", "외부(EXT) ↔ 서버 프로세스(PROC) ↔ 공유 메모리(SHM) 상호작용", rounding=0.06)
    # 범례
    add_vdx_box(940, 20, 770, 60, "#FFFFFF", "#CBD5E1", 1.0, "범례: 파랑(UDP 메시지) | 초록(공유메모리 쓰기 W) | 주황 점선(공유메모리 읽기 R) | 회색(외부 입출력)", "Visio 편집 가능 다이어그램 (Bottom to Top)", rounding=0.06)

    # --- 2) 노드 박스 추가 ---
    for nid, node in nodes.items():
        x, y, w, h = node["x"], node["y"], node["w"], node["h"]
        lbl = node["label"].replace("\n", " ")
        sub = node.get("sub", "")
        grp = node["group"]

        if grp == "SHM_CORE":
            add_vdx_box(x, y, w, h, "#FDF4FF", "#9333EA", 2.6, f"★ {lbl} ★", f"{sub}\n실시간 계측값(value), 상태(status), 통신상태(com_status) 총괄\nW: db, gw, rect, net, scan, cfg, ctrl | R: scan, alm, rt, rds, gath", is_core=True, rounding=0.12)
        elif grp == "SHM":
            add_vdx_box(x, y, w, h, "#FFFFFF", "#A855F7", 1.8, lbl, sub, rounding=0.08)
        elif grp == "PROC_MAIN":
            add_vdx_box(x, y, w, h, "#DBEAFE", "#1D4ED8", 2.4, lbl, sub, rounding=0.08)
        elif grp == "PROC":
            add_vdx_box(x, y, w, h, "#FFFFFF", "#3B82F6", 1.6, lbl, sub, rounding=0.08)
        elif grp == "EXT":
            tag = node.get("tag", "")
            sub_full = f"{sub} [{tag}]" if tag else sub
            add_vdx_box(x, y, w, h, "#FFFFFF", "#475569", 1.8, lbl, sub_full, rounding=0.08)

    # --- 3) 연결선 추가 ---
    for conn in connections:
        ctype = conn["type"]
        lbl = conn.get("label", "")
        p1 = conn["from_pt"]
        p2 = conn["to_pt"]
        special = conn.get("special", "")

        if special == "gath_host":
            mid = (750, 965)
        elif special == "main_ncfg":
            mid = (65, 530)
        else:
            mid = conn.get("mid", ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2))

        if ctype == "udp":
            add_vdx_connector(p1, p2, mid, "#1D4ED8", 2.8, arrow=True, dashed=False, label=lbl)
        elif ctype == "write":
            add_vdx_connector(p1, p2, mid, "#059669", 1.8, arrow=True, dashed=False, label=lbl)
        elif ctype == "read":
            add_vdx_connector(p1, p2, mid, "#D97706", 1.8, arrow=True, dashed=True, label=lbl)
        else: # io
            add_vdx_connector(p1, p2, mid, "#475569", 2.0, arrow=True, dashed=False, label=lbl)

    vdx.append('      </Shapes>')
    vdx.append('    </Page>')
    vdx.append('  </Pages>')
    vdx.append('</VisioDocument>')

    full_vdx = "\n".join(vdx)
    with open(out_vdx_path, "w", encoding="utf-8") as f:
        f.write(full_vdx)
    print(f"VDX generated at: {out_vdx_path}")

    # ==========================================
    # 2. VSDX (Visio 2013+ OPC 포맷) 생성
    # ==========================================
    if out_vsdx_path:
        with zipfile.ZipFile(out_vsdx_path, "w", zipfile.ZIP_DEFLATED) as z:
            # [Content_Types].xml
            z.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>
  <Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>
  <Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>
  <Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>
</Types>''')

            # _rels/.rels
            z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>
</Relationships>''')

            # visio/document.xml
            z.writestr("visio/document.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <DocumentSettings TopPage="0" DefaultTextStyle="0" DefaultLineStyle="0" DefaultFillStyle="0"/>
  <Colors/>
  <FaceNames/>
  <StyleSheets/>
</VisioDocument>''')

            # visio/_rels/document.xml.rels
            z.writestr("visio/_rels/document.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/>
  <Relationship Id="rId2" Type="http://schemas.microsoft.com/visio/2010/relationships/windows" Target="windows.xml"/>
</Relationships>''')

            # visio/pages/pages.xml
            z.writestr("visio/pages/pages.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Pages xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <Page ID="0" Name="Page-1" ViewScale="1" ViewCenterX="9.0" ViewCenterY="6.5">
    <PageSheet LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PageWidth" V="{page_w}" U="IN"/>
      <Cell N="PageHeight" V="{page_h}" U="IN"/>
      <Cell N="DrawingScale" V="1" U="IN"/>
      <Cell N="PageScale" V="1" U="IN"/>
      <Cell N="DrawingSizeType" V="3"/>
    </PageSheet>
    <Rel I="rId1"/>
  </Page>
</Pages>''')

            # visio/pages/_rels/pages.xml.rels
            z.writestr("visio/pages/_rels/pages.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page1.xml"/>
</Relationships>''')

            # visio/windows.xml
            z.writestr("visio/windows.xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Windows xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Window ID="0" WindowType="Drawing" WindowState="1073741824" Window="1">
    <ShowRulers>1</ShowRulers>
    <ShowGrid>1</ShowGrid>
    <ShowPageBreaks>0</ShowPageBreaks>
  </Window>
</Windows>''')

            # visio/pages/page1.xml (VSDX Shapes)
            p1_shapes = []
            s_id = 1

            def add_vsdx_box(x, y, w, h, fill, line, weight, title, sub=""):
                nonlocal s_id
                pw = to_vx(w)
                ph = to_vx(h)
                cx = to_vx(x + w/2)
                cy = to_vy(y + h/2)
                t_str = html.escape(title)
                if sub: t_str += "\n" + html.escape(sub)

                p1_shapes.append(f'''    <Shape ID="{s_id}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{cx}" U="IN"/>
      <Cell N="PinY" V="{cy}" U="IN"/>
      <Cell N="Width" V="{pw}" U="IN"/>
      <Cell N="Height" V="{ph}" U="IN"/>
      <Cell N="LocPinX" V="{round(pw/2, 4)}" F="Width*0.5"/>
      <Cell N="LocPinY" V="{round(ph/2, 4)}" F="Height*0.5"/>
      <Cell N="Rounding" V="0.08" U="IN"/>
      <Cell N="LineColor" V="{line}"/>
      <Cell N="LineWeight" V="{weight}" U="PT"/>
      <Cell N="FillForegnd" V="{fill}"/>
      <Cell N="FillPattern" V="1"/>
      <Section N="Geometry" IX="0">
        <Cell N="NoFill" V="0"/>
        <Cell N="NoLine" V="0"/>
        <Row T="RelMoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>
        <Row T="RelLineTo" IX="2"><Cell N="X" V="1"/><Cell N="Y" V="0"/></Row>
        <Row T="RelLineTo" IX="3"><Cell N="X" V="1"/><Cell N="Y" V="1"/></Row>
        <Row T="RelLineTo" IX="4"><Cell N="X" V="0"/><Cell N="Y" V="1"/></Row>
        <Row T="RelLineTo" IX="5"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>
      </Section>
      <Text><cp IX="0"/>{t_str}</Text>
    </Shape>''')
                s_id += 1

            # 3대 그룹
            add_vsdx_box(50, 100, 1660, 340, "#FAF5FF", "#9333EA", 1.8, "공유 메모리 (Shared Memory Segments)", "0xE3000000 계열 키")
            add_vsdx_box(50, 465, 1660, 490, "#EFF6FF", "#2563EB", 1.8, "서버 프로세스 (Server Processes)", "코어 처리단 및 인터페이스/수집단")
            add_vsdx_box(50, 980, 1660, 210, "#F8FAFC", "#475569", 1.8, "외부 (External Systems & Field Devices)", "Host 서버 및 현장 하위 계측/통신 장치")

            # 헤더
            add_vsdx_box(50, 20, 600, 60, "#FFFFFF", "#CBD5E1", 1.0, "E3-DP 공유 메모리 데이터 흐름도", "Bottom to Top 구조")
            add_vsdx_box(940, 20, 770, 60, "#FFFFFF", "#CBD5E1", 1.0, "범례: 파랑(UDP) | 초록(쓰기 W) | 주황 점선(읽기 R) | 회색(외부 입출력)", "Visio 2013-2024 호환")

            # 노드
            for nid, node in nodes.items():
                x, y, w, h = node["x"], node["y"], node["w"], node["h"]
                lbl = node["label"].replace("\n", " ")
                sub = node.get("sub", "")
                grp = node["group"]
                if grp == "SHM_CORE":
                    add_vsdx_box(x, y, w, h, "#FDF4FF", "#9333EA", 2.6, f"★ {lbl} ★", f"{sub}\n실시간 계측값(value), 상태(status), 통신상태(com_status) 총괄")
                elif grp == "SHM":
                    add_vsdx_box(x, y, w, h, "#FFFFFF", "#A855F7", 1.8, lbl, sub)
                elif grp == "PROC_MAIN":
                    add_vsdx_box(x, y, w, h, "#DBEAFE", "#1D4ED8", 2.4, lbl, sub)
                elif grp == "PROC":
                    add_vsdx_box(x, y, w, h, "#FFFFFF", "#3B82F6", 1.6, lbl, sub)
                elif grp == "EXT":
                    add_vsdx_box(x, y, w, h, "#FFFFFF", "#475569", 1.8, lbl, sub)

            # 연결선
            for conn in connections:
                ctype = conn["type"]
                lbl = conn.get("label", "")
                p1 = conn["from_pt"]
                p2 = conn["to_pt"]
                x1 = to_vx(p1[0]); y1 = to_vy(p1[1])
                x2 = to_vx(p2[0]); y2 = to_vy(p2[1])
                cw = max(abs(x2 - x1), 0.05); ch = max(abs(y2 - y1), 0.05)
                cx = round((x1 + x2)/2, 4); cy = round((y1 + y2)/2, 4)
                color = "#1D4ED8" if ctype == "udp" else "#059669" if ctype == "write" else "#D97706" if ctype == "read" else "#475569"
                dash = 2 if ctype == "read" else 1

                p1_shapes.append(f'''    <Shape ID="{s_id}" Type="Shape" LineStyle="0" FillStyle="0" TextStyle="0">
      <Cell N="PinX" V="{cx}" U="IN"/>
      <Cell N="PinY" V="{cy}" U="IN"/>
      <Cell N="Width" V="{cw}" U="IN"/>
      <Cell N="Height" V="{ch}" U="IN"/>
      <Cell N="LocPinX" V="{round(cw/2, 4)}" F="Width*0.5"/>
      <Cell N="LocPinY" V="{round(ch/2, 4)}" F="Height*0.5"/>
      <Cell N="LineColor" V="{color}"/>
      <Cell N="LineWeight" V="2" U="PT"/>
      <Cell N="LinePattern" V="{dash}"/>
      <Cell N="EndArrow" V="4"/>
      <Section N="Geometry" IX="0">
        <Cell N="NoFill" V="1"/>
        <Cell N="NoLine" V="0"/>
        <Row T="RelMoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>
        <Row T="RelLineTo" IX="2"><Cell N="X" V="1"/><Cell N="Y" V="1"/></Row>
      </Section>
      <Text><cp IX="0"/>{html.escape(lbl)}</Text>
    </Shape>''')
                s_id += 1

            page1_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + \
                        '<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n' + \
                        '  <Shapes>\n' + "\n".join(p1_shapes) + '\n  </Shapes>\n</PageContents>'
            z.writestr("visio/pages/page1.xml", page1_xml)

        print(f"VSDX generated at: {out_vsdx_path}")

if __name__ == "__main__":
    vdx_out = "공유메모리데이터흐름.vdx"
    vsdx_out = "공유메모리데이터흐름.vsdx"
    if len(sys.argv) > 1: vdx_out = sys.argv[1]
    if len(sys.argv) > 2: vsdx_out = sys.argv[2]
    generate_visio_files(vdx_out, vsdx_out)

