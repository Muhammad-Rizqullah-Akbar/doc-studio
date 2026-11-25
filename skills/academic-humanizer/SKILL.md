---
name: academic-humanizer
description: >-
  Polish academic prose (Indonesian Skripsi/Proposal/Laporan and English Q1
  journal papers) to sound natural, authoritative, and free of AI-slop while
  strictly preserving technical terminology, equations, data, and citations.
  Pairs with local Vale, Harper, ChkTeX, Unicode hygiene, and burstiness audit.
---

# Academic Humanizer & Prose Polish Runbook

Adapted from `blader/humanizer` (MIT, WikiProject AI Cleanup) specifically for **formal academic & technical writing** (unlike casual blog rewriting, NEVER introduce slang, jokes, or casual filler into theses/Q1 papers).

## Non-Negotiable Preservation Locks
1. **NEVER alter** numerical metrics, statistical values, equations, code identifiers, API paths, table schemas, or citation keys (`\cite{...}`, `[1]`, `(Author, Year)`).
2. **NEVER fabricate** citations or paraphrase technical definitions into inaccurate "tortured phrases".
3. **NEVER inject** invisible Unicode characters, homoglyphs, or mechanical synonym swaps.

## 5-Step Academic Polish Workflow
1. **Run Objective Audit First**: Call `doc-studio.audit_prose_and_hygiene(file_path, lang=...)` (or CLI `doc-studio audit <file>`) to run **Vale** (with `KBBIBakuID`, `PleonasmeFormalID`, `AcademicToneID`, `AISlopID`, `AISlopEN` rulesets), **Harper** (English Rust grammar), **ChkTeX** (LaTeX Q1 typography), invisible Unicode check, sentence burstiness metrics, and local 5-gram reference overlap.
2. **Enforce Strict KBBI / EYD V Indonesian**: Fix every `DocStudio.KBBIBakuID` error (e.g., *analisa -> analisis*, *sistim -> sistem*, *praktek -> praktik*, *dimana -> di mana*, *dikarenakan -> karena*, *merubah -> mengubah*) and `DocStudio.PleonasmeFormalID` warning (*adalah merupakan*, *agar supaya*, *yang mana*, casual words).
2. **Voice Calibration (Optional)**: If the user provides 1-2 paragraphs of their own writing, mirror their sentence length cadence, transition style, and academic register.
3. **Strip AI-isms (EN & ID)**:
   - Remove puffed-up significance claims (*"serves as a testament", "pivotal shift", "memainkan peran krusial dalam era digital yang terus berkembang"*).
   - Replace filler transitions (*"It is worth noting that...", "Penting untuk dicatat bahwa..."*) by stating the claim directly.
   - Eliminate repetitive formulaic triads (*"robust, scalable, and seamless"*) and overuse of *"Not only X, but also Y"* / *"Tidak hanya X, melainkan juga Y"*.
   - Enforce **Zero Em-Dash** on Indonesian institutional reports/proposals when the profile sets `forbid_em_dash: true`.
4. **Restore Natural Academic Rhythm (Burstiness)**:
   - Mix concise declarative sentences (10-16 words) with structured analytical sentences (20-32 words). Avoid walls of uniform 22-word sentences or 50-word run-ons.
   - Prefer concrete active verbs (*"Sistem memvalidasi..."*, *"We evaluate..."*) over bloated nominalizations (*"Dilakukannya proses validasi oleh sistem..."*).
5. **Re-Audit & Verify Citations**:
   - Re-run `doc-studio.audit_prose_and_hygiene` until `unicode_hygiene == {}`, `ai_cliches_found == []`, and `rhythm_verdict == "healthy_variation"`.
   - Run `doc-studio.verify_bib_citations` on `refs.bib` so every single reference is verified against Crossref & OpenAlex (zero retracted or hallucinated papers).
