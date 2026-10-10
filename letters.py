# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Cover letter and resume customisation for one posting, written by the local text model from the resume's plain text.

The model writes only the body paragraphs and a short resume summary. Everything else (sender and employer blocks, date,
greeting, sign-off) is assembled here so it can't be garbled. Nothing the resume doesn't say is supposed to appear, and
`unsupported_numbers` flags any figure in the draft that isn't in the resume or the posting so the person can check it.
"""
import io
import json
import re
import zipfile
from datetime import date
from xml.sax.saxutils import escape

import llm
import match

SYSTEM = ("You write job application material for the candidate, in the first person. Use ONLY facts stated in the candidate's resume. "
          "Never invent employers, job titles, numbers, certifications, tools, dates or achievements. If the posting asks for something "
          "the resume does not show, simply do not claim it. Canadian spelling (centre, colour, behaviour, analyse, -ize endings, cancelled, licence as the noun). Plain, specific and professional: no cliches, no "
          "flattery, no placeholders, no square brackets. Never write 'my resume' or 'as stated in my resume'; just state the experience as the candidate's own.")


TONES = {"professional": "Professional and confident.", "warm": "Warm, personable and genuine, still professional.",
         "concise": "Brief and direct: about 150 words."}


# US -> Canadian spellings for text the model writes (never applied to the person's own resume lines). Canadian English keeps -ize
# but uses -our, -re, -yse, a double l in past tenses, and a few others. Whole words, so nothing is guessed from word endings.
_CA = dict(
    color="colour", colors="colours", colored="coloured", coloring="colouring", colorful="colourful",
    behavior="behaviour", behaviors="behaviours", behavioral="behavioural",
    favor="favour", favors="favours", favored="favoured", favorite="favourite", favorites="favourites",
    honor="honour", honorable="honourable", honors="honours", honored="honoured", labor="labour", neighbor="neighbour", neighbors="neighbours",
    neighborhood="neighbourhood", center="centre", centers="centres", centered="centred", centering="centring",
    defense="defence", offense="offence", catalog="catalogue", catalogs="catalogues", fulfill="fulfil", fulfills="fulfils",
    fulfillment="fulfilment", enrollment="enrolment", skillful="skilful", gray="grey", fiber="fibre", fibers="fibres",
    theater="theatre", counselor="counsellor", counselors="counsellors", analyze="analyse", analyzes="analyses", analyzed="analysed",
    analyzing="analysing", analyzer="analyser", traveling="travelling", traveled="travelled", traveler="traveller",
    canceled="cancelled", canceling="cancelling", cancelation="cancellation", labeled="labelled", labeling="labelling",
    modeling="modelling", modeled="modelled", leveling="levelling", signaling="signalling", ambiance="ambience",
    plow="plough", mold="mould", pajamas="pyjamas", aluminum="aluminium", sulfur="sulphur", mom="mum")
del _CA["mom"]
_CA_RE = re.compile(r"\b(" + "|".join(sorted(_CA, key=len, reverse=True)) + r")\b", re.I)


def canadian(text):
    """Respell model-written text the Canadian way: user-centered -> user-centred, color -> colour, analyzing -> analysing."""
    def fix(m):
        w = m.group(0)
        new = _CA[w.lower()]
        return new.upper() if w.isupper() and len(w) > 1 else new.capitalize() if w[0].isupper() else new
    return _CA_RE.sub(fix, text)


def cover_body(resume, posting, title, employer, tone="professional"):
    prompt = (TONES.get(tone, TONES["professional"]) + " " +f"Write the body of a cover letter for the position \"{title}\" at {employer or 'this employer'}.\n"
              "Three short paragraphs, 200 to 260 words in total unless told to be briefer: (1) why this role and employer, (2) the two or three most relevant things "
              "from the resume for what the posting asks, (3) a brief close inviting a conversation. "
              "Separate the three paragraphs with one blank line. Name only tools, technologies, industries and settings that the resume itself mentions "
              "(for example, do not say healthcare, hospital, Windows 11 or Microsoft 365 unless the resume says so); the posting's wording is not evidence "
              "of the candidate's experience. Do NOT write a greeting, a sign-off, the candidate's name, or a heading. Return only the paragraphs.\n\n"
              f"POSTING:\n{posting[:6000]}\n\nRESUME:\n{resume[:6000]}")
    out = llm.generate(SYSTEM, prompt, temperature=0.4)
    return canadian(re.sub(r"\n{3,}", "\n\n", out).strip()) if out else None


def resume_summary(resume, posting, title):
    prompt = (f"Rewrite the candidate's resume summary for the position \"{title}\". Two or three sentences, at most 60 words, first person "
              "implied (no 'I'), drawn only from the resume, emphasising what the posting asks for that the resume truly shows. "
              "Return only the summary text.\n\n"
              f"POSTING:\n{posting[:5000]}\n\nRESUME:\n{resume[:6000]}")
    out = llm.generate(SYSTEM, prompt, temperature=0.3)
    return canadian(" ".join(out.split())) if out else None


def extract_employer(posting, title):
    """Mailing address and hiring contact if the posting states them, else blanks."""
    prompt = ("From this job posting, return ONLY JSON with keys: name (the employer), address (street address only), city, province, "
              "postal, contact (the hiring manager or recruiter's name if the posting states one). Use \"\" for anything the text "
              f"does not state. Do not guess.\n\nPOSTING ({title}):\n{posting[:6000]}")
    out = llm.generate("You extract facts from text and never guess.", prompt, json_mode=True, temperature=0, write=False)
    return out if isinstance(out, dict) else {}


def unsupported_numbers(draft, *sources):
    have = " ".join(sources).lower()
    out = set()
    for n in re.findall(r"\d[\d,.]*\+?", draft):
        core = n.rstrip("+.,").lower()
        if core and not re.search(r"(?<![\d.,])" + re.escape(core) + r"(?![\d])", have):     # a whole number, not part of a longer one
            out.add(n)
    return sorted(out)


SETTINGS = ["healthcare", "health care", "hospital", "clinical", "patient", "education", "school", "university", "college", "municipal", "government",
            "financial", "banking", "retail", "manufacturing", "nonprofit", "non-profit", "military", "police"]


SOFT = {"troubleshooting", "communication", "documentation", "customer service", "security", "scheduling", "backup", "networking", "teams"}


def drop_sentences(text, bad):
    """Last resort: remove every sentence that names an unsupported term. Keeps the text if that would remove everything."""
    pats = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I) for t in bad]
    paras = []
    for para in re.split(r"\n\s*\n", text.strip()):
        keep = [s for s in re.split(r"(?<=[.!?])\s+", para) if not any(p.search(s) for p in pats)]
        if keep:
            paras.append(" ".join(keep))
    return "\n\n".join(paras) or text


STORY = re.compile(r"\b(in one instance|on one occasion|on one project|one (time|day|instance|occasion|morning|afternoon)|once[, ]|i recall|"
                   r"there was a (time|user|teacher|case|situation)|(a|one|an) (user|teacher|client|customer|colleague|staff member|student|"
                   r"employee|manager|principal|parent) (could not|couldn't|was unable|called|reported|complained|had|came|needed|asked)|"
                   r"last (year|month|week|summer)|at (a|one) (previous|past) (job|role|position))\b", re.I)


OUTCOME = re.compile(r"\b(reduc|improv|increas|decreas|boost|cut|sav|enhanc)\w* (\w+ ){0,3}(times?|costs?|satisfaction|efficiency|downtime|productivity|tickets|errors|backlog|response|resolution)\b", re.I)


def ground(text, resume, posting="", employer="", title=""):
    """Drop sentences that read as invented specifics: a made-up incident, a figure the resume and posting don't contain, or a
    tool or setting the resume doesn't name. Deterministic on purpose (a small model is a poor judge of its own claims).
    -> (text, removed). If nothing is left, returns ("", removed)."""
    removed, kept_paras = 0, []
    for para in [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]:
        keep = []
        for s in [x for x in re.split(r"(?<=[.!?])\s+", para.strip()) if x]:
            bad = (STORY.search(s) or (OUTCOME.search(s) and not OUTCOME.search(resume)) or letters_numbers(s, resume, posting) or unsupported_terms(s, resume, employer, title))
            if bad:
                removed += 1
            else:
                keep.append(s)
        if keep:
            kept_paras.append(" ".join(keep))
    return "\n\n".join(kept_paras), removed


def letters_numbers(s, resume, posting):
    return unsupported_numbers(s, resume, posting)


def repaired(text, resume, employer, title, rounds=2):
    """Ask the model to drop any claim the resume doesn't support (up to `rounds` times), then remove whatever still remains."""
    for _ in range(rounds):
        bad = unsupported_terms(text, resume, employer, title)
        if not bad:
            return text
        fixed = llm.generate(SYSTEM, f"Rewrite the text below so that it no longer mentions: {', '.join(bad)}. The resume does not support them. "
                             "Either say the same thing using only what the resume shows, or drop that sentence. Keep the paragraph breaks and "
                             "everything else the same, and do not add anything new. You may still name the employer. Return only the rewritten text.\n\n"
                             f"TEXT:\n{text}", temperature=0.2)
        if not fixed or len(fixed) > len(text) * 1.3 + 40:        # the model rambled or echoed the resume: don't trust it
            break
        text = canadian(re.sub(r"\n{3,}", "\n\n", fixed).strip())
    bad = unsupported_terms(text, resume, employer, title)
    return drop_sentences(text, bad) if bad else text


