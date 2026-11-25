"""doc-studio MCP Server: Precision Documents, Q1 Papers, Zero-Overlap Draw.io Diagrams, Vector Figures, Visual PDF QA, and Living Project Sync."""
import json
import os
import sys

# Ensure sibling engine/ directory is importable
ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from mcp.server.fastmcp import FastMCP

from citation_engine import search_scholarly_papers as _search_papers
from citation_engine import verify_bib_citations as _verify_bib
from docx_engine import PrecisionDocBuilder, finalize_word_com_and_export_pdf, render_docx_template as _render_tpl
from drawio_engine import generate_drawio, render_drawio, validate_drawio
from latex_typst_engine import compile_latex, compile_typst, scaffold_template
from paths import resolve_binaries
from pdf_qa_engine import inspect_pdf
from project_sync_engine import sync_project_docs_manifest
from prose_qa_engine import audit_prose_and_hygiene as _audit_prose
from prose_qa_engine import sanitize_unicode_and_hygiene as _sanitize_unicode
from q1_figure_engine import build_q1_figure

mcp = FastMCP("doc-studio")


@mcp.tool()
def list_style_profiles() -> str:
    """List all available document/diagram style profiles and verify installed toolchain binaries."""
    bins = resolve_binaries()
    with open(bins["style_profiles"], encoding="utf-8") as f:
        cfg = json.load(f)
    summary = {
        "document_profiles": {k: {"name": v["name"], "engine": v["engine"]} for k, v in cfg["profiles"].items()},
        "diagram_styles": list(cfg["diagram_styles"].keys()),
        "binaries": {
            k: bool(v and os.path.exists(v))
            for k, v in bins.items()
            if k in ("drawio", "pandoc", "xelatex", "pdflatex", "latexmk", "biber", "typst", "vale", "harper", "chktex", "node", "elk_script", "repomix", "drawio_mcp")
        },
        "csl_styles": sorted(os.listdir(bins["csl_dir"])) if os.path.isdir(bins["csl_dir"]) else [],
    }
    return json.dumps(summary, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_drawio_diagram(
    spec_json: str,
    out_drawio_path: str,
    style_profile: str = "rpl-v17",
    render_formats: str = "png,svg",
    render_scale: int = 2,
) -> str:
    """Generate a zero-overlap editable .drawio diagram using ELK orthogonal routing (or deterministic SD/Swimlane solver), validate geometry, and render PNG/SVG/PDF.

    Args:
        spec_json: JSON string with keys: type (flowchart|architecture|dfd|erd|cd|sd|ufd|swimlane|state), title, direction (DOWN|RIGHT), nodes/edges OR participants/messages/fragments (for sd) OR lanes/nodes/edges (for swimlane/ufd).
        out_drawio_path: Destination .drawio file path.
        style_profile: Diagram style profile (rpl-v17, ieee-q1, clean-academic, modern-tech).
        render_formats: Comma-separated export formats (png, svg, pdf). Empty string skips rendering.
        render_scale: PNG export scale factor (2 or 3 for crisp retina/print DPI).
    """
    spec = json.loads(spec_json)
    gen = generate_drawio(spec, out_drawio_path, style_profile=style_profile)
    qa = validate_drawio(gen["drawio_path"])
    fmts = [x.strip() for x in render_formats.split(",") if x.strip()]
    rendered = render_drawio(gen["drawio_path"], formats=fmts, scale=render_scale) if fmts else {}
    return json.dumps({"generated": gen, "validation": qa, "rendered": rendered}, indent=2, ensure_ascii=False)


@mcp.tool()
def validate_and_render_drawio(
    drawio_path: str,
    out_dir: str = "",
    render_formats: str = "png,svg",
    render_scale: int = 2,
) -> str:
    """Validate any existing .drawio file for zero node/edge overlap and render to high-DPI PNG, SVG, or vector PDF."""
    qa = validate_drawio(drawio_path)
    fmts = [x.strip() for x in render_formats.split(",") if x.strip()]
    rendered = render_drawio(drawio_path, out_dir=out_dir or None, formats=fmts, scale=render_scale) if fmts else {}
    return json.dumps({"validation": qa, "rendered": rendered}, indent=2, ensure_ascii=False)


@mcp.tool()
def build_word_document(
    spec_json: str,
    out_docx_path: str,
    profile_name: str = "rpl-v17",
    profile_overrides_json: str = "",
    export_pdf: bool = True,
    out_pdf_path: str = "",
) -> str:
    """Build a precision formatted .docx (exact margins, fonts, spacing, Roman/Arabic page numbering, repeating table headers, OMML math, CSL bibliography) and finalize via Word COM (auto-updating TOC/LOF/LOT fields before exporting PDF).

    Args:
        spec_json: JSON document specification with cover, front_matter, toc/lof/lot flags, body blocks (chapter, heading, paragraph, bullets, figure, table, equation, code, page_break), and optional bibliography ({bib_path, csl, title}).
        out_docx_path: Output .docx path.
        profile_name: House style profile (rpl-v17, skripsi-unhas, tech-report-modern).
        profile_overrides_json: Optional JSON dict overriding margins, fonts, sizes, spacing, or numbering for custom campus/institution formats.
        export_pdf: When true, runs Microsoft Word COM to update all TOC/page fields and export PDF with heading bookmarks.
        out_pdf_path: Optional explicit PDF output path.
    """
    spec = json.loads(spec_json)
    overrides = json.loads(profile_overrides_json) if profile_overrides_json.strip() else None
    builder = PrecisionDocBuilder(profile_name=profile_name, overrides=overrides)
    docx_abs = builder.build_from_spec(spec, out_docx_path)
    result = {"docx_path": docx_abs, "profile": profile_name}
    if export_pdf:
        result["word_com"] = finalize_word_com_and_export_pdf(docx_abs, out_pdf=out_pdf_path or None, update_fields=True)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def build_latex_or_typst_pdf(
    source_path: str = "",
    engine: str = "pdflatex",
    scaffold_profile: str = "",
    scaffold_out_dir: str = "",
) -> str:
    """Compile a Q1 journal LaTeX (.tex via TinyTeX + BibTeX/Biber) or Typst (.typ) document to PDF, or scaffold a ready-to-compile Q1 template.

    Args:
        source_path: Path to .tex or .typ file to compile.
        engine: pdflatex, xelatex, lualatex, or typst.
        scaffold_profile: Optional template to scaffold first (ieee-q1, elsevier-q1, springer-lncs, tech-report-modern).
        scaffold_out_dir: Directory where scaffolded template should be written.
    """
    out = {}
    if scaffold_profile and scaffold_out_dir:
        out["scaffolded_path"] = scaffold_template(scaffold_profile, scaffold_out_dir)
        if not source_path:
            source_path = out["scaffolded_path"]
    if source_path:
        if engine == "typst" or source_path.lower().endswith(".typ"):
            out["compile"] = compile_typst(source_path)
        else:
            out["compile"] = compile_latex(source_path, compiler=engine)
    return json.dumps(out, indent=2, ensure_ascii=False)


@mcp.tool()
def build_q1_figure_chart(
    spec_json: str,
    out_stem_path: str,
    formats: str = "pdf,svg,png",
    dpi: int = 600,
) -> str:
    """Generate publication-grade Q1 scientific figures (line, bar, grouped_bar, scatter, heatmap) with IEEE/Elsevier column widths, TrueType embedded fonts, and Okabe-Ito colorblind-safe palette."""
    spec = json.loads(spec_json)
    fmts = [x.strip() for x in formats.split(",") if x.strip()]
    res = build_q1_figure(spec, out_stem_path, formats=fmts, dpi=dpi)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def qa_inspect_pdf(
    pdf_path: str,
    profile_name: str = "rpl-v17",
    render_dir: str = "",
    render_dpi: int = 150,
    max_render_pages: int = 12,
) -> str:
    """Run structural, typographic, margin, font, image DPI, orphan-heading, and visual PNG render QA on a PDF."""
    res = inspect_pdf(
        pdf_path,
        profile_name=profile_name or None,
        render_dir=render_dir or None,
        render_dpi=render_dpi,
        max_render_pages=max_render_pages,
    )
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def sync_project_docs_manifest(project_dir: str, out_manifest_path: str = "") -> str:
    """Scan a codebase to extract deterministic ERD models (Prisma), HTTP API routes (NestJS/FastAPI/Express), and module layout, plus compute doc-drift diff against a prior manifest snapshot."""
    res = sync_project_docs_manifest(project_dir, out_manifest_path=out_manifest_path or None)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def audit_prose_and_hygiene(
    file_path: str,
    lang: str = "auto",
    reference_files_csv: str = "",
    clean_unicode_in_place: bool = False,
    strip_em_dash: bool = False,
) -> str:
    """Run 100% offline prose QA: invisible Unicode hygiene, Vale AI-slop/style lint, Harper Rust grammar lint, ChkTeX LaTeX lint, sentence rhythm/burstiness, and local 5-gram reference overlap check."""
    refs = [x.strip() for x in reference_files_csv.split(",") if x.strip()]
    out = {}
    if clean_unicode_in_place:
        out["sanitized"] = _sanitize_unicode(file_path, strip_em_dash=strip_em_dash, in_place=True)
    out["audit"] = _audit_prose(file_path, lang=lang, reference_files=refs, run_linters=True)
    return json.dumps(out, indent=2, ensure_ascii=False)


@mcp.tool()
def verify_bib_citations(bib_path: str, max_entries: int = 40) -> str:
    """Verify every BibTeX entry (including Mendeley .bib exports) against Crossref & OpenAlex (100% free, zero API key) to catch hallucinated DOIs, title/year mismatches, and retracted papers."""
    res = _verify_bib(bib_path, max_entries=max_entries)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def search_scholarly_papers(
    query: str,
    limit: int = 5,
    source: str = "openalex",
    append_to_bib: str = "",
) -> str:
    """Search real scholarly papers via OpenAlex (270M+ works) or arXiv (100% free, zero signup) and emit ready-to-use verified BibTeX entries."""
    res = _search_papers(query, limit=limit, source=source, append_to_bib=append_to_bib)
    return json.dumps(res, indent=2, ensure_ascii=False)


@mcp.tool()
def render_docx_template(
    template_docx_path: str,
    context_json: str,
    out_docx_path: str,
    inline_images_json: str = "",
    export_pdf: bool = True,
) -> str:
    """Fill an official institutional/campus .docx template via docxtpl (preserving letterhead/frames) and optionally finalize via Word COM to PDF."""
    ctx = json.loads(context_json)
    imgs = json.loads(inline_images_json) if inline_images_json.strip() else None
    docx_abs = _render_tpl(template_docx_path, ctx, out_docx_path, inline_images=imgs)
    out = {"docx_path": docx_abs}
    if export_pdf:
        out["word_com"] = finalize_word_com_and_export_pdf(docx_abs, update_fields=True)
    return json.dumps(out, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
