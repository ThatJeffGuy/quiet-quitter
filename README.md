# The Quiet Quitter

A self-hosted job-posting monitor. It watches public-sector and other employer job boards, flags new postings that
match what you care about (IT, trades, healthcare, education, police and paramedics, finance and administration, or your own keywords),
emails you about them, and gives you a searchable site to track applications, store a resume, compare it against a posting, and more.

It is a small Python (standard library, plus `cryptography`) server with a single-page front end, packaged as a Docker image. No external services are required.

> The bundled `config.json` ships with a set of example Ontario (Canada) employers. Replace them with the boards you want to watch (see *Adding employers* below).

## Quick start

    cp .env.example .env        # set JM_USER and JM_PASS (the app refuses to start without a login)
    docker compose up -d --build
    # open http://localhost:31361

Set `public_url` in `config.json` to your site's address (used for links in emails and for the browser autofill script).
Data lives in the mounted `data/` folder (see `docker-compose.yml`); back it up.

## Features
- Adapters for common job-board software: HRsmart, Workday, ADP, SuccessFactors, iCIMS, Taleo, Oracle HCM, TalentLink, Comeet, Dayforce, RSS feeds.
- Categories with title/keyword rules (`prefs.py`), distance filter from a postal-code prefix, union/pay/closing-date extraction, status tracking.
- Per-person logins (email addresses), their own tracker, documents, and email alerts sent from their own mailbox using an app password
  (stored encrypted; never sent back to the browser).
- Keyword Finder (compare your resume with a posting), Tailor Resume (optional local LLM through Ollama; plain parsing otherwise).
- Browser autofill userscript (Tampermonkey/Violentmonkey) served from `/autofill.user.js`.
- Light/dark theme, an "at work" boss key (press Esc twice) with Excel, Windows 11 and Windows 10 desktops that run the real job board, plus full-screen fake update screens (Windows 11/10, macOS, Ubuntu), and a console line with phrases you can rewrite (`tools/phrases.py`).

## Being a good neighbour
Scans are slow and polite (`polite.py`, `politeness` in `config.json`): at least 1.5 s between requests to a site, `robots.txt` respected,
429/503 waited out, 403 stops that site for the scan, and posting detail pages are read on a limited queue.
Some boards disallow robots entirely. To read such a host anyway, add it to `politeness.robots_exceptions` **only if you have decided that is acceptable
for your use**; the list ships empty.

## Configuration
Edit `config.json`: `sources` (employers), `include`/`desc_terms` (what counts as IT), `exclude_locations`, `manual_links`, `schedule`, `politeness`.
Environment variables (see `docker-compose.yml`, `portainer-stack.yml`): `JM_USER`, `JM_PASS`, `JM_USERS`, `JM_ADMINS`,
`OLLAMA_URL`, and optionally `CROWDSEC_URL`/`CROWDSEC_KEY` to refuse visitors with an active CrowdSec ban.

Add or remove logins without redeploying:

    docker exec -it the-quiet-quitter python3 /app/users.py add you@example.com
    docker exec -it the-quiet-quitter python3 /app/users.py list

The first login (`JM_USER`) is the admin; the Admin tab adds people and resets passwords.

## Console phrases
The console line draws from `phrases.json`. Export, edit and re-import them with `tools/phrases.py` (`export`, `check`, `import`).
The "donut easter egg" plays `assets/egg.mp3` if you supply one; it is not included.

## Adding employers
Copy an existing entry in `sources`, set its `type` (the adapter), the board's URL, and tag it with `place`, `label`, `group` and `sector`.
`site-templates.json` describes how application forms on each platform are recognised by the autofill script.

## Make it your own

Use **Use this template** on GitHub (or fork), then:

1. Set your own login in `portainer-stack.yml` / `docker-compose.yml` (`JM_USER`, `JM_PASS`; add more people from the Admin tab).
2. Edit `config.json`: your region, the employers to watch, and the keywords that count as your field.
3. Change the name and slogan in `server.py` (`SITE_TITLE`, `TAGLINE`), the header in `index.html` and the email header in `emailfmt.py`; replace the images in `assets/` and bump `OG_VERSION` so chat apps refresh the share image.
4. Rewrite the console phrases with `tools/phrases.py`.
5. Build and run (`docker compose up -d --build`), then put it behind your own HTTPS reverse proxy.

Please keep the credit and licence link in the footer if you run it as a service for other people.

## Licence
Copyright (c) 2026 That Scottish Guy. Licensed under the **MIT License** (see `LICENSE`).
You may use, copy, modify and redistribute it, as long as you keep the copyright notice and licence text with it.

Every source file carries an [SPDX](https://spdx.dev) tag (`SPDX-License-Identifier: MIT`), so tools can read the licence automatically.

## Credits
The donut artwork (`assets/`: logo mark, icons, share image) was generated with Google Gemini and is included under the same licence as the rest of the project.
The optional easter-egg audio is not included.
