"""PyMuPDF Visual & Structural PDF QA Gate for Q1 Papers, Theses, Proposals, and Reports."""
import json
import os
import re

import pymupdf

from paths import resolve_binaries


def _load_profile(profile_name):
    if not profile_name:
        return {}
    bins = resolve_binaries()
    with open(bins["style_profiles"], encoding="utf-8") as f:
        return json.load(f).get("profiles", {}).get(profile_name, {})


def inspect_pdf(pdf_path, profile_name=None, render_dir=None, render_dpi=150, max_render_pages=12):
    """Run structural, typographic, margin, image DPI, and visual render QA on any PDF."""
    pdf_abs = os.path.abspath(pdf_path)
    if not os.path.exists(pdf_abs):
        return {"pass": False, "error": f"PDF not found: {pdf_abs}"}

    prof = _load_profile(profile_name)
    qa_cfg = prof.get("qa", {})
    margins_cm = prof.get("margins_cm")
    min_dpi = qa_cfg.get("min_image_dpi", 150)
    forbid_em = bool(qa_cfg.get("forbid_em_dash", False))
    allowed_fonts = qa_cfg.get("allowed_fonts", [])

    doc = pymupdf.open(pdf_abs)
    issues = []
    fonts_found = set()
    images_info = []
    blank_pages = []
    em_dash_pages = []
    broken_ref_pages = []
    orphan_heading_pages = []
    margin_violations = []
    rendered_pages = []

    pt_per_cm = 72.0 / 2.54
    left_lim = (margins_cm["left"] * pt_per_cm - 8.0) if margins_cm else None
    right_lim_off = (margins_cm["right"] * pt_per_cm - 8.0) if margins_cm else None

    for pno, page in enumerate(doc, 1):
        rect = page.rect
        text = page.get_text("text") or ""
        stripped = text.strip()
        page_imgs = page.get_images(full=True)

        # 1. Blank page check
        if len(stripped) < 5 and len(page_imgs) == 0:
            blank_pages.append(pno)

        # 2. Em-dash check
        if forbid_em and ("\u2014" in text):
            em_dash_pages.append(pno)

        # 3. Broken Word/LaTeX cross-reference / citation check
        if re.search(r"Error!\s*Reference source not found|\[\?\]|(?<!\?)\?\?(?!\?)|No table of contents entries found", text):
            broken_ref_pages.append(pno)

        # 4. Fonts audit
        for f in page.get_fonts(full=True):
            fname = f[3] or f[4] or "unknown"
            fonts_found.add(fname)

        # 5. Image DPI & placement audit
        for img in page_imgs:
            xref = img[0]
            iw, ih = img[2], img[3]
            rects = page.get_image_rects(xref)
            if rects:
                ir = rects[0]
                eff_dpi_x = round(iw / (ir.width / 72.0), 1) if ir.width > 1 else 0
                eff_dpi_y = round(ih / (ir.height / 72.0), 1) if ir.height > 1 else 0
                eff_dpi = min(eff_dpi_x, eff_dpi_y)
                images_info.append({"page": pno, "px": [iw, ih], "eff_dpi": eff_dpi})
                if 0 < eff_dpi < min_dpi:
                    issues.append({
                        "type": "low_image_dpi",
                        "severity": "warning",
                        "page": pno,
                        "detail": f"Effective DPI {eff_dpi} < {min_dpi}",
                    })

        # 6. Margin overflow & orphan heading check via text blocks
        blocks = page.get_text("dict").get("blocks", [])
        text_blocks = [b for b in blocks if b.get("type") == 0 and b.get("lines")]
        if left_lim is not None and right_lim_off is not None:
            right_max = rect.width - right_lim_off
            for b in text_blocks:
                bx0, by0, bx1, by1 = b["bbox"]
                # Ignore header/footer zone
                if by0 < rect.height * 0.08 or by1 > rect.height * 0.92:
                    continue
                if bx0 < left_lim - 4 or bx1 > right_max + 6:
                    margin_violations.append({"page": pno, "bbox": [round(bx0, 1), round(by0, 1), round(bx1, 1), round(by1, 1)]})
                    break

        if text_blocks:
            # Find lowest non-footer block
            body_blocks = [b for b in text_blocks if b["bbox"][3] < rect.height * 0.90]
            if body_blocks:
                last_b = max(body_blocks, key=lambda b: b["bbox"][3])
                if last_b["bbox"][1] > rect.height * 0.80:
                    spans = [s for ln in last_b["lines"] for s in ln.get("spans", [])]
                    all_bold = spans and all("bold" in (s.get("font", "").lower()) or (s.get("flags", 0) & 16) for s in spans if s.get("text", "").strip())
                    txt_last = "".join(s.get("text", "") for s in spans).strip()
                    if all_bold and 3 < len(txt_last) < 90 and not txt_last.lower().startswith(("gambar ", "tabel ", "figure ", "table ")):
                        orphan_heading_pages.append({"page": pno, "text": txt_last})

        # 7. Render PNGs for visual inspection
        if render_dir and pno <= max_render_pages:
            os.makedirs(render_dir, exist_ok=True)
            pix = page.get_pixmap(dpi=render_dpi)
            out_png = os.path.join(os.path.abspath(render_dir), f"page_{pno:03d}.png")
            pix.save(out_png)
            rendered_pages.append(out_png)

    # Aggregate structured issues
    if blank_pages:
        issues.append({"type": "blank_pages", "severity": "warning", "pages": blank_pages})
    if em_dash_pages:
        issues.append({"type": "forbidden_em_dash", "severity": "critical", "pages": em_dash_pages})
    if broken_ref_pages:
        issues.append({"type": "broken_references", "severity": "critical", "pages": broken_ref_pages})
    if orphan_heading_pages:
        issues.append({"type": "orphan_headings", "severity": "warning", "items": orphan_heading_pages[:10]})
    if margin_violations:
        issues.append({"type": "margin_overflow", "severity": "warning", "items": margin_violations[:10]})

    if allowed_fonts:
        stray = []
        for fn in sorted(fonts_found):
            clean_fn = fn.split("+")[-1]
            if not any(af.lower() in clean_fn.lower() for af in allowed_fonts):
                stray.append(fn)
        if stray:
            issues.append({"type": "stray_fonts", "severity": "warning", "fonts": stray})

    p0 = doc[0].rect if len(doc) > 0 else None
    size_cm = [round(p0.width / pt_per_cm, 2), round(p0.height / pt_per_cm, 2)] if p0 else [0, 0]
    page_count = len(doc)
    meta = dict(doc.metadata or {})
    doc.close()

    crit = sum(1 for x in issues if x.get("severity") == "critical")
    warn = sum(1 for x in issues if x.get("severity") == "warning")
    return {
        "pass": crit == 0,
        "score": max(0, 100 - crit * 25 - warn * 5),
        "pdf_path": pdf_abs,
        "pages": page_count,
        "page_size_cm": size_cm,
        "producer": meta.get("producer") or meta.get("creator") or "",
        "fonts": sorted(fonts_found),
        "image_count": len(images_info),
        "critical_count": crit,
        "warning_count": warn,
        "issues": issues,
        "rendered_pages": rendered_pages,
    }
