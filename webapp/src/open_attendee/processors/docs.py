"""`DocExtractor`: 발표자료와 참고자료에서 텍스트를 뽑아 `DocChunk`로 나눈다(요구사항 6, 7).

추출한 텍스트는 데이터로만 다룬다. 프롬프트에 넣을 때의 구분자 처리는 파이프라인(9.2) 몫이다.
스캔본처럼 텍스트가 없는 PDF는 조각이 0개인 결과로 알린다(OCR은 2단계).
"""

from __future__ import annotations

import binascii
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from struct import error as struct_error
from typing import BinaryIO, Final
from zipfile import BadZipFile, ZipFile

from lxml.etree import XMLSyntaxError
from pptx import Presentation
from pptx.exc import PackageNotFoundError
from pptx.shapes.base import BaseShape
from pptx.shapes.graphfrm import GraphicFrame
from pptx.shapes.group import GroupShape
from pypdf import PdfReader
from pypdf.errors import DependencyError, PyPdfError

from open_attendee.errors import PayloadTooLarge, ValidationFailed
from open_attendee.models import Asset, AssetKind, DocChunk

MAX_CHUNK_CHARS: Final = 2000  # 한 조각의 글자 수 상한(요구사항 6.2)

PDF_MIME: Final = "application/pdf"
TEXT_MIME: Final = "text/plain"
MARKDOWN_MIME: Final = "text/markdown"
PPTX_MIME: Final = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_MAX_PPTX_EXPANDED_BYTES: Final = 256 * 1024 * 1024
_MAX_PPTX_PARTS: Final = 20_000

_SUPPORTED: Final[dict[AssetKind, frozenset[str]]] = {
    AssetKind.SLIDES: frozenset({PDF_MIME, PPTX_MIME}),
    AssetKind.REFERENCE: frozenset({PDF_MIME, TEXT_MIME, MARKDOWN_MIME}),
}

# pypdf가 깨진 파일에서 낼 수 있는 오류. 종류가 많아서 한꺼번에 묶는다.
_PDF_ERRORS: Final = (
    PyPdfError,
    DependencyError,
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    AttributeError,
    ArithmeticError,
    RecursionError,
    NotImplementedError,
    OSError,
    EOFError,
    struct_error,
    zlib.error,
    binascii.Error,
)
_TEXT_ENCODINGS: Final = ("utf-8-sig", "cp949")  # cp949: 예전 한국어 메모장 파일


class CorruptDocument(ValidationFailed):
    """깨졌거나 읽을 수 없는 문서. 라우터가 422로 바꾼다."""


class EncryptedDocument(ValidationFailed):
    """암호로 잠긴 PDF. 라우터가 422로 바꾼다(요구사항 6.4)."""


@dataclass(frozen=True)
class Extraction:
    chunks: list[DocChunk]
    page_count: int

    @property
    def no_text(self) -> bool:
        """텍스트가 하나도 없다. 자료는 저장하고 화면에 "텍스트 없음"으로 보여 준다."""
        return not self.chunks


_ENCRYPTED_MESSAGE: Final = "암호로 잠긴 PDF는 올릴 수 없어요. 암호를 풀고 올려 주세요."


def _needs_password(reader: PdfReader) -> bool:
    """열람 암호가 필요한 PDF인가. 암호가 비어 있어 열리는 PDF는 거짓이다."""
    return reader.is_encrypted and not reader.decrypt("")