def unsupported_terms(draft, resume, *allowed):
    """Skills, tools and settings the draft names that the resume does not (the employer's own name and the title are allowed)."""
    have = resume.lower() + " " + " ".join(allowed).lower()
    low = draft.lower()
    out = []
    for t in match.LEXICON + SETTINGS:
        if t in SOFT:
            continue
        if re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", low) and not re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", have):
            out.append(t)
    for m in re.findall(r"\b(?:Windows|macOS|iOS|Office|Microsoft) ?\d+\b", draft):      # versions the resume never states
        if m.lower() not in have:
            out.append(m)
    return sorted(set(out))


def letter_lines(profile, employer, contact, title, body):
    """The finished letter as a list of paragraphs (empty string = blank line)."""
    name = f"{profile.get('first', '')} {profile.get('last', '')}".strip()
    city = ", ".join(x for x in (profile.get("city"), profile.get("province")) if x)
    sender = [x for x in (name, profile.get("address"), " ".join(x for x in (city, profile.get("postal")) if x),
                          profile.get("phone"), profile.get("email")) if x]
    ecity = " ".join(x for x in (", ".join(y for y in (employer.get("city"), employer.get("province")) if y), employer.get("postal")) if x)
    to = [x for x in (employer.get("name"), employer.get("address"), ecity) if x]
    greet = f"Dear {contact}," if contact else "Dear Hiring Manager,"
    lines = sender + ["", date.today().strftime("%B %-d, %Y"), ""] + to + ([""] if to else [])
    lines += [f"Re: {title}", "", greet, ""]
    for para in re.split(r"\n\s*\n", body.strip()):
        lines += [" ".join(para.split()), ""]
    return lines + ["Sincerely,", "", name]


