# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Signed one-click unsubscribe links for alert and digest emails.

A link carries the person's username and an HMAC of it, made with the server's private session key, so only
this server can create one and nobody can unsubscribe someone else. The link never expires, so an old email still works.
"""
import hashlib
import hmac
import urllib.parse
from pathlib import Path


def _key(folder):
    try:
        return (Path(folder) / "session.key").read_bytes()
    except FileNotFoundError:
        return b""


def token(folder, user):
    return hmac.new(_key(folder), f"unsubscribe|{user}".encode(), hashlib.sha256).hexdigest()[:40]


def valid(folder, user, tok):
    key = _key(folder)
    return bool(key) and isinstance(tok, str) and hmac.compare_digest(tok, token(folder, user))


def link(folder, site_url, user):
    q = urllib.parse.urlencode({"u": user, "t": token(folder, user)})
    return f"{site_url.rstrip('/')}/unsubscribe?{q}"
