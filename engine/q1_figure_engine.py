"""Publication-grade Q1 scientific figure generator (IEEE/Elsevier/Nature typography, colorblind-safe Okabe-Ito palette, vector PDF/SVG + 600 DPI PNG)."""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Okabe-Ito colorblind-safe academic palette
OKABE_ITO = [
    "#0072B2",  # blue
    "#D55E00",  # vermilion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#333333",  # charcoal
]

COL_WIDTHS = {
    "ieee_single": 3.5,
    "ieee_double": 7.16,
    "elsevier_single": 3.54,
    "elsevier_double": 7.48,
    "report_wide": 6.2,
}


def build_q1_figure(spec, out_stem, formats=("pdf", "svg", "png"), dpi=600):
    """Build publication-grade scientific chart from JSON spec."""
    col = spec.get("column", "ieee_single")
    width_in = float(spec.get("width_in", COL_WIDTHS.get(col, 3.5)))
    height_in = float(spec.get("height_in", round(width_in * 0.68, 2)))

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "font.size": spec.get("font_size", 8.5),
        "axes.labelsize": spec.get("font_size", 8.5),
        "axes.titlesize": spec.get("font_size", 9.0),
        "xtick.labelsize": spec.get("tick_size", 7.8),
        "ytick.labelsize": spec.get("tick_size", 7.8),
        "legend.fontsize": spec.get("legend_size", 7.5),
        "axes.linewidth": 0.75,
        "lines.linewidth": 1.35,
        "lines.markersize": 4.2,
        "pdf.fonttype": 42,  # TrueType embed for IEEE PDF eXpress compliance
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    })

    fig, ax = plt.subplots(figsize=(width_in, height_in))
    kind = spec.get("kind", "line")
    series = spec.get("series", [])
    markers = ["o", "s", "^", "D", "v", "P", "X"]
    linestyles = ["-", "--", "-.", ":", "-", "--", "-."]

    if kind == "line":
        for i, s in enumerate(series):
            c = s.get("color", OKABE_ITO[i % len(OKABE_ITO)])
            ax.plot(
                s["x"],
                s["y"],
                label=s.get("label"),
                color=c,
                marker=s.get("marker", markers[i % len(markers)]),
                linestyle=s.get("linestyle", linestyles[i % len(linestyles)]),
            )
            if s.get("yerr"):
                ax.errorbar(s["x"], s["y"], yerr=s["yerr"], fmt="none", ecolor=c, elinewidth=0.9, capsize=2.5)
    elif kind in ("bar", "grouped_bar"):
        cats = spec.get("categories", [])
        x = np.arange(len(cats))
        ns = max(1, len(series))
        bw = min(0.75 / ns, 0.35)
        for i, s in enumerate(series):
            offset = (i - (ns - 1) / 2.0) * bw
            c = s.get("color", OKABE_ITO[i % len(OKABE_ITO)])
            bars = ax.bar(x + offset, s["y"], width=bw, label=s.get("label"), color=c, edgecolor="#111111", linewidth=0.5, yerr=s.get("yerr"), capsize=2.5)
            if spec.get("annotate_bars", False):
                for b in bars:
                    val = b.get_height()
                    ax.annotate(f"{val:.1f}", (b.get_x() + b.get_width() / 2, val), textcoords="offset points", xytext=(0, 2), ha="center", va="bottom", fontsize=6.8)
        ax.set_xticks(x)
        ax.set_xticklabels(cats, rotation=spec.get("x_rotation", 0))
    elif kind == "scatter":
        for i, s in enumerate(series):
            c = s.get("color", OKABE_ITO[i % len(OKABE_ITO)])
            ax.scatter(s["x"], s["y"], label=s.get("label"), color=c, marker=markers[i % len(markers)], s=24, alpha=0.85, edgecolors="#111111", linewidths=0.4)
    elif kind == "heatmap":
        data = np.array(spec["matrix"], dtype=float)
        im = ax.imshow(data, cmap=spec.get("cmap", "viridis"), aspect="auto")
        if spec.get("xlabels"):
            ax.set_xticks(np.arange(len(spec["xlabels"])))
            ax.set_xticklabels(spec["xlabels"])
        if spec.get("ylabels"):
            ax.set_yticks(np.arange(len(spec["ylabels"])))
            ax.set_yticklabels(spec["ylabels"])
        for r in range(data.shape[0]):
            for c_idx in range(data.shape[1]):
                ax.text(c_idx, r, f"{data[r, c_idx]:.2f}", ha="center", va="center", color="white" if data[r, c_idx] < np.mean(data) else "black", fontsize=7)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    if spec.get("title"):
        ax.set_title(spec["title"], pad=6)
    if spec.get("xlabel"):
        ax.set_xlabel(spec["xlabel"])
    if spec.get("ylabel"):
        ax.set_ylabel(spec["ylabel"])
    if spec.get("xlim"):
        ax.set_xlim(spec["xlim"])
    if spec.get("ylim"):
        ax.set_ylim(spec["ylim"])
    if kind != "heatmap":
        ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.65)
        ax.set_axisbelow(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if any(s.get("label") for s in series):
            ax.legend(frameon=True, framealpha=0.92, edgecolor="#CCCCCC", loc=spec.get("legend_loc", "best"))

    fig.tight_layout(pad=0.5)
    out_abs = os.path.abspath(out_stem)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    outputs = {}
    for fmt in formats:
        dst = f"{out_abs}.{fmt}"
        save_kw = {"bbox_inches": "tight", "pad_inches": 0.04}
        if fmt == "png":
            save_kw["dpi"] = dpi
        fig.savefig(dst, **save_kw)
        outputs[fmt] = {"path": dst, "bytes": os.path.getsize(dst)}
    plt.close(fig)
    return {"width_in": width_in, "height_in": height_in, "outputs": outputs}
