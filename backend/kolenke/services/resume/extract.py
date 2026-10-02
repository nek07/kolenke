"""Plain text from a resume file: PDF, DOCX, TXT/MD. Old binary .doc is not supported (ask to save as DOCX or PDF)."""
import io
import re
import zipfile
from xml.etree import ElementTree

MAX_BYTES = 10 * 1024 * 1024
TYPES = (".pdf", ".docx", ".txt", ".md")


class ExtractError(ValueError):
    """A message for you: why the file could not be read."""


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if len(data) > MAX_BYTES:
        raise ExtractError("Файл больше 10 МБ")
    if name.endswith(".doc"):
        raise ExtractError("Старый формат .doc не читается: сохраните резюме как PDF или DOCX, или вставьте текст")
    if name.endswith(".pdf"):
        text = _pdf(data)
    elif name.endswith(".docx"):
        text = _docx(data)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8-sig", errors="replace")
    else:
        raise ExtractError("Нужен PDF, DOCX или TXT")
    text = clean(text)
    if len(text) < 80:
        raise ExtractError("В файле почти нет текста. Если это скан, вставьте текст резюме вручную")
    return text


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractError("PDF защищён паролем")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ExtractError:
        raise
    # a broken or AES-encrypted file fails anywhere inside pypdf, not only with PdfReadError
    except (PyPdfError, DependencyError, KeyError, ValueError, TypeError, AttributeError, IndexError) as e:
        raise ExtractError("Не удалось прочитать PDF") from e


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx(data: bytes) -> str:
    """Paragraphs of word/document.xml, table cells included; no dependency needed."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
        raise ExtractError("Не удалось прочитать DOCX") from e
    lines = []
    for p in root.iter(_W + "p"):
        parts = []
        for node in p.iter():
            if node.tag == _W + "t" and node.text:
                parts.append(node.text)
            elif node.tag in (_W + "tab",):
                parts.append(" ")
            elif node.tag in (_W + "br", _W + "cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines)
