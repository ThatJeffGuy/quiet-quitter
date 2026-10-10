"""Application profile: the facts job-application forms ask for, kept per person.

It starts as a best-effort reading of the uploaded resume's text (plain pattern matching, nothing leaves the server)
and is then edited by the person. The autofill userscript copies it into the forms of other sites.
"""
import json
import os
import re
import tempfile
from pathlib import Path

SCALARS = ("first", "last", "email", "phone", "address", "city", "province", "postal", "country", "linkedin", "website",
           "work_auth", "sponsorship", "salary", "availability", "summary", "languages", "heard_about",
           "legal_age", "travel_intl", "relocate", "work_locations", "shifts")
LIMITS = {"jobs": 15, "education": 8, "references": 6, "skills": 80, "certifications": 15}
LISTS = {
    "jobs": ("title", "employer", "location", "start", "end", "current", "type", "desc"),
    "education": ("school", "credential", "field", "level", "start", "year", "graduated"),
    "certifications": ("name", "issuer", "year"),
    "references": ("name", "title", "phone", "email"),
}

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)")
POSTAL = re.compile(r"\b([A-Za-z]\d[A-Za-z])[ -]?(\d[A-Za-z]\d)\b")
YEARS = re.compile(r"\b((?:19|20)\d{2})\b")
HEADING = re.compile(r"^[A-Z][A-Z &/,'-]{2,40}$")
SECTION_WORDS = re.compile(r"\b(profile|summary|objective|skills?|experience|employment|work history|education|certifications?|certificates?|training|courses?|"
                           r"projects?|references?|awards?|volunteer(ing)?|languages?|interests?|commitments?|achievements?|qualifications?)\b", re.I)


def is_heading(line):
    """ALL-CAPS lines, or a short line made of a known section word ("Education", "profile", "Certifications & commitments")."""
    line = line.strip().rstrip(":")
    if HEADING.match(line) and len(line.split()) <= 4:
        return True
    return (len(line) <= 40 and len(line.split()) <= 5 and not re.search(r"[\d@./]|[.!?]$", line) and SECTION_WORDS.search(line) is not None)


def path_for(state_dir, user):
    return Path(state_dir) / f"profile-{re.sub(r'[^a-z0-9._-]', '_', user)}.json"


