"""100% Free, Zero-Signup Citation & Literature Engine (Mendeley .bib + Crossref + OpenAlex + arXiv)."""
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

UA = "doc-studio-citation-verifier/1.0 (mailto:opensource@example.org)"


def _http_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def parse_bib_file(bib_path):
    """Parse a BibTeX (.bib) file (including Mendeley Reference Manager exports) into structured entries."""
    txt = open(bib_path, encoding="utf-8", errors="replace").read()
    entries = []
    # Match @type{key, ... }
    pattern = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.S)
    matches = list(pattern.finditer(txt))
    for i, m in enumerate(matches):
        etype = m.group(1).lower()
        key = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
        body = txt[start:end]
        # Trim trailing closing brace
        last_b = body.rfind("}")
        if last_b != -1:
            body = body[:last_b]
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\"|(\d+))", body, re.S):
            fk = fm.group(1).lower()
            fv = (fm.group(2) if fm.group(2) is not None else (fm.group(3) if fm.group(3) is not None else fm.group(4))) or ""
            fields[fk] = re.sub(r"\s+", " ", fv.replace("{", "").replace("}", "")).strip()
        entries.append({"type": etype, "key": key, "fields": fields})
    return entries


def _check_crossref_doi(doi):
    clean = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(doi).strip(), flags=re.I)
    url = f"https://api.crossref.org/works/{urllib.parse.quote(clean, safe='')}"
    data = _http_json(url)
    msg = data.get("message", {})
    title = (msg.get("title") or [""])[0]
    authors = [f"{a.get('family', '')}".strip() for a in msg.get("author", []) if a.get("family")]
    year = None
    for dk in ("published-print", "published-online", "issued", "created"):
        dp = msg.get(dk, {}).get("date-parts", [[]])
        if dp and dp[0]:
            year = str(dp[0][0])
            break
    retracted = False
    for upd in msg.get("update-to", []) + msg.get("updated-by", []):
        if "retract" in str(upd.get("type", "")).lower() or "retract" in str(upd.get("label", "")).lower():
            retracted = True
    return {
        "source": "crossref",
        "doi": msg.get("DOI", clean),
        "title": title,
        "authors": authors[:6],
        "year": year,
        "venue": (msg.get("container-title") or [""])[0],
        "retracted": retracted,
    }


def _search_openalex_title(title):
    q = urllib.parse.quote(title[:160])
    url = f"https://api.openalex.org/works?search={q}&per-page=3&select=id,doi,title,publication_year,is_retracted,authorships,primary_location"
    data = _http_json(url)
    best = None
    best_sim = 0.0
    nt = _norm(title)
    for w in data.get("results", []):
        wt = w.get("title") or ""
        sim = SequenceMatcher(None, nt, _norm(wt)).ratio()
        if sim > best_sim:
            best_sim = sim
            authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:6]]
            venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
            best = {
                "source": "openalex",
                "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
                "title": wt,
                "authors": authors,
                "year": str(w.get("publication_year") or ""),
                "venue": venue,
                "retracted": bool(w.get("is_retracted", False)),
                "title_similarity": round(sim, 3),
            }
    return best


def verify_bib_citations(bib_path, max_entries=40):
    """Verify every BibTeX entry against Crossref & OpenAlex (100% free, zero API key)."""
    entries = parse_bib_file(bib_path)
    results = []
    counts = {"verified": 0, "mismatch": 0, "unverified": 0, "retracted": 0}
    for ent in entries[:max_entries]:
        f = ent["fields"]
        title = f.get("title", "")
        doi = f.get("doi", "")
        year = f.get("year", "")
        rec = {"key": ent["key"], "title": title, "year": year, "doi": doi, "status": "unverified", "issues": []}
        remote = None
        try:
            if doi:
                remote = _check_crossref_doi(doi)
            elif title:
                remote = _search_openalex_title(title)
        except Exception as e:
            if title:
                try:
                    remote = _search_openalex_title(title)
                except Exception as e2:
                    rec["issues"].append(f"lookup_error: {e2}")
            else:
                rec["issues"].append(f"lookup_error: {e}")

        if remote:
            sim = SequenceMatcher(None, _norm(title), _norm(remote.get("title", ""))).ratio() if title else 1.0
            rec["matched"] = remote
            rec["title_similarity"] = round(sim, 3)
            if remote.get("retracted"):
                rec["status"] = "retracted"
                rec["issues"].append("PAPER IS RETRACTED")
            elif sim < 0.72:
                rec["status"] = "mismatch"
                rec["issues"].append(f"Title mismatch (sim={round(sim, 2)}): remote='{remote.get('title')}'")
            else:
                if year and remote.get("year") and str(year) != str(remote["year"]):
                    rec["issues"].append(f"Year differs: local={year}, remote={remote['year']}")
                rec["status"] = "mismatch" if rec["issues"] else "verified"
        counts[rec["status"]] += 1
        results.append(rec)

    return {
        "bib_path": os.path.abspath(bib_path),
        "total_entries": len(entries),
        "checked": len(results),
        "summary": counts,
        "pass": counts["retracted"] == 0 and counts["unverified"] == 0 and counts["mismatch"] == 0,
        "results": results,
    }


