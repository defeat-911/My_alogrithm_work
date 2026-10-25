"""Render the real ``git log`` as a terminal-style PNG for the report.

Usage:
    python scripts/make_git_log_figure.py

The figure is written to docs/report/figures/git_log.png.  It is intentionally
generated from the actual repository history; if there are no commits yet, a
placeholder is written instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "report" / "figures" / "git_log.png"
OUT.parent.mkdir(parents=True, exist_ok=True)


def _font(name: str, size: int):
    path = Path("C:/Windows/Fonts") / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _is_ascii(ch: str) -> bool:
    return ord(ch) < 128


def _draw_mixed(draw, x, y, text, ascii_font, cjk_font, fill):
    """Draw ASCII and CJK runs with their respective fonts."""

    run = []
    last = None
    for ch in text:
        kind = _is_ascii(ch)
        if last is None or kind == last:
            run.append(ch)
        else:
            if run:
                font = ascii_font if last else cjk_font
                draw.text((x, y), "".join(run), font=font, fill=fill)
                x += draw.textlength("".join(run), font=font)
            run = [ch]
        last = kind
    if run:
        font = ascii_font if last else cjk_font
        draw.text((x, y), "".join(run), font=font, fill=fill)


def main() -> None:
    try:
        log = subprocess.check_output(
            [
                "git",
                "log",
                "--graph",
                "--oneline",
                "--decorate",
                "--all",
                "--date=short",
                "--pretty=format:%h %ad %s",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError:
        log = ""
    lines = [line for line in log.splitlines() if line.strip()]
    if not lines:
        lines = ["No commits yet. Run git commit/tag first, then re-run this script."]

    ascii_font = _font("consola.ttf", 20)
    cjk_font = _font("simsun.ttc", 20)
    title_font = _font("consola.ttf", 22)
    line_h = 34
    width = 1600
    height = 90 + line_h * len(lines)
    img = Image.new("RGB", (width, height), "#1E1E1E")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, 46], fill="#323233")
    draw.text((20, 10), "git log --graph --oneline --decorate --all", font=title_font, fill="#CCCCCC")

    y = 62
    for line in lines:
        fill = "#DCDCAA" if line.lstrip().startswith("*") else "#D4D4D4"
        if "tag:" in line or "HEAD ->" in line:
            fill = "#4EC9B0"
        _draw_mixed(draw, 20, y, line, ascii_font, cjk_font, fill)
        y += line_h

    img.save(OUT)
    print(f"wrote {OUT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
