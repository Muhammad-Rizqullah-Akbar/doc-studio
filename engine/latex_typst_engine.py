"""Q1 Journal LaTeX (TinyTeX) & Modern Typst Compilation Engine with log diagnostics."""
import os
import re
import subprocess

from paths import build_env, resolve_binaries


def compile_latex(tex_path, compiler="pdflatex", runs=2, bib_engine="auto"):
    """Compile .tex to .pdf via TinyTeX with automatic BibTeX/Biber resolution and log QA."""
    bins = resolve_binaries()
    tex_abs = os.path.abspath(tex_path)
    cwd = os.path.dirname(tex_abs)
    stem = os.path.splitext(os.path.basename(tex_abs))[0]
    env = build_env()

    comp_bin = bins.get(compiler) or bins.get("pdflatex") or bins.get("xelatex")
    if not comp_bin:
        raise RuntimeError(f"LaTeX compiler '{compiler}' not found in TinyTeX or PATH")

    tex_src = open(tex_abs, encoding="utf-8", errors="replace").read()
    use_biber = (bib_engine == "biber") or (bib_engine == "auto" and ("biblatex" in tex_src or "\\addbibresource" in tex_src))
    use_bibtex = (bib_engine == "bibtex") or (bib_engine == "auto" and not use_biber and "\\bibliography{" in tex_src)

    def _run_cmd(cmd):
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, env=env)

    base_cmd = [comp_bin, "-interaction=nonstopmode", "-halt-on-error", os.path.basename(tex_abs)]
    p = _run_cmd(base_cmd)
    if p.returncode != 0:
        return {"ok": False, "stage": "pass1", "rc": p.returncode, "tail": (p.stdout + "\n" + p.stderr)[-2000:]}

    if use_biber and bins.get("biber"):
        _run_cmd([bins["biber"], stem])
        runs = max(runs, 3)
    elif use_bibtex and bins.get("bibtex"):
        _run_cmd([bins["bibtex"], stem])
        runs = max(runs, 3)

    for i in range(2, runs + 1):
        p = _run_cmd(base_cmd)
        if p.returncode != 0:
            return {"ok": False, "stage": f"pass{i}", "rc": p.returncode, "tail": (p.stdout + "\n" + p.stderr)[-2000:]}

    pdf_path = os.path.join(cwd, stem + ".pdf")
    log_path = os.path.join(cwd, stem + ".log")
    overfull = []
    undef_refs = []
    if os.path.exists(log_path):
        log_txt = open(log_path, encoding="utf-8", errors="replace").read()
        overfull = re.findall(r"Overfull \\hbox .*", log_txt)
        undef_refs = re.findall(r"LaTeX Warning: (?:Reference|Citation) .* undefined.*", log_txt)

    return {
        "ok": os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0,
        "pdf_path": pdf_path,
        "pdf_bytes": os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
        "compiler": compiler,
        "overfull_hbox_count": len(overfull),
        "overfull_samples": overfull[:10],
        "undefined_ref_count": len(undef_refs),
        "undefined_refs": undef_refs[:10],
    }


def compile_typst(typ_path, out_pdf=None):
    """Compile .typ to .pdf via Typst CLI."""
    bins = resolve_binaries()
    typst = bins.get("typst")
    if not typst:
        raise RuntimeError("typst binary not found")
    src = os.path.abspath(typ_path)
    dst = os.path.abspath(out_pdf or os.path.splitext(src)[0] + ".pdf")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    p = subprocess.run([typst, "compile", src, dst], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90, env=build_env())
    return {
        "ok": p.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0,
        "pdf_path": dst,
        "pdf_bytes": os.path.getsize(dst) if os.path.exists(dst) else 0,
        "rc": p.returncode,
        "stderr": p.stderr.strip()[-1000:],
    }


def scaffold_template(template_key, out_dir, filename=None):
    """Copy a ready-to-compile Q1 LaTeX or Typst template into out_dir."""
    bins = resolve_binaries()
    mapping = {
        "ieee-q1": "ieee_q1.tex",
        "elsevier-q1": "elsevier_q1.tex",
        "springer-lncs": "springer_lncs.tex",
        "tech-report-modern": "report_modern.typ",
    }
    fname = mapping.get(template_key, template_key)
    src = os.path.join(bins["templates_dir"], fname)
    if not os.path.exists(src):
        raise FileNotFoundError(f"Template not found: {src}")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(os.path.abspath(out_dir), filename or fname)
    with open(src, encoding="utf-8") as rf, open(dst, "w", encoding="utf-8") as wf:
        wf.write(rf.read())
    return dst
