# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""The look of the emails: a polished HTML version and a tidy plain-text version of each message."""
import html as _html
from datetime import date, datetime

PINK, INK, MUTED, LINE, BG = "#ec4899", "#1b1f24", "#667085", "#e4e7ec", "#f6f7f9"
MAX_ITEMS = 30


def _esc(s):
    return _html.escape(str(s or ""), quote=True)


def _plural(n, one, many):
    return one if n == 1 else many


def _nice_date(iso):
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
        return d.strftime("%b %-d")
    except (ValueError, TypeError):
        return iso


def _details(it):
    """Employer first, then the useful facts, as a list of short strings."""
    bits = [it.get("source", "")]
    if it.get("location") and it["location"] not in bits[0]:
        bits.append(it["location"])
    if it.get("pay"):
        bits.append(it["pay"])
    if it.get("closes"):
        bits.append("closes " + _nice_date(it["closes"]))
    return [b for b in bits if b]


def _union(it):
    u = it.get("union_name") or it.get("union") or ""
    return u if u and u != "Non-union" else ""


def alert_subject(n):
    return f"Hey.. I found {n} new {_plural(n, 'posting', 'postings')}!"


# ------------------------------------------------------------------ shared pieces
def _button(url, label):
    return (f'<a href="{_esc(url)}" style="display:inline-block;background:{PINK};color:#ffffff;text-decoration:none;'
            f'font-weight:700;font-size:15px;padding:12px 22px;border-radius:999px">{_esc(label)}</a>')


def _pill(text, color):
    return (f'<span style="display:inline-block;font-size:11px;font-weight:700;letter-spacing:.03em;color:{color};'
            f'border:1px solid {color};border-radius:999px;padding:1px 8px;margin-left:6px;vertical-align:middle">{_esc(text)}</span>')


