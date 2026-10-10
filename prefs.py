"""Per-person settings (what they want to see, alert email) shared by the web server and the scanner.

Stored as prefs-<user>.json in the data folder. The same rules are mirrored in the page's JavaScript
so what you see on screen and what lands in your email agree.
"""
import json
import os
import re
import tempfile
from pathlib import Path

# The categories people pick from (besides "it", which uses the scanner's IT classification, and "keywords"/"all").
# Each rule says which employer tags and title words put a posting in the category. The page reads the same rules from jobs.json.
#   tags    employers tagged this way (in config.json) are in, whatever the title
#   words   title words/phrases that put a posting in
#   strip   phrases removed from the title before looking for `words` (so "Assistant Professor" isn't an "assistant")
#   unless  a posting that is in any of these categories is NOT in this one
#   not_it  postings the scanner calls core IT are left to the IT category
_SERVICES = ["police services", "police service", "paramedic services", "paramedic service", "fire services", "fire department", "emergency services"]
SECTOR_RULES = {
    "trades": {"tags": ["utility"], "unless": ["finance"], "not_it": True, "strip": ["communications operator", "911 communications"], "words": [
        "electrician", "millwright", "mechanic", "plumber", "carpenter", "welder", "hvac", "operator", "maintenance", "labourer",
        "laborer", "mechanical technician", "lineman", "lineperson", "linesperson", "line technician", "splicer", "substation", "pipefitter",
        "steamfitter", "sheet metal", "stationary engineer", "operating engineer", "water", "wastewater", "road", "utilities",
        "custodian", "caretaker", "facilities", "fleet", "painter", "locksmith", "groundskeeper", "horticul", "journeyman", "apprentice"]},
    "healthcare": {"tags": ["healthcare", "social"], "words": [
        "nurse", "nursing", "rn", "rpn", "nurse practitioner", "paramedic", "clinical", "clinician", "patient", "physician",
        "therapist", "therapy", "pharmacist", "pharmacy", "psw", "personal support", "dietitian", "radiation", "sonographer",
        "radiologic", "laboratory", "phlebotomist", "respiratory", "psychologist", "social worker", "long-term care",
        "long term care", "health care", "healthcare", "hospital", "surgical", "anesthesia", "midwife", "occupational therapist",
        "physiotherapist", "technologist, medical"]},
    "education": {"tags": ["education"], "words": [
        "professor", "lecturer", "faculty", "academic", "librarian", "registrar", "dean", "curriculum", "instructor",
        "sessional", "postdoctoral", "provost"]},
    "uniformed": {"tags": ["police_uniform"], "strip": _SERVICES, "words": [
        "constable", "police officer", "police recruit", "paramedic", "paramedics", "firefighter", "fire fighter", "fire captain",
        "fire chief", "emergency medical", "law enforcement", "enforcement officer", "bylaw", "by-law", "parking enforcement",
        "peace officer", "correctional officer", "court security", "security officer", "security guard"]},
    "finance": {"tags": [], "strip": ["assistant professor", "associate professor", "assistant/associate", "assistant, associate", "assistant / associate",
                                      "pathologist assistant", "laboratory assistant", "dental assistant", "teaching assistant", "research assistant",
                                      "instructional assistant", "personal support"], "words": [
        "accountant", "accounting", "accounts payable", "accounts receivable", "payroll", "financial", "finance", "budget",
        "auditor", "audit", "bookkeeper", "treasury", "revenue", "tax", "procurement", "purchasing", "buyer", "controller",
        "administrative", "admin assistant", "assistant", "clerk", "receptionist", "coordinator", "secretary", "customer service",
        "office", "records", "data entry", "scheduler", "dispatcher", "communications operator", "call taker", "support services"]},
}
SECTOR_MODES = tuple(SECTOR_RULES)
MODES = ("it", "trades", "healthcare", "education", "uniformed", "finance", "keywords", "all")
# Settings saved under other category names land on the closest current one (or Everything).
MODE_ALIAS = {"itadj": "it", "social": "healthcare", "police": "uniformed", "utility": "trades", "transit": "trades", "admin": "finance",
              "civilian": "all", "military": "all", "safety": "all", "government": "all", "municipal": "all", "federal": "all",
              "engineering": "all", "recreation": "all"}
# Which category's page shows a "check manually" link, by the link's employer tag.
MANUAL_MODES = {"healthcare": ["healthcare"], "social": ["healthcare"], "utility": ["trades"], "transit": ["trades"],
                "police": ["uniformed"], "education": ["education"]}


def manual_modes(link):
    return link.get("modes") or MANUAL_MODES.get(link.get("sector"), [])