def load(state_dir, user):
    try:
        data = json.loads(path_for(state_dir, user).read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    return clean(data)


def save(state_dir, user, data):
    path = path_for(state_dir, user)
    fd, tmp = tempfile.mkstemp(dir=path.parent)       # private (0600), written atomically
    with os.fdopen(fd, "w") as f:
        json.dump(clean(data), f)
    os.replace(tmp, path)


def _s(v, n=2000):
    return v.strip()[:n] if isinstance(v, str) else ""


def _rows(v, keys, limit):
    out = []
    for item in (v if isinstance(v, list) else [])[:limit]:
        if isinstance(item, dict):
            row = {k: _s(item.get(k), 4000 if k == "desc" else 200) for k in keys}
            if any(row.values()):
                out.append(row)
    return out


def clean(data):
    data = data if isinstance(data, dict) else {}
    out = {k: _s(data.get(k), 4000 if k == "summary" else 200) for k in SCALARS}
    out["skills"] = [_s(x, 60) for x in (data.get("skills") if isinstance(data.get("skills"), list) else [])[:LIMITS["skills"]] if _s(x, 60)]
    for k, cols in LISTS.items():
        out[k] = _rows(data.get(k), cols, LIMITS[k])
    return out


def _sections(text):
    """{"profile": [lines], "skills": [...], ...} split on ALL-CAPS heading lines."""
    sections, cur = {"top": []}, "top"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if is_heading(line):
            cur = line.strip().rstrip(":").lower()
            sections.setdefault(cur, [])
        else:
            sections[cur].append(line)
    return sections


def _find(sections, *names):
    for k, v in sections.items():
        if any(n in k for n in names):
            return v
    return []


def guess_name_line(text):
    """The first of the opening lines that looks like a person's name (2-4 letters-only words, not a section heading)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:14]
    for ln in lines:
        words = ln.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words) and not SECTION_WORDS.search(ln):
            return ln
    return lines[0] if lines else ""


def find_all(sections, *names):
    """Lines of every section whose heading contains one of the names ("in school references" and "professional references" both count)."""
    out = []
    for k, v in sections.items():
        if any(n in k for n in names):
            out += v
    return out


IT_COURSE = re.compile(r"itil|servicenow|g suite|google|security|voip|cisco|assistive|accessib|\bsea\b|spinifex|configuration|incident|problem|network|cloud|linux|windows|azure|python|sql", re.I)


def parse_trainings(sections, limit=15):
    """Courses and training listed as "Title 2025" lines, usually under a 'training and professional development' sub-heading.
    The most job-relevant ones come first, so a form that only takes a few gets the right few."""
    found, on = [], False
    for k, lines in sections.items():
        if not any(w in k for w in ("educ", "train", "certif", "course", "develop")):
            continue
        for ln in lines:
            if re.search(r"training|professional development|courses|certifications?", ln, re.I) and not re.search(r"\b(19|20)\d{2}\s*$", ln):
                on = True
                continue
            m = re.match(r"^(.*?)[\s,(-]+((?:19|20)\d{2})\)?\s*$", ln.strip())
            if on and m and len(m.group(1)) > 5:
                found.append({"name": m.group(1).strip(" -:,")[:150], "issuer": "", "year": m.group(2)})
    ranked = sorted(enumerate(found), key=lambda x: (not IT_COURSE.search(x[1]["name"]), -int(x[1]["year"]), x[0]))
    return [c for _, c in ranked[:limit]]


def parse_resume(text):
    """Best-effort profile from resume text. Anything it can't tell is left empty for the person to fill in."""
    p = clean({})
    sec = _sections(text)
    top = sec.get("top", [])
    first_line = guess_name_line(text)
    head = "\n".join(([first_line] + top)[:8])
    if first_line:
        name = re.sub(r"[^A-Za-z.' -]", " ", first_line).split()
        if 2 <= len(name) <= 4:
            p["first"], p["last"] = name[0].title(), name[-1].title()
    m = EMAIL.search(head)
    if m:
        p["email"] = m.group(0)
    m = PHONE.search(head)
    if m:
        p["phone"] = f"({m.group(1)}) {m.group(2)}-{m.group(3)}"
    m = POSTAL.search(head)
    if m:
        p["postal"] = f"{m.group(1)} {m.group(2)}".upper()
    m = re.search(r"linkedin\.com/[\w/%-]+", text, re.I)
    if m:
        p["linkedin"] = "https://www." + m.group(0)
    summary = _find(sec, "profile", "summary", "objective")
    p["summary"] = " ".join(summary)[:1500]

    skills = []
    for line in _find(sec, "skill"):
        parts = [s.strip(" .;") for s in re.split(r"[,;•|]", line.split(":", 1)[-1] if ":" in line and len(line.split(":", 1)[0]) < 40 else line)]
        skills += [s for s in parts if 1 < len(s) <= 40 and len(s.split()) <= 4]
    p["skills"] = list(dict.fromkeys(skills))[:LIMITS["skills"]]

    # Experience: a line holding a year range starts a new entry; the lines after it are its description.
    jobs, cur = [], None
    for line in _find(sec, "experience", "employment", "work history"):
        yrs = YEARS.findall(line)
        looks_dated = yrs and len(line) < 90 and re.search(r"\b(to|present|current|–|-)\b|^\s*(19|20)\d{2}[,\s]", line, re.I)
        if looks_dated:
            now = bool(re.search(r"present|current", line, re.I))
            cur = {"title": "", "employer": "", "location": "", "start": yrs[0], "end": "Present" if now else (yrs[1] if len(yrs) > 1 else yrs[0]),
                   "current": "yes" if now else "", "type": "", "desc": ""}
            jobs.append(cur)
        elif cur is not None:
            cur["desc"] += ("\n" if cur["desc"] else "") + line.lstrip("•-* ")
        elif len(line) < 80:
            cur = {"title": line, "employer": "", "location": "", "start": "", "end": "", "current": "", "type": "", "desc": ""}
            jobs.append(cur)
    p["jobs"] = _rows(jobs, LISTS["jobs"], LIMITS["jobs"])

    edu = []
    for line in _find(sec, "education"):
        yrs = YEARS.findall(line)
        edu.append({"school": line[:200], "credential": "", "field": "", "level": "", "start": "", "year": yrs[-1] if yrs else "", "graduated": "yes" if yrs else ""})
    p["education"] = _rows(edu, LISTS["education"], LIMITS["education"])

    refs = []
    for line in find_all(sec, "reference"):
        e, ph = EMAIL.search(line), PHONE.search(line)
        if e or ph:
            parts = [x.strip() for x in line.split(",")]
            refs.append({"name": parts[0], "title": parts[1] if len(parts) > 1 and not PHONE.search(parts[1]) else "",
                         "phone": f"({ph.group(1)}) {ph.group(2)}-{ph.group(3)}" if ph else "", "email": e.group(0) if e else ""})
    p["references"] = _rows(refs, LISTS["references"], LIMITS["references"])
    p["certifications"] = _rows(parse_trainings(sec), LISTS["certifications"], LIMITS["certifications"])
    p["country"] = "Canada"
    return p


def merge_missing(existing, parsed):
    """Fill only the blanks of an existing profile from a fresh reading; never overwrite what the person typed."""
    out = clean(existing)
    for k, v in parsed.items():
        if not out.get(k):
            out[k] = v
    return out


TYPE_WORDS = {"Full time": r"full[- ]?time", "Part time": r"part[- ]?time", "Contract": r"contract", "Casual": r"casual",
              "Seasonal": r"seasonal", "Internship": r"intern(ship)?|co-?op"}


def verify(profile, text):
    """Drop details a model may have guessed: an employment type the resume never mentions, a certificate year that isn't on that
    certificate's own line, a 'graduated' flag with no year."""
    out = clean(profile)
    low = text.lower()
    for j in out["jobs"]:
        emp_words = set(re.findall(r"[a-z]{3,}", j.get("employer", "").lower()))
        parts = [x.strip() for x in j.get("location", "").split(",") if x.strip()]
        keep = [x for x in parts if len(emp_words & set(re.findall(r"[a-z]{3,}", x.lower()))) < 2
                and not re.search(r"\b(school|college|university|region|inc|ltd|hospital|board|centre|center|department|services?)\b", x, re.I)]
        j["location"] = ", ".join(keep)         # drop organisation names the model mixed into the place
        if j.get("current") and not re.search(r"present|current|now|ongoing", j.get("end", ""), re.I):
            j["current"] = ""                      # a job only counts as current if its end date says so
        pat = TYPE_WORDS.get(j.get("type", ""))
        if j.get("type") and not (pat and re.search(pat, low)):
            j["type"] = ""
    for r in out["references"]:
        for k in ("name", "title"):
            if r.get(k, "").isupper():
                r[k] = r[k].title()                # "ERIK GORDON" -> "Erik Gordon"
    lines = [ln.lower() for ln in text.splitlines()]
    for c in out["certifications"]:
        name = c.get("name", "").lower()
        line = next((ln for ln in lines if name and name in ln), "")
        if c.get("year") and c["year"] not in line:
            c["year"] = ""
    for e in out["education"]:
        if e.get("graduated") == "yes" and not e.get("year"):
            e["graduated"] = ""
    return out
