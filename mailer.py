# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: MIT
"""Each person's own mailbox: they give an app password, and their alerts are sent from their account to themselves.

- The app password is stored encrypted (Fernet) in mailcred-<user>.json. The key lives in mail.key beside it,
  so this protects against casual exposure of the file, not against someone with full access to the server.
- It is write-only: the web page can set or remove it but never reads it back.
- Messages go from the person's own address to the same address, so nothing can be sent to anyone else.
- Connections use TLS and certificate checks. "Other" servers must resolve to public internet addresses, so the
  site can't be pointed at machines on the home network.
"""
import ipaddress
import json
import os
import re
import smtplib
import socket
import ssl
import tempfile
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# Test hook only: allows a plain local SMTP server. Never set in the real deployment.
TEST_MODE = os.environ.get("QQ_MAIL_TEST_MODE") == "1"

PROVIDERS = {
    "gmail": {"label": "Gmail", "host": "smtp.gmail.com", "port": 587,
              "help": "https://support.google.com/accounts/answer/185833"},
    "icloud": {"label": "Apple (iCloud Mail)", "host": "smtp.mail.me.com", "port": 587,
               "help": "https://support.apple.com/en-us/102654"},
    "outlook": {"label": "Microsoft (Outlook.com, Hotmail, Live)", "host": "smtp-mail.outlook.com", "port": 587,
                "help": "https://support.microsoft.com/en-us/account-billing/using-app-passwords-with-apps-that-don-t-support-two-step-verification-5896ed9b-4263-e681-128a-a6f2979a7944"},
    "microsoft365": {"label": "Microsoft 365 (work or school)", "host": "smtp.office365.com", "port": 587,
                     "help": "https://support.microsoft.com/en-us/account-billing/using-app-passwords-with-apps-that-don-t-support-two-step-verification-5896ed9b-4263-e681-128a-a6f2979a7944"},
    "other": {"label": "Other (your own SMTP server)", "host": "", "port": 587, "help": ""},
}
PORTS = (465, 587, 2525)
HOST_RE = re.compile(r"(?=.{4,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}")


class MailError(Exception):
    """code is a short machine-readable reason; the message is safe to show to the person."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


MESSAGES = {
    "auth_failed": "The provider rejected the email address or app password. Check both (the app password is not your normal password).",
    "connect_failed": "Couldn't reach the mail server. Check the server name and port, then try again.",
    "tls_failed": "The mail server's secure connection couldn't be verified.",
    "host_not_allowed": "That server name isn't allowed. Use a public mail server.",
    "send_failed": "The provider refused to send the message.",
}


# ------------------------------------------------------------------ storage
def _safe(user):
    return re.sub(r"[^a-z0-9._-]", "_", user)


def _cred_path(folder, user):
    return Path(folder) / f"mailcred-{_safe(user)}.json"


def _fernet(folder):
    key_file = Path(folder) / "mail.key"
    if not key_file.exists():
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(Fernet.generate_key())
    return Fernet(key_file.read_bytes())


def _read(folder, user):
    try:
        return json.loads(_cred_path(folder, user).read_text())
    except (FileNotFoundError, ValueError):
        return None


def _write(folder, user, data):
    p = _cred_path(folder, user)
    fd, tmp = tempfile.mkstemp(dir=p.parent)           # private (0600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, p)


def save(folder, user, provider, address, password=None, host="", port=587):
    """Validate and store a person's mailbox settings. A missing password keeps the one already saved."""
    if provider not in PROVIDERS:
        raise ValueError("provider")
    address = (address or "").strip()
    if not re.fullmatch(r"[^@\s<>,;]{1,64}@[^@\s<>,;]{1,200}\.[A-Za-z]{2,}", address) or len(address) > 254:
        raise ValueError("address")
    if provider == "other":
        host = (host or "").strip().lower()
        if not (HOST_RE.fullmatch(host) or (TEST_MODE and host in ("localhost", "127.0.0.1"))) or port not in PORTS:
            raise ValueError("server")
    else:
        host, port = PROVIDERS[provider]["host"], PROVIDERS[provider]["port"]
    old = _read(folder, user) or {}
    if password:
        if not isinstance(password, str) or not 4 <= len(password) <= 200 or "\n" in password or "\r" in password:
            raise ValueError("password")
        token = _fernet(folder).encrypt(password.encode()).decode()
    elif old.get("token"):
        token = old["token"]
    else:
        raise ValueError("password")
    _write(folder, user, {"provider": provider, "address": address, "host": host, "port": port, "token": token,
                          "last_ok": old.get("last_ok", ""), "last_error": ""})