def letter_docx(lines, bold=lambda t: False):
    """A small, clean Word file: Calibri 11 pt, one paragraph per line, blank lines kept."""
    paras = "".join(
        f'<w:p><w:pPr><w:spacing w:after="0" w:line="264" w:lineRule="auto"/></w:pPr>' +
        (f'<w:r>{"<w:rPr><w:b/></w:rPr>" if bold(t) else ""}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>' if t else "") + "</w:p>" for t in lines)
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{paras}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
           'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault></w:docDefaults></w:styles>')
    types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    drels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", drels)
    return out.getvalue()


def text_to_docx(text):
    """A plain-text resume as a simple Word file (ALL-CAPS heading lines in bold), so it can be customised without a converter."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    return letter_docx(lines, bold=lambda t: bool(re.fullmatch(r"[A-Z][A-Z &/,'-]{2,40}", t.strip())))


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def analyze(resume, posting, title):
    """What the posting asks for, and where the resume shows it. Every piece of 'evidence' must be words really found in the
    resume; a claim whose evidence can't be found is downgraded, so the page never shows a made-up match."""
    prompt = (f"Compare this resume with the job posting for \"{title}\". Return ONLY JSON: "
              '{"role_summary": "two plain sentences on what the job really involves", "verdict": "strong|fair|stretch", '
              '"requirements": [{"need": "short phrase", "level": "must|asset", "status": "met|partial|gap", '
              '"evidence": "words copied exactly from the resume that show it, or empty", "keyword": "one short term the candidate could add to the resume only if true, or empty"}]}. '
              "List the 6 to 9 most important requirements from the posting. Say \"met\" only when the resume clearly shows it, "
              "\"partial\" for related experience, \"gap\" when the resume does not show it. Never invent evidence.\n\n"
              f"POSTING:\n{posting[:6000]}\n\nRESUME:\n{resume[:6000]}")
    out = llm.generate("You are a careful recruiter. You only report what the text states.", prompt, json_mode=True, temperature=0)
    if not isinstance(out, dict) or not isinstance(out.get("requirements"), list):
        return None
    lines = [ln.strip().lstrip("•-*· ").strip() for ln in resume.splitlines() if len(ln.strip()) > 8]
    def stems(text):                       # words (stemmed) plus any numbers, so "Windows 11" needs the 11 too
        return {match.stem(w) for w in match.words(text)} | set(re.findall(r"\d+", text))

    line_stems = [stems(ln) for ln in lines]
    all_stems = set().union(*line_stems) if line_stems else set()
    rank = {"gap": 0, "partial": 1, "met": 2}
    reqs = []
    for r in out["requirements"][:9]:
        if not isinstance(r, dict) or not str(r.get("need", "")).strip():
            continue
        need = canadian(str(r["need"]).strip()[:120])
        toks = [t for t in stems(need) if t not in match.STOP and len(t) > 1 or t.isdigit()]
        asked = r.get("status") if r.get("status") in rank else "gap"
        if toks:
            cover = sum(1 for t in toks if t in all_stems) / len(toks)
            ours = "met" if cover == 1 else "partial" if cover >= 0.5 else "gap"
            best = max(range(len(lines)), key=lambda i: sum(1 for t in toks if t in line_stems[i])) if lines else None
        else:
            ours, best = "gap", None
        status = min(asked, ours, key=rank.get)          # never more generous than either the model or the word check
        ev = lines[best][:240] if best is not None and status != "gap" and any(t in line_stems[best] for t in toks) else ""
        kw = " ".join(str(r.get("keyword", "")).split())[:40]
        reqs.append({"need": need, "level": "must" if r.get("level") == "must" else "asset",
                     "status": status, "evidence": ev, "keyword": kw if status != "met" else ""})
    if not reqs:
        return None
    verdict = out.get("verdict") if out.get("verdict") in ("strong", "fair", "stretch") else "fair"
    return {"role_summary": canadian(" ".join(str(out.get("role_summary", "")).split())[:500]), "verdict": verdict, "requirements": reqs}


