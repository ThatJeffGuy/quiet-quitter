# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Detail-page enrichment, source health tracking, and the weekly digest."""
import html
import json
import re
import sqlite3
import time
from datetime import date, datetime, timedelta
from urllib.parse import unquote
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (job-monitor; personal use)"}
TIMEOUT = 25

NEW_COLUMNS = {"pay": "TEXT", "closes": "TEXT", "details_done": "INTEGER DEFAULT 0", "desc_hits": "INTEGER DEFAULT 0", "union_name": "TEXT", "descr": "TEXT"}


def migrate(db):
    have = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
    for col, typ in NEW_COLUMNS.items():
        if col not in have:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typ}")
    db.execute("CREATE TABLE IF NOT EXISTS health (source TEXT PRIMARY KEY, fails INTEGER, alerted INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS detail_fails (source TEXT, job_id TEXT, n INTEGER, last TEXT, PRIMARY KEY (source, job_id))")


# ----------------------------------------------------------- text extraction
def to_text(markup):
    markup = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h\d)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    return re.sub(r"[ \t\r\f\v ]+", " ", text)


AMT = r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?"
PAY_RE = re.compile(rf"({AMT})(?:\s*(?:-|–|—|to)\s*({AMT}|\d{{1,3}}(?:,\d{{3}})*(?:\.\d{{1,2}})?))?", re.I)
PAY_CTX = re.compile(r"(?i)salary|wage|rate|compensation|pay|per hour|hourly|annual|range|grid")


def extract_pay(text):
    for m in PAY_RE.finditer(text):
        window = text[max(0, m.start() - 120):m.end() + 60]
        if not PAY_CTX.search(window):
            continue
        lo = m.group(1).replace(" ", "")
        hi = m.group(2)
        if hi and not hi.startswith("$"):
            hi = "$" + hi
        amount = lo + (f" – {hi.replace(' ', '')}" if hi else "")
        tail = text[m.end():m.end() + 30].lower()
        unit = ""
        if re.search(r"per hour|an hour|hourly|/\s?h(?:ou)?r", tail):
            unit = "/hr"
        elif re.search(r"per year|annual|per annum|a year|/\s?yr|/year", tail):
            unit = "/yr"
        elif not unit:
            top = max(float(x.replace("$", "").replace(",", "").replace(" ", "")) for x in (lo, hi) if x)
            unit = "/hr" if top < 400 else "/yr" if top >= 20000 else ""
        return amount + unit
    return ""


MONTHS = "Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
DATE_PATS = [
    (re.compile(rf"\b({MONTHS})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.I), "mdy"),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTHS})\.?,?\s+(\d{{4}})", re.I), "dmy"),
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
]
CLOSE_CTX = re.compile(r"(?i)clos(?:e|es|ing|ure)(?: date)?|deadline|apply (?:by|before)|applications? (?:will be )?(?:accepted )?(?:until|by)|open until|posting end")


def _parse_date(m, kind):
    try:
        if kind == "iso":
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        a, b, c = m.groups()
        mon, day = (a, b) if kind == "mdy" else (b, a)
        return datetime.strptime(f"{mon[:3].title()} {int(day)} {c}", "%b %d %Y").date()
    except ValueError:
        return None


def extract_closing(text):
    for ctx in CLOSE_CTX.finditer(text):
        chunk = text[ctx.end():ctx.end() + 80]
        for pat, kind in DATE_PATS:
            m = pat.search(chunk)
            if m:
                d = _parse_date(m, kind)
                if d:
                    return d.isoformat()
    return ""


