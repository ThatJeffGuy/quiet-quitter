#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: MIT
"""Login accounts stored in a JSON file with salted scrypt password hashes (never plaintext).

Command line (inside the container):
  docker exec -it the-quiet-quitter python3 /app/users.py add EMAIL     # prompts for the password
  docker exec -it the-quiet-quitter python3 /app/users.py remove NAME
  docker exec -it the-quiet-quitter python3 /app/users.py list
Changes take effect immediately; no restart needed.
"""
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

N, R, P = 2 ** 14, 8, 1
NAME_RE = re.compile(r"[a-z0-9._-]{1,32}")          # older accounts (older names without an @) keep working
EMAIL_RE = re.compile(r"[a-z0-9._%+-]{1,64}@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}")
DEFAULT_FILE = Path(os.environ.get("STATE_DIRECTORY", "/data")) / "users.json"


def _b64(b):
    return base64.b64encode(b).decode()


def _scrypt(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=salt, n=N, r=R, p=P, dklen=32, maxmem=64 * 1024 * 1024)


def hash_password(pw):
    salt = secrets.token_bytes(16)
    return f"scrypt${_b64(salt)}${_b64(_scrypt(pw, salt))}"


def verify_password(pw, stored):
    """Check pw against a stored value: a scrypt hash from this module, or a plaintext string (env-provided logins)."""
    if stored.startswith("scrypt$"):
        try:
            _, salt, digest = stored.split("$")
            return hmac.compare_digest(_scrypt(pw, base64.b64decode(salt)), base64.b64decode(digest))
        except ValueError:
            return False
    return hmac.compare_digest(pw.encode(), stored.encode())


def is_email(name):
    return len(name) <= 120 and bool(EMAIL_RE.fullmatch(name))


def clean_name(name):
    """Lower-cased username (an email address, or an older plain name), or None if it isn't safe (it is also used in a filename)."""
    name = name.strip().lower()
    return name if NAME_RE.fullmatch(name) or is_email(name) else None


def clean_email(name):
    """Lower-cased email address for a NEW account, or None."""
    name = name.strip().lower()
    return name if is_email(name) else None


def load_file(path):
    try:
        return {k: v for k, v in json.loads(Path(path).read_text()).items() if isinstance(v, str)}
    except (FileNotFoundError, ValueError):
        return {}


def save_file(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main(argv):
    path = DEFAULT_FILE
    if len(argv) >= 2 and argv[0].endswith(".json"):
        path, argv = Path(argv[0]), argv[1:]
    if not argv or argv[0] not in ("add", "remove", "list"):
        sys.exit(__doc__)
    users = load_file(path)
    if argv[0] == "list":
        print("\n".join(sorted(users)) or "(no file users; env logins may still exist)")
        return
    name = (clean_email if argv[0] == "add" else clean_name)(argv[1]) if len(argv) > 1 else None
    if not name:
        sys.exit("Use an email address (or, for an older account, 1-32 characters of a-z, 0-9, dot, dash or underscore).")
    if argv[0] == "remove":
        if users.pop(name, None) is None:
            sys.exit(f"No such user: {name}")
        save_file(path, users)
        print(f"removed {name}")
        return
    pw = getpass.getpass(f"Password for {name}: ")
    if len(pw) < 8 or pw != getpass.getpass("Again: "):
        sys.exit("Passwords differ or are shorter than 8 characters.")
    users[name] = hash_password(pw)
    save_file(path, users)
    print(f"saved {name}")


if __name__ == "__main__":
    main(sys.argv[1:])