def search_scholarly_papers(query, limit=5, source="openalex", append_to_bib=""):
    """Search real scholarly papers via OpenAlex or arXiv (100% free, zero signup) and emit valid BibTeX."""
    papers = []
    if source == "arxiv":
        q = urllib.parse.quote(query)
        url = f"https://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={int(limit)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        xml_raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace")
        root = ET.fromstring(xml_raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for ent in root.findall("a:entry", ns):
            aid = (ent.findtext("a:id", "", ns) or "").split("/abs/")[-1]
            title = re.sub(r"\s+", " ", ent.findtext("a:title", "", ns) or "").strip()
            year = (ent.findtext("a:published", "", ns) or "")[:4]
            authors = [a.findtext("a:name", "", ns) for a in ent.findall("a:author", ns)]
            first_last = re.sub(r"[^a-z]", "", (authors[0].split()[-1].lower() if authors else "arxiv"))
            key = f"{first_last}{year}_{re.sub(r'[^a-z0-9]', '', aid.lower())[:6]}"
            bib = (
                f"@article{{{key},\n"
                f"  author = {{{' and '.join(authors)}}},\n"
                f"  title = {{{title}}},\n"
                f"  journal = {{arXiv preprint arXiv:{aid}}},\n"
                f"  year = {{{year}}},\n"
                f"  url = {{https://arxiv.org/abs/{aid}}}\n"
                f"}}"
            )
            papers.append({"key": key, "title": title, "authors": authors[:5], "year": year, "venue": f"arXiv:{aid}", "doi": "", "bibtex": bib})
    else:
        q = urllib.parse.quote(query)
        url = (
            f"https://api.openalex.org/works?search={q}&per-page={int(limit)}"
            "&filter=is_retracted:false&sort=cited_by_count:desc"
            "&select=id,doi,title,publication_year,cited_by_count,authorships,primary_location,biblio"
        )
        data = _http_json(url, timeout=20)
        for w in data.get("results", []):
            title = (w.get("title") or "").strip()
            year = str(w.get("publication_year") or "")
            doi = (w.get("doi") or "").replace("https://doi.org/", "")
            authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", []) if a.get("author")]
            venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
            biblio = w.get("biblio") or {}
            first_last = re.sub(r"[^a-z]", "", (authors[0].split()[-1].lower() if authors else "paper"))
            first_word = re.sub(r"[^a-z]", "", (title.split()[0].lower() if title else "work"))
            key = f"{first_last}{year}{first_word}"
            lines = [f"@article{{{key},", f"  author = {{{' and '.join(authors)}}},", f"  title = {{{title}}},"]
            if venue:
                lines.append(f"  journal = {{{venue}}},")
            if year:
                lines.append(f"  year = {{{year}}},")
            if biblio.get("volume"):
                lines.append(f"  volume = {{{biblio['volume']}}},")
            if biblio.get("issue"):
                lines.append(f"  number = {{{biblio['issue']}}},")
            if biblio.get("first_page"):
                pg = f"{biblio['first_page']}--{biblio['last_page']}" if biblio.get("last_page") else str(biblio["first_page"])
                lines.append(f"  pages = {{{pg}}},")
            if doi:
                lines.append(f"  doi = {{{doi}}},")
            lines[-1] = lines[-1].rstrip(",")
            lines.append("}")
            papers.append({
                "key": key,
                "title": title,
                "authors": authors[:5],
                "year": year,
                "venue": venue,
                "cited_by": w.get("cited_by_count", 0),
                "doi": doi,
                "bibtex": "\n".join(lines),
            })

    if append_to_bib and papers:
        os.makedirs(os.path.dirname(os.path.abspath(append_to_bib)), exist_ok=True)
        existing = open(append_to_bib, encoding="utf-8", errors="replace").read() if os.path.exists(append_to_bib) else ""
        added = 0
        with open(append_to_bib, "a", encoding="utf-8") as wf:
            for p in papers:
                if f"{{{p['key']}," not in existing:
                    wf.write("\n" + p["bibtex"] + "\n")
                    added += 1
        return {"source": source, "count": len(papers), "appended_to_bib": append_to_bib, "added_count": added, "papers": papers}

    return {"source": source, "count": len(papers), "papers": papers}