def pick_highlights(resume, posting, title, limit=5):
    """The resume's own lines that best fit the posting, copied exactly (never reworded)."""
    prompt = (f"From the resume, choose up to {limit} lines (bullets or sentences) that best show fit for the position \"{title}\". "
              "Copy each one EXACTLY as written in the resume, character for character. "
              'Return ONLY JSON: {"lines": ["...", "..."]}.\n\n'
              f"POSTING:\n{posting[:5000]}\n\nRESUME:\n{resume[:6000]}")
    out = llm.generate("You select text and never rewrite it.", prompt, json_mode=True, temperature=0, write=False)
    lines = out.get("lines") if isinstance(out, dict) else None
    if not isinstance(lines, list):
        return []
    real = [ln.strip().lstrip("•-*· ").strip() for ln in resume.splitlines() if len(ln.strip()) > 25]
    keep = []
    for want in lines[:limit + 3]:
        w = _norm(str(want))
        if len(w) < 20:
            continue
        hit = next((ln for ln in real if w in _norm(ln) or _norm(ln) in w), None)
        if hit and hit not in keep:
            keep.append(hit[:300])
    return keep[:limit]


def verified_lines(resume, lines, limit=6):
    """Keep only submitted highlight lines that really are lines of the resume."""
    real = {_norm(ln.strip().lstrip("•-*· ")): ln.strip().lstrip("•-*· ").strip() for ln in resume.splitlines() if ln.strip()}
    out = []
    for ln in lines if isinstance(lines, list) else []:
        k = _norm(str(ln))
        if k in real and real[k] not in out:
            out.append(real[k][:300])
    return out[:limit]


