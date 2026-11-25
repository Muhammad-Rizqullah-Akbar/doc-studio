"""Precision Word (.docx -> Word COM Auto-TOC -> .pdf) Engine supporting any style profile."""
import json
import os
import subprocess
import tempfile

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image as PILImage

from paths import build_env, resolve_binaries


ALIGN_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


def load_doc_profile(profile_name="academic-proposal", overrides=None):
    bins = resolve_binaries()
    with open(bins["style_profiles"], encoding="utf-8") as f:
        profiles = json.load(f)["profiles"]
    if profile_name not in profiles:
        raise ValueError(f"Unknown profile '{profile_name}'. Available: {list(profiles.keys())}")
    prof = json.loads(json.dumps(profiles[profile_name]))
    if overrides:
        _deep_merge(prof, overrides)
    return prof


def _deep_merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _set_run_font(run, font_name, size_pt, bold=False, italic=False, color_hex=None):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color_hex:
        run.font.color.rgb = RGBColor.from_string(color_hex.lstrip("#"))
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), font_name)


def _set_outline_level(p, level):
    pPr = p._p.get_or_add_pPr()
    ol = pPr.find(qn("w:outlineLvl"))
    if ol is None:
        ol = OxmlElement("w:outlineLvl")
        pPr.append(ol)
    ol.set(qn("w:val"), str(level))


def _add_field(paragraph, field_instr, font_name="Times New Roman", size_pt=12, bold=False):
    run = paragraph.add_run()
    _set_run_font(run, font_name, size_pt, bold=bold)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    fld_begin.set(qn("w:dirty"), "true")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {field_instr} "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(fld_end)


def _configure_section_page_num(section, fmt="decimal", start=None, position="bottom_right", font_name="Times New Roman", size_pt=11, first_page_bottom_center=False):
    sectPr = section._sectPr
    pgNum = sectPr.find(qn("w:pgNumType"))
    if pgNum is None:
        pgNum = OxmlElement("w:pgNumType")
        sectPr.append(pgNum)
    pgNum.set(qn("w:fmt"), fmt)
    if start is not None:
        pgNum.set(qn("w:start"), str(start))

    section.different_first_page_header_footer = bool(first_page_bottom_center)
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    if first_page_bottom_center:
        section.first_page_header.is_linked_to_previous = False
        section.first_page_footer.is_linked_to_previous = False
        fp = section.first_page_footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_field(fp, "PAGE", font_name=font_name, size_pt=size_pt)

    # Normal pages
    if position == "top_right":
        p = section.header.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif position == "bottom_center":
        p = section.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p = section.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_field(p, "PAGE", font_name=font_name, size_pt=size_pt)


def _set_cell_shading(cell, fill_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex.lstrip("#")}"/>')
    tcPr.append(shd)


def _set_cell_margins(cell, pad):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for side in ("top", "bottom", "left", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(pad.get(side, 80)))
        el.set(qn("w:type"), "dxa")
        tcMar.append(el)
    tcPr.append(tcMar)


def _apply_table_borders(table, style="grid", color="374151"):
    tblPr = table._tbl.tblPr
    c = color.lstrip("#")
    if style == "booktabs":
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="single" w:sz="12" w:space="0" w:color="{c}"/>'
            f'<w:bottom w:val="single" w:sz="12" w:space="0" w:color="{c}"/>'
            f'<w:insideH w:val="none"/>'
            f'<w:left w:val="none"/>'
            f'<w:right w:val="none"/>'
            f'<w:insideV w:val="none"/>'
            f"</w:tblBorders>"
        )
    else:
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{c}"/>'
            f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{c}"/>'
            f'<w:left w:val="single" w:sz="6" w:space="0" w:color="{c}"/>'
            f'<w:right w:val="single" w:sz="6" w:space="0" w:color="{c}"/>'
            f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{c}"/>'
            f'<w:insideV w:val="single" w:sz="4" w:space="0" w:color="{c}"/>'
            f"</w:tblBorders>"
        )
    tblPr.append(borders)


def _set_row_booktabs_header_rule(row, color="111827"):
    c = color.lstrip("#")
    for cell in row.cells:
        tcPr = cell._tc.get_or_add_tcPr()
        tcB = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'<w:bottom w:val="single" w:sz="8" w:space="0" w:color="{c}"/>'
            f"</w:tcBorders>"
        )
        tcPr.append(tcB)


