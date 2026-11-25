"""Cross-platform zero-signup asset bootstrapper for portable doc-studio (Windows / macOS / Linux)."""
import csv
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
ARCH = platform.machine().lower()
EXE = ".exe" if IS_WIN else ""
UA = "doc-studio-installer/1.0"


def dl(url, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r, open(dst, "wb") as wf:
        shutil.copyfileobj(r, wf)
    print(f"  [OK] {os.path.basename(dst)} ({os.path.getsize(dst)} B)")
    return dst


def dl_gh_binary(repo, match_tokens, target_bin, out_name):
    bin_dir = os.path.join(ROOT, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    dst = os.path.join(bin_dir, out_name)
    if os.path.exists(dst):
        print(f"  [SKIP] {out_name} already exists")
        return dst
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        rel = json.loads(r.read().decode("utf-8"))
    url = None
    ext = ""
    for a in rel.get("assets", []):
        name = a["name"].lower()
        if all(t in name for t in match_tokens) and (name.endswith(".zip") or name.endswith(".tar.gz") or name.endswith(".tgz")):
            url = a["browser_download_url"]
            ext = ".zip" if name.endswith(".zip") else ".tar.gz"
            print(f"  Downloading {repo}: {a['name']}")
            break
    if not url:
        print(f"  [WARN] No matching release asset for {repo} ({match_tokens})")
        return None
    arc = os.path.join(bin_dir, f"_tmp_{out_name}{ext}")
    dl(url, arc)
    if ext == ".zip":
        with zipfile.ZipFile(arc, "r") as zf:
            for m in zf.namelist():
                if os.path.basename(m).lower() == target_bin.lower():
                    with zf.open(m) as src, open(dst, "wb") as wf:
                        shutil.copyfileobj(src, wf)
                    break
    else:
        with tarfile.open(arc, "r:gz") as tf:
            for m in tf.getmembers():
                if os.path.basename(m.name).lower() == target_bin.lower():
                    with tf.extractfile(m) as src, open(dst, "wb") as wf:
                        shutil.copyfileobj(src, wf)
                    break
    os.remove(arc)
    if os.path.exists(dst) and not IS_WIN:
        os.chmod(dst, os.stat(dst).st_mode | stat.S_IEXEC)
    return dst if os.path.exists(dst) else None


def bootstrap_binaries():
    print("\n[1/5] Downloading free portable binaries (Vale, Harper, Typst)...")
    if IS_WIN:
        vale_tok, harper_tok, typst_tok = ["windows", "64-bit"], ["harper-cli", "windows"], ["x86_64-pc-windows"]
    elif IS_MAC:
        arch_tok = "arm64" if "arm" in ARCH else "64-bit"
        vale_tok = ["macos", arch_tok]
        harper_tok = ["harper-cli", "apple-darwin", "aarch64" if "arm" in ARCH else "x86_64"]
        typst_tok = ["apple-darwin", "aarch64" if "arm" in ARCH else "x86_64"]
    else:
        vale_tok, harper_tok, typst_tok = ["linux", "64-bit"], ["harper-cli", "linux", "x86_64"], ["x86_64-unknown-linux"]

    dl_gh_binary("errata-ai/vale", vale_tok, f"vale{EXE}", f"vale{EXE}")
    dl_gh_binary("Automattic/harper", harper_tok, f"harper-cli{EXE}", f"harper-cli{EXE}")
    if not shutil.which("typst"):
        dl_gh_binary("typst/typst", typst_tok, f"typst{EXE}", f"typst{EXE}")


def bootstrap_csl():
    print("\n[2/5] Downloading official CSL citation styles...")
    csl_dir = os.path.join(ROOT, "csl")
    csls = {
        "apa.csl": "https://raw.githubusercontent.com/citation-style-language/styles/master/apa.csl",
        "ieee.csl": "https://raw.githubusercontent.com/citation-style-language/styles/master/ieee.csl",
        "springer-lncs.csl": "https://raw.githubusercontent.com/citation-style-language/styles/master/springer-lecture-notes-in-computer-science.csl",
        "elsevier-harvard.csl": "https://raw.githubusercontent.com/citation-style-language/styles/master/elsevier-harvard.csl",
        "elsevier-vancouver.csl": "https://raw.githubusercontent.com/citation-style-language/styles/master/elsevier-vancouver.csl",
        "acm-sig-proceedings.csl": "https://raw.githubusercontent.com/citation-style-language/styles/master/acm-sig-proceedings.csl",
    }
    for fn, url in csls.items():
        dst = os.path.join(csl_dir, fn)
        if not os.path.exists(dst):
            dl(url, dst)


def bootstrap_kbbi_and_vale():
    print("\n[3/5] Downloading LibreOffice id_ID Hunspell + lantip/baku-tidak-baku KBBI dataset...")
    vale_root = os.path.join(ROOT, "vale")
    dict_dir = os.path.join(vale_root, "dictionaries")
    src_dir = os.path.join(vale_root, "sources")
    styles_dir = os.path.join(vale_root, "styles", "DocStudio")
    os.makedirs(dict_dir, exist_ok=True)
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(styles_dir, exist_ok=True)

    dl("https://raw.githubusercontent.com/LibreOffice/dictionaries/master/id/id_ID.dic", os.path.join(dict_dir, "id_ID.dic"))
    dl("https://raw.githubusercontent.com/LibreOffice/dictionaries/master/id/id_ID.aff", os.path.join(dict_dir, "id_ID.aff"))

    swap_map = {}
    for fn in ("daftar_baku_ivanlanin.json", "daftar_baku_lantip.json", "daftar_baku_tidak_baku.csv"):
        dst = os.path.join(src_dir, fn)
        dl(f"https://raw.githubusercontent.com/lantip/baku-tidak-baku/main/{fn}", dst)
        if fn.endswith(".json"):
            data = json.load(open(dst, encoding="utf-8", errors="replace"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, str):
                        nk, nv = k.strip().lower(), v.strip().lower()
                        if re.fullmatch(r"[a-z][a-z\- ]{2,35}", nk) and re.fullmatch(r"[a-z][a-z\- ]{2,35}", nv) and nk != nv:
                            swap_map[nk] = nv
        else:
            with open(dst, encoding="utf-8", errors="replace") as cf:
                rdr = csv.reader(cf)
                next(rdr, None)
                for row in rdr:
                    if len(row) >= 2:
                        tb, bk = row[0].strip().lower(), row[1].strip().lower()
                        if re.fullmatch(r"[a-z][a-z\- ]{2,35}", tb) and re.fullmatch(r"[a-z][a-z\- ]{2,35}", bk) and tb != bk:
                            swap_map[tb] = bk

    lines = [
        "# Auto-generated from github.com/lantip/baku-tidak-baku (KBBI & Ivan Lanin)",
        "extends: substitution",
        "message: \"Kata tidak baku KBBI: gunakan '%s' sebagai pengganti '%s'.\"",
        "ignorecase: true",
        "level: error",
        "swap:",
    ]
    for tb in sorted(swap_map):
        lines.append(f'  "{tb}": "{swap_map[tb]}"')
    with open(os.path.join(styles_dir, "KBBIBakuID.yml"), "w", encoding="utf-8") as wf:
        wf.write("\n".join(lines) + "\n")
    print(f"  [OK] Compiled {len(swap_map)} KBBI pairs into KBBIBakuID.yml")

    print("\n[4/5] Syncing official errata-ai Vale packages (write-good, proselint, Google)...")
    vale_bin = os.path.join(ROOT, "bin", f"vale{EXE}")
    if os.path.exists(vale_bin):
        subprocess.run([vale_bin, "--config", os.path.join(vale_root, ".vale.en.ini"), "sync"], cwd=vale_root, check=False)


def generate_mcp_config():
    print("\n[5/5] Generating machine-local mcp_config.json...")
    venv_py = os.path.join(ROOT, ".venv", "Scripts" if IS_WIN else "bin", f"python{EXE}")
    py_cmd = venv_py if os.path.exists(venv_py) else sys.executable
    repomix_cmd = shutil.which("repomix") or "npx"
    repomix_args = ["--mcp"] if repomix_cmd != "npx" else ["-y", "repomix", "--mcp"]
    drawio_cmd = shutil.which("drawio-mcp") or "npx"
    drawio_args = [] if drawio_cmd != "npx" else ["-y", "@drawio/mcp"]

    cfg = {
        "mcpServers": {
            "repomix": {"command": repomix_cmd, "args": repomix_args},
            "drawio": {"command": drawio_cmd, "args": drawio_args},
            "doc-studio": {
                "command": py_cmd,
                "args": [os.path.join(ROOT, "server", "doc_studio_mcp.py")],
                "env": {"PYTHONIOENCODING": "utf-8"},
            },
        }
    }
    dst = os.path.join(ROOT, "mcp_config.json")
    with open(dst, "w", encoding="utf-8") as wf:
        json.dump(cfg, wf, indent=2)
    print(f"  [OK] Generated {dst}")


if __name__ == "__main__":
    bootstrap_binaries()
    bootstrap_csl()
    bootstrap_kbbi_and_vale()
    generate_mcp_config()
    print("\nBootstrap complete! Run: .venv/Scripts/python engine/cli.py doctor")
