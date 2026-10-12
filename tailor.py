# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: MIT
"""Make a tailored COPY of a Word resume with extra keywords the person confirmed they really have.

The keywords go on one added line right under the resume's Skills section (or at the end if there isn't one),
in the same formatting as the paragraph above it. The stored original is never touched.
"""
import html
import io
import re
import zipfile

SKILL_HEADS = {"skills", "key skills", "technical skills", "core skills", "core competencies", "skills summary", "areas of expertise"}
ACRONYMS = {"sql", "aws", "api", "gis", "erp", "sap", "dns", "dhcp", "vpn", "itil", "wsib", "cpr", "scada", "tcp/ip", "c#", ".net"}
TERM_OK = re.compile(r"[A-Za-z0-9][A-Za-z0-9 +#./&()-]{0,39}")
PARA = re.compile(r"<w:p[ >].*?</w:p>", re.S)


def pretty(term):
    t = term.strip()
    if t.lower() in ACRONYMS:
        return t.upper() if t.lower() not in ("c#", ".net") else ("C#" if t.lower() == "c#" else ".NET")
    return t if any(c.isupper() for c in t) else " ".join(w.capitalize() for w in t.split())


def clean_terms(terms):
    out = []
    for t in terms if isinstance(terms, list) else []:
        if isinstance(t, str) and TERM_OK.fullmatch(t.strip()):
            p = pretty(t)
            if p.lower() not in {x.lower() for x in out}:
                out.append(p)
    return out[:15]


