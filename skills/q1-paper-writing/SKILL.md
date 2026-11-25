---
name: q1-paper-writing
description: >-
  Q1 journal manuscript authoring discipline for IEEE Transactions, Elsevier,
  Springer LNCS, and ACM venues. Use when writing, structuring, formatting,
  plotting figures, managing BibTeX/CSL citations, or auditing an academic
  research paper targeting Q1 peer review.
---

# Q1 Academic Paper Authoring Standard

## 1. Structural Rigor (IMRaD + Explicit Contributions)
- **Abstract (150-250 words)**: Context -> Research Gap -> Proposed Method -> Experimental Setup -> Concrete Quantitative Results (with effect sizes/improvements, never vague claims).
- **Introduction**: Explicitly state the gap, Research Questions (RQ1..RQk) or Hypotheses, and numbered verifiable contributions mapped to sections.
- **Related Work**: Organize thematically (not author-by-author chronology) and include a structured **comparison matrix table** (booktabs) contrasting prior works against your method across concrete criteria.
- **Methodology**: Formal notation (consistent symbols, numbered equations with every symbol defined), complexity analysis (time/space Big-O), and reproducible architectural/algorithmic diagrams (`.drawio` exported to cropped vector `.pdf`).
- **Experimental Setup & Results**: Hardware/software specs, dataset statistics, strong baselines, ablation study, statistical significance tests (mean +/- std, confidence intervals, p-value / effect size), and Threats to Validity (internal, external, construct, conclusion).

## 2. Visual & Typographic Q1 Checklist
- **Figures**: Generate charts with `doc-studio.build_q1_figure_chart` (exact `ieee_single` 3.5" or `ieee_double` 7.16" width, TrueType font embedding `pdf.fonttype=42`, serif 8-9pt labels readable without zoom, Okabe-Ito colorblind-safe palette + distinct markers/linestyles for grayscale printing).
- **Architecture/Flow Diagrams**: Generate via `doc-studio.generate_drawio_diagram` with `style_profile="ieee-q1"` and `render_formats="pdf,png"`. Embed cropped vector `.pdf` in LaTeX (`\includegraphics[width=\columnwidth]{...}`) so text remains razor-sharp at any zoom.
- **Tables**: Strictly `booktabs` (`\toprule`, `\midrule`, `\bottomrule`, NO vertical lines), bold best results, aligned decimal columns (`siunitx`), captions ABOVE tables and BELOW figures.
- **Compilation Hygiene**: Run `doc-studio.build_latex_or_typst_pdf` and enforce `overfull_hbox_count == 0` and `undefined_ref_count == 0`.
- **Citation Integrity**: Every citation in `.bib` MUST be verified (real authors, venue, year, DOI). Never fabricate DOIs or references.
- **Final Visual Audit**: Run `doc-studio.qa_inspect_pdf` with `render_dir` and inspect rendered PNG pages visually before submission.
