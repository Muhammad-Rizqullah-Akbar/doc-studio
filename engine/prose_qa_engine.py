"""100% Free, Offline Prose Hygiene, Vale, Harper, ChkTeX, Burstiness & Local N-Gram Self-Overlap Auditor."""
import json
import math
import os
import re
import subprocess
import tempfile

from paths import build_env, resolve_binaries

INVISIBLE_CHARS = {
    "\u200b": "ZERO_WIDTH_SPACE",
    "\u200c": "ZERO_WIDTH_NON_JOINER",
    "\u200d": "ZERO_WIDTH_JOINER",
    "\ufeff": "BOM_ZERO_WIDTH_NBSP",
    "\u00ad": "SOFT_HYPHEN",
    "\u2060": "WORD_JOINER",
}

AI_CLICHES_EN = [
    r"\bdelve(?:s|d|ing)?\b",
    r"\bpivotal\b",
    r"\bserves as a testament\b",
    r"\bstands as a testament\b",
    r"\bunderscore(?:s|d|ing)?\s+(?:its|the)\s+(?:importance|significance)\b",
    r"\bevolving landscape\b",
    r"\bcomprehensive landscape\b",
    r"\btapestry\b",
    r"\bindelible mark\b",
    r"\bit is (?:worth noting|important to note) that\b",
    r"\bin today'?s fast-paced\b",
    r"\bleverage(?:s|d|ing)?\s+cutting-edge\b",
    r"\bseamlessly\b",
    r"\bgame[- ]changer\b",
]

AI_CLICHES_ID = [
    r"\bdalam era digital yang terus berkembang\b",
    r"\bmemainkan peran (?:yang )?(?:sangat )?(?:krusial|vital|penting)\b",
    r"\bsebagai bukti nyata\b",
    r"\blanskap yang terus berubah\b",
    r"\bpenting untuk dicatat bahwa\b",
    r"\bpatut dicatat bahwa\b",
    r"\bsecara mulus\b",
    r"\bsecara komprehensif dan holistik\b",
    r"\bmenjadi tonggak penting\b",
]


def _extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                parts.append(" ".join(c.text.strip() for c in row.cells if c.text.strip()))
        return "\n\n".join(parts)
    if ext == ".pdf":
        import pymupdf
        doc = pymupdf.open(path)
        txt = "\n\n".join(p.get_text("text") for p in doc)
        doc.close()
        return txt
    return open(path, encoding="utf-8", errors="replace").read()


def sanitize_unicode_and_hygiene(file_path, strip_em_dash=False, in_place=False):
    """Detect and optionally clean invisible zero-width Unicode chars and stray formatting characters."""
    p_abs = os.path.abspath(file_path)
    ext = os.path.splitext(p_abs)[1].lower()
    found = {}

    if ext == ".docx":
        import docx
        d = docx.Document(p_abs)
        changes = 0
        for par in d.paragraphs:
            for run in par.runs:
                t = run.text
                if not t:
                    continue
                new_t = t
                for ch, name in INVISIBLE_CHARS.items():
                    cnt = new_t.count(ch)
                    if cnt:
                        found[name] = found.get(name, 0) + cnt
                        new_t = new_t.replace(ch, "")
                if strip_em_dash and "\u2014" in new_t:
                    found["EM_DASH"] = found.get("EM_DASH", 0) + new_t.count("\u2014")
                    new_t = new_t.replace(" \u2014 ", " - ").replace("\u2014", " - ")
                if new_t != t:
                    changes += 1
                    if in_place:
                        run.text = new_t
        if in_place and changes:
            d.save(p_abs)
        return {"file": p_abs, "in_place": in_place, "modified_runs": changes, "found": found}

    raw = open(p_abs, encoding="utf-8", errors="replace").read()
    cleaned = raw
    for ch, name in INVISIBLE_CHARS.items():
        cnt = cleaned.count(ch)
        if cnt:
            found[name] = cnt
            cleaned = cleaned.replace(ch, "")
    if strip_em_dash and "\u2014" in cleaned:
        found["EM_DASH"] = cleaned.count("\u2014")
        cleaned = cleaned.replace(" \u2014 ", " - ").replace("\u2014", " - ")
    if in_place and cleaned != raw:
        with open(p_abs, "w", encoding="utf-8") as wf:
            wf.write(cleaned)
    return {"file": p_abs, "in_place": in_place, "changed": cleaned != raw, "found": found}


def _ngrams(text, k=5):
    words = re.findall(r"[a-z0-9]+", text.lower())
    if len(words) < k:
        return set(), words
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}, words


def _compute_local_overlap(draft_text, reference_files, k=5):
    if not reference_files:
        return []
    draft_ng, _ = _ngrams(draft_text, k=k)
    if not draft_ng:
        return []
    reports = []
    for rf in reference_files:
        if not os.path.exists(rf):
            continue
        ref_txt = _extract_text(rf)
        ref_ng, _ = _ngrams(ref_txt, k=k)
        shared = draft_ng & ref_ng
        pct = round(100.0 * len(shared) / max(1, len(draft_ng)), 2)
        reports.append({
            "reference": os.path.basename(rf),
            "shared_5grams": len(shared),
            "overlap_pct": pct,
            "sample_matches": sorted(shared)[:8],
        })
    return reports


def _detect_lang(text):
    low = text.lower()
    id_markers = (" yang ", " dan ", " untuk ", " dengan ", " pada ", " dari ", " sistem ", " adalah ", " dalam ")
    en_markers = (" the ", " and ", " for ", " with ", " that ", " from ", " system ", " this ", " which ")
    id_score = sum(low.count(m) for m in id_markers)
    en_score = sum(low.count(m) for m in en_markers)
    return "id" if id_score >= en_score else "en"


