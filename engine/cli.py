"""Unified CLI for doc-studio: doctor, audit, verify-bib, search-papers, sync, qa, render-drawio."""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from citation_engine import search_scholarly_papers, verify_bib_citations
from drawio_engine import render_drawio, validate_drawio
from paths import resolve_binaries
from pdf_qa_engine import inspect_pdf
from project_sync_engine import sync_project_docs_manifest
from prose_qa_engine import audit_prose_and_hygiene, sanitize_unicode_and_hygiene


def cmd_doctor(_args):
    bins = resolve_binaries()
    keys = ["drawio", "pandoc", "pdflatex", "xelatex", "latexmk", "biber", "typst", "vale", "harper", "chktex", "node", "elk_script", "repomix", "drawio_mcp"]
    ok_cnt = 0
    print("=== DOC-STUDIO DOCTOR ===")
    for k in keys:
        v = bins.get(k)
        ok = bool(v and os.path.exists(v))
        ok_cnt += int(ok)
        print(f"  {k:12s} : {'OK' if ok else 'MISSING':7s}  {v or '-'}")
    csls = sorted(os.listdir(bins["csl_dir"])) if os.path.isdir(bins["csl_dir"]) else []
    print(f"  CSL styles   : {len(csls)} ({', '.join(csls)})")
    print(f"  Summary      : {ok_cnt}/{len(keys)} binaries ready")
    return 0 if ok_cnt == len(keys) else 1


def cmd_audit(args):
    if args.clean:
        san = sanitize_unicode_and_hygiene(args.file, strip_em_dash=args.strip_em_dash, in_place=True)
        print("SANITIZED:", json.dumps(san, ensure_ascii=False))
    refs = [x.strip() for x in args.refs.split(",") if x.strip()] if args.refs else []
    res = audit_prose_and_hygiene(args.file, lang=args.lang, reference_files=refs, run_linters=True)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_verify_bib(args):
    res = verify_bib_citations(args.bib, max_entries=args.max)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("pass") else 1


def cmd_search_papers(args):
    res = search_scholarly_papers(args.query, limit=args.limit, source=args.source, append_to_bib=args.append_bib)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def cmd_sync(args):
    res = sync_project_docs_manifest(args.project_dir, out_manifest_path=args.out or None)
    print(json.dumps(res["summary"], indent=2, ensure_ascii=False))
    if res.get("manifest_path"):
        print("Manifest:", res["manifest_path"])
    return 0


def cmd_qa(args):
    res = inspect_pdf(args.pdf, profile_name=args.profile or None, render_dir=args.render_dir or None)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0 if res.get("pass") else 1


def cmd_render_drawio(args):
    qa = validate_drawio(args.drawio)
    fmts = [x.strip() for x in args.formats.split(",") if x.strip()]
    rnd = render_drawio(args.drawio, out_dir=args.out_dir or None, formats=fmts, scale=args.scale)
    print(json.dumps({"validation": qa, "rendered": rnd}, indent=2, ensure_ascii=False))
    return 0 if qa.get("pass") else 1


def main():
    ap = argparse.ArgumentParser(prog="doc-studio", description="Precision Document, Thesis, Q1 Paper & Zero-Overlap Diagram CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Check all local binaries, CSLs, and engines").set_defaults(func=cmd_doctor)

    p_aud = sub.add_parser("audit", help="Run KBBI/EYD V, Vale, Harper, ChkTeX, Unicode & burstiness audit")
    p_aud.add_argument("file")
    p_aud.add_argument("--lang", default="auto", choices=["auto", "id", "en"])
    p_aud.add_argument("--refs", default="", help="Comma-separated local reference files for 5-gram overlap check")
    p_aud.add_argument("--clean", action="store_true", help="Strip invisible Unicode chars in-place")
    p_aud.add_argument("--strip-em-dash", action="store_true")
    p_aud.set_defaults(func=cmd_audit)

    p_bib = sub.add_parser("verify-bib", help="Verify BibTeX entries via Crossref & OpenAlex (zero API key)")
    p_bib.add_argument("bib")
    p_bib.add_argument("--max", type=int, default=40)
    p_bib.set_defaults(func=cmd_verify_bib)

    p_sp = sub.add_parser("search-papers", help="Search OpenAlex/arXiv and emit verified BibTeX")
    p_sp.add_argument("query")
    p_sp.add_argument("--limit", type=int, default=5)
    p_sp.add_argument("--source", default="openalex", choices=["openalex", "arxiv"])
    p_sp.add_argument("--append-bib", default="")
    p_sp.set_defaults(func=cmd_search_papers)

    p_sy = sub.add_parser("sync", help="Scan project (Prisma/SQL/OpenAPI/NestJS/FastAPI) into traceability manifest")
    p_sy.add_argument("project_dir")
    p_sy.add_argument("--out", default="")
    p_sy.set_defaults(func=cmd_sync)

    p_qa = sub.add_parser("qa", help="Run PyMuPDF visual & structural PDF QA")
    p_qa.add_argument("pdf")
    p_qa.add_argument("--profile", default="academic-proposal")
    p_qa.add_argument("--render-dir", default="")
    p_qa.set_defaults(func=cmd_qa)

    p_dr = sub.add_parser("render-drawio", help="Validate zero-overlap geometry & render .drawio")
    p_dr.add_argument("drawio")
    p_dr.add_argument("--out-dir", default="")
    p_dr.add_argument("--formats", default="png,svg")
    p_dr.add_argument("--scale", type=int, default=2)
    p_dr.set_defaults(func=cmd_render_drawio)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
