"""Cross-platform, zero-hardcoded-path binary & asset auto-discovery for portable doc-studio."""
import os
import platform
import shutil
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WIN = platform.system() == "Windows"
EXE = ".exe" if IS_WIN else ""


def _first_existing(candidates, which_name=None):
    for c in candidates:
        if c and os.path.exists(c):
            return c
    if which_name:
        found = shutil.which(which_name)
        if found:
            return found
    return None


def resolve_binaries():
    local_bin = os.path.join(PLUGIN_ROOT, "bin")
    home = os.path.expanduser("~")
    local_app = os.environ.get("LOCALAPPDATA", "")
    roaming_app = os.environ.get("APPDATA", "")

    drawio_cands = [os.path.join(local_bin, "drawio", f"draw.io{EXE}")]
    if IS_WIN:
        drawio_cands.extend([
            os.path.join(local_app, "Programs", "draw.io", "draw.io.exe"),
            r"C:\Program Files\draw.io\draw.io.exe",
        ])
    elif platform.system() == "Darwin":
        drawio_cands.append("/Applications/draw.io.app/Contents/MacOS/draw.io")
    drawio = _first_existing(drawio_cands, "drawio") or _first_existing([], "draw.io")

    pandoc_cands = [os.path.join(local_bin, f"pandoc{EXE}")]
    if IS_WIN:
        pandoc_cands.extend([
            os.path.join(local_app, "Pandoc", "pandoc.exe"),
            r"C:\Program Files\Pandoc\pandoc.exe",
        ])
    pandoc = _first_existing(pandoc_cands, "pandoc")

    tex_cands = [
        os.environ.get("DOC_STUDIO_TEX_BIN", ""),
        os.path.join(local_bin, "tinytex", "TinyTeX", "bin", "windows" if IS_WIN else "x86_64-linux"),
        os.path.join(roaming_app, "TinyTeX", "bin", "windows") if IS_WIN else os.path.join(home, ".TinyTeX", "bin", "x86_64-linux"),
    ]
    tex_bin = _first_existing(tex_cands)
    if not tex_bin:
        found_pdf = shutil.which("pdflatex")
        if found_pdf:
            tex_bin = os.path.dirname(found_pdf)

    def _tex_tool(name):
        return _first_existing([os.path.join(tex_bin, f"{name}{EXE}")] if tex_bin else [], name)

    typst = _first_existing(
        [
            os.path.join(local_bin, f"typst{EXE}"),
            os.path.join(local_app, "Microsoft", "WinGet", "Links", "typst.exe") if IS_WIN else "",
        ],
        "typst",
    )
    vale = _first_existing([os.path.join(local_bin, f"vale{EXE}")], "vale")
    harper = _first_existing([os.path.join(local_bin, f"harper-cli{EXE}")], "harper-cli")
    node = _first_existing([], "node")
    repomix = _first_existing(
        [os.path.join(roaming_app, "npm", "repomix.cmd")] if IS_WIN else [],
        "repomix",
    )
    drawio_mcp = _first_existing(
        [os.path.join(roaming_app, "npm", "drawio-mcp.cmd")] if IS_WIN else [],
        "drawio-mcp",
    )
    venv_py = os.path.join(PLUGIN_ROOT, ".venv", "Scripts" if IS_WIN else "bin", f"python{EXE}")
    python_venv = venv_py if os.path.exists(venv_py) else sys.executable

    return {
        "plugin_root": PLUGIN_ROOT,
        "drawio": drawio,
        "pandoc": pandoc,
        "tex_bin": tex_bin,
        "xelatex": _tex_tool("xelatex"),
        "pdflatex": _tex_tool("pdflatex"),
        "lualatex": _tex_tool("lualatex"),
        "latexmk": _tex_tool("latexmk"),
        "biber": _tex_tool("biber"),
        "bibtex": _tex_tool("bibtex"),
        "chktex": _tex_tool("chktex"),
        "typst": typst,
        "vale": vale,
        "harper": harper,
        "node": node,
        "elk_script": os.path.join(PLUGIN_ROOT, "layout", "elk_layout.mjs"),
        "repomix": repomix,
        "drawio_mcp": drawio_mcp,
        "python_venv": python_venv,
        "style_profiles": os.path.join(PLUGIN_ROOT, "config", "style_profiles.json"),
        "csl_dir": os.path.join(PLUGIN_ROOT, "csl"),
        "templates_dir": os.path.join(PLUGIN_ROOT, "templates"),
    }


def build_env():
    bins = resolve_binaries()
    env = os.environ.copy()
    extra = [os.path.join(PLUGIN_ROOT, "bin")]
    for key in ("tex_bin",):
        if bins.get(key):
            extra.append(bins[key])
    for key in ("pandoc", "typst", "vale", "harper"):
        if bins.get(key):
            extra.append(os.path.dirname(bins[key]))
    if bins.get("pandoc"):
        env["PYPANDOC_PANDOC"] = bins["pandoc"]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    return env
