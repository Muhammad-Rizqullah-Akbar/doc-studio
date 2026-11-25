---
name: doc-diagram-studio
description: >-
  End-to-end Precision Document, Proposal, Thesis (Skripsi), Technical Report,
  and Zero-Overlap Draw.io Diagram authoring workflow. Use whenever creating or
  updating formatted Word (.docx), LaTeX, Typst, or PDF documents, generating
  Flowchart/ERD/DFD/Sequence/Class/Architecture/Swimlane Draw.io diagrams,
  matching an exact institutional format (such as RPL v17 or Skripsi), or
  synchronizing documentation after refactoring a software project.
---

# Doc & Diagram Studio Runbook

## 5-Phase Mandatory Pipeline

### Phase 1: Project Understanding & Living-Doc Sync (Before Writing)
Never invent architecture, database columns, or endpoints from memory.
1. Use `xenonite-tools` (`get_project_structure`, `get_code_outline`, `analyze_module_dependencies`, `read_targeted_snippets`) for fast targeted inspection.
2. For broad codebase snapshots or cross-file context packing, call **`repomix`** MCP (`pack_codebase`, `read_repomix_output`, `grep_repomix_output`).
3. Call **`doc-studio.sync_project_docs_manifest(project_dir, out_manifest_path)`** to extract deterministic Prisma ERD models, HTTP API routes, module layout, and compute doc-drift diffs against the previous manifest whenever a project has been refactored.
4. Maintain traceability registers (`01_SOURCE_REGISTER` through `07_ERD_RELATIONSHIP_MATRIX`) as single source of truth before drafting chapters or diagrams.

### Phase 2: Format & Style Profile Locking
1. Call **`doc-studio.list_style_profiles()`** to verify available profiles and binaries.
2. Select the exact profile matching the target format:
   - `rpl-v17`: A4, margins L4/R3/T3/B3 cm, Times New Roman 12pt, justify, 1.15 spacing, 1cm first-line indent, heading 14/12 bold, grid tables, chapter-scoped `Gambar X.Y` / `Tabel X.Y`, Word COM PDF export.
   - `skripsi-unhas`: A4, margins L4/R3/T4/B3 cm, Times New Roman 12pt, 1.5 spacing, 1.25cm indent, Roman front matter (`i, ii, iii`) + Arabic main matter (`1, 2, 3`) with bottom-center on chapter opening pages and top-right on continuation pages, academic booktabs tables, APA 7 CSL.
   - `ieee-q1`, `elsevier-q1`, `springer-lncs`: Q1 academic LaTeX templates via TinyTeX (`pdflatex`/`xelatex` + `bibtex`/`biber`).
   - `tech-report-modern`: Typst millisecond-compile modern architecture/audit report.
3. For any custom campus, client, or journal format, pass `profile_overrides_json` (custom margins, fonts, sizes, line spacing, table style, CSL) or inspect the user's reference PDF with `qa_inspect_pdf` first to clone its exact geometry and font rules.

### Phase 3: Zero-Overlap Draw.io Diagrams
Every diagram MUST remain editable (`.drawio`), crisp (2x/3x PNG + SVG/PDF vector), and strictly zero-overlap:
1. Call **`doc-studio.generate_drawio_diagram(spec_json, out_drawio_path, style_profile, render_formats="png,svg", render_scale=2)`**:
   - Prefer `style_profile="monochrome-bw"` for clean black-and-white formal reports/proposals/theses (matching RPL v17 monochrome aesthetic).
   - For **ERD**: ALWAYS specify exact `source_field` and `target_field` on every edge (e.g. `id` -> `from_state_id`, `id` -> `to_state_id`); the engine anchors edges directly to exact table row cells with staggered 90-degree orthogonal routing and fails loudly if any field name mismatches.
   - For **DFD**: the engine enforces DFD semantic rules (blocks illegal direct `external -> store` or `store -> store` flows without a process) and separates bidirectional edges cleanly.
   - Uses **ELK (`elkjs`) Sugiyama orthogonal routing** with explicit port anchors (`exitX/Y`, `entryX/Y`) and calculated bend points for `flowchart`, `architecture`, `dfd`, `erd`, `cd`, and `state`.
   - Uses dedicated deterministic zero-overlap solvers for **Sequence Diagrams (`sd`)** and **Swimlane Processes (`ufd`/`swimlane`)**.
   - Automatically runs `validate_drawio` (`node_overlap == 0`, `edge_crosses_node == 0`, bounds check) and renders PNG/SVG/PDF via `draw.io.exe` CLI.
2. If interactive browser editing or quick preview in draw.io is desired, use the official **`drawio`** MCP (`@drawio/mcp`) to open the generated `.drawio` XML in the browser editor.
3. Whenever a `.drawio` file is edited manually, re-run **`doc-studio.validate_and_render_drawio`** before rebuilding the document.
4. **MANDATORY Visual Check**: Inspect rendered diagram PNGs with `read_file` to verify clean spacing, legible labels, and clear flow before embedding.

### Phase 4: Precision Document Assembly
- **Word -> PDF (Proposals, Skripsi, Institutional Reports)**:
  - Call **`doc-studio.build_word_document(..., export_pdf=True)`**.
  - Tables automatically get `w:tblHeader` (repeat header across page breaks) and `w:cantSplit` (no split rows). Figures & captions lock via `keep_with_next`.
  - Microsoft Word COM automatically runs `Repaginate()`, updates `TablesOfContents`, `TablesOfFigures`, and all `Fields`, saves the synced `.docx`, and exports `.pdf` with heading bookmarks.
  - Supply `bibliography: {"bib_path": "...", "csl": "apa.csl|ieee.csl"}` for automatic Pandoc `--citeproc` references.
- **LaTeX / Typst -> PDF (Q1 Papers & Technical Reports)**:
  - Call **`doc-studio.build_latex_or_typst_pdf`** (check `overfull_hbox_count == 0` and `undefined_ref_count == 0`).
- **Scientific Plots & Quantitative Charts**:
  - Call **`doc-studio.build_q1_figure_chart`** for colorblind-safe Okabe-Ito vector PDF/SVG + 600 DPI PNG figures sized accurately to single/double column widths.

### Phase 5: Mandatory Visual & Structural PDF QA Gate
Never declare a document complete until QA passes:
1. Call **`doc-studio.qa_inspect_pdf(pdf_path, profile_name, render_dir=...)`**.
2. Verify: `critical_count == 0`, zero broken references (`??`, `[?]`, `Error! Reference source not found`), zero blank pages, zero low-DPI images, zero stray fonts, zero margin overflows, zero orphan headings.
3. Visually inspect rendered page PNGs (`page_001.png`, TOC page, diagram pages, table pages) via `read_file`. Fix any micro-defect and regenerate until 100% clean.
