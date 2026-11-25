# Contributing to Doc-Studio

Contributions are welcome! Whether you want to add a university thesis style profile, improve diagram layout rules, add a new codebase parser (e.g., Django/Go/Rust), or refine KBBI/Q1 linting rules:

1. Fork the repository and create a feature branch (`git checkout -b feat/my-improvement`).
2. Keep changes minimal, deterministic, and zero-hardcoded-path.
3. Verify locally with `python engine/cli.py doctor` and run end-to-end checks on any modified engine.
4. Open a Pull Request describing what changed and how it was verified.