DEFAULTS = {"mode": "all", "keywords": [], "exclude": [], "union_only": False, "employers": [],
            "email": "", "alerts": False, "digest": False, "owner_email": True, "last_visit": "", "name": ""}
NAME_OK = re.compile(r"[^\W\d_][\w .'’-]*")        # a person's display name: starts with a letter
EMAIL_RE = re.compile(r"[^@\s<>,;]{1,64}@[^@\s<>,;]{1,200}\.[A-Za-z]{2,}")


def path(folder, user):
    return Path(folder) / f"prefs-{re.sub(r'[^a-z0-9._-]', '_', user)}.json"


def load(folder, user):
    try:
        data = json.loads(path(folder, user).read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    out = {**DEFAULTS, **{k: data[k] for k in DEFAULTS if k in data}}
    out["mode"] = MODE_ALIAS.get(out["mode"], out["mode"])
    if "@" in user and EMAIL_RE.fullmatch(user):      # the username IS the email address: alerts go to (and from) it
        out["email"] = user
    return out


def display_name(p, user):
    """The person's full name (set by an admin), else a tidy version of their sign-in name."""
    if p.get("name"):
        return p["name"]
    return user.split("@")[0].replace(".", " ").replace("_", " ").title() if "@" in user else user.capitalize()


def first_name(p, user):
    return display_name(p, user).split()[0]


def save(folder, user, prefs):
    p = path(folder, user)
    fd, tmp = tempfile.mkstemp(dir=p.parent)  # private (0600) by default
    with os.fdopen(fd, "w") as f:
        json.dump(prefs, f)
    os.replace(tmp, p)


def _words(value, limit=30):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError
    out = []
    for w in value:
        if not isinstance(w, str):
            raise ValueError
        w = " ".join(w.split())[:40]
        if w and w.lower() not in [x.lower() for x in out]:
            out.append(w)
    return out


def validate(req):
    """Return only the editable fields, checked. Raises ValueError on anything unexpected."""
    out = {}
    if "mode" in req:
        mode = MODE_ALIAS.get(req["mode"], req["mode"])
        if mode not in MODES:
            raise ValueError
        out["mode"] = mode
    for k in ("keywords", "exclude"):
        if k in req:
            out[k] = _words(req[k])
    if "employers" in req:
        emp = _words(req["employers"], 60)
        out["employers"] = [e[:80] for e in emp]
    if "name" in req:
        n = req["name"]
        n = " ".join(n.split()) if isinstance(n, str) else ""
        if not 1 <= len(n) <= 60 or not NAME_OK.fullmatch(n):
            raise ValueError
        out["name"] = n
    for k in ("union_only", "alerts", "digest", "owner_email"):
        if k in req:
            if not isinstance(req[k], bool):
                raise ValueError
            out[k] = req[k]
    if "email" in req:
        e = req["email"]
        if not isinstance(e, str) or len(e) > 254 or (e and not EMAIL_RE.fullmatch(e.strip())):
            raise ValueError
        out["email"] = e.strip()
    return out


def _has(word, text):
    return re.search(r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)", text) is not None


def in_sector(job, sector):
    """True if the employer is tagged for the category, or the title clearly belongs to it."""
    r = SECTOR_RULES[sector]
    title = (job.get("title") or "").lower()
    for ph in r.get("strip", ()):
        title = title.replace(ph, " ")
    if not (job.get("sector") in r["tags"] or any(_has(w, title) for w in r["words"])):
        return False
    if r.get("not_it") and job.get("matched", job.get("it")) == 1:
        return False
    return not any(in_sector(job, other) for other in r.get("unless", ()))


def normalize(p, known_sources):
    """Ticking every employer means the same as ticking none: no restriction. (Also keeps working as sources are added.)"""
    if p.get("employers") and set(known_sources) <= set(p["employers"]):
        return {**p, "employers": []}
    return p


def matches(job, p):
    """Does this posting fit one person's settings? job needs title, source, matched, union_name (and sector)."""
    title = (job.get("title") or "").lower()
    if any(w.lower() in title for w in p["exclude"]):
        return False
    if p["employers"] and job.get("source") not in p["employers"]:
        return False
    if p["union_only"] and (job.get("union_name") or "") in ("", "Non-union"):
        return False
    if p["mode"] == "it":
        return job.get("matched") == 1            # core IT only; adjacent postings have their own view
    if p["mode"] in SECTOR_MODES:
        return in_sector(job, p["mode"])
    if p["mode"] == "keywords":
        return any(_has(w, title) for w in p["keywords"])
    return True
