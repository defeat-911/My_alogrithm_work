"""Merge a body-only DOCX into the 4-section course-template base.

Usage:
    python docs/report/merge_into_template.py ^
        --base docs/report/report_base.docx ^
        --body docs/report/sample_body.docx ^
        --out-docx docs/report/sample_merged.docx ^
        --out-pdf docs/report/sample_merged.pdf
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import win32com.client


def _page_of(doc, needle: str) -> int | None:
    for paragraph in doc.Paragraphs:
        style_name = str(paragraph.Style.NameLocal).lower()
        if "toc" in style_name:
            continue
        text = paragraph.Range.Text.strip()
        if needle in text:
            return int(paragraph.Range.Information(3))  # wdActiveEndPageNumber
    return None


def merge(base: Path, body: Path, out_docx: Path, out_pdf: Path) -> None:
    out_docx.parent.mkdir(parents=True, exist_ok=True)
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    doc = None
    body_doc = None
    try:
        doc = word.Documents.Open(str(base.resolve()))
        if doc.Sections.Count != 4:
            raise RuntimeError(f"base sections={doc.Sections.Count}, expected 4")
        if not doc.Bookmarks.Exists("BODY_INSERT"):
            raise RuntimeError("BODY_INSERT bookmark not found")

        body_doc = word.Documents.Open(str(body.resolve()), False, True)
        # Exclude the final paragraph mark so the source sectPr is not copied.
        src_end = max(0, body_doc.Content.End - 1)
        src = body_doc.Range(0, src_end)
        src.Copy()

        rng = doc.Bookmarks("BODY_INSERT").Range
        rng.Select()
        rng.PasteAndFormat(16)  # wdFormatOriginalFormatting
        body_doc.Close(False)
        body_doc = None

        if doc.Sections.Count != 4:
            raise RuntimeError(
                f"after paste sections={doc.Sections.Count}, expected 4"
            )

        # Front matter: the TOC section uses uppercase Roman numerals (I).
        toc_footer = doc.Sections(3).Footers(1)
        toc_footer.PageNumbers.RestartNumberingAtSection = True
        toc_footer.PageNumbers.StartingNumber = 1
        toc_footer.PageNumbers.NumberStyle = 1  # wdPageNumberStyleUppercaseRoman

        # Ensure the body section restarts at page 1 and has a PAGE field.
        body_section = doc.Sections(4)
        footer = body_section.Footers(1)
        footer.PageNumbers.RestartNumberingAtSection = True
        footer.PageNumbers.StartingNumber = 1
        footer.PageNumbers.NumberStyle = 0  # wdPageNumberStyleArabic
        if "PAGE" not in footer.Range.Text and not footer.Range.Fields.Count:
            footer.Range.Fields.Add(footer.Range, 33)  # wdFieldPage
        footer.Range.ParagraphFormat.Alignment = 1  # wdAlignParagraphCenter

        # Update fields and TOC twice (page numbers need a repagination pass).
        doc.Fields.Update()
        if doc.TablesOfContents.Count:
            doc.TablesOfContents(1).Update()
            doc.Repaginate()
            doc.TablesOfContents(1).Update()
        doc.Repaginate()

        total_pages = int(doc.ComputeStatistics(2))
        first_page = _page_of(doc, "一、需求分析")
        refs_page = _page_of(doc, "参考文献")
        appendix_page = _page_of(doc, "附录")
        print(f"SECTIONS={doc.Sections.Count}")
        print(f"PAGES_TOTAL={total_pages}")
        print(f"FIRST_CHAPTER_PAGE={first_page}")
        print(f"REFERENCES_PAGE={refs_page}")
        print(f"APPENDIX_PAGE={appendix_page}")
        if first_page and refs_page:
            print(f"BODY_PAGES={refs_page - first_page}")

        doc.SaveAs2(str(out_docx.resolve()), 16)
        doc.ExportAsFixedFormat(str(out_pdf.resolve()), 17)
        print(f"wrote {out_docx}")
        print(f"wrote {out_pdf}")
    finally:
        if body_doc is not None:
            body_doc.Close(False)
        if doc is not None:
            doc.Close(False)
        word.Quit()
        try:
            import pythoncom

            pythoncom.CoUninitialize()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="docs/report/report_base.docx")
    parser.add_argument("--body", default="docs/report/sample_body.docx")
    parser.add_argument("--out-docx", default="docs/report/sample_merged.docx")
    parser.add_argument("--out-pdf", default="docs/report/sample_merged.pdf")
    args = parser.parse_args()
    merge(
        Path(args.base),
        Path(args.body),
        Path(args.out_docx),
        Path(args.out_pdf),
    )


if __name__ == "__main__":
    main()
