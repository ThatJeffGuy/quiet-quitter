#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: MIT
"""Local-government job monitor for Newmarket / York Region.

Polls each source, remembers what it has seen in SQLite, and emails only
postings that are new (and match config.json filters).

  monitor.py              normal run (emails new matches)
  monitor.py --dry-run    print what would be sent, change nothing
  monitor.py --list       print every current matching posting (no state change)
"""
import argparse
import atexit
import fcntl
import html
import json
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import requests

import emailfmt
import extras
import mailer
import polite
import unsub
import prefs as prefslib

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (job-monitor; personal use)"}
TIMEOUT = 30


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


# --------------------------------------------------------------- adapters
# Each adapter returns a list of dicts: id, title, url, location (optional).

def hrsmart(base):
    """HRsmart ATS (York Region, Town of Newmarket)."""
    r = requests.get(f"{base}/hr/ats/JobSearch/viewAll", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = {}
    for href, text in re.findall(r'<a[^>]+href="([^"]*ats/Posting/view/\d+[^"]*)"[^>]*>(.*?)</a>', r.text, re.S):
        jid = re.search(r"/view/(\d+)", href).group(1)
        title = clean(text)
        if title:
            out[jid] = {"id": jid, "title": title, "url": urljoin(base, href)}
    return list(out.values())


def workday(host, tenant, site, base_path=""):
    """Workday CXS JSON API (Southlake)."""
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out, offset = [], 0
    while True:
        r = requests.post(url, headers=UA, timeout=TIMEOUT, json={
            "appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
        r.raise_for_status()
        j = r.json()
        for p in j.get("jobPostings", []):
            out.append({"id": p["externalPath"], "title": p["title"],
                        "location": p.get("locationsText", ""),
                        "url": f"https://{host}/{site}{p['externalPath']}"})
        offset += 20
        if offset >= j.get("total", 0) or not j.get("jobPostings"):
            return out


def adp(cid):
    """ADP WorkforceNow recruitment (Aurora, East Gwillimbury)."""
    r = requests.get(
        "https://workforcenow.adp.com/mascsr/default/careercenter/public/events/staffing/v1/job-requisitions",
        params={"cid": cid, "ccId": "19000101_000001", "lang": "en_CA", "locale": "en_CA", "$top": 100},
        headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for q in r.json().get("jobRequisitions", []):
        item = q["itemID"]
        out.append({"id": item, "title": q.get("requisitionTitle", "").strip(),
                    "url": ("https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html"
                            f"?cid={cid}&ccId=19000101_000001&lang=en_CA&jobId={item}")})
    return out


def rss(url):
    """Plain RSS feed (York Regional Police)."""
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        link = (it.findtext("link") or "").strip()
        if re.match(r"(?i)\s*no jobs? (currently )?available", clean(it.findtext("title"))):
            continue          # YRP publishes a placeholder entry when it has nothing open
        out.append({"id": link or it.findtext("guid"), "title": clean(it.findtext("title")),
                    "url": link, "location": clean(it.findtext("location") or "")})
    return out


def successfactors(base):
    """SAP SuccessFactors career site search page (Richmond Hill, City of Toronto, Mississauga, U of T, Toronto Hydro)."""
    out, start, step = {}, 0, None
    while start < 5000:
        r = requests.get(f"{base}/search/", params={"q": "", "startrow": start}, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        rows = re.findall(r'<a[^>]+class="[^"]*jobTitle-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)
        fresh = [(h, t) for h, t in rows if h not in out]
        if not fresh:
            break
        for h, t in fresh:
            out[h] = {"id": h, "title": clean(t), "url": urljoin(base, h)}
        step = step or len(set(h for h, _ in rows))      # the page size, counted once even if links are repeated
        start += step
    return list(out.values())

def comeet(url):
    """Comeet careers page with embedded JSON (Township of King)."""
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    m = re.search(r"COMPANY_POSITIONS_DATA\s*=\s*(\[.*?\]);", r.text, re.S)
    out = []
    for p in json.loads(m.group(1)) if m else []:
        loc = p.get("location") or {}
        out.append({"id": p["uid"], "title": p["name"], "location": loc.get("name", "") if isinstance(loc, dict) else "",
                    "url": p.get("url_active_page") or p.get("url_comeet_hosted_page") or url})
    return out


def icims(base):
    """iCIMS career portal search pages (Mackenzie Health)."""
    out, page = {}, 0
    while page < 30:
        r = requests.get(f"{base}/jobs/search", params={"ss": 1, "in_iframe": 1, "pr": page}, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        rows = re.findall(r'<a[^>]+href="([^"]*/jobs/(\d+)/[^"]*)"[^>]*class="iCIMS_Anchor"[^>]*title="[^"]*?-\s*([^"]*)"', r.text)
        new = [x for x in rows if x[1] not in out]
        if not new:
            break
        for href, jid, title in new:
            out[jid] = {"id": jid, "title": clean(title), "url": html.unescape(href).replace("?in_iframe=1", "")}
        page += 1
    return list(out.values())


def taleo_tbe(base, org, cws):
    """Oracle Taleo 'TBE' careers v2 (Seneca). Follows the site's own 'next' links, which need its session cookie."""
    s = requests.Session()
    s.headers.update(UA)
    url, out, pages = f"{base}/searchResults?org={org}&cws={cws}", {}, 0
    while url and pages < 40:
        r = s.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        fresh = 0
        for block in re.findall(r'oracletaleocwsv2-accordion-head-info">(.*?)</div>\s*<!--/.accordion-head-info', r.text, re.S):
            m = re.search(r'href="([^"]*viewRequisition[^"]*rid=(\d+)[^"]*)"[^>]*class="viewJobLink"[^>]*>(.*?)</a>', block, re.S)
            if not m or m.group(2) in out:
                continue
            divs = [clean(d) for d in re.findall(r'<div[^>]*>(.*?)</div>', block, re.S)]
            out[m.group(2)] = {"id": m.group(2), "title": clean(m.group(3)), "url": html.unescape(m.group(1)),
                               "location": divs[-1] if divs else ""}
            fresh += 1
        nxt = re.search(r'href="(/[^"]*searchResults\?next[^"]*)"', r.text)
        url = urljoin(base, html.unescape(nxt.group(1))) if nxt and fresh else None
        pages += 1
    return list(out.values())


def sf_category(url):
    """A SuccessFactors 'go' category page (York Regional Police): ordinary HTML that robots.txt allows."""
    out, start = {}, 0
    while start < 500:
        page = url.rstrip("/") + "/" + (f"{start}/" if start else "")
        r = requests.get(page, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        rows = re.findall(r'<a[^>]+class="[^"]*jobTitle-link[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)
        fresh = [(h, t) for h, t in rows if h not in out and not re.match(r"(?i)\s*no jobs? (currently )?available", clean(t))]
        if not fresh:
            break
        for h, t in fresh:
            out[h] = {"id": h, "title": clean(t), "url": urljoin(page, h)}
        start += 25
    return list(out.values())


def oracle_hcm(base, site="CX_1"):
    """Oracle HCM 'Candidate Experience' public job API (Metrolinx)."""
    out, offset = {}, 0
    api = f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    while offset < 2000:
        r = requests.get(api, params={"onlyData": "true", "expand": "requisitionList.secondaryLocations",
                                      "finder": f"findReqs;siteNumber={site},limit=50,offset={offset},sortBy=POSTING_DATES_DESC"},
                         headers={**UA, "Accept": "application/json"}, timeout=TIMEOUT)
        r.raise_for_status()
        items = (r.json().get("items") or [{}])[0].get("requisitionList") or []
        if not items:
            break
        for it in items:
            out[str(it["Id"])] = {"id": str(it["Id"]), "title": clean(it.get("Title", "")), "location": clean(it.get("PrimaryLocation", "")),
                                  "url": f"{base}/hcmUI/CandidateExperience/en/sites/{site}/job/{it['Id']}"}
        offset += 50
    return list(out.values())


def talentlink(host, tech_id, detail_base):
    """Lumesse TalentLink career site (Toronto District School Board). Its list already carries each posting's full text.

    The host's robots.txt asks automated clients to stay out; this runs only because the owner chose it as an exception
    (config politeness.robots_exceptions). One small request per scan, through the same throttle as every other site.
    """
    print(f"note: {host} asks automated tools not to use it (robots.txt); continuing only because it is listed as an exception in the config",
          file=sys.stderr)
    hdr = {**UA, "Content-Type": "application/json", "lumesse-language": "EN", "username": f"{tech_id}:guest:FO", "password": "guest"}
    out, first, total = {}, 0, None
    while first < 500 and (total is None or first < total):
        r = requests.post(f"https://{host}/fo/rest/jobs", params={"firstResult": first, "maxResults": 50, "sortBy": 1, "sortOrder": 0},
                          json={"searchCriteria": {"criteria": []}}, headers=hdr, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        total = int((data.get("globals") or {}).get("jobsCount") or 0)
        rows = data.get("jobs") or []
        if not rows:
            break
        for x in rows:
            f = x.get("jobFields") or {}
            jid, title = str(x.get("id")), clean(f.get("jobTitle") or f.get("SJOBTITLE") or "")
            if not jid or not title or jid in out:
                continue
            parts = [f"{title}. {clean(f.get('SLOVLIST11'))}. {clean(f.get('SLOVLIST17'))}."]
            parts += [clean(c.get("content")) for c in x.get("customFields") or [] if c.get("title") != "Working at the TDSB"]
            extras.TL_TEXT[(host, jid)] = "\n".join(p for p in parts if p)
            out[jid] = {"id": jid, "title": title, "location": clean(f.get("SLOVLIST2")) or "Toronto",
                        "url": f"{detail_base}?jobId={jid}&jobTitle={quote_plus(title)}"}
        first += len(rows)
    return list(out.values())


def taleo_location(value):
    """Taleo hands the location over as JSON text (["Barrie Campus"]); show it as plain words."""
    v = (value or "").strip()
    if v.startswith("["):
        try:
            parts = json.loads(v)
            if isinstance(parts, list):
                return ", ".join(clean(str(x)) for x in parts if x)
        except ValueError:
            pass
    return clean(v)


def taleo_tee(host, section, portal):
    """Oracle Taleo 'TEE' career section JSON search (Georgian College)."""
    out, page = {}, 1
    s = requests.Session()
    s.headers.update({**UA, "Accept": "application/json, text/javascript, */*", "X-Requested-With": "XMLHttpRequest",
                      "Content-Type": "application/json", "tz": "GMT-05:00",
                      "Referer": f"https://{host}/careersection/{section}/jobsearch.ftl?lang=en"})
    s.get(f"https://{host}/careersection/{section}/jobsearch.ftl?lang=en", timeout=TIMEOUT)          # picks up the session cookie
    while page <= 40:
        body = {"multilineEnabled": False, "sortingSelection": {"sortBySelectionParam": "3", "ascendingSortingOrder": "false"},
                "fieldData": {"fields": {"KEYWORD": "", "LOCATION": ""}, "valid": True},
                "filterSelectionParam": {"searchFilterSelections": []},
                "advancedSearchFiltersSelectionParam": {"searchFilterSelections": []}, "pageNo": page}
        r = s.post(f"https://{host}/careersection/rest/jobboard/searchjobs?lang=en&portal={portal}", json=body, timeout=TIMEOUT)
        r.raise_for_status()
        rows = r.json().get("requisitionList") or []
        fresh = [x for x in rows if str(x.get("jobId")) not in out]
        if not fresh:
            break
        for x in fresh:
            cols = x.get("column") or []
            out[str(x["jobId"])] = {"id": str(x["jobId"]), "title": clean(cols[0] if cols else ""), "location": taleo_location(cols[1] if len(cols) > 1 else ""),
                                    "url": f"https://{host}/careersection/{section}/jobdetail.ftl?job={x.get('contestNo', x['jobId'])}&lang=en"}
        page += 1
    return list(out.values())


def dayforce(tenant, site, culture="en-US"):
    """Dayforce candidate-portal JSON API (employer career sites hosted on jobs.dayforcehcm.com). Method borrowed from freehire (MIT, strelov1/freehire internal/ingest/sources/dayforce.go):
    GET /api/auth/csrf sets a cookie and returns a token, which is echoed in X-CSRF-TOKEN on the listing POST. 25 postings per page."""
    s = requests.Session()
    s.headers.update(UA)
    base = "https://jobs.dayforcehcm.com"
    tok = s.get(base + "/api/auth/csrf", timeout=TIMEOUT)
    tok.raise_for_status()
    token = tok.json()["csrfToken"]
    out, start = {}, 0
    while start < 1000:
        r = s.post(f"{base}/api/geo/{tenant}/jobposting/search", headers={"X-CSRF-TOKEN": token, "Accept": "application/json"}, timeout=TIMEOUT,
                   json={"clientNamespace": tenant, "jobBoardCode": site, "cultureCode": culture, "paginationStart": start})
        r.raise_for_status()
        d = r.json()
        items = d.get("jobPostings") or []
        if not items:
            break
        for it in items:
            jid = str(it["jobPostingId"])
            places = []
            for a in it.get("postingLocations") or []:
                p = ", ".join(x for x in (a.get("cityName"), a.get("stateCode")) if x)
                if p and p not in places:
                    places.append(p)
            out[jid] = {"id": jid, "title": clean(it.get("jobTitle", "")), "location": clean("; ".join(places)),
                        "url": f"{base}/{culture}/{tenant}/{site}/jobs/{jid}"}
        start += 25
        if len(out) >= d.get("maxCount", 0):
            break
    return list(out.values())


ADAPTERS = {"hrsmart": hrsmart, "workday": workday, "adp": adp, "rss": rss,
            "successfactors": successfactors, "comeet": comeet, "icims": icims, "taleo": taleo_tbe, "oracle_hcm": oracle_hcm, "taleo_tee": taleo_tee, "sf_category": sf_category, "talentlink": talentlink, "dayforce": dayforce}


# ---------------------------------------------------------------- filters
def score(job, cfg):
    """Return None if excluded, else an int (higher = better match)."""
    raw = f"{job['title']} {job.get('location', '')}"
    text = raw.lower()

    def word(w, s):
        return re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", s) is not None

    if any(w.lower() in text for w in cfg.get("exclude", [])):
        return None
    if any(w.lower() in text for w in cfg.get("exclude_locations", [])):
        return None
    inc, inc_cs = cfg.get("include", []), cfg.get("include_case_sensitive", [])
    if (inc or inc_cs) and not (any(word(w.lower(), text) for w in inc)
                                or any(word(w, raw) for w in inc_cs)):
        return None
    return 1 + sum(2 for w in cfg.get("boost", []) if w.lower() in text)


def classify(job, cfg):
    """0 = not IT, 1 = core IT, 2 = IT-adjacent.

    Core means the title names an IT job outright. Anything else that got past the broad `include` list (data, GIS, ERP, digital,
    "technology" teachers...) is adjacent, and so is an IT-sounding title in another field (a *Financial* Systems Analyst, a
    Health and Safety *Systems* role): the words in `it_domain` push it to adjacent."""
    if score(job, cfg) is None:
        return 0
    raw = job["title"]
    text = raw.lower()
    core = any(re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", text) for w in cfg.get("it_core", [])
               if w.lower() != "it") or any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", raw) for w in cfg.get("it_core_case_sensitive", []))
    strong = any(re.search(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", text) for w in cfg.get("it_strong", []))
    if core and not strong and any(re.search(r"(?<!\w)" + re.escape(w), text) for w in cfg.get("it_domain", [])):
        return 2
    return 1 if core else 2


# ------------------------------------------------------------------ email
def load_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_]\w*)=(.*)", line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip("'\"")
    return env


def mail_conf(cfg):
    env = load_env(cfg["email_env_file"])
    return {"env": env, "host": env.get("SMTP_HOST") or "smtp.gmail.com", "port": env.get("SMTP_PORT") or "587",
            "user": env.get("SMTP_USER") or env.get("GMAIL_USER"), "pw": env.get("SMTP_PASS") or env.get("GMAIL_APP_PASS"),
            "from_addr": env.get("MAIL_FROM_ADDRESS", ""), "from_name": env.get("MAIL_FROM_NAME", "The Quiet Quitter"),
            "owner": env.get("EMAIL_TO")}


def mail_ready(cfg):
    """True once a dedicated sender (SMTP_HOST + MAIL_FROM_ADDRESS) is configured. Until then only the owner gets mail,
    so nobody else is ever sent a message that carries the owner's personal address."""
    try:
        c = mail_conf(cfg)
    except (FileNotFoundError, KeyError):
        return False
    return bool(c["env"].get("SMTP_HOST") and c["from_addr"] and c["user"] and c["pw"])


def send_email(cfg, subject, body, to=None, html=None, headers=None):
    try:
        c = mail_conf(cfg)
        from_addr = c["from_addr"] or c["env"]["GMAIL_USER"]
        recipient = to or c["owner"]
        if not (recipient and c["user"] and c["pw"]):
            raise KeyError("incomplete mail settings")
    except (FileNotFoundError, KeyError) as e:   # report a failed send; never take the whole scan down
        print(f"email not sent: mail settings unavailable ({type(e).__name__})", file=sys.stderr)
        return False
    msg = mailer.build_message(c["from_name"], from_addr, recipient, subject, body, html, headers)
    try:
        mailer.deliver(c["host"], c["port"], c["user"], c["pw"], msg, trusted=True)   # our own configured server
        return True
    except mailer.MailError as e:
        print(f"email not sent: {e.code}", file=sys.stderr)
        return False


def unsub_headers(url):
    """The standard headers that give mail apps their own Unsubscribe button (RFC 8058 one-click)."""
    return {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"} if url else {}


def send_to_person(cfg, folder, user, p, subject, text, html=None, headers=None):
    """Send through the person's own mailbox if they set one up, else through the shared sender if there is one."""
    own = mailer.load(folder, user)
    if own:
        try:
            mailer.send(own, subject, text, html=html, headers=headers)
            mailer.record(folder, user)
            return True
        except mailer.MailError as e:
            mailer.record(folder, user, e.code)
            print(f"mail for {user}: {e.code}", file=sys.stderr)
            return False
    return mail_ready(cfg) and send_email(cfg, subject, text, to=p["email"], html=html, headers=headers)


def can_send(cfg, folder, user):
    return mailer.load(folder, user) is not None or mail_ready(cfg)


def user_alerts(db, cfg, dry=False):
    """Email each opted-in person their own new matches. The first run, or any change to their filters, is silent."""
    folder = Path(cfg.get("data_dir", HERE))
    db.execute("CREATE TABLE IF NOT EXISTS user_alerts (user TEXT, source TEXT, job_id TEXT, PRIMARY KEY (user, source, job_id))")
    db.execute("CREATE TABLE IF NOT EXISTS alert_state (user TEXT PRIMARY KEY, sig TEXT)")
    cols = ("source", "job_id", "title", "url", "location", "matched", "union_name", "pay", "closes")
    sector = {s["name"]: s.get("sector", "") for s in cfg["sources"]}
    known = [s["name"] for s in cfg["sources"]]
    rows = [{**dict(zip(cols, r)), "sector": sector.get(r[0], "")} for r in db.execute(f"SELECT {', '.join(cols)} FROM jobs WHERE active=1")]
    sent = 0
    for pf in sorted(folder.glob("prefs-*.json")):
        user = pf.stem[len("prefs-"):]
        p = prefslib.normalize(prefslib.load(folder, user), known)
        sig = json.dumps([p["mode"], p["keywords"], p["exclude"], p["employers"], p["union_only"]], sort_keys=True)
        have = {(s, j) for s, j in db.execute("SELECT source, job_id FROM user_alerts WHERE user=?", (user,))}
        state = db.execute("SELECT sig FROM alert_state WHERE user=?", (user,)).fetchone()
        declined = {u for u, t in extras.load_track(cfg, user).items() if t.get("status") == "not_interested"}
        new = [r for r in rows if prefslib.matches(r, p) and (r["source"], r["job_id"]) not in have and r["url"] not in declined]
        silent = state is None or state[0] != sig or not (p["alerts"] and p["email"] and can_send(cfg, folder, user))
        if dry:
            print(f"  alerts[{user}]: {'silent baseline' if silent else 'would email'} {len(new)} posting(s)")
            continue
        if not silent and new:
            site = cfg.get("public_url", "")
            items = [{"title": r["title"], "url": r["url"], "source": r["source"], "location": r["location"], "pay": r["pay"],
                      "closes": r["closes"], "union_name": r["union_name"], "adjacent": r["matched"] == 2} for r in new]
            link = unsub.link(folder, site, user) if site else ""
            subject, text, html = emailfmt.render_alert(prefslib.first_name(p, user), user, items, site, site + "/#settings", link)
            if not send_to_person(cfg, folder, user, p, subject, text, html, unsub_headers(link)):
                print(f"alerts[{user}]: email failed, will retry next run", file=sys.stderr)
                continue
            sent += 1
        for r in new:
            db.execute("INSERT OR IGNORE INTO user_alerts VALUES (?,?,?)", (user, r["source"], r["job_id"]))
        db.execute("INSERT OR REPLACE INTO alert_state VALUES (?,?)", (user, sig))
    db.commit()
    return sent


def user_digests(db, cfg, dry=False):
    folder = Path(cfg.get("data_dir", HERE))
    n = 0
    for pf in sorted(folder.glob("prefs-*.json")):
        user = pf.stem[len("prefs-"):]
        p = prefslib.normalize(prefslib.load(folder, user), [s["name"] for s in cfg["sources"]])
        if not (p["digest"] and p["email"] and can_send(cfg, folder, user)):
            continue
        site = cfg.get("public_url", "")
        link = unsub.link(folder, site, user) if site else ""
        subject, text, html = emailfmt.render_digest(prefslib.first_name(p, user), user, extras.digest_data(db, cfg, user=user, p=p),
                                                     site, site + "/#settings", link)
        if dry:
            print(f"--- digest for {user} -> {p['email']}\n{text}\n")
        elif send_to_person(cfg, folder, user, p, subject, text, html, unsub_headers(link)):
            n += 1
    return n


def notify(cfg, subject, body, html=None, headers=None):
    ok = send_email(cfg, subject, body, html=html, headers=headers)
    if cfg.get("ntfy_url"):  # optional, off by default: ntfy.sh is a public service
        try:
            requests.post(cfg["ntfy_url"], data=subject.encode(), headers={"Title": "Job Monitor"}, timeout=15)
        except requests.RequestException:
            pass
    return ok


# ------------------------------------------------------------------- site
def record_jobs(db, source, jobs, cfg):
    """Upsert every posting (matched or not) so the website can show all of them."""
    now = datetime.now().isoformat(timespec="seconds")
    # Postings already on a board when we first start watching it have no known first-seen date.
    known = db.execute("SELECT 1 FROM jobs WHERE source=? LIMIT 1", (source,)).fetchone()
    first = now if known else None
    db.execute("UPDATE jobs SET active=0 WHERE source=?", (source,))
    for j in jobs:
        matched = classify(j, cfg)
        db.execute("""INSERT INTO jobs (source, job_id, title, url, location, matched, first_seen, last_seen, active)
            VALUES (?,?,?,?,?,?,?,?,1)
            ON CONFLICT(source, job_id) DO UPDATE SET title=excluded.title, url=excluded.url,
            location=excluded.location, last_seen=excluded.last_seen, active=1,
            matched=CASE WHEN excluded.matched>0 THEN excluded.matched WHEN jobs.matched=2 THEN 2 ELSE 0 END""",
                   (source, j["id"], j["title"], j["url"], j.get("location", ""), matched, first, now))


def write_site(db, cfg, errors):
    site = Path(cfg.get("site_dir", HERE / "site"))
    site.mkdir(parents=True, exist_ok=True)
    cols = "source, title, url, location, matched, first_seen, pay, closes, union_name"
    rows = [r + (0,) for r in db.execute(
        f"SELECT {cols} FROM jobs WHERE active=1 ORDER BY matched DESC, first_seen DESC").fetchall()]
    track = extras.load_track(cfg)
    if track:  # keep postings you're tracking visible even after the employer takes them down
        marks = ",".join("?" * len(track))
        rows += [r + (1,) for r in db.execute(
            f"SELECT {cols} FROM jobs WHERE active=0 AND url IN ({marks})", list(track)).fetchall()]
    keys = ("source", "title", "url", "location", "it", "first_seen", "pay", "closes", "union", "closed")
    place = {s["name"]: s.get("place", "") for s in cfg["sources"]}
    jobs = []
    for r in rows:
        j = dict(zip(keys, r))
        j["lat"], j["lon"], j["place"], j["remote"] = extras.locate(place.get(j["source"], ""), j["location"], j["title"])
        jobs.append(j)
    sector = {s["name"]: s.get("sector", "") for s in cfg["sources"]}
    for j in jobs:
        j["sector"] = sector.get(j["source"], "")
    data = {"updated": datetime.now().isoformat(timespec="seconds"), "errors": errors,
            "manual": [{**m, "modes": prefslib.manual_modes(m)} for m in cfg.get("manual_links", [])], "jobs": jobs, "sector_rules": prefslib.SECTOR_RULES, "group_order": cfg.get("group_order", []),
            "sources": [{"name": s["name"], "label": s.get("label", s["name"]), "group": s.get("group", "Other"),
                         "sector": s.get("sector", "")} for s in cfg["sources"]]}
    (site / "jobs.json").write_text(json.dumps(data))
    tpl = HERE / "index.html"
    if tpl.exists():
        (site / "index.html").write_text(tpl.read_text())


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--digest", action="store_true", help="send the weekly summary email")
    ap.add_argument("--details", action="store_true", help="read one polite batch of waiting postings (exit 10 = more waiting, 11 = a scan is running)")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    pol = polite.Polite(**cfg.get("politeness", {})).install()
    atexit.register(lambda: print(pol.summary(), flush=True))

    lock = None
    if not (args.list or args.dry_run):    # only one scan at a time (the scheduler and a manual run must not collide)
        lock = open(Path(cfg.get("data_dir", HERE)) / "monitor.lock", "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another scan is already running; skipping this one")
            sys.exit(11 if args.details else 0)
    db = sqlite3.connect(Path(cfg.get("data_dir", HERE)) / "seen.db", timeout=30)
    db.execute("""CREATE TABLE IF NOT EXISTS seen (
        source TEXT, job_id TEXT, title TEXT, url TEXT, first_seen TEXT,
        PRIMARY KEY (source, job_id))""")
    db.execute("CREATE TABLE IF NOT EXISTS baselined (source TEXT PRIMARY KEY)")
    db.execute("""CREATE TABLE IF NOT EXISTS jobs (
        source TEXT, job_id TEXT, title TEXT, url TEXT, location TEXT,
        matched INTEGER, first_seen TEXT, last_seen TEXT, active INTEGER,
        PRIMARY KEY (source, job_id))""")
    extras.migrate(db)

    if args.details:
        res = extras.enrich(db, cfg)
        db.commit()
        if res["read"]:
            write_site(db, cfg, [])                      # publish the newly read closing dates, pay and unions
        print(f"details: read {res['read']}, failed {res['failed']}, {res['left']} still waiting")
        sys.exit(10 if res["left"] else 0)

    if args.digest:
        folder, owner = Path(cfg.get("data_dir", HERE)), cfg.get("digest_user", "admin")
        site = cfg.get("public_url", "")
        link = unsub.link(folder, site, owner) if site else ""
        owner_prefs = prefslib.normalize(prefslib.load(folder, owner), [s["name"] for s in cfg["sources"]])
        # the owner's summary follows their saved settings (employers, mode, excluded words, union), like everyone else's
        subject, text, html = emailfmt.render_digest(prefslib.first_name(owner_prefs, owner), owner, extras.digest_data(db, cfg, user=owner, p=owner_prefs), site, site + "/#settings", link)
        if args.dry_run or args.list:
            print(subject + "\n\n" + text)
            user_digests(db, cfg, dry=True)
        elif not prefslib.load(folder, owner)["owner_email"]:
            print("owner digest skipped: unsubscribed")
            print(f"person digests sent: {user_digests(db, cfg)}")
        elif not notify(cfg, subject, text, html=html, headers=unsub_headers(link)):
            print("EMAIL FAILED", file=sys.stderr)
            sys.exit(2)
        else:
            print(f"person digests sent: {user_digests(db, cfg)}")
        return

    new_by_source, errors, tripped = {}, [], []
    for src in cfg["sources"]:
        name = src["name"]
        try:
            jobs = ADAPTERS[src["type"]](*src.get("args", []))
        except Exception as e:  # one broken site must not stop the rest
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            if not args.list and not args.dry_run and extras.record_health(db, name, False):
                tripped.append(errors[-1])
            continue
        if not jobs and src.get("allow_empty"):
            jobs = []         # a board that is valid but has nothing open right now
        elif not jobs:
            errors.append(f"{name}: returned 0 postings (site layout may have changed)")
            if not args.list and not args.dry_run and extras.record_health(db, name, False):
                tripped.append(errors[-1])
            continue
        if not args.list and not args.dry_run:
            extras.record_health(db, name, True)
        matched = [(classify(j, cfg), j) for j in jobs]
        matched = [(s, {**j, "adjacent": s == 2}) for s, j in matched if s]       # core IT sorts first, adjacent is flagged
        if not args.list and not args.dry_run:
            record_jobs(db, name, jobs, cfg)
        if args.list:
            print(f"\n== {name} ({len(matched)}/{len(jobs)} match)")
            for s, j in sorted(matched, key=lambda x: -x[0]):
                print(f"  [{s}] {j['title']}  {j.get('location', '')}\n      {j['url']}")
            continue
        first_run = db.execute("SELECT 1 FROM baselined WHERE source=?", (name,)).fetchone() is None
        fresh = []
        for s, j in matched:
            if db.execute("SELECT 1 FROM seen WHERE source=? AND job_id=?", (name, j["id"])).fetchone():
                continue
            fresh.append((s, j))
            if not args.dry_run:
                db.execute("INSERT INTO seen VALUES (?,?,?,?,?)",
                           (name, j["id"], j["title"], j["url"], datetime.now().isoformat()))
        if first_run:
            # Don't email the whole existing board as "new" on the first run.
            print(f"{name}: baselined {len(fresh)} existing postings")
            if not args.dry_run:
                db.execute("INSERT INTO baselined VALUES (?)", (name,))
        elif fresh:
            new_by_source[name] = sorted(fresh, key=lambda x: x[0])      # core IT (1) before adjacent (2)
    if not args.dry_run and not args.list:
        db.commit()
        extras.enrich(db, cfg)
        maybe = db.execute("""SELECT j.source, j.job_id, j.title, j.url, j.location FROM jobs j
            WHERE j.active=1 AND j.matched=2 AND NOT EXISTS
            (SELECT 1 FROM seen s WHERE s.source=j.source AND s.job_id=j.job_id)""").fetchall()
        desc_first = db.execute("SELECT 1 FROM baselined WHERE source='__desc__'").fetchone() is None
        for source, jid, title, url, loc in maybe:
            db.execute("INSERT INTO seen VALUES (?,?,?,?,?)", (source, jid, title, url, datetime.now().isoformat()))
            if not desc_first:
                new_by_source.setdefault(source, []).append(
                    (1, {"title": title, "url": url, "location": loc, "adjacent": True}))
        if desc_first and db.execute("SELECT COUNT(*) FROM jobs WHERE details_done=1").fetchone()[0] \
                and not db.execute("SELECT 1 FROM jobs WHERE details_done=0 AND active=1").fetchone():
            db.execute("INSERT INTO baselined VALUES ('__desc__')")  # description scan has covered every posting once
        db.commit()
        write_site(db, cfg, errors)
        user_alerts(db, cfg)

    if args.list:
        for e in errors:
            print("ERROR", e)
        return

    declined = {u for u, t in extras.load_track(cfg, cfg.get("digest_user", "admin")).items() if t.get("status") == "not_interested"}
    if declined:    # the owner's own alerts also skip anything marked "not interested"
        new_by_source = {n: [x for x in items if x[1]["url"] not in declined] for n, items in new_by_source.items()}
        new_by_source = {n: items for n, items in new_by_source.items() if items}
    folder, owner = Path(cfg.get("data_dir", HERE)), cfg.get("digest_user", "admin")
    owner_prefs = prefslib.normalize(prefslib.load(folder, owner), [s["name"] for s in cfg["sources"]])
    sector = {s["name"]: s.get("sector", "") for s in cfg["sources"]}
    items = []
    for name, entries in new_by_source.items():
        for _, j in entries:
            row = db.execute("SELECT pay, closes, union_name FROM jobs WHERE source=? AND url=?", (name, j["url"])).fetchone() or ("", "", "")
            item = {"title": j["title"], "url": j["url"], "source": name, "location": j.get("location", ""), "pay": row[0] or "",
                    "closes": row[1] or "", "union_name": row[2] or "", "adjacent": bool(j.get("adjacent"))}
            # the owner's alerts follow their saved settings (employers, mode, excluded words, union), like everyone else's
            if prefslib.matches({**item, "matched": 2 if item["adjacent"] else 1, "sector": sector.get(name, "")}, owner_prefs):
                items.append(item)
    total = len(items)
    if total:
        site = cfg.get("public_url", "")
        link = unsub.link(folder, site, owner) if site else ""
        subject, text, html = emailfmt.render_alert(prefslib.first_name(owner_prefs, owner), owner, items, site, site + "/#settings", link)
        if args.dry_run:
            print(subject + "\n" + text)
        elif not prefslib.load(folder, owner)["owner_email"]:
            print(f"{total} new postings (not emailed: unsubscribed)")
        elif not notify(cfg, subject, text, html=html, headers=unsub_headers(link)):
            print("EMAIL FAILED", file=sys.stderr)
            sys.exit(2)
        else:
            print(f"emailed {total} new postings")
    else:
        print("no new postings")
    for e in errors:
        print("ERROR", e, file=sys.stderr)
    if tripped and not args.dry_run:
        notify(cfg, f"[Job Monitor] {len(tripped)} source(s) failing",
               "These sources have failed 3 runs in a row and may have changed their site:\n\n" + "\n".join(tripped))


if __name__ == "__main__":
    main()
