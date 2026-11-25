# Doc-Studio

**100% Free, Zero-Signup, Portable Precision Document, Thesis (Skripsi), Q1 Journal Paper, Zero-Overlap Draw.io Diagram, KBBI/Vale/Harper Prose QA, and Codebase-Synced Living Docs Studio (MCP Server + CLI + Agent Skills).**

Designed to run identically on any Windows, macOS, or Linux machine with **Antigravity, Claude Code, Cursor, Codex, or Hermes** — zero paid APIs, zero cloud lock-in, zero hardcoded local paths.

## Capabilities

1. **Zero-Overlap Draw.io Diagram Engine (`elkjs` + Draw.io CLI + `@drawio/mcp`)**
   - Sugiyama orthogonal routing with explicit ports & diamond vertex snapping (`flowchart`, `architecture`, `dfd`, `erd`, `cd`, `state`).
   - Exact **row-level ERD PK -> FK pointers** (including staggered 90-degree orthogonal dual-FK routing) with fail-loud field name validation.
   - **DFD semantic guard** (forbids illegal direct `external -> store` / `store -> store` flows) + clean bidirectional arrow separation.
   - Deterministic **Sequence Diagram (`sd`)** & **Swimlane (`ufd`/`swimlane`)** solvers.
   - Monochrome B&W (`monochrome-bw`), `ieee-q1`, `clean-academic`, `rpl-v17`, and `modern-tech` diagram palettes + strict geometric zero-overlap validator.

2. **Precision Document Engine (Word COM / LibreOffice + TinyTeX Q1 LaTeX + Typst)**
   - Modular style profiles (`rpl-v17`, `skripsi-unhas`, `ieee-q1`, `elsevier-q1`, `springer-lncs`, `tech-report-modern`) + arbitrary JSON overrides for any campus/institution format.
   - Word `.docx`: exact margins/fonts/spacing, dual Roman (`i, ii`) & Arabic (`1, 2`) sections, auto-height figure capping (caption never splits across pages), `colspan`/`rowspan` merged tables with `tblHeader` & `cantSplit`, monochrome callout boxes, aligned `signature_grid` (Lembar Pengesahan), OMML equations, `docxtpl` official template injection, and Word COM auto-update for **Daftar Isi, Daftar Gambar, and Daftar Tabel**.
   - Q1 LaTeX templates (`IEEEtran`, `elsarticle`, `springer-lncs`) + **Typst** modern engineering report + **Matplotlib** Q1 colorblind-safe Okabe-Ito vector figures (PDF/SVG/600 DPI PNG).
   - **PyMuPDF Visual & Structural PDF QA Gate**: checks page geometry, embedded fonts, image DPI, blank pages, margin overflow, orphan headings, broken references, and renders page PNGs for visual inspection.

3. **Authoritative Offline Prose QA & Zero-Signup Citations**
   - **Indonesian KBBI / EYD V**: 1,413 verified `tidak-baku -> baku` pairs from `lantip/baku-tidak-baku` (KBBI / Ivan Lanin) + official **LibreOffice Hunspell `id_ID`** dictionary via `Vale`.
   - **English Q1 Prose**: official `errata-ai` Vale packages (`write-good`, `proselint`, `Google`) + **Automattic `Harper` CLI** (Rust offline grammar) + **`ChkTeX`** (LaTeX typography).
   - **Unicode Hygiene, Burstiness & Local 5-Gram Reference Overlap Check** (100% offline).
   - **Free Zero-Signup Citation Engine**: reads local Mendeley `.bib` exports, verifies DOIs & retractions against **Crossref + OpenAlex**, and searches 270M+ scholarly works via **OpenAlex + arXiv**.

4. **Living Project Sync**
   - Deterministic codebase scanner (`Prisma`, `SQL DDL`, `OpenAPI/Swagger`, `NestJS`, `FastAPI`, `Express`) + `repomix` MCP integration for fast documentation updates after major refactoring.

## Quick Portable Install

### Windows (PowerShell)
```powershell
git clone https://github.com/Muhammad-Rizqullah-Akbar/doc-studio.git
cd doc-studio
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
```

### macOS / Linux
```bash
git clone https://github.com/Muhammad-Rizqullah-Akbar/doc-studio.git
cd doc-studio
bash scripts/install.sh
```

The installer automatically:
- Creates an isolated `.venv` (`uv sync` or `python -m venv`)
- Installs `elkjs`, `repomix`, and `@drawio/mcp`
- Downloads portable `Vale`, `Harper CLI`, `Typst`, 6 official CSL styles, `LibreOffice/dictionaries` `id_ID`, `lantip/baku-tidak-baku` KBBI dataset, and runs `vale sync` for `write-good`, `proselint`, and `Google`
- Generates a ready-to-use local `mcp_config.json` with your machine's exact paths

## CLI Usage
```bash
# Verify all 14 tools & styles
.venv/Scripts/python engine/cli.py doctor

# Audit Indonesian (KBBI + Hunspell id_ID) or English Q1 (write-good + proselint + Google + Harper)
.venv/Scripts/python engine/cli.py audit draft.md --lang id --clean

# Verify Mendeley/BibTeX citations against Crossref & OpenAlex (zero API key)
.venv/Scripts/python engine/cli.py verify-bib refs.bib

# Search OpenAlex/arXiv and append verified BibTeX
.venv/Scripts/python engine/cli.py search-papers "workflow state machine audit" --append-bib refs.bib

# Scan codebase into traceability manifest & ERD spec
.venv/Scripts/python engine/cli.py sync /path/to/repo --out manifest.json

# Visual & structural PDF QA
.venv/Scripts/python engine/cli.py qa output.pdf --profile rpl-v17 --render-dir qa_pages
```

## License
MIT License. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for upstream open-source attributions.