# ---------------------------------------------------------------- what the posting asks applicants to provide
COVER_RE = re.compile(r"cover letter|covering letter|letter of interest|letter of intent|letter of application|statement of interest", re.I)
DOCS = [("References", r"\breferences?\b"), ("Transcripts", r"\btranscripts?\b"), ("Certificates or licences", r"\b(certificates?|certifications?|licen[cs]es?)\b.{0,40}\b(copy|copies|proof|attach|submit|provide)|\b(copy|copies|proof)\b.{0,40}\b(certificates?|certifications?|licen[cs]es?)"),
        ("Portfolio or work samples", r"\b(portfolio|writing sample|work samples?)\b"), ("Police record check", r"vulnerable sector|police (record|information|clearance|check)|criminal (record|background)"),
        ("Proof of vaccination or immunization", r"immuni[sz]ation|vaccination|vaccine")]
QUESTION_HINT = re.compile(r"please (describe|explain|answer|respond|outline|tell us)|in (\d+|\w+) words|following questions?|written (response|answer)|essay|short answer|"
                           r"briefly (describe|explain|outline)|tell us (about|why|how)|statement (of|addressing)|address the following", re.I)


def posting_requirements(posting):
    """What the posting itself asks applicants to supply: a cover letter, other documents, written questions. Only what it states."""
    out = {"cover_letter": bool(COVER_RE.search(posting)), "documents": [], "questions": []}
    for name, pat in DOCS:
        if re.search(pat, posting, re.I):
            out["documents"].append(name)
    if QUESTION_HINT.search(posting):                        # only spend a model call when the text hints at written questions
        prompt = ("List any written questions or essay prompts that this job posting explicitly tells applicants to answer or address "
                  "(for example \"In 300 words, describe a time you...\"). Copy each one word for word from the posting. "
                  'Return ONLY JSON: {"questions": []}. Use an empty list if there are none.\n\nPOSTING:\n' + posting[:7000])
        res = llm.generate("You extract text and never invent any.", prompt, json_mode=True, temperature=0, write=False)
        have = _norm(posting)
        for q in (res.get("questions") if isinstance(res, dict) else None) or []:
            if isinstance(q, str) and 15 < len(q) < 600 and _norm(q) in have and q.strip() not in out["questions"]:
                out["questions"].append(q.strip())
        out["questions"] = out["questions"][:5]
    return out


# ---------------------------------------------------------------- one open-ended answer
PERSONAL = re.compile(r"\b(salary|wage|compensation|pay expectation|social insurance|sin number|date of birth|birth ?date|sexual orientation|"
                      r"criminal|convicted|start date|notice period|first nations|m[eé]tis|inuit)\b|\b(gender|pronoun|ethnic|indigenous|disabilit|veteran|"
                      r"racial|race|citizenship|passport)\w*", re.I)