def extract_union(text):
    names = "CUPE|OPSEU|SEFPO|ONA|PWU|IBEW|ATU|UNIFOR|UFCW|SEIU|OPFFA|PSAC|USW|LiUNA|Teamsters|ETFO|OSSTF|OECTA|CUPW|CAPE"
    # a site's own navigation menu ("CUPE 3902 (Unit 3) Opportunities", "USW Staff Appointed Opportunities") is not the posting's union
    text = re.sub(rf"(?i)\b(?:{names})\s*\d*\s*(?:\(Unit\s*\d+\)\s*)?(?:Emergency Posting\s*|Staff Appointed\s*)?Opportunities\b", " ", text)
    g = re.search(r"Employee Group:\s*(.{1,40}?)\s+(?:Appointment Type|Schedule|Job Category|Pay Scale|Department|Closing)", text)
    if g:                                   # U of T lists the group outright ("USW", "CUPE F/T L3261", "Salaried ...: PM")
        grp = g.group(1)
        n = re.search(rf"(?i)\b({names})\b", grp)
        if n:
            num = re.search(r"\d{3,4}", grp[n.end():])
            return n.group(1).upper() + (" " + num.group(0) if num else "")
        if re.search(r"(?i)\b(PM|Admin\./?\s*Conf\w*|managerial|confidential|non-?union)\b", grp):
            return "Non-union"
    m = re.search(rf"(?i)\bunion\b\s*:?\s*({names})(?:\s+(?:Local\s+)?\d[\d.]*)?", text)
    if m:
        return re.sub(r"\s+", " ", m.group(0).split(":", 1)[-1] if ":" in m.group(0) else m.group(0)[5:]).strip()
    m = re.search(rf"(?<![\w-])({names})(?:\s+(?:Local\s+)?\d[\d.]*)?(?![\w])", text)
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()
    if re.search(r"(?i)non-?union|not (?:a )?(?:member of )?(?:the )?bargaining unit|excluded from the bargaining", text):
        return "Non-union"
    # "For positions covered by a collective agreement, placement ... will follow" is a conditional pay note, not this job's status
    text = re.sub(r"(?i)\bfor positions[^.]{0,60}covered by a collective agreement[^.]*\.?", " ", text)
    if re.search(r"(?i)bargaining unit|collective agreement|collective bargaining", text):
        return "Union"
    return ""


def desc_it_hits(text, terms):
    low = text.lower()
    return sum(1 for t in terms if re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", low))


# ----------------------------------------------------------------- places
# Town centres (lat, lon), checked against the open postal-area data. Used only to estimate distance.
PLACES = {
    "Newmarket": (44.059, -79.461), "Aurora": (44.006, -79.450), "East Gwillimbury": (44.100, -79.480),
    "Holland Landing": (44.098, -79.488), "Sharon": (44.067, -79.433), "Mount Albert": (44.133, -79.314),
    "Georgina": (44.230, -79.467), "Keswick": (44.250, -79.465), "Sutton": (44.300, -79.366),
    "Whitchurch-Stouffville": (43.970, -79.244), "Stouffville": (43.970, -79.244),
    "King": (43.923, -79.528), "King City": (43.923, -79.528), "Nobleton": (43.910, -79.650), "Schomberg": (44.000, -79.680),
    "Richmond Hill": (43.883, -79.440), "Markham": (43.856, -79.337), "Unionville": (43.866, -79.313), "Thornhill": (43.815, -79.426),
    "Vaughan": (43.837, -79.508), "Woodbridge": (43.783, -79.600), "Maple": (43.855, -79.510), "Concord": (43.800, -79.480),
    "Bradford West Gwillimbury": (44.117, -79.567), "Bradford": (44.117, -79.567),
    "Innisfil": (44.300, -79.650), "Uxbridge": (44.109, -79.121), "Barrie": (44.389, -79.690), "Orillia": (44.608, -79.420),
    "Pickering": (43.838, -79.087), "Ajax": (43.851, -79.020), "Whitby": (43.897, -78.943), "Oshawa": (43.897, -78.865),
    "Brampton": (43.685, -79.760), "Mississauga": (43.589, -79.644), "Caledon": (43.870, -79.860),
    "Toronto": (43.653, -79.383), "Newnham": (43.795, -79.348), "North York": (43.761, -79.411), "Scarborough": (43.773, -79.258), "Etobicoke": (43.654, -79.567),
}
_PLACE_RE = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(PLACES, key=len, reverse=True)) + r")(?![\w-])", re.I)
_PLACE_CANON = {n.lower(): n for n in PLACES}
REMOTE_RE = re.compile(r"(?i)\b(remote|work from home|telework|hybrid)\b")


def locate(default_place, location, title=""):
    """Best-guess (lat, lon, label, remote) for a posting. Falls back to the employer's usual town."""
    remote = bool(REMOTE_RE.search(f"{location} {title}"))
    m = _PLACE_RE.search(location or "")
    if m:
        name = _PLACE_CANON[m.group(1).lower()]
    elif default_place in PLACES:
        name = default_place
    else:
        return None, None, "", remote
    lat, lon = PLACES[name]
    return lat, lon, name, remote