def _text(p):
    return html.unescape("".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", p, re.S)))


def _para_xml(like, line):
    ppr = re.search(r"<w:pPr>.*?</w:pPr>", like, re.S)
    rpr = re.search(r"<w:r[ >].*?(<w:rPr>.*?</w:rPr>)", like, re.S)
    return ("<w:p>" + (ppr.group(0) if ppr else "") + "<w:r>" + (rpr.group(1) if rpr else "") +
            f'<w:t xml:space="preserve">{html.escape(line, quote=False)}</w:t></w:r></w:p>')


def add_keywords(docx, terms):
    """-> (new docx bytes, where) where is "skills" or "end". Raises ValueError if nothing can be added."""
    terms = clean_terms(terms)
    if not terms:
        raise ValueError("no usable keywords")
    with zipfile.ZipFile(io.BytesIO(docx)) as zin:
        xml = zin.read("word/document.xml").decode("utf-8")
        paras = list(PARA.finditer(xml))
        line = "Additional keywords: " + ", ".join(terms)
        at, like, where = None, None, "end"
        for i, m in enumerate(paras):
            if _text(m.group(0)).strip().rstrip(":").lower() in SKILL_HEADS:
                last = None
                for n in paras[i + 1:]:
                    t = _text(n.group(0)).strip()
                    if t and ((t.isupper() and len(t) < 40) or "<w:pStyle w:val=\"Heading" in n.group(0)):
                        break
                    if t:
                        last = n
                if last is not None:
                    at, like, where = last.end(), last.group(0), "skills"
                break
        if at is None:
            body_end = xml.rfind("<w:sectPr")
            body_end = body_end if body_end != -1 else xml.rfind("</w:body>")
            like = next((m.group(0) for m in reversed(paras) if _text(m.group(0)).strip()), "")
            at = body_end
        new = xml[:at] + _para_xml(like, line) + xml[at:]
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                zout.writestr(item, new.encode("utf-8") if item.filename == "word/document.xml" else zin.read(item.filename))
    return out.getvalue(), where


def add_keywords_text(text, terms):
    """Same idea for a plain-text resume: one added line under the Skills heading, or at the end."""
    terms = clean_terms(terms)
    if not terms:
        raise ValueError("no usable keywords")
    line = "Additional keywords: " + ", ".join(terms)
    lines = text.replace("\r\n", "\n").split("\n")
    for i, l in enumerate(lines):
        if l.strip().rstrip(":").lower() in SKILL_HEADS:
            j = i + 1
            while j < len(lines) and lines[j].strip() and not (lines[j].strip().isupper() and len(lines[j].strip()) < 40):
                j += 1
            lines.insert(j, line)
            return "\n".join(lines)
    return text.rstrip("\n") + "\n\n" + line + "\n"


SUMMARY_HEADS = {"profile", "summary", "professional summary", "career summary", "objective", "about me", "personal profile"}


def _swap_summary(xml, text):
    """Replace the first paragraph under the summary heading with `text`, keeping that paragraph's formatting. -> (xml, done)"""
    paras = list(PARA.finditer(xml))
    for i, m in enumerate(paras):
        if _text(m.group(0)).strip().rstrip(":").lower() in SUMMARY_HEADS:
            for n in paras[i + 1:]:
                if _text(n.group(0)).strip():
                    old = n.group(0)
                    ppr = re.search(r"<w:pPr>.*?</w:pPr>", old, re.S)
                    rpr = re.search(r"<w:r[ >].*?(<w:rPr>.*?</w:rPr>)", old, re.S)
                    new = ("<w:p>" + (ppr.group(0) if ppr else "") + "<w:r>" + (rpr.group(1) if rpr else "") +
                           f'<w:t xml:space="preserve">{html.escape(text, quote=False)}</w:t></w:r></w:p>')
                    return xml[:n.start()] + new + xml[n.end():], True
            break
    return xml, False


def add_highlights(docx, lines):
    """Insert a 'Relevant highlights' section of lines taken from the resume, right after its summary (or before Skills). -> (bytes, bool)"""
    lines = [" ".join(str(x).split()) for x in lines if str(x).strip()][:6]
    if not lines:
        return docx, False
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
        paras = list(PARA.finditer(xml))
        at = head = body = None
        for i, m in enumerate(paras):
            if _text(m.group(0)).strip().rstrip(":").lower() in SUMMARY_HEADS:
                nxt = next((n for n in paras[i + 1:] if _text(n.group(0)).strip()), None)
                if nxt is not None:
                    at, head, body = nxt.end(), m.group(0), nxt.group(0)
                break
        if at is None:
            for i, m in enumerate(paras):
                if _text(m.group(0)).strip().rstrip(":").lower() in SKILL_HEADS:
                    nxt = next((n for n in paras[i + 1:] if _text(n.group(0)).strip()), None)
                    if nxt is not None:
                        at, head, body = m.start(), m.group(0), nxt.group(0)
                    break
        if at is None:
            return docx, False
        block = _para_xml(head, "RELEVANT HIGHLIGHTS") + "".join(_para_xml(body, "\u2022 " + ln) for ln in lines)
        new = xml[:at] + block + xml[at:]
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in z.infolist():
                zout.writestr(item, new.encode("utf-8") if item.filename == "word/document.xml" else z.read(item.filename))
    return out.getvalue(), True


def customize(docx, summary="", terms=(), highlights=()):
    """A tailored copy of a Word resume: new summary paragraph (if the resume has a summary section) and a keywords line.
    -> (bytes, {"summary": bool, "keywords": "skills|end|none"})"""
    summary = " ".join((summary or "").split())[:700]
    terms = clean_terms(list(terms))
    done = {"summary": False, "keywords": "none", "highlights": False}
    if summary:
        with zipfile.ZipFile(io.BytesIO(docx)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
            new, ok = _swap_summary(xml, summary)
            if ok:
                out = io.BytesIO()
                with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                    for item in z.infolist():
                        zout.writestr(item, new.encode("utf-8") if item.filename == "word/document.xml" else z.read(item.filename))
                docx, done["summary"] = out.getvalue(), True
    if highlights:
        docx, done["highlights"] = add_highlights(docx, highlights)
    if terms:
        docx, done["keywords"] = add_keywords(docx, terms)
    return docx, done
