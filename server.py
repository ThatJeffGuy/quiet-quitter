#!/usr/bin/env python3
"""Serves the job-monitor site and stores your application tracking.

  python3 server.py SITE_DIR BIND PORT

  GET  /api/me      -> {"user": "<signed-in name>"}
  GET  /api/docs                 -> your uploaded resume and cover letter files: {"resume": {"file"}, "cover": {"file"}}
  POST /api/docs/file?name=&filename=   raw file bytes (PDF, Word, ODT, RTF or text, max 5 MB): upload your own file
  GET  /api/docs/file?name=      -> download the file you uploaded
  POST /api/docs/file/delete     {"name"}                         remove your uploaded file
  POST /api/docs/convert         {"name","to": "txt"} -> the plain text read from your file (the original is never changed)
  GET  /api/me                   -> {"user", "role": "admin|user", "flavor": {"greeting"}}
  GET  /api/admin/users          (admin) -> everyone who can sign in
  POST /api/admin/users          (admin) {"name","password"}                 add a person
  POST /api/admin/users/remove   (admin) {"name","purge": bool}              remove a person (purge also deletes their data)
  POST /api/admin/users/password (admin) {"name","password"}                 reset a password (signs them out everywhere)
  GET  /api/admin/flavor         (admin) -> all greeting text: {"_default": {"greeting"}, "<name>": {"greeting"}}
  POST /api/admin/flavor         (admin) {"key": "_default|<name>", "greeting": "..."}
  POST /api/autofill/report-fields (Bearer token, from the browser script) {"host","url","dump"} -> the script's silent "unrecognised form" report
  GET  /api/admin/field-reports  (admin) -> pending unrecognised-form reports, newest activity first: [{"host","url","dump","reported_by","first_seen","last_seen"}]
  POST /api/admin/field-reports/dismiss (admin) {"host"}   clear one report once its site has a template
  POST /api/password             {"current","new"}                           change your own password
  GET/POST /unsubscribe?u=&t=    (public, signed link in every email) stop alerts and the weekly summary with one click
  POST /api/mail                 {"provider","email","password","host","port"}   save YOUR mailbox + app password (write-only)
  POST /api/mail/test            send yourself a test message through that mailbox
  POST /api/mail/remove          forget your app password
  GET  /api/prefs                -> your settings + whether email alerts are available
  POST /api/prefs                body: any of mode, keywords, exclude, employers, union_only, email, alerts, digest
  POST /api/visit                -> {"since": <your previous visit>} and records this one
  GET  /api/match?url=           -> how well your resume matches one posting (terms found / missing)
  GET  /api/profile              -> your application profile (what autofill puts into other sites' forms)
  POST /api/profile              the whole profile object: save it
  POST /api/profile/parse        read your uploaded resume into the profile (fills blanks only; uses the local model if configured)
  POST /api/docs/tailor          {"terms": [...]} -> a COPY of your resume (.docx) with those keywords added under Skills
  GET  /api/autofill/token       -> the key your browser script uses to ask for drafted answers (POST /api/autofill/token/rotate replaces it)
  POST /api/answer               {"question","url"?,"max_words"?} -> a drafted answer to one application question (session or Bearer key)
  POST /api/fields               {"fields":[{"id","label","type","options"}]} -> values the profile/resume support (browser script fallback)
  POST /api/match/ai             {"url"} -> AI reading of the posting against your resume: requirements met/partial/gap with evidence
  POST /api/apply/draft          {"url"} -> drafts for one posting: employer details (remembered), cover letter, resume summary
  POST /api/apply/build          {"url","employer","contact","cover","summary","terms"} -> saves a personalised application pack
  GET  /api/apply/packs          -> your saved packs (newest first)
  GET  /api/apply/pack/file?id=&kind=cover|resume&fmt=docx|pdf   download one file of a pack
  GET  /autofill.user.js         the browser userscript (Tampermonkey/Violentmonkey) that fills other sites' forms
  GET  /api/track   -> your own {"<posting url>": {"status", "applied_at", "notes", "follow_up"}, ...}
  POST /api/track   body {"url": "...", "status": "applied|interview|offer|rejected|withdrawn|not_interested|none",
                          "notes": "...", "follow_up": "YYYY-MM-DD"}   (all but url optional)

Auth: a login page sets a 30-day session cookie. Everything except /login and /healthz needs it.

Environment:
  CROWDSEC_URL, CROWDSEC_KEY  if set, visitors with an active CrowdSec ban get 403 (fails open if CrowdSec is unreachable)
  STATE_DIRECTORY   data folder: users.json, track-<user>.json, session.key (default: current directory)
  JM_USER, JM_PASS  the primary login (plaintext, from the environment)
  JM_USERS          optional extra plaintext logins "a:pw1,b:pw2" (avoid `$` in values, Compose expands it)
  JM_ADMINS         comma list of admin usernames (default: the primary JM_USER)
  flavor.json       optional greeting text per person (see README)
  users.json        more logins with hashed passwords, managed with users.py; reloaded automatically.
  At least one login is required unless JM_ALLOW_OPEN=1.
"""
import base64
import hashlib
import html as htmllib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import appprofile
import docfiles
import employers
import letters
import llm
import tailor
import mailer
import match as matchlib
import unsub
import prefs as prefslib
import sqlite3
import users as userlib

SITE_DIR = Path(sys.argv[1])
BIND, PORT = sys.argv[2], int(sys.argv[3])
STATE_DIR = Path(os.environ.get("STATE_DIRECTORY", "."))
TRACK = STATE_DIR / "track.json"
LEGACY = STATE_DIR / "applied.json"  # older format: url -> ISO time
SESSION_DAYS = 30


STATE_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = STATE_DIR / "users.json"
_FILE_CACHE = {"mtime": None, "users": {}}


def env_users():
    users = {}
    if os.environ.get("JM_USER") and os.environ.get("JM_PASS"):
        users[os.environ["JM_USER"].strip().lower()] = os.environ["JM_PASS"]
    for pair in filter(None, os.environ.get("JM_USERS", "").split(",")):
        name, _, pw = pair.strip().partition(":")
        if name and pw:
            users[name.strip().lower()] = pw
    return users


ENV_USERS = env_users()
PRIMARY = next(iter(ENV_USERS), None)  # owner of any pre-existing single-user tracker
ADMINS = {a.strip().lower() for a in os.environ.get("JM_ADMINS", "").split(",") if a.strip()} or ({PRIMARY} if PRIMARY else set())


def login_name(typed):
    """The account a sign-in name belongs to: the account itself, or an older account without an @ whose saved email address was typed."""
    users = all_users()
    if typed in users or not userlib.is_email(typed):
        return typed
    for pf in STATE_DIR.glob("prefs-*.json"):
        try:
            if json.loads(pf.read_text()).get("email", "").strip().lower() == typed:
                name = pf.stem[len("prefs-"):]
                if name in users:
                    return name
        except (OSError, ValueError, AttributeError):
            continue
    return typed


def email_taken(addr, me):
    """True if another account already uses this address as its username or saved email (so sign-in stays unambiguous)."""
    addr = addr.strip().lower()
    if addr in all_users() and addr != me:
        return True
    for pf in STATE_DIR.glob("prefs-*.json"):
        try:
            if pf.stem[len("prefs-"):] != me and json.loads(pf.read_text()).get("email", "").strip().lower() == addr:
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def role_of(user):
    return "admin" if user in ADMINS else "user"


def cred_tag(user):
    """Short fingerprint of someone's current credential. Baked into their session cookie, so changing or
    resetting a password (or removing the person) signs them out everywhere."""
    stored = all_users().get(user, "")
    return hashlib.sha256(("tag|" + stored).encode()).hexdigest()[:10]


def all_users():
    """Environment logins plus users.json (re-read whenever the file changes). Environment wins on a name clash."""
    try:
        mtime = USERS_FILE.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    if mtime != _FILE_CACHE["mtime"]:
        _FILE_CACHE.update(mtime=mtime, users=userlib.load_file(USERS_FILE) if mtime else {})
    return {**_FILE_CACHE["users"], **ENV_USERS}