def load(folder, user):
    """Decrypted settings for sending, or None."""
    d = _read(folder, user)
    if not d or not d.get("token"):
        return None
    try:
        pw = _fernet(folder).decrypt(d["token"].encode()).decode()
    except (InvalidToken, ValueError):
        return None
    return {k: d[k] for k in ("provider", "address", "host", "port")} | {"password": pw}


def public_view(folder, user):
    """What the web page may see: never the password."""
    d = _read(folder, user)
    if not d:
        return {"configured": False}
    return {"configured": True, "provider": d["provider"], "address": d["address"], "host": d["host"], "port": d["port"],
            "last_ok": d.get("last_ok", ""), "last_error": d.get("last_error", "")}


def remove(folder, user):
    try:
        _cred_path(folder, user).unlink()
    except FileNotFoundError:
        pass


def record(folder, user, error=""):
    """Remember whether the last send worked, so the settings page can say so."""
    d = _read(folder, user)
    if not d:
        return
    if error:
        d["last_error"] = error
    else:
        d["last_error"], d["last_ok"] = "", time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    _write(folder, user, d)


# ------------------------------------------------------------------ sending
def _resolve(host, port, trusted=False):
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise MailError("connect_failed", MESSAGES["connect_failed"])
    addrs = [i[4][0] for i in infos]
    if not addrs:
        raise MailError("connect_failed", MESSAGES["connect_failed"])
    if not (TEST_MODE or trusted) and any(not ipaddress.ip_address(a).is_global for a in addrs):
        raise MailError("host_not_allowed", MESSAGES["host_not_allowed"])
    return addrs[0]


def build_message(from_name, from_addr, to, subject, text, html=None, headers=None):
    """A tidy message: plain text plus (optionally) an HTML version, with any extra headers such as List-Unsubscribe."""
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg["Auto-Submitted"] = "auto-generated"
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


def deliver(host, port, user, pw, msg, trusted=False, timeout=25):
    """Log in to a mail server over TLS and send one prepared message. `trusted` skips the public-address check (our own configured server)."""
    port = int(port)
    ip = _resolve(host, port, trusted)                 # connect to the address we just vetted, verify the TLS name below
    ctx = ssl.create_default_context()
    smtp = None
    try:
        if port == 465:
            class _SSL(smtplib.SMTP_SSL):
                def _get_socket(self, h, p, t):
                    return ctx.wrap_socket(socket.create_connection((ip, p), t), server_hostname=host)
            smtp = _SSL(timeout=timeout, context=ctx)
            smtp.connect(host, port)
        else:
            smtp = smtplib.SMTP(timeout=timeout)
            smtp.connect(ip, port)
            smtp._host = host            # connect() records the raw IP; STARTTLS must check the certificate against the real name
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls(context=ctx)
                smtp.ehlo()
            elif not TEST_MODE:
                raise MailError("tls_failed", MESSAGES["tls_failed"])   # never send a password over an unencrypted link
        smtp.login(user, pw)
        smtp.send_message(msg)
    except MailError:
        raise
    except smtplib.SMTPAuthenticationError:
        raise MailError("auth_failed", MESSAGES["auth_failed"])
    except ssl.SSLError:
        raise MailError("tls_failed", MESSAGES["tls_failed"])
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, socket.timeout, TimeoutError, OSError):
        raise MailError("connect_failed", MESSAGES["connect_failed"])
    except smtplib.SMTPException:
        raise MailError("send_failed", MESSAGES["send_failed"])
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass


def send(creds, subject, body, from_name="The Quiet Quitter", html=None, headers=None, timeout=25):
    """Send one message from the person's own address to the same address."""
    msg = build_message(from_name, creds["address"], creds["address"], subject, body, html, headers)
    deliver(creds["host"], creds["port"], creds["address"], creds["password"], msg, timeout=timeout)
