"""Zero-Overlap Draw.io Diagram Engine: ELK Sugiyama orthogonal routing + deterministic SD/Swimlane + strict geometric QA + headless render."""
import base64
import html
import json
import math
import os
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

from paths import build_env, resolve_binaries


def load_diagram_style(profile_name="monochrome-bw"):
    bins = resolve_binaries()
    with open(bins["style_profiles"], encoding="utf-8") as f:
        data = json.load(f)
    styles = data.get("diagram_styles", {})
    if profile_name in styles:
        return styles[profile_name]
    doc_prof = data.get("profiles", {}).get(profile_name, {})
    dp = doc_prof.get("diagram_profile", "monochrome-bw")
    return styles.get(dp, styles["monochrome-bw"])


def _esc(text):
    return html.escape(str(text or ""), quote=True)


def _estimate_box_size(label, font_size=12, kind="process", min_w=150, min_h=54):
    raw = str(label or "")
    lines = raw.replace("<br/>", "\n").replace("<br>", "\n").split("\n")
    max_chars = max([len(l.strip()) for l in lines] or [6])
    char_w = font_size * 0.62
    line_h = font_size * 1.48
    w = max(min_w, int(math.ceil(max_chars * char_w + 34)))
    h = max(min_h, int(math.ceil(len(lines) * line_h + 24)))
    if kind == "decision":
        w = max(170, int(w * 1.32))
        h = max(84, int(h * 1.38))
    elif kind == "cylinder" or kind == "store":
        h = max(66, h + 14)
    elif kind == "actor":
        w = max(90, min(140, w))
        h = 92
    # Snap to grid 10
    w = int(math.ceil(w / 10.0) * 10)
    h = int(math.ceil(h / 10.0) * 10)
    return w, h


