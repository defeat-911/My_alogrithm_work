"""Build the final v1 report: fill numbers -> figures -> body -> merge -> PDF.

Run from the project root:

    python docs/report/build_report.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "report"
OUT_DOCX = ROOT / "docs" / "算法_班级_学号_姓名.docx"
OUT_PDF = ROOT / "docs" / "算法_班级_学号_姓名.pdf"


def run(cmd: list[str], cwd: Path | None = None) -> str:
    print("$", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return proc.stdout


def main() -> None:
    # 1) Fill numeric placeholders from results/summary.json.
    run([sys.executable, str(REPORT / "fill_report.py")])

    # 2) Generate the Git log image (placeholder if no commits yet).
    run([sys.executable, str(ROOT / "scripts" / "make_git_log_figure.py")])

    # 3) Build the body-only docx.
    run(
        [
            "node",
            "js/build_paper.js",
            "report.md",
            "report_body.docx",
            "--body-only",
            "--campus-template",
        ],
        cwd=REPORT,
    )

    # 4) Prepare the 4-section template base.
    run([sys.executable, str(REPORT / "prepare_base.py")])

    # 5) Merge and export PDF.
    run(
        [
            sys.executable,
            str(REPORT / "merge_into_template.py"),
            "--base",
            str(REPORT / "report_base.docx"),
            "--body",
            str(REPORT / "report_body.docx"),
            "--out-docx",
            str(OUT_DOCX),
            "--out-pdf",
            str(OUT_PDF),
        ]
    )

    # 6) Quick content checks.
    from docx import Document

    doc = Document(OUT_DOCX)
    text = "\n".join(p.text for p in doc.paragraphs)
    for table in doc.tables:
        text += "\n" + "\n".join(c.text for row in table.rows for c in row.cells)
    unresolved = text.count("{{")
    dashes = text.count("—")
    print(f"paragraphs={len(doc.paragraphs)} tables={len(doc.tables)} images={len(doc.inline_shapes)}")
    print(f"unresolved placeholders={{...}} count={unresolved}; em-dash count={dashes}")
    print(f"output docx: {OUT_DOCX}")
    print(f"output pdf : {OUT_PDF}")


if __name__ == "__main__":
    main()