# --------------------------------------------------------------- fetching
def site_address(html):
    """The work-site street address from a posting's schema.org JobPosting block, as a plain sentence ('' if there isn't one).
    Costs no extra request: it is read from the page we already fetched."""
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            locs = item.get("jobLocation")
            for loc in locs if isinstance(locs, list) else [locs]:
                a = (loc or {}).get("address") if isinstance(loc, dict) else None
                if isinstance(a, dict):
                    parts = [str(a.get(k, "")).strip() for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")]
                    parts = [p for p in parts if p and p.upper() != "UNAVAILABLE"]
                    if parts and a.get("streetAddress"):
                        return "Work site address: " + ", ".join(parts) + "."
    return ""


TL_TEXT = {}      # (host, job id) -> full posting text kept from a TalentLink list request (the posting page is a JavaScript shell)


def taleo_tee_text(page):
    """Taleo "TEE" pages (Georgian College) draw the posting with JavaScript, but its text is already in the page as
    URL-encoded HTML inside an api.fillList(...) call, which the generic reader skips along with all other script."""
    m = re.search(r"api\.fillList\('requisitionDescriptionInterface',\s*'descRequisition',\s*\[(.*?)\]\);", page, re.S)
    if not m:
        return ""
    blocks, seen = [], set()
    for item in re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1)):
        if item.startswith("!*!"):
            markup = re.sub(r"\\(.)", r"\1", unquote(item[3:]))
            if markup not in seen:
                seen.add(markup)
                blocks.append(to_text(markup))
    return "\n".join(blocks).strip()


class NotNow(Exception):
    """This posting can't be read in this kind of run (not a failure, so it is neither retried nor counted)."""


