# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Uploaded resumes and cover letters: recognise the file type, pull the text out, and convert between formats.

Type is decided from the file's own bytes, never from its name or the browser's claim.
Conversion uses headless LibreOffice, one conversion at a time, with a hard time limit.
"""
import html
import io
import os
import re
import subprocess
import tempfile
import threading
import unicodedata
import zipfile
from pathlib import Path

MAX_BYTES = 5_000_000
MAX_TEXT = 100_000

# What can be uploaded, and what it can be converted to (extension -> name shown to people).
UPLOAD_TYPES = ("pdf", "docx", "doc", "odt", "rtf", "txt")
TARGETS = {"pdf": "PDF", "docx": "Word (.docx)", "doc": "Word 97-2003 (.doc)", "rtf": "Rich Text (.rtf)",
           "odt": "OpenDocument (.odt)", "txt": "Plain text (.txt)"}
MIME = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword", "rtf": "application/rtf", "odt": "application/vnd.oasis.opendocument.text",
        "txt": "text/plain; charset=utf-8"}
# LibreOffice output filter for each target.
FILTERS = {"pdf": "pdf:writer_pdf_Export", "docx": "docx:MS Word 2007 XML", "doc": "doc:MS Word 97", "rtf": "rtf:Rich Text Format",
           "odt": "odt:writer8", "txt": "txt:Text (encoded):UTF8"}


def sniff(data):
    """Return one of UPLOAD_TYPES judged from the bytes themselves, or None."""
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "doc"                                   # legacy Office container (we only accept it as a Word file)
    if data[:5] == b"{\\rtf":
        return "rtf"
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "word/document.xml" in names:
                    return "docx"
                if "content.xml" in names and "mimetype" in names and z.read("mimetype")[:60] == b"application/vnd.oasis.opendocument.text":
                    return "odt"
        except (zipfile.BadZipFile, KeyError, RuntimeError):
            return None
        return None
    if b"\x00" not in data[:4096]:
        try:
            data.decode("utf-8")
            return "txt"
        except UnicodeDecodeError:
            return None
    return None


def safe_name(name, ext):
    """A tidy display/download file name that can't carry path tricks or header injection."""
    plain = unicodedata.normalize("NFKD", Path(str(name)).stem).encode("ascii", "ignore").decode()   # é -> e
    stem = re.sub(r"[^A-Za-z0-9._ ()-]", "_", plain)[:80].strip(" ._") or "document"
    return f"{stem}.{ext}"


# ------------------------------------------------------------------ text extraction
def docx_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.getinfo("word/document.xml").file_size > 40_000_000:
            raise ValueError("document too large")
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    lines = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):       # plain pattern matching: no XML parser to abuse
        parts = []
        for m in re.finditer(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:tab\s*/>|<w:(?:br|cr)\s*/>", para, re.S):
            parts.append(html.unescape(m.group(1)) if m.group(1) is not None else ("\t" if "tab" in m.group(0) else "\n"))
        lines.append("".join(parts))
    return "\n".join(lines)


def pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("this PDF is password-protected")
    return "\n\n".join((page.extract_text() or "") for page in reader.pages[:60])


def extract_text(data, ext):
    """Best-effort text from an uploaded file. Raises ValueError with a person-readable reason."""
    try:
        if ext == "txt":
            text = data.decode("utf-8", "ignore")
        elif ext == "docx":
            text = docx_text(data)
        elif ext == "pdf":
            text = pdf_text(data)
        else:                                          # doc, odt, rtf: let LibreOffice read them
            text = convert(data, ext, "txt").decode("utf-8", "ignore")
            if len(text.strip()) < 20:                 # text kept in floating boxes is skipped by that export; read a rendered copy
                text = pdf_text(convert(data, ext, "pdf"))
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"couldn't read this file ({type(e).__name__})")
    text = re.sub(r"[ \t]+\n", "\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    return text[:MAX_TEXT]


# ------------------------------------------------------------------ conversion
_LOCK = threading.Lock()
PROFILE_DIR = Path(os.environ.get("LO_PROFILE", "/tmp/lo-profile"))


def convert(data, src_ext, to_ext, timeout=90):
    """Convert a document with headless LibreOffice and return the new file's bytes."""
    if to_ext not in FILTERS or src_ext not in UPLOAD_TYPES or src_ext == to_ext:
        raise ValueError("unsupported conversion")
    with _LOCK, tempfile.TemporaryDirectory(prefix="conv-") as work:     # one at a time keeps memory in check
        src = Path(work) / f"in.{src_ext}"
        src.write_bytes(data if src_ext != "txt" else b"\xef\xbb\xbf" + data.lstrip(b"\xef\xbb\xbf"))   # BOM: read as UTF-8
        out = Path(work) / "out"
        cmd = ["soffice", "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo",
               f"-env:UserInstallation=file://{PROFILE_DIR}"]
        if src_ext == "pdf":
            cmd.append("--infilter=writer_pdf_import")  # open the PDF as an editable document, not as a drawing
        cmd += ["--convert-to", FILTERS[to_ext], "--outdir", str(out), str(src)]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": work, "LANG": "C.UTF-8"}
        try:
            subprocess.run(cmd, cwd=work, env=env, capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["pkill", "-f", "soffice"], capture_output=True)
            raise ValueError("the conversion took too long")
        result = out / f"in.{to_ext}"
        if not result.exists() or result.stat().st_size == 0:
            raise ValueError("this file couldn't be converted")
        if result.stat().st_size > 25_000_000:
            raise ValueError("the converted file is too large")
        return result.read_bytes()