# Whether logins are required is decided once at start, so removing every user later can never open the site.
AUTH_REQUIRED = bool(all_users())
if not AUTH_REQUIRED and os.environ.get("JM_ALLOW_OPEN") != "1":
    sys.exit("Refusing to start without a login: set JM_USER and JM_PASS, add users.json, "
             "or set JM_ALLOW_OPEN=1 to serve with no login.")
KEY_FILE = STATE_DIR / "session.key"
if AUTH_REQUIRED and not KEY_FILE.exists():
    KEY_FILE.write_bytes(secrets.token_bytes(32))
    KEY_FILE.chmod(0o600)
KEY = KEY_FILE.read_bytes() if AUTH_REQUIRED else b""
DUMMY_HASH = userlib.hash_password("not-a-real-password")  # makes unknown-user logins cost the same as real ones
FAILS = {}  # client -> [timestamps of recent failed logins]


CS_URL, CS_KEY = os.environ.get("CROWDSEC_URL", "").rstrip("/"), os.environ.get("CROWDSEC_KEY", "")
CS_CACHE = {}          # ip -> (checked_at, banned)
CS_TTL = 60            # seconds a verdict is reused
CS_WARNED = [0.0]


def crowdsec_banned(ip):
    """True if CrowdSec has an active ban for this IP. Non-public addresses are never checked; errors fail open."""
    if not (CS_URL and CS_KEY):
        return False
    try:
        a = ipaddress.ip_address(ip)
        if not a.is_global:     # LAN, loopback, CGNAT, documentation ranges: never banned
            return False
    except ValueError:
        return False
    now = time.time()
    hit = CS_CACHE.get(ip)
    if hit and now - hit[0] < CS_TTL:
        return hit[1]
    try:
        req = urllib.request.Request(f"{CS_URL}/v1/decisions?{urllib.parse.urlencode({'ip': ip, 'type': 'ban'})}",
                                     headers={"X-Api-Key": CS_KEY})
        body = urllib.request.urlopen(req, timeout=3).read()
        banned = bool(json.loads(body or b"null"))
    except Exception as e:
        if now - CS_WARNED[0] > 300:
            print(f"crowdsec check failed ({type(e).__name__}); allowing traffic", flush=True)
            CS_WARNED[0] = now
        return False
    if len(CS_CACHE) > 5000:
        CS_CACHE.clear()
    CS_CACHE[ip] = (now, banned)
    if banned:
        print(f"blocked banned address {ip}", flush=True)
    return banned


def _is_public(ip):
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def client_ip(xff, cf_ip, peer):
    """Best guess at the real visitor address.

    The proxy appends the address it saw as the LAST X-Forwarded-For entry (earlier ones are client-supplied).
    Behind the Cloudflare Tunnel that address is just the tunnel host, so when it is internal we trust
    CF-Connecting-IP, which Cloudflare sets itself and visitors cannot override.
    """
    hop = xff.split(",")[-1].strip() or peer
    cf_ip = cf_ip.strip()
    if cf_ip and not _is_public(hop) and _is_public(cf_ip):
        return cf_ip
    return hop


_FLAVOR = {"mtime": None, "data": {}}


def flavor_data():
    path = STATE_DIR / "flavor.json"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    if mtime != _FLAVOR["mtime"]:
        try:
            data = json.loads(path.read_text()) if mtime else {}
        except ValueError:
            data = {}
        _FLAVOR.update(mtime=mtime, data=data if isinstance(data, dict) else {})
    return _FLAVOR["data"]


def flavor_for(user):
    """Greeting for one person: their own entry over the shared "_default". Empty means show nothing."""
    data = flavor_data()
    merged = {**(data.get("_default") or {}), **(data.get(user) or {})}
    return {"greeting": str(merged.get("greeting", ""))[:200].replace("{name}", prefslib.display_name(prefslib.load(STATE_DIR, user), user))}


TAGLINE = "Because a Timmy's giftcard doesn't pay the rent.."


OG_VERSION = "20261011b"       # bump when og-image.png changes: chat apps cache preview images by address
SITE_TITLE = "The Quiet Quitter"
IMAGE_ALT = f"A pink sprinkled donut beside the words {SITE_TITLE}. {TAGLINE}"


def page_title():
    return f"{SITE_TITLE} \u00b7 {TAGLINE}"


def manifest_json():
    """How the site presents itself when installed or pinned on a desktop or phone."""
    return json.dumps({"name": SITE_TITLE, "short_name": "Quiet Quitter", "description": TAGLINE, "lang": "en-CA",
                       "start_url": "/", "scope": "/", "display": "standalone", "background_color": "#f4f5f8", "theme_color": "#ec4899",
                       "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                                 {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                                 {"src": "/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
                                 {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png", "purpose": "any"}]}, indent=2)


def share_tags(base):
    """Open Graph / Twitter tags so a pasted link shows a proper preview card instead of a bare URL."""
    e = htmllib.escape
    img = f"{e(base)}/og-image.png?v={OG_VERSION}"
    return (f'<meta name="description" content="{e(TAGLINE)}">'
            f'<meta name="application-name" content="{SITE_TITLE}"><meta name="apple-mobile-web-app-title" content="Quiet Quitter">'
            f'<meta name="apple-mobile-web-app-capable" content="yes"><link rel="manifest" href="/manifest.webmanifest">'
            f'<meta property="og:type" content="website"><meta property="og:site_name" content="{SITE_TITLE}"><meta property="og:locale" content="en_CA">'
            f'<meta property="og:title" content="{SITE_TITLE}"><meta property="og:description" content="{e(TAGLINE)}">'
            f'<meta property="og:url" content="{e(base)}/"><meta property="og:image" content="{img}">'
            f'<meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            f'<meta property="og:image:alt" content="{e(IMAGE_ALT)}">'
            f'<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{SITE_TITLE}">'
            f'<meta name="twitter:description" content="{e(TAGLINE)}"><meta name="twitter:image" content="{img}">'
            f'<meta name="twitter:image:alt" content="{e(IMAGE_ALT)}">')


def login_page(base=""):
    page = LOGIN_PAGE.replace("</h1>", f'</h1><p class="tag">{htmllib.escape(TAGLINE)}</p>', 1)
    return page.replace("<title>The Quiet Quitter</title>", f"<title>{htmllib.escape(page_title())}</title>" + share_tags(base), 1)


def make_token(user):
    body = base64.urlsafe_b64encode(f"{user}|{int(time.time()) + SESSION_DAYS * 86400}|{cred_tag(user)}".encode()).decode()
    return body + "." + hmac.new(KEY, body.encode(), hashlib.sha256).hexdigest()


def check_token(token):
    try:
        body, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(KEY, body.encode(), hashlib.sha256).hexdigest()):
            return None
        user, exp, tag = base64.urlsafe_b64decode(body).decode().rsplit("|", 2)
        ok = int(exp) > time.time() and user in all_users() and hmac.compare_digest(tag, cred_tag(user))
        return user if ok else None
    except Exception:
        return None


LOGIN_PAGE = """<!doctype html><html lang="en-CA"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>The Quiet Quitter</title><link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#ec4899">
<style>
:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#667085;--line:#e4e7ec;--accent:#2563eb;--bad:#dc2626}
@media (prefers-color-scheme:dark){:root{--bg:#0f1318;--card:#171c23;--text:#e6e9ee;--muted:#8b95a5;--line:#262d37;--accent:#6ea0ff;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,sans-serif}
form{width:min(520px,94vw);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:24px;display:grid;gap:12px}
h1{font-size:20px;margin:0;display:flex;align-items:center;gap:10px}.mark{display:inline-block;width:1.6em;height:1.6em;background:#ec4899;-webkit-mask:url(/donut-mark.png) center/contain no-repeat;mask:url(/donut-mark.png) center/contain no-repeat;flex:none}@media (prefers-color-scheme:dark){.mark{background:#f472b6}}p{margin:0;color:var(--muted);font-size:13px}p.tag{font-style:italic;font-size:16px;margin:-2px 0 20px;white-space:nowrap;-webkit-user-select:none;user-select:none}@media (max-width:480px){p.tag{white-space:normal;font-size:15px}}p.note{text-align:center;font-size:12px;margin:0}
input,button{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text)}
button{background:var(--accent);border-color:var(--accent);color:#fff;cursor:pointer}#err{color:var(--bad);font-size:13px;min-height:1.2em}
</style></head><body>
<form id="f"><h1><span class="mark" aria-hidden="true"></span>The Quiet Quitter</h1>
<input name="user" type="text" inputmode="email" placeholder="Email address" autocomplete="username" autocapitalize="none" required autofocus>
<input name="pass" type="password" placeholder="Password" autocomplete="current-password" required>
<div id="err"></div><button>Sign in</button><p class="note">Sign-ups are closed.</p></form>
<script>
document.getElementById("f").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target, err = document.getElementById("err"); err.textContent = "";
  const r = await fetch("login", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({user: f.user.value.trim(), pass: f.pass.value})});
  if (r.ok) location.href = "./";
  else err.textContent = r.status === 429 ? "Too many attempts. Wait a few minutes." : "Wrong email or password.";
});
</script></body></html>"""
PAGE_CSS = """:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f24;--muted:#667085;--line:#e4e7ec;--accent:#ec4899}
@media (prefers-color-scheme:dark){:root{--bg:#0f1318;--card:#171c23;--text:#e6e9ee;--muted:#8b95a5;--line:#262d37;--accent:#f472b6}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}
main{width:min(420px,92vw);background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px;display:grid;gap:12px}
h1{font-size:20px;margin:0}p{margin:0;color:var(--muted)}button,.btn{font:inherit;padding:10px 16px;border:1px solid var(--accent);border-radius:999px;background:var(--accent);color:#fff;cursor:pointer;text-decoration:none;text-align:center}
.btn.alt{background:transparent;color:var(--accent)}"""


def simple_page(heading, message, extra=""):
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>The Quiet Quitter</title><link rel="icon" href="/favicon.ico"><style>{PAGE_CSS}</style></head>'
            f'<body><main><h1>{htmllib.escape(heading)}</h1><p>{message}</p>{extra}</main></body></html>')


ASSET_DIR = Path(__file__).resolve().parent / "assets"
PUBLIC_ASSETS = {"/atwork.js": "text/javascript; charset=utf-8", "/manifest.webmanifest": "application/manifest+json", "/og-image.png": "image/png", "/fsa.json": "application/json", "/favicon.ico": "image/x-icon", "/favicon-32.png": "image/png", "/icon-192.png": "image/png", "/icon-512.png": "image/png", "/icon-512-maskable.png": "image/png",
                 "/apple-touch-icon.png": "image/png", "/donut-mark.png": "image/png"}
STATUSES = {"applied", "interview", "offer", "rejected", "withdrawn", "not_interested"}
LOCK = threading.Lock()


def track_path(user):
    return STATE_DIR / f"track-{re.sub(r'[^a-z0-9._-]', '_', user)}.json"


def load(user):
    path = track_path(user)
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        pass
    except ValueError:
        return {}
    if user == PRIMARY:  # carry over the tracker from before there were separate users
        try:
            return json.loads(TRACK.read_text())
        except (FileNotFoundError, ValueError):
            pass
        try:
            return {u: {"status": "applied", "applied_at": t, "notes": "", "follow_up": ""}
                    for u, t in json.loads(LEGACY.read_text()).items()}
        except (FileNotFoundError, ValueError):
            pass
    return {}


def save(user, data):
    path = track_path(user)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)  # atomic: never leaves a half-written file


