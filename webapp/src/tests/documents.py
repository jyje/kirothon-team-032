"""테스트용 문서 만들기: 텍스트가 든 PDF, 암호 PDF, PPTX."""

from __future__ import annotations

import io

from pptx import Presentation
from pypdf import PdfWriter


def make_pdf(pages: list[str]) -> bytes:
    """쪽마다 영문 텍스트 한 줄이 든 PDF. 빈 문자열은 텍스트 없는 쪽이 된다."""
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # 1번 자리. 나중에 채운다
    pages_obj = add(b"")  # 2번 자리
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids: list[int] = []
    for text in pages:
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode() if text else b""
        content = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        page = add(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (font, content)
        )
        kids.append(page)
    objects[catalog - 1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    refs = b" ".join(b"%d 0 R" % k for k in kids)
    objects[pages_obj - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (refs, len(kids))

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    )
    return out.getvalue()


def make_encrypted_pdf(password: str = "secret") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_pptx(slides: list[str]) -> bytes:
    deck = Presentation()
    for text in slides:
        slide = deck.slides.add_slide(deck.slide_layouts[5])  # 제목만 있는 레이아웃
        slide.shapes.title.text = text
    out = io.BytesIO()
    deck.save(out)
    return out.getvalue()