def _run_elk(elk_spec):
    bins = resolve_binaries()
    node = bins["node"]
    script = bins["elk_script"]
    if not node or not os.path.exists(script):
        raise RuntimeError(f"ELK runtime missing: node={node}, script={script}")
    p = subprocess.run(
        [node, script],
        input=json.dumps(elk_spec),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ELK layout failed (rc={p.returncode}): {p.stderr[-800:]}")
    return json.loads(p.stdout)


def _node_style(kind, style_cfg, extra=None):
    pal = style_cfg["palette"]
    font = style_cfg["font_primary"]
    fsize = style_cfg["node_size"]
    sw = style_cfg["stroke_width"]
    p = pal.get(kind, pal["process"])
    fill, stroke, fcol = p["fill"], p["stroke"], p["fontColor"]
    base = (
        f"html=1;whiteSpace=wrap;fontFamily={font};fontSize={fsize};"
        f"fontStyle=1;fontColor={fcol};fillColor={fill};strokeColor={stroke};"
        f"strokeWidth={sw};"
    )
    if kind == "decision":
        s = f"rhombus;{base}"
    elif kind == "start_end":
        s = f"rounded=1;arcSize=50;{base}"
    elif kind in ("store", "cylinder", "database"):
        s = f"shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;{base}"
    elif kind == "actor":
        s = (
            f"shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;"
            f"html=1;outlineConnect=0;fontFamily={font};fontSize={fsize};"
            f"fontStyle=1;fontColor={fcol};fillColor={fill};strokeColor={stroke};"
            f"strokeWidth={sw};"
        )
    elif kind == "usecase":
        s = f"ellipse;{base}"
    elif kind == "group":
        gp = pal["group"]
        s = (
            f"rounded=1;arcSize=6;html=1;whiteSpace=wrap;verticalAlign=top;"
            f"align=left;spacingLeft=12;spacingTop=8;dashed=1;dashPattern=6 4;"
            f"fontFamily={font};fontSize={fsize};fontStyle=1;"
            f"fontColor={gp['fontColor']};fillColor={gp['fill']};"
            f"strokeColor={gp['stroke']};strokeWidth=1.5;container=1;collapsible=0;"
        )
    elif kind == "external":
        s = f"rounded=0;{base}"
    else:
        s = f"rounded=1;arcSize=10;{base}"
    if extra:
        s += extra
    return s


def _edge_style(style_cfg, edge_spec, exit_port=None, entry_port=None):
    font = style_cfg["font_primary"]
    esize = style_cfg["edge_size"]
    ecol = style_cfg["palette"]["edge"]
    sw = edge_spec.get("stroke_width", style_cfg["stroke_width"])
    end_arrow = edge_spec.get("end_arrow", "block")
    start_arrow = edge_spec.get("start_arrow", "none")
    dashed = "1" if edge_spec.get("dashed") else "0"
    open_arrows = ("open", "none", "ERone", "ERmandOne", "ERmany", "ERoneToMany", "ERzeroToMany", "ERzeroToOne")
    end_fill = "0" if end_arrow in open_arrows else "1"
    start_fill = "0" if start_arrow in open_arrows else "1"
    edge_routing = edge_spec.get("edge_style", "orthogonalEdgeStyle")
    parts = [
        f"edgeStyle={edge_routing}",
        "rounded=0",
        "orthogonalLoop=1",
        "jettySize=auto",
        "html=1",
        f"strokeColor={edge_spec.get('color', ecol)}",
        f"strokeWidth={sw}",
        f"dashed={dashed}",
        f"endArrow={end_arrow}",
        f"endFill={end_fill}",
        f"startArrow={start_arrow}",
        f"startFill={start_fill}",
        f"fontFamily={font}",
        f"fontSize={esize}",
        "fontStyle=1",
        "labelBackgroundColor=#FFFFFF",
        "labelBorderColor=none",
    ]
    if exit_port:
        parts.extend([
            f"exitX={exit_port['x']}",
            f"exitY={exit_port['y']}",
            "exitDx=0",
            "exitDy=0",
        ])
    if entry_port:
        parts.extend([
            f"entryX={entry_port['x']}",
            f"entryY={entry_port['y']}",
            "entryDx=0",
            "entryDy=0",
        ])
    return ";".join(parts) + ";"


def _make_mxfile(diagram_name, page_w, page_h, cells, grid=10):
    mxfile = ET.Element("mxfile", {"host": "doc-studio", "agent": "doc-studio/1.0"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "d1", "name": diagram_name})
    model = ET.SubElement(
        diagram,
        "mxGraphModel",
        {
            "dx": "1422",
            "dy": "794",
            "grid": "1",
            "gridSize": str(grid),
            "guides": "1",
            "tooltips": "1",
            "connect": "1",
            "arrows": "1",
            "fold": "1",
            "page": "1",
            "pageScale": "1",
            "pageWidth": str(int(page_w)),
            "pageHeight": str(int(page_h)),
            "background": "#FFFFFF",
            "math": "0",
            "shadow": "0",
        },
    )
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    for c in cells:
        root.append(c)
    ET.indent(mxfile, space="  ")
    return ET.tostring(mxfile, encoding="unicode", xml_declaration=True)


def _cell_vertex(cid, value, style, x, y, w, h, parent="1"):
    cell = ET.Element(
        "mxCell",
        {"id": str(cid), "value": str(value), "style": style, "vertex": "1", "parent": str(parent)},
    )
    ET.SubElement(
        cell,
        "mxGeometry",
        {"x": str(int(round(x))), "y": str(int(round(y))), "width": str(int(round(w))), "height": str(int(round(h))), "as": "geometry"},
    )
    return cell


def _cell_edge(cid, value, style, source=None, target=None, bend_points=None, src_pt=None, tgt_pt=None, parent="1"):
    attrs = {"id": str(cid), "value": str(value or ""), "style": style, "edge": "1", "parent": str(parent)}
    if source:
        attrs["source"] = str(source)
    if target:
        attrs["target"] = str(target)
    cell = ET.Element("mxCell", attrs)
    geom = ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    if src_pt and not source:
        ET.SubElement(geom, "mxPoint", {"x": str(int(round(src_pt["x"]))), "y": str(int(round(src_pt["y"]))), "as": "sourcePoint"})
    if tgt_pt and not target:
        ET.SubElement(geom, "mxPoint", {"x": str(int(round(tgt_pt["x"]))), "y": str(int(round(tgt_pt["y"]))), "as": "targetPoint"})
    if bend_points:
        arr = ET.SubElement(geom, "Array", {"as": "points"})
        for bp in bend_points:
            ET.SubElement(arr, "mxPoint", {"x": str(int(round(bp["x"]))), "y": str(int(round(bp["y"])))})
    return cell


def _build_erd_table_cells(tid, name, fields, x, y, w, style_cfg):
    pal = style_cfg["palette"]
    fprim = style_cfg["font_primary"]
    fmono = style_cfg["font_mono"]
    head_h = 30
    row_h = 24
    total_h = head_h + max(1, len(fields)) * row_h
    th = pal["table_header"]
    tb = pal["table_body"]
    cells = []
    # Outer container
    container_style = (
        f"swimlane;fontStyle=1;childLayout=stackLayout;horizontal=1;"
        f"startSize={head_h};horizontalStack=0;resizeParent=1;resizeParentMax=0;"
        f"resizeLast=0;collapsible=0;marginBottom=0;whiteSpace=wrap;html=1;"
        f"fontFamily={fprim};fontSize={style_cfg['node_size']};fontColor={th['fontColor']};"
        f"fillColor={th['fill']};strokeColor={th['stroke']};strokeWidth={style_cfg['stroke_width']};"
    )
    cells.append(_cell_vertex(tid, name, container_style, x, y, w, total_h, parent="1"))
    key_fill = pal.get("key_row", "#F9FAFB")
    for idx, fld in enumerate(fields):
        is_key = any(tok in str(fld).upper() for tok in ("PK", "FK"))
        fstyle = "1" if is_key else "0"
        rfill = key_fill if is_key else tb["fill"]
        rstyle = (
            f"text;strokeColor={tb['stroke']};fillColor={rfill};align=left;"
            f"verticalAlign=middle;spacingLeft=8;spacingRight=6;overflow=hidden;"
            f"rotatable=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;html=1;"
            f"fontFamily={fmono};fontSize=11;fontStyle={fstyle};fontColor={tb['fontColor']};"
        )
        cells.append(_cell_vertex(f"{tid}_r{idx}", str(fld), rstyle, 0, head_h + idx * row_h, w, row_h, parent=tid))
    return cells, total_h


def _build_class_box_cells(cid, name, stereotype, attrs, methods, x, y, w, style_cfg):
    pal = style_cfg["palette"]
    fprim = style_cfg["font_primary"]
    fmono = style_cfg["font_mono"]
    p = pal["process"]
    head_h = 38 if stereotype else 30
    row_h = 22
    attr_h = max(24, len(attrs) * row_h + 8) if attrs else 24
    meth_h = max(24, len(methods) * row_h + 8) if methods else 24
    total_h = head_h + attr_h + meth_h
    title_html = f"&lt;&lt;{html.escape(stereotype)}&gt;&gt;<br/><b>{html.escape(name)}</b>" if stereotype else f"<b>{html.escape(name)}</b>"
    cstyle = (
        f"swimlane;fontStyle=0;childLayout=stackLayout;horizontal=1;startSize={head_h};"
        f"horizontalStack=0;resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=0;"
        f"marginBottom=0;whiteSpace=wrap;html=1;fontFamily={fprim};fontSize=12;"
        f"fontColor={p['fontColor']};fillColor={p['fill']};strokeColor={p['stroke']};"
        f"strokeWidth={style_cfg['stroke_width']};"
    )
    cells = [_cell_vertex(cid, title_html, cstyle, x, y, w, total_h, parent="1")]
    sec_style = (
        f"text;strokeColor={p['stroke']};fillColor=#FFFFFF;align=left;verticalAlign=top;"
        f"spacingLeft=8;spacingTop=4;spacingRight=6;html=1;whiteSpace=wrap;"
        f"fontFamily={fmono};fontSize=10.5;fontColor={p['fontColor']};"
    )
    cells.append(_cell_vertex(f"{cid}_attrs", "<br/>".join(html.escape(a) for a in attrs) or " ", sec_style, 0, head_h, w, attr_h, parent=cid))
    cells.append(_cell_vertex(f"{cid}_meths", "<br/>".join(html.escape(m) for m in methods) or " ", sec_style, 0, head_h + attr_h, w, meth_h, parent=cid))
    return cells, total_h


def _generate_sequence_diagram(spec, style_cfg):
    """Deterministic zero-overlap Sequence Diagram solver."""
    title = spec.get("title", "Sequence Diagram")
    participants = spec.get("participants", [])
    messages = spec.get("messages", [])
    fragments = spec.get("fragments", [])

    font = style_cfg["font_primary"]
    fmono = style_cfg["font_mono"]
    pal = style_cfg["palette"]
    p_box = pal["process"]
    p_frag = pal["external"]

    n = len(participants)
    if n == 0:
        raise ValueError("Sequence diagram requires non-empty 'participants'")

    idx_map = {str(p["id"]): i for i, p in enumerate(participants)}
    box_w = 150
    box_h = 48
    # Compute minimum gap between adjacent lifelines based on message label widths
    gaps = [210] * max(0, n - 1)
    for m in messages:
        si = idx_map.get(str(m["from"]))
        ti = idx_map.get(str(m["to"]))
        if si is None or ti is None or si == ti:
            continue
        lo, hi = min(si, ti), max(si, ti)
        span = hi - lo
        need = int(len(str(m.get("label", ""))) * 7.6 + 64)
        per_gap = max(210, int(math.ceil(need / span / 10.0) * 10))
        for g in range(lo, hi):
            if per_gap > gaps[g]:
                gaps[g] = per_gap

    margin_x = 70
    top_y = 64
    xs = [margin_x]
    for g in gaps:
        xs.append(xs[-1] + g)
    centers = [x + box_w // 2 for x in xs]

    step_y = 58
    first_msg_y = top_y + box_h + 44
    last_msg_y = first_msg_y + max(1, len(messages)) * step_y + 36
    page_w = xs[-1] + box_w + margin_x + 60
    page_h = last_msg_y + 70

    cells = []
    # Title
    tstyle = f"text;html=1;align=center;verticalAlign=middle;fontFamily={font};fontSize={style_cfg['title_size']};fontStyle=1;fontColor=#111827;"
    cells.append(_cell_vertex("title", title, tstyle, 30, 14, page_w - 60, 32))

    # Fragment frames rendered first (behind arrows)
    for fi, fr in enumerate(fragments):
        s_step = max(0, int(fr.get("from_step", 0)))
        e_step = max(s_step, int(fr.get("to_step", s_step)))
        fy = first_msg_y + s_step * step_y - 26
        fh = (e_step - s_step + 1) * step_y + 24
        fx = xs[0] - 24
        fw = (xs[-1] + box_w + 24) - fx
        lbl = f"{fr.get('kind', 'alt')} [{fr.get('condition', '')}]".strip()
        tab_w = max(116, int(len(lbl) * 7.8 + 26))
        fstyle = (
            f"shape=umlFrame;whiteSpace=wrap;html=1;pointerEvents=0;width={tab_w};height=24;"
            f"fontFamily={font};fontSize=11;fontStyle=1;fillColor=none;"
            f"strokeColor={p_frag['stroke']};strokeWidth=1.5;fontColor={p_frag['stroke']};"
        )
        cells.append(_cell_vertex(f"frag_{fi}", lbl, fstyle, fx, fy, fw, fh))

    # Lifelines & headers
    for i, part in enumerate(participants):
        pid = str(part["id"])
        cx = centers[i]
        kind = part.get("kind", "object")
        if kind == "actor":
            cells.append(_cell_vertex(f"head_{pid}", part["label"], _node_style("actor", style_cfg), cx - 22, top_y - 10, 44, 62))
            line_start_y = top_y + 62
        else:
            bstyle = (
                f"rounded=1;arcSize=8;html=1;whiteSpace=wrap;fontFamily={font};fontSize=12;"
                f"fontStyle=1;fillColor={p_box['fill']};strokeColor={p_box['stroke']};"
                f"strokeWidth={style_cfg['stroke_width']};fontColor={p_box['fontColor']};"
            )
            cells.append(_cell_vertex(f"head_{pid}", part["label"], bstyle, xs[i], top_y, box_w, box_h))
            line_start_y = top_y + box_h
        # Lifeline dashed line
        lstyle = "endArrow=none;dashed=1;dashPattern=6 4;html=1;strokeColor=#9CA3AF;strokeWidth=1.5;"
        cells.append(
            _cell_edge(
                f"life_{pid}",
                "",
                lstyle,
                src_pt={"x": cx, "y": line_start_y},
                tgt_pt={"x": cx, "y": last_msg_y},
            )
        )

    # Messages & activation bars
    for mi, m in enumerate(messages):
        y = first_msg_y + mi * step_y
        si = idx_map[str(m["from"])]
        ti = idx_map[str(m["to"])]
        sx, tx = centers[si], centers[ti]
        is_ret = bool(m.get("return") or m.get("dashed"))
        arrow = "open" if is_ret else "block"
        dashed = "1" if is_ret else "0"
        end_fill = "0" if is_ret else "1"
        mstyle = (
            f"html=1;verticalAlign=bottom;labelBackgroundColor=#FFFFFF;"
            f"endArrow={arrow};endFill={end_fill};dashed={dashed};rounded=0;"
            f"strokeColor=#1A1A1A;strokeWidth=1.8;fontFamily={fmono};fontSize=11;fontStyle=1;"
        )
        lbl = f"{mi + 1}. {m.get('label', '')}" if spec.get("number_messages", True) else str(m.get("label", ""))
        if si == ti:
            # Self-call orthogonal loop
            cells.append(
                _cell_edge(
                    f"msg_{mi}",
                    lbl,
                    mstyle + "edgeStyle=orthogonalEdgeStyle;",
                    src_pt={"x": sx, "y": y},
                    tgt_pt={"x": sx, "y": y + 26},
                    bend_points=[{"x": sx + 48, "y": y}, {"x": sx + 48, "y": y + 26}],
                )
            )
        else:
            # Draw neat activation rectangle on target for sync calls
            if not is_ret:
                act_style = f"rounded=0;whiteSpace=wrap;html=1;fillColor={p_box['fill']};strokeColor={p_box['stroke']};strokeWidth=1.2;"
                cells.append(_cell_vertex(f"act_{mi}", "", act_style, tx - 6, y - 4, 12, 34))
            cells.append(
                _cell_edge(
                    f"msg_{mi}",
                    lbl,
                    mstyle,
                    src_pt={"x": sx, "y": y},
                    tgt_pt={"x": tx, "y": y},
                )
            )

    xml_str = _make_mxfile(title, page_w, page_h, cells, grid=style_cfg["grid"])
    return xml_str, {"width": page_w, "height": page_h, "node_count": n, "edge_count": len(messages)}


def _generate_swimlane_diagram(spec, style_cfg):
    """Deterministic zero-overlap vertical/horizontal Swimlane Flowchart (UFD/BPMN-style)."""
    title = spec.get("title", "Swimlane Process Flow")
    lanes = spec.get("lanes", [])
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])

    font = style_cfg["font_primary"]
    pal = style_cfg["palette"]

    # Build ELK spec per node with lane assignment, lay out top-to-bottom within lanes
    # Assign topological rank via BFS/longest path
    node_map = {str(n["id"]): n for n in nodes}
    adj = {str(n["id"]): [] for n in nodes}
    indeg = {str(n["id"]): 0 for n in nodes}
    for e in edges:
        s, t = str(e["source"]), str(e["target"])
        if s in adj and t in indeg:
            adj[s].append(t)
            indeg[t] += 1

    rank = {}
    queue = [nid for nid, d in indeg.items() if d == 0]
    if not queue and nodes:
        queue = [str(nodes[0]["id"])]
    for q in queue:
        rank[q] = 0
    # Longest path acyclic rank
    visited_order = []
    q_idx = 0
    while q_idx < len(queue):
        u = queue[q_idx]
        q_idx += 1
        visited_order.append(u)
        for v in adj[u]:
            if rank.get(v, -1) < rank[u] + 1 and v not in visited_order:
                rank[v] = rank[u] + 1
            indeg[v] -= 1
            if indeg[v] <= 0 and v not in queue:
                queue.append(v)
    for n in nodes:
        nid = str(n["id"])
        if nid not in rank:
            rank[nid] = len(rank)

    # Size each node cleanly
    sizes = {}
    for n in nodes:
        nid = str(n["id"])
        kind = n.get("kind", "process")
        w, h = _estimate_box_size(n.get("label", nid), style_cfg["node_size"], kind)
        sizes[nid] = (int(n.get("width", w)), int(n.get("height", h)))

    # Group nodes by lane + rank; resolve multiple nodes in same (lane, rank) by offsetting row
    lane_ids = [str(l["id"]) for l in lanes]
    lane_col = {lid: i for i, lid in enumerate(lane_ids)}
    lane_max_w = {lid: 240 for lid in lane_ids}
    for n in nodes:
        lid = str(n.get("lane", lane_ids[0]))
        w, _ = sizes[str(n["id"])]
        lane_max_w[lid] = max(lane_max_w.get(lid, 240), w + 70)

    # Ensure unique (lane, row) slot so ZERO nodes overlap
    used_slots = set()
    node_row = {}
    for n in sorted(nodes, key=lambda x: (rank[str(x["id"])], lane_col.get(str(x.get("lane", lane_ids[0])), 0))):
        nid = str(n["id"])
        lid = str(n.get("lane", lane_ids[0]))
        r = rank[nid]
        while (lid, r) in used_slots:
            r += 1
        used_slots.add((lid, r))
        node_row[nid] = r

    max_row = max(node_row.values(), default=0)
    row_h = 128
    header_h = 40
    top_y = 64
    margin_x = 40

    lane_x = {}
    cur_x = margin_x
    for lid in lane_ids:
        lane_x[lid] = cur_x
        cur_x += lane_max_w[lid]

    total_lane_h = header_h + (max_row + 1) * row_h + 44
    page_w = cur_x + margin_x
    page_h = top_y + total_lane_h + 40

    cells = []
    tstyle = f"text;html=1;align=center;verticalAlign=middle;fontFamily={font};fontSize={style_cfg['title_size']};fontStyle=1;fontColor=#111827;"
    cells.append(_cell_vertex("title", title, tstyle, 20, 14, page_w - 40, 32))

    # Draw swimlane columns
    for li, lane in enumerate(lanes):
        lid = str(lane["id"])
        lw = lane_max_w[lid]
        fill_bg = "#F8FAFC" if li % 2 == 0 else "#FFFFFF"
        lstyle = (
            f"swimlane;whiteSpace=wrap;html=1;startSize={header_h};horizontal=1;"
            f"collapsible=0;fontFamily={font};fontSize=12;fontStyle=1;"
            f"fillColor={pal['process']['fill']};swimlaneFillColor={fill_bg};"
            f"strokeColor={pal['group']['stroke']};strokeWidth=1.5;fontColor=#111827;"
        )
        cells.append(_cell_vertex(f"lane_{lid}", lane["label"], lstyle, lane_x[lid], top_y, lw, total_lane_h))

    # Place nodes inside lanes (absolute coordinates relative to parent="1" for crisp cross-lane edge routing)
    abs_pos = {}
    for n in nodes:
        nid = str(n["id"])
        lid = str(n.get("lane", lane_ids[0]))
        w, h = sizes[nid]
        nx = lane_x[lid] + (lane_max_w[lid] - w) // 2
        ny = top_y + header_h + 26 + node_row[nid] * row_h + (84 - h) // 2
        abs_pos[nid] = (nx, ny, w, h, lid, node_row[nid])
        cells.append(_cell_vertex(nid, n.get("label", nid), _node_style(n.get("kind", "process"), style_cfg), nx, ny, w, h))

    # Route orthogonal edges cleanly with smart ports & clear channels
    for ei, e in enumerate(edges):
        s, t = str(e["source"]), str(e["target"])
        if s not in abs_pos or t not in abs_pos:
            continue
        sx, sy, sw, sh, sl, sr = abs_pos[s]
        tx, ty, tw, th, tl, tr = abs_pos[t]
        sc, tc = lane_col[sl], lane_col[tl]
        bps = []
        if sc == tc and tr > sr:
            ex_p, en_p = {"x": 0.5, "y": 1}, {"x": 0.5, "y": 0}
            if tr - sr > 1:
                # Detour along right edge of lane channel to avoid intermediate boxes
                ch_x = lane_x[sl] + lane_max_w[sl] - 18
                ex_p, en_p = {"x": 1, "y": 0.5}, {"x": 1, "y": 0.5}
                bps = [{"x": ch_x, "y": sy + sh // 2}, {"x": ch_x, "y": ty + th // 2}]
        elif sc == tc and tr < sr:
            # Back-edge loop on left channel
            ch_x = lane_x[sl] + 18
            ex_p, en_p = {"x": 0, "y": 0.5}, {"x": 0, "y": 0.5}
            bps = [{"x": ch_x, "y": sy + sh // 2}, {"x": ch_x, "y": ty + th // 2}]
        else:
            # Cross-lane edge: clean non-crossing orthogonal routing
            if tc > sc:
                if tr == sr:
                    ex_p, en_p = {"x": 1, "y": 0.5}, {"x": 0, "y": 0.5}
                elif tr > sr:
                    # Forward-right: exit right, go horizontally to target center, drop straight down
                    ex_p, en_p = {"x": 1, "y": 0.5}, {"x": 0.5, "y": 0}
                    bps = [{"x": tx + tw // 2, "y": sy + sh // 2}]
                else:
                    # Backward-right: exit top/right cleanly into target bottom
                    ex_p, en_p = {"x": 1, "y": 0.5}, {"x": 0.5, "y": 1}
                    bps = [{"x": tx + tw // 2, "y": sy + sh // 2}]
            else:
                if tr == sr:
                    ex_p, en_p = {"x": 0, "y": 0.5}, {"x": 1, "y": 0.5}
                elif tr < sr:
                    # Backward-left (e.g. revision loop): exit left, travel straight left to target center, go straight up!
                    ex_p, en_p = {"x": 0, "y": 0.5}, {"x": 0.5, "y": 1}
                    bps = [{"x": tx + tw // 2, "y": sy + sh // 2}]
                else:
                    # Forward-left: exit bottom, drop to inter-row gap, travel left to target top
                    ex_p, en_p = {"x": 0.5, "y": 1}, {"x": 0.5, "y": 0}
                    gap_y = ty - 24
                    bps = [{"x": sx + sw // 2, "y": gap_y}, {"x": tx + tw // 2, "y": gap_y}]
        estyle = _edge_style(style_cfg, e, exit_port=ex_p, entry_port=en_p)
        cells.append(_cell_edge(f"edge_{ei}", e.get("label", ""), estyle, source=s, target=t, bend_points=bps))

    xml_str = _make_mxfile(title, page_w, page_h, cells, grid=style_cfg["grid"])
    return xml_str, {"width": page_w, "height": page_h, "node_count": len(nodes), "edge_count": len(edges)}


def generate_drawio(spec, out_path, style_profile="monochrome-bw"):
    """Generate a clean, zero-overlap .drawio diagram from a structured spec."""
    style_cfg = load_diagram_style(style_profile)
    dtype = str(spec.get("type", "flowchart")).lower()

    if dtype in ("sd", "sequence"):
        xml_str, meta = _generate_sequence_diagram(spec, style_cfg)
    elif dtype in ("ufd", "swimlane") and spec.get("lanes"):
        xml_str, meta = _generate_swimlane_diagram(spec, style_cfg)
    else:
        # Graph layout via ELK Sugiyama orthogonal engine (flowchart, architecture, dfd, erd, cd, state, ufd-graph)
        title = spec.get("title", "Diagram")
        direction = spec.get("direction", "RIGHT" if dtype in ("erd", "cd", "architecture") else "DOWN")
        raw_nodes = spec.get("nodes", [])
        raw_edges = spec.get("edges", [])

        # Normalize node specs & compute accurate dimensions
        meta_nodes = {}
        def prep_node(n):
            nid = str(n["id"])
            kind = n.get("kind", "process")
            if dtype == "erd" or n.get("fields"):
                fields = n.get("fields", [])
                max_len = max([len(str(n.get("label", nid)))] + [len(str(f)) for f in fields])
                w = int(n.get("width", max(210, int(math.ceil((max_len * 7.6 + 26) / 10.0) * 10))))
                h = 30 + max(1, len(fields)) * 24
                kind = "erd_table"
            elif dtype == "cd" and (n.get("attributes") is not None or n.get("methods") is not None):
                attrs = n.get("attributes", [])
                meths = n.get("methods", [])
                lines = [str(n.get("label", nid))] + [str(a) for a in attrs] + [str(m) for m in meths]
                max_len = max(len(l) for l in lines)
                w = int(n.get("width", max(210, int(math.ceil((max_len * 7.4 + 28) / 10.0) * 10))))
                head_h = 38 if n.get("stereotype") else 30
                h = head_h + max(24, len(attrs) * 22 + 8) + max(24, len(meths) * 22 + 8)
                kind = "uml_class"
            elif n.get("children"):
                w, h = 200, 120
                kind = "group"
            else:
                est_w, est_h = _estimate_box_size(n.get("label", nid), style_cfg["node_size"], kind)
                w = int(n.get("width", est_w))
                h = int(n.get("height", est_h))
            meta_nodes[nid] = {**n, "id": nid, "kind": kind, "width": w, "height": h}
            elk_n = {"id": nid, "width": w, "height": h}
            if n.get("children"):
                elk_n["children"] = [prep_node(ch) for ch in n["children"]]
            return elk_n

        elk_nodes = [prep_node(n) for n in raw_nodes]

        # Semantic DFD guard: prevent illegal DFD topologies (must pass through a process)
        if dtype == "dfd":
            for e in raw_edges:
                sk = meta_nodes.get(str(e["source"]), {}).get("kind", "")
                tk = meta_nodes.get(str(e["target"]), {}).get("kind", "")
                if sk in ("external", "store", "cylinder", "database") and tk in ("external", "store", "cylinder", "database"):
                    raise ValueError(
                        f"DFD semantic violation: direct edge '{e['source']}' ({sk}) -> '{e['target']}' ({tk}) is forbidden; data flows must pass through a process node."
                    )

        # Helper to resolve exact ERD row index for field-level pointer accuracy
        def _resolve_erd_field(tid, field_name):
            fields = meta_nodes.get(tid, {}).get("fields", [])
            if not field_name:
                return None
            q = str(field_name).strip().lower()
            for idx, raw_f in enumerate(fields):
                # Strip leading PK/FK badges and trailing type info to match exact column name
                cleaned = str(raw_f).strip()
                for prefix in ("PK:", "FK:", "PK ", "FK ", "PK/FK "):
                    if cleaned.upper().startswith(prefix):
                        cleaned = cleaned[len(prefix):].strip()
                col_tok = cleaned.split(":")[0].split("(")[0].strip().lower()
                if col_tok == q or q == cleaned.lower():
                    return idx
            raise ValueError(
                f"ERD field mismatch: field '{field_name}' not found in table '{tid}'. Available fields: {fields}"
            )

        # Pre-validate ERD field pointers before layout
        if dtype == "erd":
            for e in raw_edges:
                if e.get("source_field"):
                    _resolve_erd_field(str(e["source"]), e["source_field"])
                if e.get("target_field"):
                    _resolve_erd_field(str(e["target"]), e["target_field"])

        elk_edges = []
        for idx, e in enumerate(raw_edges):
            elk_edges.append({
                "id": str(e.get("id", f"e{idx}")),
                "source": str(e["source"]),
                "target": str(e["target"]),
                "label": str(e.get("label", "")),
            })

        elk_spec = {
            "direction": direction,
            "nodeSpacing": spec.get("node_spacing", 84 if dtype in ("erd", "cd") else 64),
            "layerSpacing": spec.get("layer_spacing", 130 if dtype in ("erd", "cd") else 92),
            "edgeNodeSpacing": spec.get("edge_node_spacing", 36),
            "edgeEdgeSpacing": spec.get("edge_edge_spacing", 26),
            "edgeFontSize": style_cfg["edge_size"],
            "nodes": elk_nodes,
            "edges": elk_edges,
        }
        laid = _run_elk(elk_spec)

        offset_y = 54 if title else 10
        page_w = max(800, laid["width"] + 60)
        page_h = max(500, laid["height"] + offset_y + 40)

        cells = []
        if title:
            tstyle = f"text;html=1;align=center;verticalAlign=middle;fontFamily={style_cfg['font_primary']};fontSize={style_cfg['title_size']};fontStyle=1;fontColor=#111827;"
            cells.append(_cell_vertex("title", title, tstyle, 20, 14, page_w - 40, 32))

        # Render groups first (background), then leaf vertices
        laid_nodes = laid["nodes"]
        group_ids = [nid for nid, mn in meta_nodes.items() if mn["kind"] == "group"]
        leaf_ids = [nid for nid, mn in meta_nodes.items() if mn["kind"] != "group"]

        for nid in group_ids:
            ln = laid_nodes[nid]
            mn = meta_nodes[nid]
            cells.append(_cell_vertex(nid, mn.get("label", nid), _node_style("group", style_cfg), ln["x"], ln["y"] + offset_y, ln["width"], ln["height"]))

        for nid in leaf_ids:
            ln = laid_nodes[nid]
            mn = meta_nodes[nid]
            x, y, w, h = ln["x"], ln["y"] + offset_y, ln["width"], ln["height"]
            if mn["kind"] == "erd_table":
                tcells, _ = _build_erd_table_cells(nid, mn.get("label", nid), mn.get("fields", []), x, y, w, style_cfg)
                cells.extend(tcells)
            elif mn["kind"] == "uml_class":
                ccells, _ = _build_class_box_cells(
                    nid, mn.get("label", nid), mn.get("stereotype"), mn.get("attributes", []), mn.get("methods", []), x, y, w, style_cfg
                )
                cells.extend(ccells)
            else:
                cells.append(_cell_vertex(nid, mn.get("label", nid), _node_style(mn["kind"], style_cfg), x, y, w, h))

        def _snap_diamond_port(port, nid):
            if not port or meta_nodes.get(nid, {}).get("kind") != "decision":
                return port
            px, py = port["x"], port["y"]
            # Snap strictly to the nearest rhombus vertex (top, right, bottom, left)
            corners = [{"x": 0.5, "y": 0}, {"x": 1, "y": 0.5}, {"x": 0.5, "y": 1}, {"x": 0, "y": 0.5}]
            return min(corners, key=lambda c: (c["x"] - px) ** 2 + (c["y"] - py) ** 2)

        # Detect antiparallel edges (A->B and B->A) to separate ports cleanly
        pair_set = {(str(e["source"]), str(e["target"])) for e in raw_edges}
        card_map = {
            "1:N": ("ERmandOne", "ERzeroToMany"),
            "1:1..N": ("ERmandOne", "ERoneToMany"),
            "1:0..N": ("ERmandOne", "ERzeroToMany"),
            "1:1": ("ERmandOne", "ERmandOne"),
            "1:0..1": ("ERmandOne", "ERzeroToOne"),
            "N:M": ("ERzeroToMany", "ERzeroToMany"),
        }

        edge_lookup = {str(e.get("id", f"e{i}")): e for i, e in enumerate(raw_edges)}
        used_decision_ports = {}
        erd_pair_counts = {}
        erd_pair_seen = {}
        if dtype == "erd":
            for le in laid["edges"]:
                pk = (le["source"], le["target"])
                erd_pair_counts[pk] = erd_pair_counts.get(pk, 0) + 1

        for le in laid["edges"]:
            orig = dict(edge_lookup.get(le["id"], {}))
            src_id, tgt_id = le["source"], le["target"]
            ex_p = _snap_diamond_port(le.get("exitPort"), src_id)
            en_p = _snap_diamond_port(le.get("entryPort"), tgt_id)
            bps = [{"x": bp["x"], "y": bp["y"] + offset_y} for bp in le.get("bendPoints", [])]

            if dtype == "erd":
                card = orig.get("cardinality", "1:N")
                sa_def, ea_def = card_map.get(card, ("ERmandOne", "ERzeroToMany"))
                orig.setdefault("start_arrow", sa_def)
                orig.setdefault("end_arrow", ea_def)
                s_idx = _resolve_erd_field(src_id, orig.get("source_field"))
                t_idx = _resolve_erd_field(tgt_id, orig.get("target_field"))
                if s_idx is None and meta_nodes[src_id].get("fields"):
                    s_idx = 0
                sb = laid_nodes[src_id]
                tb = laid_nodes[tgt_id]
                go_right = (tb["x"] + tb["width"] / 2) >= (sb["x"] + sb["width"] / 2)
                s_cell = f"{src_id}_r{s_idx}" if s_idx is not None else src_id
                t_cell = f"{tgt_id}_r{t_idx}" if t_idx is not None else tgt_id
                sy_abs = sb["y"] + offset_y + (30 + (s_idx + 0.5) * 24 if s_idx is not None else sb["height"] / 2)
                ty_abs = tb["y"] + offset_y + (30 + (t_idx + 0.5) * 24 if t_idx is not None else tb["height"] / 2)
                sx_abs = (sb["x"] + sb["width"]) if go_right else sb["x"]
                tx_abs = tb["x"] if go_right else (tb["x"] + tb["width"])
                pk = (src_id, tgt_id)
                k_idx = erd_pair_seen.get(pk, 0)
                erd_pair_seen[pk] = k_idx + 1
                k_tot = erd_pair_counts.get(pk, 1)
                frac = (k_idx + 1) / float(k_tot + 1)
                mid_x = int(round(sx_abs + (tx_abs - sx_abs) * frac))
                segs = [((sx_abs, sy_abs), (mid_x, sy_abs)), ((mid_x, sy_abs), (mid_x, ty_abs)), ((mid_x, ty_abs), (tx_abs, ty_abs))]
                blocked = False
                for nid_o in leaf_ids:
                    if nid_o in (src_id, tgt_id):
                        continue
                    ob = laid_nodes[nid_o]
                    if any(_seg_intersects_rect(p1, p2, ob["x"], ob["y"] + offset_y, ob["width"], ob["height"], pad=2) for p1, p2 in segs):
                        blocked = True
                        break
                ex_p = {"x": 1 if go_right else 0, "y": 0.5}
                en_p = {"x": 0 if go_right else 1, "y": 0.5}
                orig["edge_style"] = "orthogonalEdgeStyle"
                if not blocked:
                    # Crisp 90-degree orthogonal Z-route with staggered mid_x for dual FKs
                    if abs(sy_abs - ty_abs) > 2:
                        bps = [{"x": mid_x, "y": int(round(sy_abs))}, {"x": mid_x, "y": int(round(ty_abs))}]
                    else:
                        bps = []
                else:
                    # Keep ELK's obstacle-free detour intact; step cleanly from exact row Y into ELK channel
                    if bps:
                        bps = [{"x": bps[0]["x"], "y": int(round(sy_abs))}] + bps + [{"x": bps[-1]["x"], "y": int(round(ty_abs))}]
                estyle = _edge_style(style_cfg, orig, exit_port=ex_p, entry_port=en_p)
                cells.append(_cell_edge(le["id"], orig.get("label", ""), estyle, source=s_cell, target=t_cell, bend_points=bps))
                continue

            # Antiparallel edge separation ONLY when nodes are aligned horizontally or vertically
            if (tgt_id, src_id) in pair_set:
                is_first = src_id < tgt_id
                sb, tb = laid_nodes[src_id], laid_nodes[tgt_id]
                dx = abs((tb["x"] + tb["width"] / 2) - (sb["x"] + sb["width"] / 2))
                dy = abs((tb["y"] + tb["height"] / 2) - (sb["y"] + sb["height"] / 2))
                if dy < 45:
                    y_slot = 0.28 if is_first else 0.72
                    go_r = (tb["x"] + tb["width"] / 2) >= (sb["x"] + sb["width"] / 2)
                    ex_p = {"x": 1 if go_r else 0, "y": y_slot}
                    en_p = {"x": 0 if go_r else 1, "y": y_slot}
                    bps = []
                elif dx < 45:
                    x_slot = 0.28 if is_first else 0.72
                    go_d = (tb["y"] + tb["height"] / 2) >= (sb["y"] + sb["height"] / 2)
                    ex_p = {"x": x_slot, "y": 1 if go_d else 0}
                    en_p = {"x": x_slot, "y": 0 if go_d else 1}
                    bps = []

            # Prevent two outgoing edges from sharing the same rhombus corner
            if meta_nodes.get(src_id, {}).get("kind") == "decision" and ex_p:
                used = used_decision_ports.setdefault(src_id, set())
                key = (ex_p["x"], ex_p["y"])
                if key in used:
                    src_b = laid_nodes[src_id]
                    tgt_b = laid_nodes[tgt_id]
                    pref = {"x": 0, "y": 0.5} if (tgt_b["x"] + tgt_b["width"] / 2) < (src_b["x"] + src_b["width"] / 2) else {"x": 1, "y": 0.5}
                    if (pref["x"], pref["y"]) not in used:
                        ex_p = pref
                used.add((ex_p["x"], ex_p["y"]))
                bps = []  # Let Draw.io orthogonal router connect cleanly from exact rhombus vertex
            estyle = _edge_style(style_cfg, orig, exit_port=ex_p, entry_port=en_p)
            cells.append(_cell_edge(le["id"], orig.get("label", ""), estyle, source=src_id, target=tgt_id, bend_points=bps))

        xml_str = _make_mxfile(title, page_w, page_h, cells, grid=style_cfg["grid"])
        meta = {"width": page_w, "height": page_h, "node_count": len(leaf_ids), "edge_count": len(laid["edges"])}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    return {"drawio_path": os.path.abspath(out_path), **meta}


def _extract_graph_model(drawio_path):
    tree = ET.parse(drawio_path)
    root = tree.getroot()
    diag = root.find("diagram")
    if diag is None:
        return root.find(".//mxGraphModel")
    model = diag.find("mxGraphModel")
    if model is not None:
        return model
    # Decompress deflate+base64 encoded diagram content
    raw = (diag.text or "").strip()
    if raw:
        data = base64.b64decode(raw)
        xml_bytes = zlib.decompress(data, -15)
        decoded = urllib.parse.unquote(xml_bytes.decode("utf-8"))
        return ET.fromstring(decoded)
    return None


def _seg_intersects_rect(p1, p2, rx, ry, rw, rh, pad=2):
    """Check whether orthogonal/straight segment p1-p2 penetrates interior of rectangle."""
    x1, y1 = p1
    x2, y2 = p2
    left, right = rx + pad, rx + rw - pad
    top, bottom = ry + pad, ry + rh - pad
    if left >= right or top >= bottom:
        return False
    # Fast bounding box reject
    if max(x1, x2) <= left or min(x1, x2) >= right or max(y1, y2) <= top or min(y1, y2) >= bottom:
        return False
    # Orthogonal exact checks
    if abs(x1 - x2) < 1e-6:
        return left < x1 < right and not (max(y1, y2) <= top or min(y1, y2) >= bottom)
    if abs(y1 - y2) < 1e-6:
        return top < y1 < bottom and not (max(x1, x2) <= left or min(x1, x2) >= right)
    # Parametric Liang-Barsky for diagonal segments
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in [(-dx, x1 - left), (dx, right - x1), (-dy, y1 - top), (dy, bottom - y1)]:
        if abs(p) < 1e-9:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    return False
                t0 = max(t0, r)
            else:
                if r < t0:
                    return False
                t1 = min(t1, r)
    return t0 < t1


def validate_drawio(drawio_path):
    """Strict geometric zero-overlap & cleanliness validator for .drawio files."""
    model = _extract_graph_model(drawio_path)
    if model is None:
        return {"pass": False, "score": 0, "issues": [{"type": "parse_error", "detail": "No mxGraphModel found"}]}

    pw = float(model.attrib.get("pageWidth", 1200))
    ph = float(model.attrib.get("pageHeight", 900))
    cells = model.findall(".//mxCell")

    vertices = {}
    containers = set()
    edges = []

    for c in cells:
        cid = c.attrib.get("id", "")
        if cid in ("0", "1"):
            continue
        style = c.attrib.get("style", "")
        parent = c.attrib.get("parent", "1")
        geom = c.find("mxGeometry")
        if c.attrib.get("vertex") == "1" and geom is not None:
            x = float(geom.attrib.get("x", 0))
            y = float(geom.attrib.get("y", 0))
            w = float(geom.attrib.get("width", 0))
            h = float(geom.attrib.get("height", 0))
            is_container = any(k in style for k in ("container=1", "swimlane", "umlFrame"))
            is_text_only = style.startswith("text;")
            is_act = cid.startswith("act_")
            if is_container and "childLayout=stackLayout" not in style:
                containers.add(cid)
            vertices[cid] = {
                "id": cid, "parent": parent, "x": x, "y": y, "w": w, "h": h,
                "style": style, "value": c.attrib.get("value", ""),
                "is_container": is_container, "is_text_only": is_text_only, "is_act": is_act,
            }
        elif c.attrib.get("edge") == "1" and geom is not None:
            pts = []
            for mp in geom.findall("./Array[@as='points']/mxPoint"):
                pts.append((float(mp.attrib.get("x", 0)), float(mp.attrib.get("y", 0))))
            src_pt = geom.find("./mxPoint[@as='sourcePoint']")
            tgt_pt = geom.find("./mxPoint[@as='targetPoint']")
            edges.append({
                "id": cid,
                "source": c.attrib.get("source"),
                "target": c.attrib.get("target"),
                "style": style,
                "points": pts,
                "src_pt": (float(src_pt.attrib["x"]), float(src_pt.attrib["y"])) if src_pt is not None else None,
                "tgt_pt": (float(tgt_pt.attrib["x"]), float(tgt_pt.attrib["y"])) if tgt_pt is not None else None,
            })

    issues = []

    # 1. Node-Node Overlap check (among top-level non-container non-activation nodes)
    check_nodes = [
        v for v in vertices.values()
        if v["parent"] == "1" and v["id"] not in containers and not v["is_act"] and v["id"] != "title"
    ]
    for i in range(len(check_nodes)):
        a = check_nodes[i]
        for j in range(i + 1, len(check_nodes)):
            b = check_nodes[j]
            ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ix > 1 and iy > 1:
                issues.append({
                    "type": "node_overlap",
                    "severity": "critical",
                    "nodes": [a["id"], b["id"]],
                    "overlap_px": [round(ix, 1), round(iy, 1)],
                })

    # 2. Edge-Through-Node crossing check (resolving nested child row cells to absolute canvas coordinates)
    def _abs_box(v):
        ax, ay = v["x"], v["y"]
        p = v.get("parent", "1")
        while p in vertices and p not in ("0", "1"):
            pv = vertices[p]
            ax += pv["x"]
            ay += pv["y"]
            p = pv.get("parent", "1")
        return ax, ay, v["w"], v["h"]

    def _root_node_id(cid):
        if cid not in vertices:
            return cid
        cur = cid
        while vertices[cur].get("parent", "1") in vertices:
            cur = vertices[cur]["parent"]
        return cur

    def _port_pt(v, style, prefix):
        px, py = 0.5, 0.5
        for part in style.split(";"):
            if part.startswith(f"{prefix}X="):
                px = float(part.split("=")[1])
            elif part.startswith(f"{prefix}Y="):
                py = float(part.split("=")[1])
        ax, ay, aw, ah = _abs_box(v)
        return (ax + aw * px, ay + ah * py)

    all_segments = []
    for e in edges:
        if e["id"].startswith("life_"):
            continue
        sp = e["src_pt"]
        tp = e["tgt_pt"]
        if e["source"] in vertices:
            sp = _port_pt(vertices[e["source"]], e["style"], "exit")
        if e["target"] in vertices:
            tp = _port_pt(vertices[e["target"]], e["style"], "entry")
        if not sp or not tp:
            continue
        src_root = _root_node_id(e["source"])
        tgt_root = _root_node_id(e["target"])
        poly = [sp] + e["points"] + [tp]
        for k in range(len(poly) - 1):
            p1, p2 = poly[k], poly[k + 1]
            all_segments.append((e["id"], p1, p2))
            for v in check_nodes:
                if v["id"] in (e["source"], e["target"], src_root, tgt_root):
                    continue
                if _seg_intersects_rect(p1, p2, v["x"], v["y"], v["w"], v["h"], pad=4):
                    issues.append({
                        "type": "edge_crosses_node",
                        "severity": "critical",
                        "edge": e["id"],
                        "crossed_node": v["id"],
                    })

    # 3. Collinear overlapping edge segments (stacked lines)
    for i in range(len(all_segments)):
        id1, (x1, y1), (x2, y2) = all_segments[i]
        for j in range(i + 1, len(all_segments)):
            id2, (x3, y3), (x4, y4) = all_segments[j]
            if id1 == id2:
                continue
            # Both vertical & collinear
            if abs(x1 - x2) < 1 and abs(x3 - x4) < 1 and abs(x1 - x3) < 2:
                ov = min(max(y1, y2), max(y3, y4)) - max(min(y1, y2), min(y3, y4))
                if ov > 10:
                    issues.append({"type": "edge_overlap", "severity": "warning", "edges": [id1, id2], "overlap_px": round(ov, 1)})
            # Both horizontal & collinear
            elif abs(y1 - y2) < 1 and abs(y3 - y4) < 1 and abs(y1 - y3) < 2:
                ov = min(max(x1, x2), max(x3, x4)) - max(min(x1, x2), min(x3, x4))
                if ov > 10:
                    issues.append({"type": "edge_overlap", "severity": "warning", "edges": [id1, id2], "overlap_px": round(ov, 1)})

    # 4. Page bounds check
    for v in check_nodes:
        if v["x"] < 0 or v["y"] < 0 or (v["x"] + v["w"]) > pw + 5 or (v["y"] + v["h"]) > ph + 5:
            issues.append({"type": "out_of_bounds", "severity": "warning", "node": v["id"]})

    crit = sum(1 for x in issues if x.get("severity") == "critical")
    warn = sum(1 for x in issues if x.get("severity") == "warning")
    score = max(0, 100 - crit * 25 - warn * 5)
    return {
        "pass": crit == 0,
        "score": score,
        "critical_count": crit,
        "warning_count": warn,
        "node_count": len(check_nodes),
        "edge_count": len(edges),
        "issues": issues[:30],
    }


def render_drawio(drawio_path, out_dir=None, formats=("png", "svg"), scale=2, border=12):
    """Render .drawio to PNG, SVG, and/or vector PDF via headless draw.io CLI."""
    bins = resolve_binaries()
    exe = bins["drawio"]
    if not exe:
        raise RuntimeError("draw.io.exe not found")
    src = os.path.abspath(drawio_path)
    out_dir = os.path.abspath(out_dir or os.path.dirname(src))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    outputs = {}
    for fmt in formats:
        dst = os.path.join(out_dir, f"{stem}.{fmt}")
        cmd = [
            exe,
            "--no-sandbox",
            "--disable-gpu",
            "-x",
            "-f",
            fmt,
            "--border",
            str(border),
            "-o",
            dst,
            src,
        ]
        if fmt == "png":
            cmd.insert(cmd.index("-o"), "-s")
            cmd.insert(cmd.index("-o"), str(scale))
        elif fmt == "pdf":
            cmd.insert(cmd.index("-o"), "--crop")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=build_env())
        ok = os.path.exists(dst) and os.path.getsize(dst) > 0
        outputs[fmt] = {"path": dst, "ok": ok, "bytes": os.path.getsize(dst) if ok else 0, "rc": p.returncode}
    return outputs
