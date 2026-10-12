# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: MIT
"""Be a considerate visitor to other people's websites.

Installed once per scan, it wraps every outgoing HTTP request that the scanner makes and:
  * waits at least `min_gap` seconds between requests to the same site;
  * reads each site's robots.txt and refuses pages it asks automated clients not to fetch
    (except for hosts you list under `robots_exceptions`, which are logged every run);
  * backs off when a site answers 429 or 503 (honouring Retry-After), and gives up on that site for the rest of the run;
  * stops asking a site for the rest of the run the moment it answers 403 (forbidden);
  * counts requests per site so the log shows exactly how much load a scan caused.
"""
import re
import sys
import time
import urllib.robotparser
from collections import Counter
from urllib.parse import urlparse

import requests

_ORIGINAL = requests.sessions.Session.request


class Blocked(requests.RequestException):
    """Raised instead of making a request we shouldn't (or can't usefully) make."""


class Polite:
    def __init__(self, min_gap=1.5, robots=True, robots_exceptions=(), max_tries=3, **other_settings):   # other settings belong to other parts
        self.min_gap, self.robots, self.exceptions = float(min_gap), robots, {h.lower() for h in robots_exceptions}
        self.max_tries = max_tries
        self.last, self.counts, self.stopped, self.noted = {}, Counter(), {}, set()
        self._robots = {}

    # -------------------------------------------------------------- robots.txt
    def _parser(self, scheme, host):
        key = (scheme, host)
        if key not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = _ORIGINAL(requests.Session(), "GET", f"{scheme}://{host}/robots.txt", timeout=10,
                              headers={"User-Agent": "job-monitor"})
                self.counts[host] += 1
                if r.status_code == 200 and "<html" not in r.text[:300].lower():
                    rp.parse(r.text.splitlines())
                else:
                    rp.parse([])                     # no robots.txt: nothing is restricted
            except requests.RequestException:
                rp.parse([])                         # couldn't read it: don't treat that as a ban
            self._robots[key] = rp
        return self._robots[key]

    def _allowed(self, method, url):
        if not self.robots or method.upper() != "GET":      # POSTs go to a site's own data endpoints, as its pages do
            return True
        p = urlparse(url)
        if p.path == "/robots.txt":
            return True
        if self._parser(p.scheme, p.netloc.lower()).can_fetch("job-monitor", url):
            return True
        host = p.netloc.lower()
        if host in self.exceptions:
            if host not in self.noted:
                self.noted.add(host)
                print(f"note: {host} asks automated tools not to fetch its job list (robots.txt); "
                      f"continuing only because it is listed as an exception in the config", file=sys.stderr)
            return True
        return False

    # -------------------------------------------------------------- the wrapper
    def _wait(self, host):
        gap = self.min_gap - (time.time() - self.last.get(host, 0))
        if gap > 0:
            time.sleep(gap)
        self.last[host] = time.time()

    def request(self, session, method, url, **kw):
        host = urlparse(url).netloc.lower()
        if host in self.stopped:
            raise Blocked(f"not asking {host} again this run ({self.stopped[host]})")
        if not self._allowed(method, url):
            raise Blocked(f"{host} asks automated tools not to fetch this page (robots.txt)")
        for attempt in range(1, self.max_tries + 1):
            self._wait(host)
            resp = _ORIGINAL(session, method, url, **kw)
            self.counts[host] += 1
            if resp.status_code in (429, 503):
                m = re.fullmatch(r"\d{1,3}", resp.headers.get("Retry-After", "").strip())
                pause = min(60, int(m.group(0)) if m else 10 * attempt * attempt)
                if attempt < self.max_tries:
                    time.sleep(pause)
                    continue
                self.stopped[host] = f"it keeps answering {resp.status_code}"
                raise Blocked(f"{host} is asking us to slow down ({resp.status_code}); giving up for this run")
            if resp.status_code == 403:
                self.stopped[host] = "it answered 403 forbidden"
            return resp
        raise Blocked("unreachable")

    def install(self):
        polite = self

        def wrapped(session, method, url, **kw):
            return polite.request(session, method, url, **kw)
        requests.sessions.Session.request = wrapped
        return self

    @staticmethod
    def uninstall():
        requests.sessions.Session.request = _ORIGINAL

    def summary(self):
        total = sum(self.counts.values())
        top = ", ".join(f"{h} {n}" for h, n in self.counts.most_common(3))
        stopped = "; ".join(f"{h}: {why}" for h, why in self.stopped.items())
        return f"requests this scan: {total} across {len(self.counts)} sites (busiest: {top})" + (f" | stopped early: {stopped}" if stopped else "")