def _shell(preheader, inner, footer_html):
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:{BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{INK}">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{_esc(preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px">
<tr><td style="padding:0 4px 14px 4px"><div style="font-size:20px;font-weight:800;color:{INK}"><span style="color:{PINK}">&#9679;</span>&nbsp; The Quiet Quitter</div>
<div style="font-size:14px;font-style:italic;color:{MUTED};margin-top:2px">Because a Timmy&rsquo;s giftcard doesn&rsquo;t pay the rent..</div></td></tr>
<tr><td style="background:#ffffff;border:1px solid {LINE};border-radius:14px;padding:26px 26px 22px 26px">{inner}</td></tr>
<tr><td style="padding:16px 8px 0 8px;font-size:12px;line-height:1.6;color:{MUTED};text-align:center">{footer_html}</td></tr>
</table></td></tr></table></body></html>"""


def _footer(user, settings_url, unsub_url, why):
    html = (f'{_esc(why)}<br>'
            f'<a href="{_esc(settings_url)}" style="color:{MUTED}">Change what you get</a> &nbsp;&middot;&nbsp; '
            f'<a href="{_esc(unsub_url)}" style="color:{MUTED}">Unsubscribe</a><br>'
            f'<span style="color:#98a2b3">Please don&rsquo;t reply to this message.</span>')
    text = (f"{why}\nChange what you get: {settings_url}\nUnsubscribe in one click: {unsub_url}\nPlease don't reply to this message.")
    return html, text


# ------------------------------------------------------------------ new-posting alert
def render_alert(name, user, items, site_url, settings_url, unsub_url):
    """-> (subject, plain_text, html) for a list of new postings."""
    n = len(items)
    subject = alert_subject(n)
    shown = items[:MAX_ITEMS]
    rest = n - len(shown)
    intro = f"Here {_plural(n, 'is the one', 'are the ones')} that match what you're looking for."
    # plain text
    lines = [f"Hey {name},", "", f"I found {n} new {_plural(n, 'posting', 'postings')}! {intro}", ""]
    for i, it in enumerate(shown, 1):
        tags = ["IT adjacent"] if it.get("adjacent") else []
        if _union(it):
            tags.append(_union(it))
        lines += [f"{i}. {it['title']}" + (f"   [{', '.join(tags)}]" if tags else ""), "   " + " · ".join(_details(it)), f"   {it['url']}", ""]
    if rest > 0:
        lines += [f"...and {rest} more on the site.", ""]
    lines += [f"See everything: {site_url}", ""]
    f_html, f_text = _footer(user, settings_url, unsub_url, f"You're getting this because email alerts are on for your account ({user}).")
    text = "\n".join(lines) + "\n--\n" + f_text + "\n"
    # html
    rows = []
    for it in shown:
        pills = (_pill("IT ADJACENT", "#7c3aed") if it.get("adjacent") else "") + (_pill(_union(it), "#2563eb") if _union(it) else "")
        rows.append(f"""<tr><td style="padding:14px 0;border-top:1px solid {LINE}">
<a href="{_esc(it['url'])}" style="color:{INK};font-weight:700;font-size:16px;text-decoration:none">{_esc(it['title'])}</a>{pills}
<div style="margin-top:4px;font-size:13px;color:{MUTED};line-height:1.5">{' &middot; '.join(_esc(b) for b in _details(it))}</div>
<div style="margin-top:6px"><a href="{_esc(it['url'])}" style="color:{PINK};font-size:13px;font-weight:700;text-decoration:none">View posting &rarr;</a></div>
</td></tr>""")
    more = f'<p style="margin:12px 0 0 0;font-size:13px;color:{MUTED}">&hellip;and {rest} more on the site.</p>' if rest > 0 else ""
    inner = f"""<p style="margin:0 0 4px 0;font-size:22px;font-weight:800;line-height:1.25">Hey {_esc(name)} &#128075;</p>
<p style="margin:0 0 18px 0;font-size:15px;line-height:1.55;color:{MUTED}">I found <b style="color:{INK}">{n} new {_plural(n, 'posting', 'postings')}</b>. {_esc(intro)}</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{''.join(rows)}</table>{more}
<p style="margin:22px 0 0 0">{_button(site_url, 'Open The Quiet Quitter')}</p>"""
    return subject, text, _shell(f"{n} new {_plural(n, 'posting', 'postings')} for you", inner, f_html)


# ------------------------------------------------------------------ weekly digest
def render_digest(name, user, data, site_url, settings_url, unsub_url):
    """data comes from extras.digest_data(). -> (subject, plain_text, html)"""
    subject = "Your weekly roundup from The Quiet Quitter"
    sections = [("New this week", data["new"], "Nothing new this week."),
                ("Closing within 10 days", data["soon"], "Nothing closing soon."),
                ]
    f_html, f_text = _footer(user, settings_url, unsub_url, f"You're getting this weekly summary because it's switched on for your account ({user}).")
    # plain text
    out = [f"Hey {name},", "", "Here's your week."]
    for title, items, empty in sections:
        out += ["", f"{title.upper()} ({len(items)})"]
        if not items:
            out.append("  " + empty)
        for it in items[:MAX_ITEMS]:
            extra = " · ".join(_details(it)[1:])
            out += [f"  - {it['title']} ({it.get('source', '')})" + (f" · {extra}" if extra else ""), f"    {it['url']}"]
        if len(items) > MAX_ITEMS:
            out.append(f"  ...and {len(items) - MAX_ITEMS} more on the site.")
    out += ["", f"FOLLOW-UPS DUE ({len(data['due'])})"]
    out += [f"  - {d['date']}  {d['title']}" + (f" ({d['source']})" if d.get("source") else "") + (f"\n    note: {d['notes']}" if d.get("notes") else "") for d in data["due"]] or ["  Nothing due."]
    out += ["", f"YOUR PIPELINE: {data['pipeline']}", "", f"Open The Quiet Quitter: {site_url}", "", "--", f_text, ""]
    text = "\n".join(out)
    # html
    def block(title, items, empty):
        if not items:
            return f'<h3 style="margin:22px 0 6px 0;font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:{MUTED}">{_esc(title)}</h3><p style="margin:0;font-size:14px;color:{MUTED}">{_esc(empty)}</p>'
        rows = "".join(f"""<tr><td style="padding:10px 0;border-top:1px solid {LINE}"><a href="{_esc(it['url'])}" style="color:{INK};font-weight:700;font-size:15px;text-decoration:none">{_esc(it['title'])}</a>
{_pill("IT ADJACENT", "#7c3aed") if it.get("adjacent") else ""}{_pill(_union(it), "#2563eb") if _union(it) else ""}
<div style="margin-top:3px;font-size:13px;color:{MUTED}">{' &middot; '.join(_esc(b) for b in _details(it))}</div></td></tr>""" for it in items[:MAX_ITEMS])
        more = f'<p style="margin:8px 0 0 0;font-size:13px;color:{MUTED}">&hellip;and {len(items) - MAX_ITEMS} more on the site.</p>' if len(items) > MAX_ITEMS else ""
        return f'<h3 style="margin:22px 0 6px 0;font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:{MUTED}">{_esc(title)} <span style="color:{PINK}">({len(items)})</span></h3><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>{more}'
    due = "".join(f'<tr><td style="padding:8px 0;border-top:1px solid {LINE};font-size:14px"><b>{_esc(d["date"])}</b> &nbsp; {_esc(d["title"])}'
                  f'{(" <span style=color:" + MUTED + ">(" + _esc(d["source"]) + ")</span>") if d.get("source") else ""}'
                  f'{("<div style=color:" + MUTED + ";font-size:13px>Note: " + _esc(d["notes"]) + "</div>") if d.get("notes") else ""}</td></tr>' for d in data["due"])
    due_block = (f'<h3 style="margin:22px 0 6px 0;font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:{MUTED}">Follow-ups due <span style="color:{PINK}">({len(data["due"])})</span></h3>'
                 f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{due}</table>') if data["due"] else \
        f'<h3 style="margin:22px 0 6px 0;font-size:14px;letter-spacing:.04em;text-transform:uppercase;color:{MUTED}">Follow-ups due</h3><p style="margin:0;font-size:14px;color:{MUTED}">Nothing due.</p>'
    inner = f"""<p style="margin:0 0 2px 0;font-size:22px;font-weight:800">Hey {_esc(name)} &#128075;</p>
<p style="margin:0;font-size:15px;color:{MUTED}">Here&rsquo;s your week.</p>
{''.join(block(*s) for s in sections)}{due_block}
<p style="margin:22px 0 4px 0;font-size:13px;color:{MUTED}"><b style="color:{INK}">Your pipeline:</b> {_esc(data['pipeline'])}</p>
<p style="margin:18px 0 0 0">{_button(site_url, 'Open The Quiet Quitter')}</p>"""
    return subject, text, _shell("Your weekly roundup", inner, f_html)
