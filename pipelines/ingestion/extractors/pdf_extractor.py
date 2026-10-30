import pdfplumber
import pypdfium2 as pdfium
import pytesseract

from pipelines.ingestion.extractors import ExtractedPage, rows_to_markdown

MIN_TEXT_CHARS = 50
OCR_SCALE = 300 / 72


def extract_pdf(path: str) -> list[ExtractedPage]:
    pages: list[ExtractedPage] = []

    pdf = pdfium.PdfDocument(path)
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            number = index + 1
            text = page.get_textpage().get_text_range().strip()
            scanned = len(text) < MIN_TEXT_CHARS
            if scanned:
                image = page.render(scale=OCR_SCALE).to_pil()
                text = pytesseract.image_to_string(image, config="--psm 6").strip()
            if text:
                pages.append(ExtractedPage(number, text, "text", {"page": number, "ocr": scanned}))
    finally:
        pdf.close()

    with pdfplumber.open(path) as plumber:
        for index, page in enumerate(plumber.pages):
            for table_no, table in enumerate(page.extract_tables(), start=1):
                markdown = rows_to_markdown(table)
                if markdown:
                    pages.append(
                        ExtractedPage(index + 1, markdown, "table", {"page": index + 1, "table_index": table_no})
                    )

    pages.sort(key=lambda p: p.page_number)
    return pages