def fetch_text(src, job_id, url):
    """Return the posting's text, or '' if this source type can't be read generically."""
    typ = src["type"]
    if typ == "workday":
        host, tenant, site = src["args"][:3]
        r = requests.get(f"https://{host}/wday/cxs/{tenant}/{site}{job_id}", headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        info = r.json().get("jobPostingInfo", {})
        return to_text(info.get("jobDescription", "")) + "\n" + (info.get("endDate") and f"Closing date: {info['endDate']}" or "")
    if typ == "talentlink":
        text = TL_TEXT.get((src["args"][0], job_id))
        if text is None:
            raise NotNow()                   # only a full scan's list request carries the text
        return text
    if typ in ("adp", "comeet", "rss"):
        return ""  # JS-rendered or no useful body
    if typ == "taleo_tee":
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        return taleo_tee_text(r.text) or to_text(r.text)
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return to_text(r.text) + (("\n" + site_address(r.text)) if site_address(r.text) else "")


FAIL_LIMIT, FAIL_PARK_HOURS = 3, 24      # a posting that fails to load 3 times is left alone for a day


def enrich(db, cfg, limit=120, pause=0.0):
    """Read the pages of postings we haven't read yet (or whose description we haven't kept). Never raises.

    At most `detail_pages_per_site` per site per call, so a big backlog is worked off in polite batches (see drain in run.py).
    Returns {"read": n, "failed": n, "left": n}: `left` is how many readable postings are still waiting for a later batch."""
    srcs = {s["name"]: s for s in cfg["sources"]}
    terms, need = cfg.get("desc_terms", []), cfg.get("desc_min", 3)
    rows = db.execute("""SELECT source, job_id, url, title, location, matched, details_done FROM jobs
                         WHERE active=1 AND (details_done=0 OR descr IS NULL)
                         ORDER BY matched DESC, details_done""").fetchall()   # the per-site cap below limits reads, so one backlogged site can't starve the rest
    parked = {(s, j) for s, j, n, last in db.execute("SELECT source, job_id, n, last FROM detail_fails")
              if n >= FAIL_LIMIT and last and last > (datetime.now() - timedelta(hours=FAIL_PARK_HOURS)).isoformat()}
    base_cfg = {k: v for k, v in cfg.items() if k not in ("include", "include_case_sensitive")}
    from monitor import score  # local import: monitor imports this module
    from urllib.parse import urlparse
    cap = cfg.get("politeness", {}).get("detail_pages_per_site", 12)     # reads per site per batch
    per_site, read, failed, left = {}, 0, 0, 0
    for source, job_id, url, title, location, matched, was_done in rows:
        src = srcs.get(source)
        if not src or (source, job_id) in parked:
            continue
        host = urlparse(url).netloc
        if read + failed >= limit or per_site.get(host, 0) >= cap:
            left += 1                                    # waits for the next batch
            continue
        per_site[host] = per_site.get(host, 0) + 1
        try:
            text = fetch_text(src, job_id, url)
        except NotNow:
            continue
        except Exception:                                # leave it unread and retry; give up for a day after a few tries
            failed += 1
            db.execute("""INSERT INTO detail_fails VALUES (?,?,1,?) ON CONFLICT(source, job_id)
                          DO UPDATE SET n = n + 1, last = excluded.last""", (source, job_id, datetime.now().isoformat()))
            db.commit()
            continue
        read += 1
        db.execute("DELETE FROM detail_fails WHERE source=? AND job_id=?", (source, job_id))
        hits = desc_it_hits(text, terms) if text else 0
        if matched == 0 and hits >= need and score({"title": title, "location": location}, base_cfg) is not None:
            matched = 2
        descr = re.sub(r"\s+", " ", text).strip()[:8000]
        db.execute("""UPDATE jobs SET pay=?, closes=?, union_name=?, desc_hits=?, matched=?, details_done=1, descr=?
                      WHERE source=? AND job_id=?""",
                   (extract_pay(text), extract_closing(text), extract_union(text), hits, matched, descr, source, job_id))
        db.commit()            # short transactions, so the web server's read-only lookups are never kept waiting
        time.sleep(pause)
    db.commit()
    return {"read": read, "failed": failed, "left": left}


# ------------------------------------------------------------------ health
def record_health(db, name, ok):
    """Return True exactly once when a source reaches 3 consecutive failed runs."""
    row = db.execute("SELECT fails, alerted FROM health WHERE source=?", (name,)).fetchone()
    fails, alerted = row or (0, 0)
    if ok:
        db.execute("INSERT OR REPLACE INTO health VALUES (?,0,0)", (name,))
        return False
    fails += 1
    trip = fails >= 3 and not alerted
    db.execute("INSERT OR REPLACE INTO health VALUES (?,?,?)", (name, fails, 1 if trip or alerted else 0))
    return trip


# ------------------------------------------------------------------ digest
def load_track(cfg, user=None):
    """One user's tracker, or (no user) every user's merged, which is all the site builder needs to know what to keep."""
    folder = Path(cfg.get("data_dir", "."))
    if user:
        files = [folder / f"track-{user}.json"]
        if not files[0].exists():
            files = [folder / "track.json"]  # pre-multi-user tracker belonged to the primary user
    else:
        files = sorted(folder.glob("track*.json"))
    merged = {}
    for f in files:
        try:
            for url, entry in json.loads(f.read_text()).items():
                merged.setdefault(url, entry)
        except (FileNotFoundError, ValueError):
            continue
    return merged


def digest_data(db, cfg, user=None, p=None):
    """What goes in the weekly summary, as plain data. With no `p` it is the owner's IT digest."""
    import prefs as prefslib
    today = date.today()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    track = load_track(cfg, user or cfg.get("digest_user", "admin"))
    cols = ("source", "job_id", "title", "url", "location", "matched", "union_name", "pay", "closes", "first_seen")
    sector = {s["name"]: s.get("sector", "") for s in cfg.get("sources", [])}
    rows = [dict(zip(cols, r)) for r in db.execute(f"SELECT {', '.join(cols)} FROM jobs WHERE active=1")]
    for r in rows:
        r["sector"] = sector.get(r["source"], "")
        r["adjacent"] = r["matched"] == 2
    pred = (lambda r: r["matched"] > 0) if p is None else (lambda r: prefslib.matches(r, p))
    mine = [r for r in rows if pred(r) and track.get(r["url"], {}).get("status") != "not_interested"]
    new = sorted((r for r in mine if (r["first_seen"] or "") >= week_ago), key=lambda r: r["first_seen"], reverse=True)
    soon = sorted((r for r in mine if r["closes"] and today.isoformat() <= r["closes"] <= (today + timedelta(days=10)).isoformat()),
                  key=lambda r: r["closes"])
    by_url = {r["url"]: r for r in rows}
    due = []
    for u, entry in track.items():
        fu = entry.get("follow_up")
        if fu and fu <= (today + timedelta(days=3)).isoformat() and entry.get("status") in ("applied", "interview"):
            r = by_url.get(u)
            due.append({"date": fu, "title": r["title"] if r else u, "source": r["source"] if r else "", "notes": entry.get("notes", "")})
    counts = {}
    for entry in track.values():
        if entry.get("status") != "not_interested":
            counts[entry.get("status", "applied")] = counts.get(entry.get("status", "applied"), 0) + 1
    return {"new": new, "soon": soon, "due": sorted(due, key=lambda d: d["date"]),
            "pipeline": ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "nothing tracked yet"}


def build_digest(db, cfg, user=None, p=None):
    """The digest as plain text (used for dry runs and tests)."""
    import emailfmt
    who = user or cfg.get("digest_user", "admin")
    import prefs as prefslib
    first = prefslib.first_name(p or prefslib.load(Path(cfg.get("data_dir", ".")), who), who)
    return emailfmt.render_digest(first, who, digest_data(db, cfg, user, p), cfg.get("public_url", ""), "", "")[1]
