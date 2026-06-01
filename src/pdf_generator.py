from __future__ import annotations

import html
import re
from pathlib import Path


def _strip_html(text: str) -> str:
    value = re.sub(r"<[^>]+>", " ", text)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _chunk_lines(lines: list[str], size: int = 42) -> list[list[str]]:
    return [lines[index : index + size] for index in range(0, len(lines), size)] or [[]]


def _build_text_pdf(path: Path, title: str, text: str) -> Path:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = ["(empty report)"]
    pages = _chunk_lines(lines)
    objects: dict[int, bytes] = {}
    object_no = 1
    objects[object_no] = b"<< /Type /Catalog /Pages 2 0 R >>"
    object_no += 1
    font_obj = 3
    objects[2] = b"<< /Type /Pages /Kids [] /Count 0 >>"
    objects[font_obj] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    next_obj = 4
    page_object_numbers: list[int] = []
    content_object_numbers: list[int] = []
    for _ in pages:
        content_object_numbers.append(next_obj)
        next_obj += 1
        page_object_numbers.append(next_obj)
        next_obj += 1

    for page_index, chunk in enumerate(pages):
        content_no = content_object_numbers[page_index]
        page_no = page_object_numbers[page_index]
        text_lines = [
            "BT",
            "/F1 14 Tf",
            "40 780 Td",
            f"({_escape_pdf_text(title[:90])}) Tj",
            "/F1 10 Tf",
            "0 -22 Td",
        ]
        for line in chunk:
            text_lines.append(f"({_escape_pdf_text(line[:120])}) Tj")
            text_lines.append("0 -14 Td")
        text_lines.append("ET")
        stream = "\n".join(text_lines).encode("utf-8")
        objects[content_no] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("utf-8") + stream + b"\nendstream"
        )
        objects[page_no] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_no} 0 R >>"
        ).encode("utf-8")

    kids = " ".join(f"{page_no} 0 R" for page_no in page_object_numbers)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("utf-8")

    ordered_numbers = sorted(objects)
    xref_positions: dict[int, int] = {}
    output = bytearray(b"%PDF-1.4\n")
    for number in ordered_numbers:
        xref_positions[number] = len(output)
        output.extend(f"{number} 0 obj\n".encode("utf-8"))
        output.extend(objects[number])
        if not objects[number].endswith(b"\n"):
            output.extend(b"\n")
        output.extend(b"endobj\n")
    xref_start = len(output)
    max_obj = max(ordered_numbers)
    output.extend(f"xref\n0 {max_obj + 1}\n".encode("utf-8"))
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, max_obj + 1):
        position = xref_positions.get(number, 0)
        output.extend(f"{position:010d} 00000 n \n".encode("utf-8"))
    output.extend(
        (
            "trailer\n"
            f"<< /Size {max_obj + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode("utf-8")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)
    return path


def write_customer_pdf(html_path: Path, pdf_path: Path, *, title: str = "") -> Path:
    html_text = html_path.read_text(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return _build_text_pdf(pdf_path, title or html_path.stem, _strip_html(html_text))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(html_path.as_uri(), wait_until="load")
            page.emulate_media(media="screen")
            page.pdf(path=str(pdf_path), format="A4", print_background=True, prefer_css_page_size=True)
            browser.close()
            return pdf_path
    except Exception:
        return _build_text_pdf(pdf_path, title or html_path.stem, _strip_html(html_text))
