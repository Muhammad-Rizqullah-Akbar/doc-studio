# Doc & Diagram Studio Operational Rules

When authoring or updating formal documents (proposals, reports, theses/skripsi, Q1 papers) or technical diagrams:
1. Ground all technical content in actual codebase facts first using `repomix` and `doc-studio.sync_project_docs_manifest`.
2. For diagrams, always produce editable `.drawio` via `doc-studio.generate_drawio_diagram` (ELK orthogonal routing / deterministic SD & Swimlane solvers) and verify `validation.pass == true` (`node_overlap == 0`, `edge_crosses_node == 0`). Use `@drawio/mcp` (`drawio`) when interactive browser viewing/editing is helpful.
3. For Word documents (`.docx`), enforce the target style profile (`academic-proposal`, `academic-thesis`, or custom overrides) and always finalize via Word COM / LibreOffice (`export_pdf=True`) so TOC/LOF/LOT fields and page numbers stay 100% synchronized.
4. Always run `doc-studio.qa_inspect_pdf` with PNG rendering and inspect output visually before marking any deliverable final.