DOC_NAMES = ("resume", "cover")


def docs_path(user):
    return STATE_DIR / f"docs-{re.sub(r'[^a-z0-9._-]', '_', user)}.json"


def load_docs(user):
    try:
        data = json.loads(docs_path(user).read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    for n in DOC_NAMES:                                 # older versions also kept an editable text copy; it is ignored now
        data[n] = {"file": (data.get(n) or {}).get("file")}
    return data


FILES_DIR = STATE_DIR / "files"


def user_files(user):
    return FILES_DIR / re.sub(r"[^a-z0-9._-]", "_", user)


def clear_doc_file(user, name):
    folder = user_files(user)
    for ext in list(docfiles.UPLOAD_TYPES) + ["extracted"]:
        try:
            (folder / f"{name}.{ext}").unlink()
        except FileNotFoundError:
            pass


def write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def save_docs(user, data):
    path = docs_path(user)
    fd, tmp = tempfile.mkstemp(dir=path.parent)   # mkstemp creates the file private (0600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


_MAIL = {"mtime": None, "ready": False, "from": ""}


def mail_status():
    """Whether a dedicated sender is configured (names/values of non-secret settings only; the password is never read)."""
    path = STATE_DIR / "mail.env"
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return False, ""
    if mtime != _MAIL["mtime"]:
        env = {}
        for line in path.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?(SMTP_HOST|MAIL_FROM_ADDRESS)=(.*)", line)
            if m:
                env[m.group(1)] = m.group(2).strip().strip("'\"")
        _MAIL.update(mtime=mtime, ready=bool(env.get("SMTP_HOST") and env.get("MAIL_FROM_ADDRESS")),
                     **{"from": env.get("MAIL_FROM_ADDRESS", "")})
    return _MAIL["ready"], _MAIL["from"]


def site_templates():
    """Field templates for other employers' forms, shared by everyone's browser script. The copy shipped with the app is extended or
    overridden, site by site, by a site-templates.json in the data folder (so new ones can be added without a rebuild)."""
    out = {"version": 1, "sites": []}
    for path in (Path(__file__).resolve().parent / "site-templates.json", STATE_DIR / "site-templates.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for site in data.get("sites", []):
            if isinstance(site, dict) and site.get("id"):
                out["sites"] = [x for x in out["sites"] if x["id"] != site["id"]] + [site]
    return out


def job_row(url):
    """(source, title, description) for one posting, or None."""
    try:
        db = sqlite3.connect(f"file:{STATE_DIR / 'seen.db'}?mode=ro", uri=True, timeout=5)
        try:
            return db.execute("SELECT source, title, descr FROM jobs WHERE url=? LIMIT 1", (url,)).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return None


def source_label(source):
    try:
        cfg = json.loads((Path(__file__).resolve().parent / "config.json").read_text())
        return next((s.get("label", s["name"]) for s in cfg["sources"] if s["name"] == source), source)
    except (OSError, ValueError, KeyError):
        return source


TOKEN_FILE = "answer-tokens.json"
_ANSWER_TIMES = {}
_REPORT_TIMES = {}
FIELD_REPORTS_DIR = STATE_DIR / "field-reports"


def _tokens():
    try:
        d = json.loads((STATE_DIR / TOKEN_FILE).read_text())
        return d if isinstance(d, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def token_for(user, rotate=False):
    """A per-person key that lets their browser script ask for drafted answers (and nothing else)."""
    with LOCK:
        d = _tokens()
        if rotate or user not in d:
            d[user] = secrets.token_urlsafe(32)
            fd, tmp = tempfile.mkstemp(dir=STATE_DIR)
            with os.fdopen(fd, "w") as f:
                json.dump(d, f)
            os.replace(tmp, STATE_DIR / TOKEN_FILE)
        return d[user]


def user_for_token(tok):
    for user, t in _tokens().items():
        if hmac.compare_digest(str(t), tok):
            return user if user in all_users() else None        # a removed person's key stops working
    return None


MODEL_LOCK = threading.Lock()                 # the GPU does one request at a time
PACK_KEEP = 10


def packs_path(user):
    return STATE_DIR / f"packs-{re.sub(r'[^a-z0-9._-]', '_', user)}.json"


def load_packs(user):
    try:
        data = json.loads(packs_path(user).read_text())
        return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def job_id_of(url):
    m = re.search(r"(?<!\d)(\d{4,})(?!\d)", urllib.parse.urlparse(url).path)
    return m.group(1) if m else ""


def job_description(url, with_source=False):
    try:
        db = sqlite3.connect(f"file:{STATE_DIR / 'seen.db'}?mode=ro", uri=True, timeout=5)
        try:
            row = db.execute(f"SELECT title, descr{', source' if with_source else ''} FROM jobs WHERE url=? LIMIT 1", (url,)).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return None
    return row


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _base_url(self):
        proto = self.headers.get("X-Forwarded-Proto") or "http"
        host = self.headers.get("Host") or "localhost"
        return f"{proto}://{host}" if re.fullmatch(r"[A-Za-z0-9.\-:]{1,100}", host) else ""

    def _client(self):
        return client_ip(self.headers.get("X-Forwarded-For", ""), self.headers.get("CF-Connecting-IP", ""),
                         self.client_address[0])

    def _session_user(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, val = part.strip().partition("=")
            if name == "jm_session":
                return check_token(val)
        return None

    def _authorized(self, api=False):
        """True if the request may proceed. Otherwise a login page (browsers) or 401 (API) was sent."""
        if not AUTH_REQUIRED or self._session_user():
            return True
        if api:
            self._json({"error": "login required"}, 401)
        else:
            body = login_page(self._base_url()).encode()
            self.send_response(200 if self.path.split("?")[0] in ("/", "/index.html") else 401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        return False

    def _login(self):
        client, now = self._client(), time.time()
        recent = [t for t in FAILS.get(client, []) if now - t < 600]
        FAILS[client] = recent
        if len(recent) >= 10:
            return self._json({"error": "too many attempts"}, 429)
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= 1024:
                raise ValueError
            req = json.loads(self.rfile.read(n))
            user, pw = str(req["user"]), str(req["pass"])
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        user = login_name(user.strip().lower())
        stored = all_users().get(user)
        ok = userlib.verify_password(pw, stored if stored else DUMMY_HASH) and bool(stored)
        if not ok:
            FAILS[client].append(now)
            time.sleep(1)
            return self._json({"error": "bad login"}, 401)
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", f"jm_session={make_token(user)}; Path=/; HttpOnly; SameSite=Lax; "
                                       f"Max-Age={SESSION_DAYS * 86400}{secure}")
        self.end_headers()
        self.wfile.write(body)

    def _admin(self, who):
        if role_of(who) != "admin":
            self._json({"error": "forbidden"}, 403)
            return False
        return True

    def _same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urllib.parse.urlparse(origin).netloc == self.headers.get("Host", "")

    def _user_list(self):
        users = all_users()
        order = sorted(users, key=lambda n: (role_of(n) != "admin", n))
        return {"users": [{"name": n, "display": prefslib.display_name(prefslib.load(STATE_DIR, n), n), "role": role_of(n),
                           "managed": "portainer" if n in ENV_USERS else "site"} for n in order]}

    def _audit(self, who, action, target):
        try:
            with open(STATE_DIR / "admin.log", "a") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {who} {action} {target}\n")
        except OSError:
            pass

    def _body(self, limit=2048):
        n = int(self.headers.get("Content-Length", 0))
        if not 0 < n <= limit:
            raise ValueError
        req = json.loads(self.rfile.read(n))
        if not isinstance(req, dict):
            raise ValueError
        return req

    def _admin_post(self, who, path):
        if not self._admin(who):
            return
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body()
            name = userlib.clean_name(str(req["name"]))
            password = req.get("password")
            if name is None or (path == "/api/admin/users" and not userlib.is_email(name)):
                return self._json({"error": "bad_name"}, 400)
            if path != "/api/admin/users/remove" and (not isinstance(password, str) or not 8 <= len(password) <= 200):
                return self._json({"error": "weak_password"}, 400)
            purge = req.get("purge") is True
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            file_users = userlib.load_file(USERS_FILE)
            if path == "/api/admin/users":
                if name in all_users():
                    return self._json({"error": "exists"}, 409)
                file_users[name] = userlib.hash_password(password)
                action = "add"
            else:
                if name in ENV_USERS:
                    return self._json({"error": "managed_in_portainer"}, 400)
                if name not in file_users:
                    return self._json({"error": "not_found"}, 404)
                if path == "/api/admin/users/remove":
                    if name == who:
                        return self._json({"error": "cannot_remove_self"}, 400)
                    if name in ADMINS:
                        return self._json({"error": "cannot_remove_admin"}, 400)
                    del file_users[name]
                    action = "remove+purge" if purge else "remove"
                else:
                    file_users[name] = userlib.hash_password(password)
                    action = "reset-password"
            userlib.save_file(USERS_FILE, file_users)
            _FILE_CACHE["mtime"] = None       # make the change visible immediately
            if action == "remove+purge":
                safe = re.sub(r"[^a-z0-9._-]", "_", name)
                shutil.rmtree(user_files(name), ignore_errors=True)
                for prefix in ("docs", "track", "prefs", "mailcred"):
                    try:
                        (STATE_DIR / f"{prefix}-{safe}.json").unlink()
                    except FileNotFoundError:
                        pass
        self._audit(who, action, name)
        self._json(self._user_list())

    def _set_display(self, who):
        """Admin: set the full name shown for someone (the sign-in name is untouched)."""
        if not self._admin(who):
            return
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body(1024)
            user, disp = str(req["name"]).strip().lower(), " ".join(str(req["display"]).split())
            if user not in all_users():
                return self._json({"error": "not_found"}, 404)
            if not 1 <= len(disp) <= 60 or not re.fullmatch(r"[^\W\d_][\w .'’-]*", disp):
                return self._json({"error": "bad_display"}, 400)
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            p = prefslib.load(STATE_DIR, user)
            p["name"] = disp
            prefslib.save(STATE_DIR, user, p)
        self._audit(who, "set-name", user)
        self._json(self._user_list())

    def _save_flavor(self, who):
        if not self._admin(who):
            return
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body(4096)
            key = str(req["key"]).strip().lower()
            if key != "_default" and key not in all_users():
                return self._json({"error": "not_found"}, 404)
            if not isinstance(req.get("greeting"), str):
                raise ValueError
            fields = {"greeting": " ".join(req["greeting"].split())[:200]}
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            data = dict(flavor_data())
            entry = dict(data.get(key) or {})
            entry.update(fields)
            data[key] = {k: v for k, v in entry.items() if v}   # empty text means "show nothing": don't store it
            if not data[key]:
                del data[key]
            path = STATE_DIR / "flavor.json"
            fd, tmp = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
            _FLAVOR["mtime"] = None
        self._audit(who, "set-flavor", key)
        self._json(flavor_data())

    def _change_password(self, who):
        try:
            req = self._body()
            current, new = req["current"], req["new"]
            if not isinstance(current, str) or not isinstance(new, str) or not 8 <= len(new) <= 200:
                return self._json({"error": "weak_password"}, 400)
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        if who in ENV_USERS:
            return self._json({"error": "managed_in_portainer"}, 400)
        key, now = ("password", who), time.time()          # wrong guesses are limited, just like at sign-in
        recent = [t for t in FAILS.get(key, []) if now - t < 600]
        FAILS[key] = recent
        if len(recent) >= 10:
            return self._json({"error": "too many attempts"}, 429)
        with LOCK:
            file_users = userlib.load_file(USERS_FILE)
            if who not in file_users or not userlib.verify_password(current, file_users[who]):
                FAILS[key].append(now)
                time.sleep(1)
                return self._json({"error": "wrong_password"}, 403)
            file_users[who] = userlib.hash_password(new)
            userlib.save_file(USERS_FILE, file_users)
            _FILE_CACHE["mtime"] = None
        body = b'{"ok": true}'                  # the old session is now invalid; hand back a fresh one
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
        self.send_header("Set-Cookie", f"jm_session={make_token(who)}; Path=/; HttpOnly; SameSite=Lax; "
                                       f"Max-Age={SESSION_DAYS * 86400}{secure}")
        self.end_headers()
        self.wfile.write(body)
        self._audit(who, "change-own-password", who)

    def _save_prefs(self, who, visit=False):
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 <= n <= 8192 or (n == 0 and not visit):
                raise ValueError
            req = json.loads(self.rfile.read(n)) if n else {}
            changes = {} if visit else prefslib.validate(req)
        except (ValueError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            p = prefslib.load(STATE_DIR, who)
            if visit:
                previous = p["last_visit"]
                p["last_visit"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                prefslib.save(STATE_DIR, who, p)
                return self._json({"since": previous})
            p.update(changes)
            if p["alerts"] and not p["email"]:
                return self._json({"error": "email_required"}, 400)
            if (p["alerts"] or p["digest"]) and not (mail_status()[0] or mailer.public_view(STATE_DIR, who)["configured"]):
                return self._json({"error": "mail_not_set_up"}, 400)
            prefslib.save(STATE_DIR, who, p)
        ready, sender = mail_status()
        self._json({"prefs": p, "mail_ready": ready, "mail_from": sender, "mail_own": mailer.public_view(STATE_DIR, who)})

    def _page(self, html, code=200):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _unsub_who(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        user, tok = q.get("u", [""])[0].strip().lower(), q.get("t", [""])[0]
        good = userlib.clean_name(user) == user and unsub.valid(STATE_DIR, user, tok)      # an email address, or an older plain username
        return user, good

    def _unsubscribe(self, post):
        user, good = self._unsub_who()
        if not good:
            return self._page(simple_page("That link isn't valid", "It may have been copied incompletely. You can switch email alerts off any time "
                                          "under Settings after signing in.", '<a class="btn alt" href="/">Open The Quiet Quitter</a>'), 400)
        if not post:
            return self._page(simple_page("Stop these emails?", "You'll stop getting new-posting alerts and the weekly summary. "
                                          "You can turn them back on any time under Settings.",
                                          f'<form method="post" action="{htmllib.escape(self.path)}"><button>Yes, unsubscribe me</button></form>'
                                          '<a class="btn alt" href="/">Never mind</a>'))
        try:                                            # drain the small form body, if any (mail apps send "List-Unsubscribe=One-Click")
            self.rfile.read(min(int(self.headers.get("Content-Length", 0) or 0), 2048))
        except (ValueError, OSError):
            pass
        with LOCK:
            p = prefslib.load(STATE_DIR, user)
            p.update(alerts=False, digest=False, owner_email=False)
            prefslib.save(STATE_DIR, user, p)
        self._page(simple_page("You're unsubscribed", "No more alert or summary emails will be sent. "
                               "Changed your mind? Sign in and switch them back on under Settings.",
                               '<a class="btn" href="/#settings">Open Settings</a>'))

    def _send_file(self, data, ext, filename):
        self.send_response(200)
        self.send_header("Content-Type", docfiles.MIME[ext])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    _LAST_TEST = {}

    def _mail(self, who, path):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body(2048) if path == "/api/mail" else {}
        except (ValueError, TypeError):
            return self._json({"error": "bad request"}, 400)
        if path == "/api/mail/remove":
            with LOCK:
                mailer.remove(STATE_DIR, who)
                p = prefslib.load(STATE_DIR, who)
                if not mail_status()[0]:                # without any way to send, switch the email options off
                    p["alerts"] = p["digest"] = False
                    prefslib.save(STATE_DIR, who, p)
            return self._json({"mail_own": mailer.public_view(STATE_DIR, who), "prefs": p})
        if path == "/api/mail":
            try:
                port = req.get("port", 587)
                if not isinstance(port, int) or isinstance(port, bool):
                    raise ValueError("server")
                provider = req.get("provider")
                password = req.get("password") or None
                address = who if userlib.is_email(who) else str(req.get("email") or "").strip()   # the username is the sending address
                if not userlib.is_email(who) and address and email_taken(address, who):
                    return self._json({"error": "email_taken", "message": "Another account already uses that address."}, 409)
                with LOCK:
                    mailer.save(STATE_DIR, who, provider, address, password, str(req.get("host", "")), port)
                    p = prefslib.load(STATE_DIR, who)
                    p["email"] = address    # the alert address and the mailbox are one and the same
                    prefslib.save(STATE_DIR, who, p)
            except ValueError as e:
                return self._json({"error": f"bad_{e}"}, 400)
            return self._json({"mail_own": mailer.public_view(STATE_DIR, who), "prefs": p})
        # /api/mail/test: one message to yourself, from yourself; at most one every 20 seconds
        now = time.time()
        if now - self._LAST_TEST.get(who, 0) < 20:
            return self._json({"error": "slow_down", "message": "Please wait a few seconds before testing again."}, 429)
        self._LAST_TEST[who] = now
        creds = mailer.load(STATE_DIR, who)
        if not creds:
            return self._json({"error": "not_configured", "message": "Save your email address and app password first."}, 400)
        try:
            mailer.send(creds, "Test message from The Quiet Quitter",
                        "If you can read this, email alerts are set up and working.\n\nYou can turn alerts on under Settings. "
                        "This message was sent from your own account to yourself.")
            mailer.record(STATE_DIR, who)
            return self._json({"ok": True})
        except mailer.MailError as e:
            mailer.record(STATE_DIR, who, e.code)
            return self._json({"error": e.code, "message": str(e)}, 422)

    def _doc_name(self):
        name = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("name", [""])[0]
        return name if name in DOC_NAMES else None

    def _doc_file_get(self, who, path):
        name = self._doc_name()
        if name is None:
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            meta = load_docs(who)[name]["file"]
        if not meta:
            return self._json({"error": "no_file"}, 404)
        folder = user_files(who)
        if path == "/api/docs/file":
            try:
                data = (folder / f"{name}.{meta['ext']}").read_bytes()
            except FileNotFoundError:
                return self._json({"error": "no_file"}, 404)
            return self._send_file(data, meta["ext"], meta["name"])
        return self._json({"error": "not found"}, 404)

    def _upload_doc(self, who):
        name = self._doc_name()
        if name is None:
            return self._json({"error": "bad request"}, 400)
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n <= 0:
            return self._json({"error": "bad request"}, 400)
        if n > docfiles.MAX_BYTES:
            self.close_connection = True
            return self._json({"error": "too_large"}, 413)
        data = self.rfile.read(n)
        ext = docfiles.sniff(data)
        if ext is None:
            return self._json({"error": "unsupported_type"}, 415)
        filename = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("filename", ["document"])[0]
        try:                                           # reading the file can take a moment; do it before taking the lock
            text, note = docfiles.extract_text(data, ext), "ok"
        except ValueError as e:
            text, note = "", str(e)
        if ext in ("pdf", "docx", "doc", "odt", "rtf") and not text and note == "ok":
            note = "no_text"                           # e.g. a scanned PDF that is only pictures
        with LOCK:
            docs = load_docs(who)
            d = docs[name]
            clear_doc_file(who, name)
            folder = user_files(who)
            write_private(folder / f"{name}.{ext}", data)
            write_private(folder / f"{name}.extracted", text.encode())
            d["file"] = {"name": docfiles.safe_name(filename, ext), "ext": ext, "size": n, "note": note, "chars": len(text),
                         "uploaded": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            save_docs(who, docs)
            out = {"file": d["file"]}
        self._json(out)

    def _userscript(self):
        """The autofill script with its @match list limited to the employer hosts this site already watches
        (configured sources and manual links, plus the host of every posting currently listed)."""
        hosts, cfg = set(), {}
        try:
            cfg = json.loads((Path(__file__).resolve().parent / "config.json").read_text())
            urls = [v for s in cfg.get("sources", []) for v in s.values() if isinstance(v, (str, list))]
            urls = [x for u in urls for x in (u if isinstance(u, list) else [u])] + [m.get("url") for m in cfg.get("manual_links", [])]
            hosts |= {urllib.parse.urlparse(u).hostname for u in urls if isinstance(u, str) and u.startswith("https://")}
        except (OSError, ValueError):
            pass
        try:
            jobs = json.loads((Path(self.directory) / "jobs.json").read_text()).get("jobs", [])
            hosts |= {urllib.parse.urlparse(j.get("url", "")).hostname for j in jobs if str(j.get("url", "")).startswith("https://")}
        except (OSError, ValueError):
            pass
        for h in list(hosts):          # iCIMS serves its application forms from the bare tenant address (employment-x.icims.com -> x.icims.com)
            m = h and re.fullmatch(r"(?:employment|careers|jobs)-([a-z0-9-]+)\.icims\.com", h)
            if m:
                hosts.add(m.group(1) + ".icims.com")
        for site in site_templates().get("sites", []):      # forms that live on a different address than the postings (SuccessFactors, iCIMS forms...)
            hosts |= {h for h in site.get("match", []) if isinstance(h, str)}
        home = urllib.parse.urlparse(cfg.get("public_url", "")).hostname or ""
        hosts = sorted(h for h in hosts if h and re.fullmatch(r"[a-z0-9.-]+", h) and h != home)
        lines = "\n".join(f"// @match        https://{h}/*" for h in hosts) or "// (no employer sites known yet)"
        text = (Path(__file__).resolve().parent / "autofill.user.js").read_text().replace("// @@MATCHES@@", lines, 1)
        text = text.replace("@@HOME@@", home or (self.headers.get("Host") or "localhost").split(":")[0])
        return text.encode()

    def _apply_draft(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body(4096)
            url = req["url"]
            tone = req.get("tone") if req.get("tone") in letters.TONES else "professional"
            force_cover = bool(req.get("force_cover"))
            if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 1000:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        row = job_row(url)
        if row is None:
            return self._json({"error": "unknown_job"})
        source, title, descr = row
        resume = self._resume_text(who)
        if not resume.strip():
            return self._json({"error": "no_resume"})
        with LOCK:
            prof = appprofile.load(STATE_DIR, who)
        if not (prof["first"] and prof["last"]):
            return self._json({"error": "no_profile"})
        if not llm.URL:
            return self._json({"error": "no_model"})
        posting = descr if descr and len(descr) > 200 else title
        with MODEL_LOCK:
            emp = employers.get(STATE_DIR, source)
            found = letters.extract_employer(posting, title) if len(posting) > 200 else {}
            for k in employers.FIELDS:                  # remembered values win; the posting only fills blanks
                if not emp[k] and isinstance(found.get(k), str):
                    emp[k] = found[k].strip()[:200]
            emp["name"] = employers.get(STATE_DIR, source)["name"] or source_label(source) or emp["name"]
            reqs = letters.posting_requirements(posting) if posting is descr else {"cover_letter": False, "documents": [], "questions": []}
            highlights = letters.pick_highlights(resume, posting, title)       # fact-extraction first (fast model), then the writing
            want_cover = reqs["cover_letter"] or force_cover
            body = letters.cover_body(resume, posting, title, emp["name"], tone) if want_cover else ""
            summary = letters.resume_summary(resume, posting, title)
        if want_cover and not body:
            return self._json({"error": "model_failed"})
        with MODEL_LOCK:                               # drop claims the resume doesn't support (the posting's wording is not evidence)
            body = letters.repaired(body, resume, emp["name"], title) if body else ""
            summary = letters.repaired(summary, resume, emp["name"], title) if summary else summary
            g_body, cut_cover = letters.ground(body, resume, posting, emp["name"], title) if body else ("", 0)
            g_sum, cut_sum = letters.ground(summary, resume, posting, emp["name"], title) if summary else ("", 0)
            body, summary = g_body or body, g_sum or summary          # if everything was cut, keep the draft and let the warnings show
        contact = found.get("contact") if isinstance(found.get("contact"), str) else ""
        text = (body or "") + " " + (summary or "")
        warn = letters.unsupported_numbers(text, resume, posting)
        terms_warn = letters.unsupported_terms(text, resume, emp["name"], title)
        self._json({"title": title, "employer": emp, "contact": contact.strip()[:100], "cover": body, "summary": summary or "",
                    "check_numbers": warn, "check_terms": terms_warn, "highlights": highlights, "tone": tone, "requirements": reqs, "removed": cut_cover + cut_sum, "cover_skipped": not want_cover, "basis": "full posting" if posting is descr else "title only"})

    def _apply_build(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body(40000)
            url, cover = req["url"], str(req.get("cover", "")).strip()[:6000]
            if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 1000:
                raise ValueError
            emp = {k: str((req.get("employer") or {}).get(k, "")) for k in employers.FIELDS}
            contact = " ".join(str(req.get("contact", "")).split())[:100]
            summary = " ".join(str(req.get("summary", "")).split())[:700]
            wanted = req.get("highlights") if isinstance(req.get("highlights"), list) else []
            terms = tailor.clean_terms([t.strip() for t in str(req.get("terms", "")).split(",")]) if isinstance(req.get("terms"), str) else tailor.clean_terms(req.get("terms"))
        except (ValueError, KeyError, TypeError, AttributeError):
            return self._json({"error": "bad request"}, 400)
        row = job_row(url)
        if row is None:
            return self._json({"error": "unknown_job"})
        source, title, _ = row
        with LOCK:
            prof = appprofile.load(STATE_DIR, who)
            meta = load_docs(who)["resume"]["file"]
            emp = employers.save(STATE_DIR, source, emp)           # remembered for next time
        if not meta:
            return self._json({"error": "no_file"}, 404)
        try:
            data = (user_files(who) / f"resume.{meta['ext']}").read_bytes()
            if meta["ext"] == "txt":
                data = letters.text_to_docx(data.decode("utf-8", "ignore"))
            elif meta["ext"] != "docx":                            # backend-only conversion so the copy can be edited
                data = docfiles.convert(data, meta["ext"], "docx")
            resume_docx, done = tailor.customize(data, summary, terms, letters.verified_lines(self._resume_text(who), wanted))
        except (FileNotFoundError, ValueError, KeyError, OSError) as e:
            return self._json({"error": "build_failed", "message": str(e)}, 422)
        cover_docx = letters.letter_docx(letters.letter_lines(prof, emp, contact, title, cover)) if cover else None
        pid = hashlib.sha1(url.encode()).hexdigest()[:12]
        folder = user_files(who) / "packs" / pid
        if cover_docx:
            write_private(folder / "cover.docx", cover_docx)
        else:
            (folder / "cover.docx").unlink(missing_ok=True)
        write_private(folder / "resume.docx", resume_docx)
        entry = {"id": pid, "url": url, "title": title[:200], "employer": emp["name"], "job_id": job_id_of(url), "cover_text": cover,
                 "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with LOCK:
            packs = [p for p in load_packs(who) if p["id"] != pid]
            packs.insert(0, entry)
            for old in packs[PACK_KEEP:]:
                shutil.rmtree(user_files(who) / "packs" / old["id"], ignore_errors=True)
            fd, tmp = tempfile.mkstemp(dir=STATE_DIR)
            with os.fdopen(fd, "w") as f:
                json.dump(packs[:PACK_KEEP], f)
            os.replace(tmp, packs_path(who))
        self._json({"pack": entry, "summary_applied": done["summary"], "highlights_applied": done["highlights"], "keywords": done["keywords"]})

    def _pack_file(self, who):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        pid, kind, fmt = q.get("id", [""])[0], q.get("kind", [""])[0], q.get("fmt", ["docx"])[0]
        if kind not in ("cover", "resume") or fmt not in ("docx", "pdf") or not re.fullmatch(r"[0-9a-f]{12}", pid):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            entry = next((p for p in load_packs(who) if p["id"] == pid), None)
        if entry is None:
            return self._json({"error": "not found"}, 404)
        try:
            data = (user_files(who) / "packs" / pid / f"{kind}.docx").read_bytes()
            if fmt == "pdf":
                data = docfiles.convert(data, "docx", "pdf")
        except (FileNotFoundError, ValueError):
            return self._json({"error": "not found"}, 404)
        who_name = (appprofile.load(STATE_DIR, who).get("last") or "").strip()
        label = ("Cover letter" if kind == "cover" else "Resume") + (f" - {who_name}" if who_name else "") + f" - {entry['employer'] or entry['title']}"
        self._send_file(data, fmt, docfiles.safe_name(label.replace(".", ""), fmt))

    AI_CACHE = {}

    def _match_ai(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            url = self._body(4096)["url"]
            if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 1000:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        if not llm.URL:
            return self._json({"error": "no_model"})
        row, resume = job_row(url), self._resume_text(who)
        if row is None or not resume.strip():
            return self._json({"error": "unavailable"})
        posting = row[2] if row[2] and len(row[2]) > 200 else row[1]
        key = (who, url, hashlib.sha1((resume + posting).encode()).hexdigest())
        if key not in self.AI_CACHE:
            with MODEL_LOCK:
                result = letters.analyze(resume, posting, row[1])
            if not result:
                return self._json({"error": "model_failed"})
            if len(self.AI_CACHE) > 300:
                self.AI_CACHE.clear()
            self.AI_CACHE[key] = result
        self._json(self.AI_CACHE[key])

    def _answer(self, who, bearer):
        if not bearer and not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        now = time.time()
        recent = [t for t in _ANSWER_TIMES.get(who, []) if now - t < 60]
        if len(recent) >= 8:                                  # the GPU is shared: a handful of answers a minute is plenty
            return self._json({"error": "slow_down"}, 429)
        _ANSWER_TIMES[who] = recent + [now]
        try:
            req = self._body(8192)
            question = " ".join(str(req["question"]).split())[:1000]
            url = req.get("url") if isinstance(req.get("url"), str) and req.get("url", "").startswith(("http://", "https://")) else ""
            if len(question) < 8:
                raise ValueError
            max_words = int(req.get("max_words") or 150)
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        if not llm.URL:
            return self._json({"error": "no_model"})
        resume = self._resume_text(who)
        if not resume.strip():
            return self._json({"error": "no_resume"})
        row = job_row(url) if url else None
        title, employer, posting = (row[1], source_label(row[0]), row[2] or "") if row else ("", "", "")
        with MODEL_LOCK:
            res = letters.answer_question(resume, posting if len(posting) > 200 else "", title, employer, question, max_words)
        answer, removed = res if res else (None, 0)
        if res and (not answer or (removed >= 3 and len(answer.split()) < 40)):     # nothing real left to say: offer lines to build from
            with MODEL_LOCK:
                starters = letters.pick_highlights(resume, question, title, limit=3)
            return self._json({"error": "thin", "starters": starters, "message":
                               "Your resume doesn't describe a specific example for this, and I won't make one up. " +
                               ("Here are lines from it you could build your own answer on." if starters else "Please write it yourself.")})
        if answer is None:
            return self._json({"error": "personal", "message": "This asks for a personal detail or isn't something your resume can answer. Please answer it yourself."})
        self._json({"answer": answer, "check_numbers": letters.unsupported_numbers(answer, resume, posting),
                    "check_terms": letters.unsupported_terms(answer, resume, employer, title), "removed": removed, "job": title})

    def _fields(self, who, bearer):
        if not bearer and not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        now = time.time()
        recent = [t for t in _ANSWER_TIMES.get(who, []) if now - t < 60]
        if len(recent) >= 8:
            return self._json({"error": "slow_down"}, 429)
        _ANSWER_TIMES[who] = recent + [now]
        try:
            fields = self._body(30000)["fields"]
            if not isinstance(fields, list) or not fields or not all(isinstance(f, dict) for f in fields):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        if not llm.URL:
            return self._json({"error": "no_model"})
        with LOCK:
            prof = appprofile.load(STATE_DIR, who)
        with MODEL_LOCK:
            answers = letters.field_answers(prof, self._resume_text(who), fields)
        self._json({"answers": answers})

    def _report_fields(self, who, bearer):
        # The browser script's silent, background "here's a form I don't recognise" report.
        # Never includes what anyone typed -- only field names/labels/types (same shape as "List this page's fields").
        if not bearer and not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        now = time.time()
        recent = [t for t in _REPORT_TIMES.get(who, []) if now - t < 60]
        if len(recent) >= 10:
            return self._json({"error": "slow_down"}, 429)
        _REPORT_TIMES[who] = recent + [now]
        try:
            req = self._body(40000)
            host = str(req["host"]).strip().lower()
            dump = str(req["dump"])
            url = str(req.get("url", ""))[:500]
            if not re.fullmatch(r"[a-z0-9.-]{1,253}", host) or not dump.strip() or len(dump) > 20000:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        FIELD_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = FIELD_REPORTS_DIR / (host + ".json")
        with LOCK:
            try:
                existing = json.loads(path.read_text())
            except (OSError, ValueError):
                existing = {}
            if existing.get("dump") == dump:
                existing["last_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            else:
                existing = {"host": host, "url": url, "dump": dump, "reported_by": who,
                            "first_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "last_seen": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            path.write_text(json.dumps(existing))
        self._json({"ok": True})

    def _field_reports_list(self):
        out = []
        if FIELD_REPORTS_DIR.is_dir():
            for p in FIELD_REPORTS_DIR.glob("*.json"):
                try:
                    out.append(json.loads(p.read_text()))
                except (OSError, ValueError):
                    continue
        out.sort(key=lambda r: r.get("last_seen", ""), reverse=True)
        return {"reports": out}

    def _field_reports_dismiss(self, who):
        if not self._admin(who):
            return
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            host = str(self._body()["host"]).strip().lower()
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        (FIELD_REPORTS_DIR / (host + ".json")).unlink(missing_ok=True)
        self._json(self._field_reports_list())

    def _resume_text(self, who):
        try:
            return (user_files(who) / "resume.extracted").read_text()
        except FileNotFoundError:
            return ""

    def _profile_parse(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        text = self._resume_text(who)
        if not text.strip():
            return self._json({"error": "no_resume"})
        found = appprofile.parse_resume(text)
        smart = llm.parse_resume(text)
        if smart:                                       # the model's reading wins where it found something
            sec = appprofile._sections(text)
            for kind, names in (("education", ("educ",)), ("certifications", ("certif", "train", "course")), ("references", ("refer",))):
                if not appprofile.clean({kind: smart.get(kind)})[kind]:           # the big pass came back empty: try just that section
                    chunk = "\n".join(appprofile.find_all(sec, *names))
                    items = llm.parse_list(kind, chunk) if chunk.strip() else None
                    if items:
                        smart[kind] = items
            smart = appprofile.verify(smart, text)
            found = {k: (smart[k] or found[k]) for k in found}
        with LOCK:
            data = appprofile.merge_missing(appprofile.load(STATE_DIR, who), found)
            appprofile.save(STATE_DIR, who, data)
        self._json({"profile": data, "model": bool(smart)})

    def _profile_save(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            data = self._body(200_000)
        except (ValueError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            appprofile.save(STATE_DIR, who, data)
            data = appprofile.load(STATE_DIR, who)
        self._json({"profile": data})

    def _tailor_doc(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            terms = tailor.clean_terms(self._body(8192).get("terms"))
            if not terms:
                raise ValueError
        except (ValueError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            meta = load_docs(who)["resume"]["file"]
        if not meta:
            return self._json({"error": "no_file"}, 404)
        try:
            data = (user_files(who) / f"resume.{meta['ext']}").read_bytes()
            if meta["ext"] == "txt":
                out, where, ext = tailor.add_keywords_text(data.decode("utf-8", "ignore"), terms).encode(), "end", "txt"
            else:
                if meta["ext"] != "docx":              # backend-only use of the converter: PDF, .doc, ODT, RTF -> Word, then add the line
                    data = docfiles.convert(data, meta["ext"], "docx")
                (out, where), ext = tailor.add_keywords(data, terms), "docx"
        except FileNotFoundError:
            return self._json({"error": "no_file"}, 404)
        except (ValueError, KeyError, OSError) as e:
            return self._json({"error": "tailor_failed", "message": str(e)}, 422)
        self.send_response(200)
        self.send_header("Content-Type", docfiles.MIME[ext])
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Content-Disposition", f'attachment; filename="{docfiles.safe_name(Path(meta["name"]).stem + " tailored", ext)}"')
        self.send_header("X-Tailor-Where", where)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(out)

    def _delete_doc_file(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            name = self._body()["name"]
            if name not in DOC_NAMES:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            docs = load_docs(who)
            clear_doc_file(who, name)
            docs[name]["file"] = None
            save_docs(who, docs)
        self._json({"ok": True})

    def _convert_doc(self, who):
        if not self._same_origin():
            return self._json({"error": "forbidden"}, 403)
        try:
            req = self._body()
            name, to = req["name"], req["to"]
            if name not in DOC_NAMES or to != "txt":                  # the only copy offered is the plain text we read
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        with LOCK:
            meta = load_docs(who)[name]["file"]
        if not meta:
            return self._json({"error": "no_file"}, 404)
        if meta["ext"] == to:
            return self._json({"error": "same_format"}, 400)
        folder = user_files(who)
        try:
            if to == "txt":                            # the text is already extracted: no conversion engine needed
                try:
                    out = (folder / f"{name}.extracted").read_bytes()
                except FileNotFoundError:
                    out = docfiles.extract_text((folder / f"{name}.{meta['ext']}").read_bytes(), meta["ext"]).encode()
            else:
                out = docfiles.convert((folder / f"{name}.{meta['ext']}").read_bytes(), meta["ext"], to)
        except FileNotFoundError:
            return self._json({"error": "no_file"}, 404)
        except ValueError as e:
            return self._json({"error": "convert_failed", "message": str(e)}, 422)
        self._send_file(out, to, docfiles.safe_name(meta["name"], to))     # a copy; the stored original is untouched

    def _logout(self):
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", "jm_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _blocked(self):
        if crowdsec_banned(self._client()):
            body = b"Forbidden"
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        return False

    def _asset(self, path, head=False):
        """Brand images are public: the sign-in page itself needs them."""
        try:
            body = manifest_json().encode() if path == "/manifest.webmanifest" else (ASSET_DIR / path.lstrip("/")).read_bytes()
        except FileNotFoundError:
            self._json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", PUBLIC_ASSETS[path])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def do_GET(self):
        if self._blocked():
            return
        path = self.path.split("?")[0]
        if path in PUBLIC_ASSETS:
            return self._asset(path)
        if path == "/unsubscribe":
            return self._unsubscribe(post=False)
        if path == "/autofill.user.js":                # holds no personal data; the script reads your profile after you sign in
            body = self._userscript()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return self.wfile.write(body)
        if path == "/autofill-templates.json":             # shared form knowledge: field patterns only, nothing personal
            body = json.dumps(site_templates()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return self.wfile.write(body)
        if path == "/healthz":
            return self._json({"ok": True})
        if path.startswith("/api/"):
            if not self._authorized(api=True):
                return
            who = self._session_user() or "anonymous"
            if path == "/api/me":
                return self._json({"user": who, "role": role_of(who), "flavor": flavor_for(who), "email_login": userlib.is_email(who),
                                  "display": prefslib.display_name(prefslib.load(STATE_DIR, who), who)})
            if path == "/api/admin/users":
                if not self._admin(who):
                    return
                return self._json(self._user_list())
            if path == "/api/admin/flavor":
                if not self._admin(who):
                    return
                return self._json(flavor_data())
            if path == "/api/admin/field-reports":
                if not self._admin(who):
                    return
                return self._json(self._field_reports_list())
            if path == "/api/track":
                return self._json(load(who))
            if path == "/api/prefs":
                ready, sender = mail_status()
                with LOCK:
                    p = prefslib.load(STATE_DIR, who)
                return self._json({"prefs": p, "mail_ready": ready, "mail_from": sender, "mail_own": mailer.public_view(STATE_DIR, who)})
            if path == "/api/match":
                url = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("url", [""])[0]
                if not url.startswith(("http://", "https://")) or len(url) > 1000:
                    return self._json({"error": "bad request"}, 400)
                with LOCK:
                    meta = load_docs(who)["resume"]["file"]
                if not meta:
                    return self._json({"error": "no_resume"})
                try:
                    resume = (user_files(who) / "resume.extracted").read_text()
                except FileNotFoundError:
                    resume = ""
                if not resume.strip():
                    return self._json({"error": "no_text"})
                row = job_description(url, with_source=True)
                if row is None:
                    return self._json({"error": "unknown_job"})
                title, descr, source = row
                text = descr or ""
                basis = "full posting" if len(text) > 200 else "title only"
                result = matchlib.compare(text if len(text) > 200 else title, resume, skip=re.findall(r"[A-Za-z]{3,}", source or ""))   # the employer's own name isn't a skill
                result["basis"] = basis
                return self._json(result)
            if path == "/api/autofill/token":
                return self._json({"token": token_for(who)})
            if path == "/api/apply/packs":
                with LOCK:
                    return self._json({"packs": load_packs(who)})
            if path == "/api/apply/pack/file":
                return self._pack_file(who)
            if path == "/api/profile":
                with LOCK:
                    return self._json({"profile": appprofile.load(STATE_DIR, who), "model": bool(llm.URL)})
            if path == "/api/docs/file":
                return self._doc_file_get(who, path)
            if path == "/api/docs":
                with LOCK:
                    docs = load_docs(who)
                return self._json({n: {"file": docs[n]["file"]} for n in DOC_NAMES})
            return self._json({"error": "not found"}, 404)
        if not self._authorized():
            return
        super().do_GET()

    def do_HEAD(self):
        if self._blocked():
            return
        if self.path.split("?")[0] in PUBLIC_ASSETS:
            return self._asset(self.path.split("?")[0], head=True)
        if self._authorized():
            super().do_HEAD()

    def do_POST(self):
        if self._blocked():
            return
        path = self.path.split("?")[0]
        if path == "/unsubscribe":
            return self._unsubscribe(post=True)
        if path == "/login":
            return self._login()
        if path == "/logout":
            return self._logout()
        if path in ("/api/answer", "/api/fields", "/api/autofill/report-fields") and self.headers.get("Authorization", "").startswith("Bearer "):
            who = user_for_token(self.headers["Authorization"][7:].strip())     # the browser script's key: these routes only
            if not who:
                return self._json({"error": "unauthorized"}, 401)
            if path == "/api/answer":
                return self._answer(who, True)
            if path == "/api/fields":
                return self._fields(who, True)
            return self._report_fields(who, True)
        if not self._authorized(api=True):
            return
        if path == "/api/answer":
            return self._answer(self._session_user() or "anonymous", False)
        if path == "/api/fields":
            return self._fields(self._session_user() or "anonymous", False)
        if path == "/api/autofill/token/rotate":
            if not self._same_origin():
                return self._json({"error": "forbidden"}, 403)
            return self._json({"token": token_for(self._session_user() or "anonymous", rotate=True)})
        if path in ("/api/mail", "/api/mail/test", "/api/mail/remove"):
            return self._mail(self._session_user() or "anonymous", path)
        if path == "/api/docs/file":
            return self._upload_doc(self._session_user() or "anonymous")
        if path == "/api/docs/file/delete":
            return self._delete_doc_file(self._session_user() or "anonymous")
        if path == "/api/docs/convert":
            return self._convert_doc(self._session_user() or "anonymous")
        if path == "/api/match/ai":
            return self._match_ai(self._session_user() or "anonymous")
        if path == "/api/apply/draft":
            return self._apply_draft(self._session_user() or "anonymous")
        if path == "/api/apply/build":
            return self._apply_build(self._session_user() or "anonymous")
        if path == "/api/docs/tailor":
            return self._tailor_doc(self._session_user() or "anonymous")
        if path == "/api/profile":
            return self._profile_save(self._session_user() or "anonymous")
        if path == "/api/profile/parse":
            return self._profile_parse(self._session_user() or "anonymous")
        if path in ("/api/admin/users", "/api/admin/users/remove", "/api/admin/users/password"):
            return self._admin_post(self._session_user() or "anonymous", path)
        if path == "/api/admin/users/display":
            return self._set_display(self._session_user() or "anonymous")
        if path == "/api/admin/flavor":
            return self._save_flavor(self._session_user() or "anonymous")
        if path == "/api/admin/field-reports/dismiss":
            return self._field_reports_dismiss(self._session_user() or "anonymous")
        if path == "/api/password":
            return self._change_password(self._session_user() or "anonymous")
        if path == "/api/prefs" or path == "/api/visit":
            return self._save_prefs(self._session_user() or "anonymous", visit=(path == "/api/visit"))
        if path != "/api/track":
            return self._json({"error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            if not 0 < n <= 8192:
                raise ValueError
            req = json.loads(self.rfile.read(n))
            url = req["url"]
            if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 1000:
                raise ValueError
            status = req.get("status")
            if status is not None and status not in STATUSES | {"none"}:
                raise ValueError
            notes = req.get("notes")
            if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
                raise ValueError
            follow = req.get("follow_up")
            if follow is not None and not (isinstance(follow, str) and re.fullmatch(r"(\d{4}-\d{2}-\d{2})?", follow)):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._json({"error": "bad request"}, 400)
        who = self._session_user() or "anonymous"
        with LOCK:
            data = load(who)
            if status == "none":
                data.pop(url, None)
            else:
                e = data.setdefault(url, {"status": "applied", "notes": "", "follow_up": "",
                                          "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                if status:
                    e["status"] = status
                if notes is not None:
                    e["notes"] = notes
                if follow is not None:
                    e["follow_up"] = follow
            save(who, data)
        self._json(data)


ThreadingHTTPServer((BIND, PORT), partial(Handler, directory=str(SITE_DIR))).serve_forever()