def _run_vale(target_path, lang="id"):
    bins = resolve_binaries()
    vale = os.path.join(bins["plugin_root"], "bin", "vale.exe")
    vale_dir = os.path.join(bins["plugin_root"], "vale")
    ini_name = ".vale.id.ini" if lang == "id" else ".vale.en.ini"
    ini = os.path.join(vale_dir, ini_name)
    if not os.path.exists(ini):
        ini = os.path.join(vale_dir, ".vale.ini")
    if not (os.path.exists(vale) and os.path.exists(ini)):
        return {"available": False, "issues": []}
    p = subprocess.run(
        [vale, "--config", ini, "--output=JSON", os.path.abspath(target_path)],
        cwd=vale_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=build_env(),
    )
    try:
        data = json.loads(p.stdout or "{}")
    except Exception:
        return {"available": True, "lang_config": ini_name, "issues": [], "raw_err": p.stderr[:300]}
    flat = []
    for fpath, items in data.items():
        for it in items:
            flat.append({
                "line": it.get("Line"),
                "severity": it.get("Severity"),
                "check": it.get("Check"),
                "message": it.get("Message"),
                "match": it.get("Match"),
            })
    return {"available": True, "lang_config": ini_name, "count": len(flat), "issues": flat[:30]}


def _run_harper(target_path):
    bins = resolve_binaries()
    harper = os.path.join(bins["plugin_root"], "bin", "harper-cli.exe")
    if not os.path.exists(harper):
        return {"available": False, "issues": []}
    p = subprocess.run(
        [harper, "lint", target_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=build_env(),
    )
    lines = [ln.strip() for ln in (p.stdout + "\n" + p.stderr).splitlines() if ln.strip()]
    return {"available": True, "rc": p.returncode, "output_lines": lines[:25]}


def _run_chktex(tex_path):
    bins = resolve_binaries()
    if not bins.get("tex_bin"):
        return {"available": False, "warnings": []}
    chk = os.path.join(bins["tex_bin"], "chktex.exe")
    if not os.path.exists(chk):
        return {"available": False, "warnings": []}
    p = subprocess.run(
        [chk, "-q", "-n1", "-n8", "-n24", "-n36", tex_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        env=build_env(),
    )
    warns = [ln.strip() for ln in p.stdout.splitlines() if ln.strip()]
    return {"available": True, "count": len(warns), "warnings": warns[:25]}


def audit_prose_and_hygiene(file_path, lang="auto", reference_files=None, run_linters=True):
    """Comprehensive 100% local prose audit: Unicode hygiene, AI-cliches, burstiness, Vale, Harper, ChkTeX, and local n-gram overlap."""
    p_abs = os.path.abspath(file_path)
    text = _extract_text(p_abs)
    ext = os.path.splitext(p_abs)[1].lower()

    # 1. Invisible Unicode hygiene
    hygiene = sanitize_unicode_and_hygiene(p_abs, strip_em_dash=False, in_place=False)

    # 2. Sentence rhythm / burstiness
    clean_prose = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", text) if ext == ".tex" else text
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_prose) if len(s.strip().split()) >= 4]
    lengths = [len(s.split()) for s in sents]
    avg_len = round(sum(lengths) / max(1, len(lengths)), 1)
    var = sum((x - avg_len) ** 2 for x in lengths) / max(1, len(lengths))
    std_len = round(math.sqrt(var), 1)
    burstiness = round(std_len / max(1.0, avg_len), 2)
    long_sents = [s[:120] for s in sents if len(s.split()) > 42]

    # 3. AI-cliche scanner (EN + ID)
    cliches = []
    for pat in AI_CLICHES_EN + AI_CLICHES_ID:
        for m in re.finditer(pat, clean_prose, re.I):
            cliches.append(m.group(0))

    # 4. External local linters (Vale [official write-good/proselint/Google + KBBI/Hunspell id_ID] + Harper + ChkTeX)
    eff_lang = _detect_lang(clean_prose) if lang == "auto" else lang
    vale_res = {"available": False}
    harper_res = {"available": False}
    chktex_res = {"available": False}
    if run_linters:
        if ext in (".md", ".txt", ".tex"):
            vale_res = _run_vale(p_abs, lang=eff_lang)
            if ext in (".md", ".txt") and eff_lang == "en":
                harper_res = _run_harper(p_abs)
            if ext == ".tex":
                chktex_res = _run_chktex(p_abs)
        else:
            with tempfile.TemporaryDirectory() as td:
                tmp_md = os.path.join(td, "extracted.md")
                with open(tmp_md, "w", encoding="utf-8") as wf:
                    wf.write(text)
                vale_res = _run_vale(tmp_md, lang=eff_lang)
                if eff_lang == "en":
                    harper_res = _run_harper(tmp_md)

    # 5. Local reference overlap (Winnowing 5-gram check)
    overlap = _compute_local_overlap(clean_prose, reference_files or [], k=5)

    return {
        "file": p_abs,
        "word_count": len(clean_prose.split()),
        "sentence_count": len(sents),
        "rhythm": {
            "avg_sentence_words": avg_len,
            "std_dev_words": std_len,
            "burstiness_ratio": burstiness,
            "rhythm_verdict": "monotone_risk" if (len(sents) >= 8 and burstiness < 0.25) else "healthy_variation",
            "overlong_sentences_gt42w": len(long_sents),
        },
        "unicode_hygiene": hygiene["found"],
        "ai_cliches_found": sorted(set(c.lower() for c in cliches)),
        "vale": vale_res,
        "harper": harper_res,
        "chktex": chktex_res,
        "local_source_overlap": overlap,
    }