def split_text(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """`limit`자 이하 조각으로 나눈다. 줄바꿈, 공백 순으로 끊을 자리를 찾고 없으면 그대로 자른다.

    조각은 앞뒤 공백을 뺀 비어 있지 않은 문자열이다. 공백을 뺀 내용을 이어 붙이면 원문과 같다.
    """
    floor = max(limit // 2, 1)  # 이보다 앞에서는 끊지 않는다(너무 작은 조각 방지)
    parts: list[str] = []
    rest = text.strip()
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        window = rest[: limit + 1]  # 끊을 자리가 limit 바로 뒤의 공백일 수도 있다
        cut = max(window.rfind("\n", floor), window.rfind(" ", floor), window.rfind("\t", floor))
        if cut < floor:
            cut = limit
        piece, rest = rest[:cut].strip(), rest[cut:].strip()
        if piece:
            parts.append(piece)
    return parts


def _clean(text: str) -> str:
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def _shape_texts(shapes: Iterable[BaseShape]) -> Iterator[str]:
    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _shape_texts(shape.shapes)
        elif isinstance(shape, GraphicFrame) and shape.has_table:
            for row in shape.table.rows:
                yield " ".join(cell.text for cell in row.cells if not cell.is_spanned)
        elif shape.has_text_frame:
            yield shape.text_frame.text.replace("\v", "\n")


class DocExtractor:
    @staticmethod
    def supports(mime: str, kind: AssetKind) -> bool:
        """이 종류의 자료로 받아 텍스트를 뽑을 수 있는 형식인가."""
        return mime in _SUPPORTED.get(kind, frozenset())

    def extract(self, asset: Asset, data: BinaryIO) -> Extraction:
        """PDF와 PPTX는 페이지 순서대로, 텍스트 파일은 한 페이지로 나눈다."""
        if not self.supports(asset.mime, asset.kind):
            raise CorruptDocument("텍스트를 뽑을 수 없는 형식이에요.")
        if asset.mime == PDF_MIME:
            pages = self._pdf_pages(data)
        elif asset.mime == PPTX_MIME:
            pages = self._pptx_pages(data)
        else:
            pages = [self._plain_text(data)]
        chunks = [
            DocChunk(asset_id=asset.id, page=number, part=part, text=piece)
            for number, text in enumerate(pages, start=1)
            for part, piece in enumerate(split_text(_clean(text)))
        ]
        return Extraction(chunks, page_count=len(pages))

    # ------------------------------------------------------------------ 형식별 읽기

    def _pptx_pages(self, data: BinaryIO) -> list[str]:
        try:
            with ZipFile(data) as archive:
                parts = archive.infolist()
                if (
                    len(parts) > _MAX_PPTX_PARTS
                    or sum(part.file_size for part in parts) > _MAX_PPTX_EXPANDED_BYTES
                ):
                    raise PayloadTooLarge("PPTX 압축을 풀었을 때 자료의 크기 한도를 넘어요.")
            data.seek(0)
            return ["\n".join(_shape_texts(slide.shapes)) for slide in Presentation(data).slides]
        except (
            BadZipFile,
            PackageNotFoundError,
            XMLSyntaxError,
            zlib.error,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
        ) as exc:
            raise CorruptDocument("PPTX 파일이 깨졌거나 읽을 수 없어요.") from exc

    def _pdf_pages(self, data: BinaryIO) -> list[str]:
        try:
            reader = PdfReader(data)
            if _needs_password(reader):
                raise EncryptedDocument(_ENCRYPTED_MESSAGE)  # noqa: TRY301
            return [page.extract_text() or "" for page in reader.pages]
        except EncryptedDocument:
            raise
        except DependencyError as exc:
            # AES 암호 PDF를 풀 라이브러리가 없다. 사용자에게는 같은 안내가 맞다.
            raise EncryptedDocument(_ENCRYPTED_MESSAGE) from exc
        except _PDF_ERRORS as exc:
            # 라이브러리 메시지에는 파일 내용이 섞일 수 있어서 종류만 남긴다.
            raise CorruptDocument("PDF 파일이 깨졌거나 읽을 수 없어요.") from exc

    def _plain_text(self, data: BinaryIO) -> str:
        raw = data.read()
        for encoding in _TEXT_ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise CorruptDocument("텍스트 파일의 문자 인코딩을 읽을 수 없어요. UTF-8로 저장해 주세요.")
