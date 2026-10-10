# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Remembered employer details (name, mailing address) so a cover letter can be addressed without asking each time.

Stored once per employer source in employers.json. The first time a posting is prepared the address is read from the
posting text when it lists one; after that the saved value is reused and the person can correct it.
"""
import json
import os
import re
import tempfile
from pathlib import Path

FIELDS = ("name", "address", "city", "province", "postal")
POSTAL = re.compile(r"\b[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d\b")


def _path(state_dir):
    return Path(state_dir) / "employers.json"


def _all(state_dir):
    try:
        data = json.loads(_path(state_dir).read_text())
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def get(state_dir, source):
    row = _all(state_dir).get(source) or {}
    return {k: str(row.get(k, ""))[:200] for k in FIELDS}


def save(state_dir, source, info):
    data = _all(state_dir)
    row = {k: " ".join(str(info.get(k, "")).split())[:200] for k in FIELDS}
    if row["postal"]:
        m = POSTAL.search(row["postal"])
        row["postal"] = (m.group(0)[:3] + " " + m.group(0)[-3:]).upper() if m else ""
    data[source] = row
    path = _path(state_dir)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    return row