def _lock_row(row, is_header=False, cant_split=True):
    trPr = row._tr.get_or_add_trPr()
    if is_header:
        trPr.append(OxmlElement("w:tblHeader"))
    if cant_split:
        trPr.append(OxmlElement("w:cantSplit"))


def _latex_to_omml_element(latex_expr):
    """Convert LaTeX math string to Word OMML element via Pandoc."""
    bins = resolve_binaries()
    if not bins["pandoc"]:
        return None
    with tempfile.TemporaryDirectory() as td:
        md = os.path.join(td, "eq.md")
        dx = os.path.join(td, "eq.docx")
        with open(md, "w", encoding="utf-8") as f:
            f.write(f"$$\n{latex_expr}\n$$\n")
        p = subprocess.run([bins["pandoc"], md, "-o", dx], capture_output=True, text=True, timeout=30, env=build_env())
        if p.returncode != 0 or not os.path.exists(dx):
            return None
        tmp_doc = Document(dx)
        omath = tmp_doc.element.body.find(".//{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath")
        if omath is not None:
            return omath
    return None


def _render_bibliography_entries(bib_path, csl_name, cite_keys=None):
    """Render formatted bibliography entries using Pandoc --citeproc."""
    bins = resolve_binaries()
    if not bins["pandoc"] or not os.path.exists(bib_path):
        return []
    csl_path = csl_name if os.path.exists(csl_name) else os.path.join(bins["csl_dir"], csl_name)
    with tempfile.TemporaryDirectory() as td:
        md = os.path.join(td, "refs.md")
        out_txt = os.path.join(td, "refs.plain")
        nocite = " ".join(f"@{k}" for k in cite_keys) if cite_keys else "@*"
        with open(md, "w", encoding="utf-8") as f:
            f.write(f"---\nnocite: |\n  {nocite}\n---\n\n::: {{#refs}}\n:::\n")
        cmd = [bins["pandoc"], md, "--citeproc", f"--bibliography={bib_path}", "-t", "plain", "--wrap=none", "-o", out_txt]
        if os.path.exists(csl_path):
            cmd.append(f"--csl={csl_path}")
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=45, env=build_env())
        if p.returncode != 0 or not os.path.exists(out_txt):
            return []
        raw = open(out_txt, encoding="utf-8", errors="replace").read()
        entries = [blk.strip().replace("\n", " ") for blk in raw.split("\n\n") if blk.strip()]
        return entries


