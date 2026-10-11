# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Optional local language model (Ollama) used to read a resume more cleverly than pattern matching can.

Set OLLAMA_URL (for example http://ollama-host:11434) and optionally OLLAMA_MODEL. Nothing is sent anywhere else.
The model only ever receives the plain text already read from the uploaded file (never the file, images or scans).
Every function returns None when the model is unset or unreachable, and callers fall back to plain parsing.
"""
import json
import os
import urllib.request

URL = os.environ.get("OLLAMA_URL", "").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")


# Two jobs, two models: a fast one for pulling facts out of text, a stronger one for analysis and writing.
WRITE_MODEL = os.environ.get("OLLAMA_WRITE_MODEL", MODEL)


def _extra(model):
    """Qwen3 models 'think' out loud by default, which is slow and not wanted for extraction and drafting."""
    return {"think": False} if model.lower().startswith("qwen3") else {}

PROMPT = """Read this resume and return ONLY a JSON object with these keys (use "" or [] when unknown, never guess: copy only what the text states. If an employer, title, address or phone is not written in the resume, leave it empty):
first, last, email, phone, address, city, province, postal, linkedin, website, summary,
skills (list of short strings),
jobs (list, newest first, each {{title, employer, location, start, end, current, type, desc}} where start/end are copied exactly as written in the resume, month and day included when given, and end is "Present" only for a job that has not ended; location is a city and province only, never an employer name; current is "yes" for a job that has not ended, else ""; type is Full time, Part time, Contract, Casual, Seasonal or Internship only when the resume says so; desc is the bullet points joined by newlines),
education (list of {{school, credential, field, level, start, year, graduated}}; level is exactly one of High School, College Diploma, Bachelor's Degree, Master's Degree, PhD or "" ; start and year are years; graduated is "yes" only if the resume says the person finished),
certifications (list of {{name, issuer, year}}: professional certificates and training courses),
references (list of {{name, title, phone, email}}).

RESUME:
{text}"""


JUNK = {"various", "n/a", "na", "unknown", "none", "not specified", "not stated", "null", "tbd"}


def _blank_guesses(v):
    """Models like to write 'Various' or 'N/A' instead of leaving a blank; blank those so forms don't get them."""
    if isinstance(v, str):
        return "" if v.strip().lower() in JUNK else v
    if isinstance(v, list):
        return [_blank_guesses(x) for x in v]
    if isinstance(v, dict):
        return {k: _blank_guesses(x) for k, x in v.items()}
    return v


def parse_resume(text, timeout=180):
    if not URL:
        return None
    body = json.dumps({"model": MODEL, "prompt": PROMPT.format(text=text[:12000]), "stream": False, "format": "json",
                       "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 4000}, **_extra(MODEL)}).encode()
    try:
        req = urllib.request.Request(URL + "/api/generate", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(json.loads(r.read())["response"])
        return _blank_guesses(out) if isinstance(out, dict) else None
    except (OSError, ValueError, KeyError):
        return None


def generate(system, prompt, json_mode=False, temperature=0.4, timeout=300, write=True):
    """One chat reply as text (or a parsed object when json_mode). None if the model is unset or unreachable."""
    if not URL:
        return None
    model = WRITE_MODEL if write else MODEL
    body = json.dumps({"model": model, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                       **({"format": "json"} if json_mode else {}), "options": {"temperature": temperature, "num_ctx": 8192}, **_extra(model)}).encode()
    try:
        req = urllib.request.Request(URL + "/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.loads(r.read())["message"]["content"].strip()
        return _blank_guesses(json.loads(text)) if json_mode else text
    except (OSError, ValueError, KeyError):
        return None


LIST_PROMPTS = {
    "education": 'a list of {school, credential, field, level, start, year, graduated}; level is exactly one of High School, College Diploma, Bachelor\'s Degree, Master\'s Degree, PhD or ""; start and year are years; graduated is "yes" only if the text says the person finished',
    "certifications": 'a list of {name, issuer, year}: professional certificates and training courses',
    "references": 'a list of {name, title, phone, email}',
}


def parse_list(kind, section_text, timeout=120):
    """A second, narrower pass over just one resume section (education, certifications, references). None if unavailable."""
    if not URL or kind not in LIST_PROMPTS:
        return None
    prompt = (f"From this resume section, return ONLY JSON {{\"items\": ...}} where items is {LIST_PROMPTS[kind]}. Copy only what the text states; "
              f"use \"\" for anything it doesn't state.\n\nSECTION:\n{section_text[:4000]}")
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0, "num_ctx": 8192}, **_extra(MODEL)}).encode()
    try:
        req = urllib.request.Request(URL + "/api/generate", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(json.loads(r.read())["response"])
        items = out.get("items") if isinstance(out, dict) else None
        return _blank_guesses(items) if isinstance(items, list) else None
    except (OSError, ValueError, KeyError):
        return None
