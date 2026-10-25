"""Prepare a 4-section base document from the course template.

Keeps: cover, grading table, TOC field.
Replaces: notification, sample body, references, appendix.
Adds: a body section with the template's own body sectPr (footer PAGE field,
page numbering start 1) and a BODY_INSERT bookmark for the Word COM merge.

Run from the project root:

    python docs/report/prepare_base.py
"""

from __future__ import annotations

import shutil
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "算法课程设计通知及报告模版2026.docx"
OUT = ROOT / "docs" / "report" / "report_base.docx"


def main() -> None:
    if not TEMPLATE.exists():
        raise FileNotFoundError(TEMPLATE)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, OUT)

    doc = Document(OUT)
    body = doc.element.body

    # Save the body section's properties before deleting the sample body.
    if len(doc.sections) < 4:
        raise RuntimeError(f"unexpected section count: {len(doc.sections)}")
    body_sectPr = deepcopy(doc.sections[3]._sectPr)
    pg_num = body_sectPr.find(qn("w:pgNumType"))
    if pg_num is None:
        pg_num = OxmlElement("w:pgNumType")
        body_sectPr.append(pg_num)
    pg_num.set(qn("w:start"), "1")
    doc_grid = body_sectPr.find(qn("w:docGrid"))
    if doc_grid is not None:
        doc_grid.set(qn("w:type"), "none")

    # 0) Remove the TOC page's footer page number: front matter should not be
    #    numbered with Arabic digits, otherwise the TOC and body both show "1".
    toc_footer = doc.sections[2].footer
    toc_footer.is_linked_to_previous = False
    for paragraph in toc_footer.paragraphs:
        for child in list(paragraph._p):
            if child.tag != qn("w:pPr"):
                paragraph._p.remove(child)

    # 1) Remove the course notification (original body children 0--18).
    children = list(body)
    for child in children[:19]:
        body.remove(child)

    # 2) Remove the TOC instruction paragraph.
    for child in list(body):
        if child.tag == qn("w:p") and "后面按格式完成后" in "".join(child.itertext()):
            body.remove(child)
            break

    # 3) Remove the sample body/references/appendix from the body title onward.
    body_start = None
    for idx, child in enumerate(list(body)):
        if child.tag == qn("w:p") and "XXXX程序设计" in "".join(child.itertext()):
            body_start = idx
            break
    if body_start is None:
        raise RuntimeError("could not find the sample body title 'XXXX程序设计'")
    for child in list(body)[body_start:]:
        body.remove(child)

    # 4) Append the saved body section properties and a bookmark paragraph.
    body.append(body_sectPr)
    bookmark_p = OxmlElement("w:p")
    bookmark_start = OxmlElement("w:bookmarkStart")
    bookmark_start.set(qn("w:id"), "9001")
    bookmark_start.set(qn("w:name"), "BODY_INSERT")
    bookmark_end = OxmlElement("w:bookmarkEnd")
    bookmark_end.set(qn("w:id"), "9001")
    bookmark_p.append(bookmark_start)
    bookmark_p.append(bookmark_end)
    body.insert(len(body) - 1, bookmark_p)

    doc.save(OUT)

    check = Document(OUT)
    print(f"wrote {OUT}")
    print(f"sections={len(check.sections)}")
    for i, section in enumerate(check.sections):
        print(
            f"  section {i}: margins L/R={section.left_margin.cm:.2f}/"
            f"{section.right_margin.cm:.2f} T/B={section.top_margin.cm:.2f}/"
            f"{section.bottom_margin.cm:.2f}"
        )
    print("has BODY_INSERT:", "BODY_INSERT" in check.element.xml)
    print("has TOC field:", "TOC \\o" in check.element.xml or "TOC \\\\o" in check.element.xml)


if __name__ == "__main__":
    main()