class PrecisionDocBuilder:
    def __init__(self, profile_name="academic-proposal", overrides=None):
        self.prof = load_doc_profile(profile_name, overrides)
        self.doc = Document()
        self.chapter = 0
        self.fig_no = 0
        self.tbl_no = 0
        self.eq_no = 0
        self._apply_page_setup(self.doc.sections[0])
        self._apply_base_styles()

    def _apply_page_setup(self, section):
        pg = self.prof["page"]
        mg = self.prof["margins_cm"]
        section.page_width = Cm(pg["width_cm"])
        section.page_height = Cm(pg["height_cm"])
        section.left_margin = Cm(mg["left"])
        section.right_margin = Cm(mg["right"])
        section.top_margin = Cm(mg["top"])
        section.bottom_margin = Cm(mg["bottom"])

    def _apply_base_styles(self):
        fonts = self.prof["fonts"]
        sizes = self.prof["sizes_pt"]
        par = self.prof["paragraph"]
        st = self.doc.styles["Normal"]
        st.font.name = fonts["body"]
        st.font.size = Pt(sizes["body"])
        rPr = st.element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rFonts.set(qn(attr), fonts["body"])
        pf = st.paragraph_format
        pf.alignment = ALIGN_MAP.get(par["alignment"], WD_ALIGN_PARAGRAPH.JUSTIFY)
        pf.line_spacing = par["line_spacing"]
        pf.space_before = Pt(par["space_before_pt"])
        pf.space_after = Pt(par["space_after_pt"])
        pf.first_line_indent = Cm(par["first_line_indent_cm"])
        pf.widow_control = bool(par.get("widow_control", True))

        # Dedicated caption styles so Word COM auto-populates Daftar Gambar & Daftar Tabel
        for cname in ("CaptionGambar", "CaptionTabel"):
            if cname not in self.doc.styles:
                cs = self.doc.styles.add_style(cname, WD_STYLE_TYPE.PARAGRAPH)
                cs.font.name = fonts["caption"]
                cs.font.size = Pt(sizes["caption"])
                cs.font.bold = True

    def _usable_width_cm(self):
        pg = self.prof["page"]
        mg = self.prof["margins_cm"]
        return round(pg["width_cm"] - mg["left"] - mg["right"], 2)

    def _usable_height_cm(self):
        pg = self.prof["page"]
        mg = self.prof["margins_cm"]
        return round(pg["height_cm"] - mg["top"] - mg["bottom"], 2)

    def add_cover(self, cover):
        fonts = self.prof["fonts"]
        sec = self.doc.sections[0]
        sec.different_first_page_header_footer = True
        if cover.get("doc_type"):
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(14)
            _set_run_font(p.add_run(cover["doc_type"].upper()), fonts["heading"], 14, bold=True)
        if cover.get("title"):
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.line_spacing = 1.25
            p.paragraph_format.space_after = Pt(10)
            _set_run_font(p.add_run(cover["title"]), fonts["heading"], 16, bold=True)
        if cover.get("subtitle"):
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_after = Pt(24)
            _set_run_font(p.add_run(cover["subtitle"]), fonts["body"], 12, italic=True)
        if cover.get("logo_path") and os.path.exists(cover["logo_path"]):
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_before = Pt(18)
            p.paragraph_format.space_after = Pt(28)
            p.add_run().add_picture(cover["logo_path"], width=Cm(cover.get("logo_width_cm", 4.5)))
        if cover.get("authors"):
            p0 = self.doc.add_paragraph()
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p0.paragraph_format.first_line_indent = Cm(0)
            p0.paragraph_format.space_after = Pt(8)
            _set_run_font(p0.add_run(cover.get("authors_label", "Disusun Oleh:")), fonts["body"], 12, bold=True)
            for a in cover["authors"]:
                pa = self.doc.add_paragraph()
                pa.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pa.paragraph_format.first_line_indent = Cm(0)
                pa.paragraph_format.space_after = Pt(2)
                _set_run_font(pa.add_run(str(a)), fonts["body"], 12)
        if cover.get("institution"):
            pi = self.doc.add_paragraph()
            pi.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pi.paragraph_format.first_line_indent = Cm(0)
            pi.paragraph_format.space_before = Pt(42)
            pi.paragraph_format.line_spacing = 1.25
            _set_run_font(pi.add_run("\n".join(cover["institution"])), fonts["heading"], 13, bold=True)

    def start_front_matter(self):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self._apply_page_setup(sec)
        num = self.prof["numbering"]
        _configure_section_page_num(
            sec,
            fmt=num.get("front_matter", "lowerRoman"),
            start=1,
            position="bottom_center",
            font_name=self.prof["fonts"]["body"],
            size_pt=11,
            first_page_bottom_center=False,
        )

    def start_main_matter(self):
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        self._apply_page_setup(sec)
        num = self.prof["numbering"]
        _configure_section_page_num(
            sec,
            fmt=num.get("main_matter", "decimal"),
            start=1,
            position=num.get("main_position", "bottom_right"),
            font_name=self.prof["fonts"]["body"],
            size_pt=11,
            first_page_bottom_center=num.get("chapter_first_page_bottom_center", False),
        )

    def add_toc_page(self, title="DAFTAR ISI", field_instr='TOC \\o "1-3" \\h \\z \\u', page_break_before=False):
        if page_break_before:
            self.doc.add_page_break()
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_after = Pt(12)
        p.paragraph_format.keep_with_next = True
        _set_run_font(p.add_run(title), self.prof["fonts"]["heading"], self.prof["sizes_pt"]["h1"], bold=True)
        tp = self.doc.add_paragraph()
        tp.paragraph_format.first_line_indent = Cm(0)
        _add_field(tp, field_instr, font_name=self.prof["fonts"]["body"], size_pt=self.prof["sizes_pt"]["body"])

    def add_heading(self, text, level=1, new_chapter=False):
        hd = self.prof["headings"]
        fonts = self.prof["fonts"]
        sizes = self.prof["sizes_pt"]
        if new_chapter:
            if self.chapter > 0:
                if self.prof["numbering"].get("chapter_first_page_bottom_center"):
                    sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
                    self._apply_page_setup(sec)
                    _configure_section_page_num(
                        sec,
                        fmt=self.prof["numbering"].get("main_matter", "decimal"),
                        start=None,
                        position=self.prof["numbering"].get("main_position", "top_right"),
                        font_name=fonts["body"],
                        size_pt=11,
                        first_page_bottom_center=True,
                    )
                else:
                    self.doc.add_page_break()
            self.chapter += 1
            self.fig_no = 0
            self.tbl_no = 0
            self.eq_no = 0

        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.keep_with_next = True
        if level == 1:
            p.alignment = ALIGN_MAP.get(hd.get("h1_align", "left"), WD_ALIGN_PARAGRAPH.LEFT)
            p.paragraph_format.space_before = Pt(hd["h1_space_before_pt"])
            p.paragraph_format.space_after = Pt(hd["h1_space_after_pt"])
            txt = text.upper() if hd.get("h1_uppercase") else text
            _set_run_font(p.add_run(txt), fonts["heading"], sizes["h1"], bold=True)
            _set_outline_level(p, 0)
        elif level == 2:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(hd["h2_space_before_pt"])
            p.paragraph_format.space_after = Pt(hd["h2_space_after_pt"])
            _set_run_font(p.add_run(text), fonts["heading"], sizes["h2"], bold=True)
            _set_outline_level(p, 1)
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(hd["h3_space_before_pt"])
            p.paragraph_format.space_after = Pt(hd["h3_space_after_pt"])
            _set_run_font(p.add_run(text), fonts["heading"], sizes["h3"], bold=True)
            _set_outline_level(p, 2)
        return p

    def add_paragraph(self, text, indent=True, bold=False, italic=False, align=None):
        par = self.prof["paragraph"]
        p = self.doc.add_paragraph()
        p.alignment = ALIGN_MAP.get(align or par["alignment"], WD_ALIGN_PARAGRAPH.JUSTIFY)
        pf = p.paragraph_format
        pf.line_spacing = par["line_spacing"]
        pf.space_before = Pt(par["space_before_pt"])
        pf.space_after = Pt(par["space_after_pt"])
        pf.first_line_indent = Cm(par["first_line_indent_cm"]) if indent else Cm(0)
        pf.widow_control = True
        _set_run_font(p.add_run(text), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"], bold=bold, italic=italic)
        return p

    def add_bullets(self, items, numbered=False):
        par = self.prof["paragraph"]
        for idx, item in enumerate(items, 1):
            p = self.doc.add_paragraph()
            p.alignment = ALIGN_MAP.get(par["alignment"], WD_ALIGN_PARAGRAPH.JUSTIFY)
            pf = p.paragraph_format
            pf.line_spacing = par["line_spacing"]
            pf.space_after = Pt(3)
            pf.left_indent = Cm(1.25)
            pf.first_line_indent = Cm(-0.5)
            prefix = f"{idx}.\t" if numbered else "\u2022\t"
            _set_run_font(p.add_run(prefix + str(item)), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"])

    def add_figure(self, image_path, caption, width_cm=None, max_height_cm=None):
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Figure image not found: {image_path}")
        self.fig_no += 1
        num = self.prof["numbering"]
        prefix = num.get("figure_prefix", "Gambar")
        sep = num.get("caption_sep", " ")
        code = f"{self.chapter}.{self.fig_no}" if (num.get("chapter_scoped_captions", True) and self.chapter > 0) else str(self.fig_no)
        usable_w = self._usable_width_cm()
        req_w = min(width_cm or (usable_w - 0.5), usable_w)
        # Auto-cap height using real image aspect ratio so caption NEVER splits onto next page
        cap_h = max_height_cm or max(6.0, round(self._usable_height_cm() - 4.2, 2))
        with PILImage.open(image_path) as im:
            iw, ih = im.size
        if iw > 0 and ih > 0:
            est_h = req_w * (ih / float(iw))
            if est_h > cap_h:
                req_w = round(cap_h * (iw / float(ih)), 2)

        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(image_path, width=Cm(req_w))

        cap_text = f"{prefix} {code}{sep}{caption}"
        cp = self.doc.add_paragraph(style="CaptionGambar")
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.paragraph_format.first_line_indent = Cm(0)
        cp.paragraph_format.space_after = Pt(10)
        _set_run_font(cp.add_run(cap_text), self.prof["fonts"]["caption"], self.prof["sizes_pt"]["caption"], bold=True)
        # Locale-independent TC field for auto-populated Daftar Gambar (TOC \f g)
        safe_tc = cap_text.replace('"', "'")
        _add_field(cp, f'TC "{safe_tc}" \\f g \\l 1', font_name=self.prof["fonts"]["caption"], size_pt=self.prof["sizes_pt"]["caption"])

    def add_table(self, headers, rows, caption, widths_cm=None):
        self.tbl_no += 1
        num = self.prof["numbering"]
        tbl_cfg = self.prof["table"]
        prefix = num.get("table_prefix", "Tabel")
        sep = num.get("caption_sep", " ")
        cap_align = ALIGN_MAP.get(num.get("caption_align", "left"), WD_ALIGN_PARAGRAPH.LEFT)
        code = f"{self.chapter}.{self.tbl_no}" if (num.get("chapter_scoped_captions", True) and self.chapter > 0) else str(self.tbl_no)

        # Caption above table with keep_with_next & locale-independent TC field for Daftar Tabel (TOC \f t)
        cap_text = f"{prefix} {code}{sep}{caption}"
        cp = self.doc.add_paragraph(style="CaptionTabel")
        cp.alignment = cap_align
        cp.paragraph_format.first_line_indent = Cm(0)
        cp.paragraph_format.space_before = Pt(10)
        cp.paragraph_format.space_after = Pt(4)
        cp.paragraph_format.keep_with_next = True
        _set_run_font(cp.add_run(cap_text), self.prof["fonts"]["caption"], self.prof["sizes_pt"]["caption"], bold=True)
        safe_tc = cap_text.replace('"', "'")
        _add_field(cp, f'TC "{safe_tc}" \\f t \\l 1', font_name=self.prof["fonts"]["caption"], size_pt=self.prof["sizes_pt"]["caption"])

        ncols = len(headers)
        table = self.doc.add_table(rows=1 + len(rows), cols=ncols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        table._tbl.tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))
        _apply_table_borders(table, style=tbl_cfg.get("style", "grid"), color=tbl_cfg.get("border_color", "1F2937"))

        usable = self._usable_width_cm()
        if not widths_cm or len(widths_cm) != ncols:
            widths_cm = [round(usable / ncols, 2)] * ncols
        pad = tbl_cfg.get("cell_pad_twips", {"top": 65, "bottom": 65, "left": 100, "right": 100})
        hdr_align = ALIGN_MAP.get(tbl_cfg.get("header_align", "center"), WD_ALIGN_PARAGRAPH.CENTER)

        # Header row
        hrow = table.rows[0]
        _lock_row(hrow, is_header=bool(tbl_cfg.get("repeat_header", True)), cant_split=True)
        for ci, htext in enumerate(headers):
            cell = hrow.cells[ci]
            cell.width = Cm(widths_cm[ci])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_margins(cell, pad)
            if tbl_cfg.get("header_bg"):
                _set_cell_shading(cell, tbl_cfg["header_bg"])
            p = cell.paragraphs[0]
            p.alignment = hdr_align
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.05
            _set_run_font(p.add_run(str(htext)), self.prof["fonts"]["body"], self.prof["sizes_pt"]["table"], bold=bool(tbl_cfg.get("header_bold", True)))
        if tbl_cfg.get("style") == "booktabs":
            _set_row_booktabs_header_rule(hrow, color=tbl_cfg.get("border_color", "111827"))

        # Data rows (supports plain strings OR dicts with text/colspan/rowspan/align/bold/bg)
        merged_skip = set()
        for ri, rdata in enumerate(rows):
            row = table.rows[ri + 1]
            _lock_row(row, is_header=False, cant_split=bool(tbl_cfg.get("cant_split_rows", True)))
            for ci in range(ncols):
                if (ri, ci) in merged_skip:
                    continue
                raw_cell = rdata[ci] if ci < len(rdata) else ""
                if isinstance(raw_cell, dict):
                    val = str(raw_cell.get("text", ""))
                    cspan = max(1, int(raw_cell.get("colspan", 1)))
                    rspan = max(1, int(raw_cell.get("rowspan", 1)))
                    calign = ALIGN_MAP.get(raw_cell.get("align", "left"), WD_ALIGN_PARAGRAPH.LEFT)
                    cbold = bool(raw_cell.get("bold", False))
                    cbg = raw_cell.get("bg")
                else:
                    val, cspan, rspan, calign, cbold, cbg = str(raw_cell), 1, 1, WD_ALIGN_PARAGRAPH.LEFT, False, None
                cell = row.cells[ci]
                if cspan > 1 or rspan > 1:
                    end_r = min(len(rows) - 1, ri + rspan - 1)
                    end_c = min(ncols - 1, ci + cspan - 1)
                    cell.merge(table.rows[end_r + 1].cells[end_c])
                    for mr in range(ri, end_r + 1):
                        for mc in range(ci, end_c + 1):
                            if (mr, mc) != (ri, ci):
                                merged_skip.add((mr, mc))
                cell.width = Cm(sum(widths_cm[ci : min(ncols, ci + cspan)]))
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER if rspan > 1 else WD_ALIGN_VERTICAL.TOP
                _set_cell_margins(cell, pad)
                if cbg:
                    _set_cell_shading(cell, cbg)
                p = cell.paragraphs[0]
                p.alignment = calign
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.1
                _set_run_font(p.add_run(val), self.prof["fonts"]["body"], self.prof["sizes_pt"]["table"], bold=cbold)

        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)

    def add_callout(self, title, text):
        """Monochrome left-accented academic callout box (e.g. Executive Summary, RQ, Key Finding)."""
        tbl = self.doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        _lock_row(tbl.rows[0], cant_split=True)
        tbl._tbl.tblPr.append(
            parse_xml(
                f'<w:tblBorders {nsdecls("w")}>'
                '<w:top w:val="single" w:sz="4" w:space="0" w:color="D1D5DB"/>'
                '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D1D5DB"/>'
                '<w:left w:val="single" w:sz="24" w:space="0" w:color="111827"/>'
                '<w:right w:val="single" w:sz="4" w:space="0" w:color="D1D5DB"/>'
                "</w:tblBorders>"
            )
        )
        cell = tbl.rows[0].cells[0]
        cell.width = Cm(self._usable_width_cm())
        _set_cell_shading(cell, "F9FAFB")
        _set_cell_margins(cell, {"top": 110, "bottom": 110, "left": 160, "right": 140})
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.space_after = Pt(4)
        _set_run_font(p.add_run(title), self.prof["fonts"]["heading"], self.prof["sizes_pt"]["body"], bold=True)
        p2 = cell.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p2.paragraph_format.first_line_indent = Cm(0)
        p2.paragraph_format.line_spacing = self.prof["paragraph"]["line_spacing"]
        p2.paragraph_format.space_after = Pt(0)
        _set_run_font(p2.add_run(text), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"])
        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(6)

    def add_signature_grid(self, signers, heading="LEMBAR PENGESAHAN"):
        """Aligned borderless approval/signature grid for Indonesian Skripsi & Proposal."""
        if heading:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(18)
            _set_run_font(p.add_run(heading), self.prof["fonts"]["heading"], self.prof["sizes_pt"]["h1"], bold=True)
        cols = min(2, max(1, len(signers)))
        rows_cnt = (len(signers) + cols - 1) // cols
        tbl = self.doc.add_table(rows=rows_cnt, cols=cols)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        tbl._tbl.tblPr.append(
            parse_xml(
                f'<w:tblBorders {nsdecls("w")}>'
                '<w:top w:val="none"/><w:bottom w:val="none"/><w:left w:val="none"/>'
                '<w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/>'
                "</w:tblBorders>"
            )
        )
        col_w = round(self._usable_width_cm() / cols, 2)
        for idx, s in enumerate(signers):
            r, c = idx // cols, idx % cols
            _lock_row(tbl.rows[r], cant_split=True)
            cell = tbl.rows[r].cells[c]
            cell.width = Cm(col_w)
            _set_cell_margins(cell, {"top": 80, "bottom": 140, "left": 80, "right": 80})
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.line_spacing = 1.15
            _set_run_font(p.add_run(str(s.get("role", "")) + "\n\n\n\n"), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"])
            _set_run_font(p.add_run(str(s.get("name", ""))), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"], bold=True)
            if s.get("id"):
                _set_run_font(p.add_run("\n" + str(s["id"])), self.prof["fonts"]["body"], self.prof["sizes_pt"]["caption"])

    def add_equation(self, latex_expr, numbered=True):
        self.eq_no += 1
        eq_label = f"({self.chapter}.{self.eq_no})" if (self.chapter > 0 and numbered) else (f"({self.eq_no})" if numbered else "")
        usable = self._usable_width_cm()
        tbl = self.doc.add_table(rows=1, cols=2)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        _lock_row(tbl.rows[0], cant_split=True)
        # Borderless layout table
        tbl._tbl.tblPr.append(
            parse_xml(
                f'<w:tblBorders {nsdecls("w")}>'
                '<w:top w:val="none"/><w:bottom w:val="none"/><w:left w:val="none"/>'
                '<w:right w:val="none"/><w:insideH w:val="none"/><w:insideV w:val="none"/>'
                "</w:tblBorders>"
            )
        )
        c0, c1 = tbl.rows[0].cells[0], tbl.rows[0].cells[1]
        c0.width = Cm(usable - 2.0)
        c1.width = Cm(2.0)
        c0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p0 = c0.paragraphs[0]
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p0.paragraph_format.first_line_indent = Cm(0)
        omml = _latex_to_omml_element(latex_expr)
        if omml is not None:
            p0._p.append(omml)
        else:
            _set_run_font(p0.add_run(latex_expr), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"], italic=True)
        p1 = c1.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p1.paragraph_format.first_line_indent = Cm(0)
        _set_run_font(p1.add_run(eq_label), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"])

    def add_code_block(self, code_text):
        tbl = self.doc.add_table(rows=1, cols=1)
        tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl.autofit = False
        _apply_table_borders(tbl, style="grid", color="CBD5E1")
        cell = tbl.rows[0].cells[0]
        cell.width = Cm(self._usable_width_cm())
        _set_cell_shading(cell, "F8FAFC")
        _set_cell_margins(cell, {"top": 100, "bottom": 100, "left": 140, "right": 140})
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.first_line_indent = Cm(0)
        p.paragraph_format.line_spacing = 1.05
        p.paragraph_format.space_after = Pt(0)
        _set_run_font(p.add_run(code_text), self.prof["fonts"]["mono"], self.prof["sizes_pt"]["code"])
        sp = self.doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)

    def add_bibliography(self, bib_path, csl=None, title="DAFTAR PUSTAKA", cite_keys=None):
        entries = _render_bibliography_entries(bib_path, csl or self.prof.get("citation", {}).get("csl", "ieee.csl"), cite_keys)
        self.add_heading(title, level=1, new_chapter=True)
        for ent in entries:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            pf = p.paragraph_format
            pf.line_spacing = 1.15
            pf.space_after = Pt(6)
            pf.left_indent = Cm(1.0)
            pf.first_line_indent = Cm(-1.0)
            _set_run_font(p.add_run(ent), self.prof["fonts"]["body"], self.prof["sizes_pt"]["body"])
        return len(entries)

    def build_from_spec(self, spec, out_docx):
        if spec.get("cover"):
            self.add_cover(spec["cover"])
        if spec.get("front_matter") or spec.get("toc") or spec.get("lof") or spec.get("lot"):
            self.start_front_matter()
            for blk in spec.get("front_matter", []):
                self._render_block(blk)
            if spec.get("toc", True):
                self.add_toc_page(spec.get("toc_title", "DAFTAR ISI"), 'TOC \\o "1-3" \\h \\z \\u', page_break_before=bool(spec.get("front_matter")))
            if spec.get("lof"):
                self.add_toc_page(spec.get("lof_title", "DAFTAR GAMBAR"), 'TOC \\h \\z \\f g', page_break_before=True)
            if spec.get("lot"):
                self.add_toc_page(spec.get("lot_title", "DAFTAR TABEL"), 'TOC \\h \\z \\f t', page_break_before=True)
        self.start_main_matter()
        for blk in spec.get("body", []):
            self._render_block(blk)
        if spec.get("bibliography"):
            bib = spec["bibliography"]
            self.add_bibliography(
                bib["bib_path"],
                csl=bib.get("csl"),
                title=bib.get("title", "DAFTAR PUSTAKA"),
                cite_keys=bib.get("cite_keys"),
            )
        os.makedirs(os.path.dirname(os.path.abspath(out_docx)), exist_ok=True)
        self.doc.save(out_docx)
        return os.path.abspath(out_docx)

    def _render_block(self, blk):
        kind = blk.get("type", "paragraph")
        if kind == "chapter":
            self.add_heading(blk["text"], level=1, new_chapter=True)
        elif kind == "heading":
            self.add_heading(blk["text"], level=int(blk.get("level", 2)), new_chapter=False)
        elif kind == "paragraph":
            self.add_paragraph(blk["text"], indent=blk.get("indent", True), bold=blk.get("bold", False), italic=blk.get("italic", False), align=blk.get("align"))
        elif kind == "bullets":
            self.add_bullets(blk["items"], numbered=bool(blk.get("numbered", False)))
        elif kind == "figure":
            self.add_figure(blk["path"], blk["caption"], width_cm=blk.get("width_cm"))
        elif kind == "table":
            self.add_table(blk["headers"], blk["rows"], blk["caption"], widths_cm=blk.get("widths_cm"))
        elif kind == "equation":
            self.add_equation(blk["latex"], numbered=blk.get("numbered", True))
        elif kind == "code":
            self.add_code_block(blk["text"])
        elif kind == "callout":
            self.add_callout(blk.get("title", "Catatan"), blk.get("text", ""))
        elif kind == "signature_grid":
            self.add_signature_grid(blk.get("signers", []), heading=blk.get("heading", "LEMBAR PENGESAHAN"))
        elif kind == "page_break":
            self.doc.add_page_break()


def render_docx_template(template_docx_path, context_dict, out_docx_path, inline_images=None):
    """Fill an official institutional .docx template via docxtpl while preserving original letterhead, borders, and styles."""
    from docxtpl import DocxTemplate, InlineImage

    tpl = DocxTemplate(os.path.abspath(template_docx_path))
    ctx = dict(context_dict or {})
    for key, img_spec in (inline_images or {}).items():
        ipath = img_spec["path"] if isinstance(img_spec, dict) else str(img_spec)
        width_cm = float(img_spec.get("width_cm", 13.0)) if isinstance(img_spec, dict) else 13.0
        if os.path.exists(ipath):
            ctx[key] = InlineImage(tpl, ipath, width=Cm(width_cm))
    tpl.render(ctx)
    os.makedirs(os.path.dirname(os.path.abspath(out_docx_path)), exist_ok=True)
    tpl.save(out_docx_path)
    return os.path.abspath(out_docx_path)


def finalize_word_com_and_export_pdf(docx_path, out_pdf=None, update_fields=True):
    """Open .docx in Microsoft Word COM (or LibreOffice headless fallback), update TOC/LOF/LOT & fields, and export PDF."""
    import shutil

    src = os.path.abspath(docx_path)
    dst = os.path.abspath(out_pdf or os.path.splitext(src)[0] + ".pdf")
    os.makedirs(os.path.dirname(dst), exist_ok=True)

    try:
        import win32com.client
    except ImportError:
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            raise RuntimeError("Neither Microsoft Word COM (pywin32) nor LibreOffice (soffice) is available")
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", os.path.dirname(dst), src], check=True, timeout=120)
        return {"docx_path": src, "pdf_path": dst, "engine": "libreoffice", "pdf_bytes": os.path.getsize(dst)}

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(src, ReadOnly=False, AddToRecentFiles=False)
        try:
            if update_fields:
                doc.Repaginate()
                for i in range(1, doc.TablesOfContents.Count + 1):
                    doc.TablesOfContents(i).Update()
                for i in range(1, doc.TablesOfFigures.Count + 1):
                    doc.TablesOfFigures(i).Update()
                doc.Fields.Update()
                for sec in doc.Sections:
                    for hf in (sec.Headers, sec.Footers):
                        for idx in (1, 2, 3):
                            try:
                                hf(idx).Range.Fields.Update()
                            except Exception:
                                pass
                doc.Repaginate()
                doc.Save()
            # ExportAsFixedFormat: CreateBookmarks=1 (wdExportCreateHeadingBookmarks)
            doc.ExportAsFixedFormat(
                OutputFileName=dst,
                ExportFormat=17,
                OpenAfterExport=False,
                OptimizeFor=0,
                CreateBookmarks=1,
                DocStructureTags=True,
                BitmapMissingFonts=True,
                UseISO19005_1=False,
            )
            pages = doc.ComputeStatistics(2)
            words = doc.ComputeStatistics(0)
        finally:
            doc.Close(False)
    finally:
        word.Quit()

    if not os.path.exists(dst) or not open(dst, "rb").read(5).startswith(b"%PDF-"):
        raise RuntimeError(f"Word COM failed to create valid PDF at {dst}")
    return {"docx_path": src, "pdf_path": dst, "pages": pages, "words": words, "pdf_bytes": os.path.getsize(dst)}