def answer_question(resume, posting, title, employer, question, max_words=150):
    """A draft answer to one application question, in the first person, from the resume only. None if it isn't a question the
    resume can answer (personal details are left for the person)."""
    if PERSONAL.search(question):
        return None
    max_words = max(30, min(int(max_words or 150), 400))
    story = re.search(r"\b(describe|tell us|tell me|give|share)\b.{0,40}\b(a time|an example|a situation|an instance|a case)\b", question, re.I)
    approach = ("This asks for an example, but the resume holds no detailed incidents. Do NOT tell a story or invent an incident: instead explain, in general terms, "
                "how the candidate approaches this kind of situation, backed by real experience from the resume. " if story else "")
    prompt = (approach + f"Answer this job application question as the candidate. At most {max_words} words, one to three short paragraphs, "
              "first person, no greeting or sign-off. Use only experience that appears in the resume, at the level of detail the resume gives. "
              "NEVER invent a specific incident, person, device, number, duration or outcome. If the question asks for a particular example and the "
              "resume has none, describe the candidate's real, relevant experience and usual approach in general terms drawn from the resume lines. "
              "Never write 'my resume'. Return only the answer.\n\n"
              f"QUESTION:\n{question[:1000]}\n\n" + (f"POSITION: {title} at {employer}\nPOSTING:\n{posting[:4000]}\n\n" if posting else "") +
              f"RESUME:\n{resume[:6000]}")
    out = llm.generate(SYSTEM, prompt, temperature=0.4)
    if not out:
        return None
    text = canadian(re.sub(r"\n{3,}", "\n\n", out).strip())
    text = repaired(text, resume, employer or "", title or "")
    return ground(text, resume, posting, employer or "", title or "")


# ---------------------------------------------------------------- form fields the script's own rules couldn't place
def field_answers(profile, resume, fields):
    """Best-effort values for form fields the browser script couldn't fill by its rules. Only values the profile or resume actually
    supports are returned; anything else comes back empty so the person answers it. -> {field id: value}"""
    ok = []
    for f in fields[:15]:
        label = " ".join(str(f.get("label", "")).split())[:200]
        if not label or PERSONAL.search(label) or re.search(r"\b(sin|password|signature|card|cvv|captcha)\b", label, re.I):
            continue
        opts = [str(o)[:80] for o in (f.get("options") or [])[:40]]
        ok.append({"id": str(f.get("id"))[:20], "label": label, "type": str(f.get("type", "text"))[:12], "options": opts})
    if not ok:
        return {}
    facts = {k: v for k, v in profile.items() if v and k not in ("summary",)}
    prompt = ("Fill job-application form fields for the candidate using ONLY the PROFILE and RESUME below. For each field give the value, or an empty "
              "string if those facts don't clearly give it. Never guess. For a field with options, answer with exactly one of the options. Keep text "
              'values short. Return ONLY JSON: {"answers": {"<id>": "<value>"}}.\n\nFIELDS:\n' + json.dumps(ok) +
              "\n\nPROFILE:\n" + json.dumps(facts)[:3000] + "\n\nRESUME:\n" + resume[:3500])
    res = llm.generate("You fill forms from facts and never guess.", prompt, json_mode=True, temperature=0, write=False)
    ans = res.get("answers") if isinstance(res, dict) else None
    if not isinstance(ans, dict):
        return {}
    have = _norm(json.dumps(profile) + " " + resume)
    out = {}
    for f in ok:
        v = ans.get(f["id"])
        if not isinstance(v, str) or not v.strip():
            continue
        v = " ".join(v.split())[:200]
        if f["options"] and v not in f["options"]:
            continue
        toks = _norm(v).split()
        if toks and all(t in have.split() for t in toks):          # every word of the value must come from the person's own facts
            out[f["id"]] = v
    return out
