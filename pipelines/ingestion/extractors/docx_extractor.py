from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from pipelines.ingestion.extractors import ExtractedPage, rows_to_markdown


def _heading_level(paragraph: Paragraph) -> int | None:
    name = paragraph.style.name if paragraph.style is not None else ""
    if name == "Title":
        return 1
    if name.startswith("Heading "):
        try:
            return int(name.split()[1])
        except ValueError:
            return None
    return None


def extract_docx(path: str) -> list[ExtractedPage]:
    doc = Document(path)
    pages: list[ExtractedPage] = []
    current = {"level": "h0", "section": "Document start"}
    lines: list[str] = []

    def add(content: str, content_type: str, meta: dict) -> None:
        pages.append(ExtractedPage(len(pages) + 1, content, content_type, meta))

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            add(text, "text", dict(current))
        lines.clear()

    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            if not text:
                continue
            level = _heading_level(paragraph)
            if level is not None:
                flush()
                current = {"level": f"h{level}", "section": text}
            lines.append(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, doc)
            markdown = rows_to_markdown([[cell.text for cell in row.cells] for row in table.rows])
            if markdown:
                add(markdown, "table", {**current, "part": "table"})
    flush()

    seen: set[str] = set()
    for section in doc.sections:
        header_text = "\n".join(p.text.strip() for p in section.header.paragraphs if p.text.strip())
        if header_text and header_text not in seen:
            seen.add(header_text)
            add(header_text, "text", {"level": "header", "section": "header", "part": "header"})

    return pages