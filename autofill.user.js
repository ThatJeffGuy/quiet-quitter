// ==UserScript==
// @name         Quiet Quitter Autofill
// @namespace    https://@@HOME@@/
// @version      2.8
// @updateURL    https://@@HOME@@/autofill.user.js
// @downloadURL  https://@@HOME@@/autofill.user.js
// @description  Fills job-application forms from your Quiet Quitter profile and attaches your resume. You review and press Submit yourself.
// @match        https://@@HOME@@/*
// @@MATCHES@@
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_registerMenuCommand
// @grant        GM_setClipboard
// @grant        GM_xmlhttpRequest
// @connect      @@HOME@@
// @run-at       document-idle
// ==/UserScript==
// SPDX-FileCopyrightText: 2026 That Scottish Guy
// SPDX-License-Identifier: AGPL-3.0-only
(() => {
  "use strict";
  const HOME = "@@HOME@@";

  // ---------- On the Quiet Quitter site: copy profile + documents into the script's private storage ----------
  if (location.hostname === HOME) {
    const toB64 = buf => { let s = ""; const b = new Uint8Array(buf); for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000)); return btoa(s); };
    (async () => {
      try {
        const p = await (await fetch("/api/profile", { cache: "no-store" })).json();
        if (!p.profile) return;
        GM_setValue("profile", JSON.stringify(p.profile));
        const files = {};
        for (const n of ["resume", "cover"]) {
          const r = await fetch("/api/docs/file?name=" + n, { cache: "no-store" });
          if (!r.ok) continue;
          const cd = r.headers.get("Content-Disposition") || "";
          files[n] = { name: (cd.match(/filename="([^"]+)"/) || [])[1] || n, type: r.headers.get("Content-Type") || "application/octet-stream", b64: toB64(await r.arrayBuffer()) };
        }
        GM_setValue("files", JSON.stringify(files));
        try { GM_setValue("token", (await (await fetch("/api/autofill/token", { cache: "no-store" })).json()).token || ""); } catch (e) {}
        // Personalised application packs (cover letter + tailored resume per posting), newest five.
        const packs = [];
        try {
          const list = (await (await fetch("/api/apply/packs", { cache: "no-store" })).json()).packs || [];
          for (const p of list.slice(0, 5)) {
            const got = {};
            for (const kind of ["cover", "resume"]) {
              const r = await fetch(`/api/apply/pack/file?id=${p.id}&kind=${kind}&fmt=docx`, { cache: "no-store" });
              if (!r.ok) continue;
              const cd = r.headers.get("Content-Disposition") || "";
              got[kind] = { name: (cd.match(/filename="([^"]+)"/) || [])[1] || `${kind}.docx`, type: r.headers.get("Content-Type"), b64: toB64(await r.arrayBuffer()) };
            }
            packs.push({ id: p.id, title: p.title, employer: p.employer, job_id: p.job_id, url: p.url, cover_text: p.cover_text || "", files: got });
          }
        } catch (e) { /* packs are optional */ }
        GM_setValue("packs", JSON.stringify(packs));
        GM_setValue("synced", Date.now());
      } catch (e) { /* signed out: nothing to sync */ }
    })();
    return;
  }

  const P = (() => { try { return JSON.parse(GM_getValue("profile", "null")); } catch { return null; } })();
  const FILES = (() => { try { return JSON.parse(GM_getValue("files", "{}")); } catch { return {}; } })();
  const MEM = (() => { try { return JSON.parse(GM_getValue("memory", "{}")); } catch { return {}; } })();   // answers you typed, per site
  const memKey = (el, lab) => el.name || lab;
  const PACKS = (() => { try { return JSON.parse(GM_getValue("packs", "[]")); } catch { return []; } })();

  // Which pack to attach: the one you chose from the menu, else the pack whose job number is in this page's address,
  // else your plain resume and cover letter.
  function currentPack() {
    const chosen = GM_getValue("activePack", "");
    return PACKS.find(p => p.id === chosen) || PACKS.find(p => p.job_id && location.href.includes(p.job_id)) || null;
  }

  // ---------- Field discovery ----------
  const norm = s => (s || "").toLowerCase().replace(/[*:]/g, " ").replace(/\s+/g, " ").trim();
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== "hidden";

  // "icims_0_AddressLine" / "LastName" / "first-name" -> "address line" / "last name" / "first name"
  const humanize = s => s.replace(/^icims_(f|\d+|gh|ga)_/i, "").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/([a-zA-Z])(\d)/g, "$1 $2").replace(/[_-]+/g, " ");
  // What the browser's own autofill hints say a field is (Workday, Oracle, SuccessFactors and most modern forms set them).
  const AUTOCOMPLETE = { "given-name": "first name", "family-name": "last name", "additional-name": "middle name", "email": "email", "tel": "phone", "tel-national": "phone",
    "street-address": "address line 1", "address-line1": "address line 1", "address-line2": "address line 2", "address-level2": "city", "address-level1": "province",
    "postal-code": "postal code", "country": "country", "country-name": "country" };

  function caption(el) {                           // the visible text beside the field (e.g. a table cell's heading), without option lists
    const cell = el.closest("td, th, .form-group, .field");
    if (!cell) return "";
    const clone = cell.cloneNode(true);
    clone.querySelectorAll("select, option, input, textarea, script, style, button").forEach(n => n.remove());
    return clone.textContent.replace(/\s+/g, " ").trim().slice(0, 60);
  }

  function labelOf(el) {
    const bits = [];
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) bits.push(l.textContent); }
    const wrap = el.closest("label"); if (wrap) bits.push(wrap.textContent);
    ["aria-label", "placeholder", "title", "name", "id", "data-label", "data-automation-id", "data-testid", "data-qa", "data-test-id"]
      .forEach(a => el.getAttribute(a) && bits.push(humanize(el.getAttribute(a))));
    (el.getAttribute("autocomplete") || "").split(/\s+/).forEach(t => AUTOCOMPLETE[t] && bits.push(AUTOCOMPLETE[t]));
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach(i => { const n = document.getElementById(i); if (n) bits.push(n.textContent); });
    if (!bits.length || bits.join("").length < 3) {                       // fall back to the nearest text in the same row
      const row = el.closest(".form-group, .field, .row, li, tr, [class*=field], [class*=question]");
      if (row) bits.push(row.textContent.slice(0, 160));
    }
    const cap = caption(el); if (cap) bits.push(cap);
    return norm(bits.join(" | "));
  }

  // ---------- What each label means. First match wins, so order matters. ----------
  const PROV = { AB: "Alberta", BC: "British Columbia", MB: "Manitoba", NB: "New Brunswick", NL: "Newfoundland", NS: "Nova Scotia", NT: "Northwest Territories",
                 NU: "Nunavut", ON: "Ontario", PE: "Prince Edward Island", QC: "Quebec", SK: "Saskatchewan", YT: "Yukon" };
  function eduLevel(p) {                    // candidate wordings, best first ("||" separated); different employers word the same level differently
    const t = (p.education || []).map(e => `${e.credential} ${e.school}`).join(" ").toLowerCase();
    if (/ph\.?d|doctor/.test(t)) return "PhD||Doctorate";
    if (/master|msc|\bma\b|mba/.test(t)) return "Master's Degree||Masters Degree||Master";
    if (/bachelor|\bba\b|bsc|b\.a|b\.sc|university|degree/.test(t)) return "University Degree||Bachelor's Degree||Bachelor Degree||Undergraduate Degree";
    if (/diploma|college|certificate/.test(t)) return "College Diploma||Diploma||Associate Degree";
    if (/high school|secondary/.test(t)) return "High School||High School or GED||Secondary";
    return "";
  }
  const RULES = [
    [/highest (level of )?education/, p => eduLevel(p)],
    [/how did you hear|hear about us|referral source/, p => p.heard_about],
    [/e-?mail|courriel/, p => p.email],
    [/first name|given name|prénom|prenom/, p => p.first],
    [/last name|family name|surname|nom de famille/, p => p.last],
    [/preferred name|nickname/, p => p.first],
    [/full name|^name$|your name|legal name/, p => `${p.first} ${p.last}`.trim()],
    [/phone|mobile|cell|telephone|téléphone/, p => p.phone],
    [/postal|zip/, p => p.postal],
    [/address line 2|address 2|address2|apt\b|suite|unit number/, () => ""],         // second address line: leave empty
    [/street|address line 1|^address(?: \||$)/, p => p.address],
    [/\bcity|town|municipality/, p => p.city],
    [/province|state|region/, p => PROV[(p.province || "").toUpperCase()] || p.province],
    [/country|pays/, p => p.country],
    [/linkedin/, p => p.linkedin],
    [/website|portfolio|github|url/, p => p.website || p.linkedin],
    [/salary|compensation|pay expectation|wage/, p => p.salary],
    [/availab|start date|notice|earliest/, p => p.availability],
    [/summary|about you|tell us about|professional profile/, p => p.summary],
    [/skills|competenc/, p => (p.skills || []).join(", ")],
    [/current (job )?title|most recent (job )?title/, p => p.jobs?.[0]?.title],
    [/current employer|most recent employer|current company/, p => p.jobs?.[0]?.employer],
  ];
  const YESNO = [
    [/legally (entitled|eligible|authori[sz]ed|able)|authori[sz]ed to work|right to work|eligible to work|work (legally )?in canada/, p => p.work_auth],
    [/sponsor/, p => p.sponsorship],
  ];

  // Cards, ID numbers, birth date and the voluntary equity/demographic questions are left for you to answer.
  const SENSITIVE = /\b(sin|ssn|sex|dob|cvv|cvc|race|credit|card number|social insurance|date of birth|birth ?date|sexual orientation|first nations|m[eé]tis|inuit|visible minorit\w*)\b|\b(gender|pronoun|ethnic|indigenous|disabilit|veteran|racial|passport|password)\w*/;


  // ---------- Shared site templates (fetched from the Quiet Quitter site; they hold field patterns, never personal data) ----------
  // A rule matches a field by name/id/label regex and says what to do: value ("{first}", "{jobs[$1].employer}", "{salary|salary_n}"),
  // radio (a yes/no profile answer), pick (choose among option texts by profile conditions), checks (tick boxes named in a profile list),
  // or skip. "when" makes a rule apply only when an expression is non-empty. $1.. are the regex's captured numbers.
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function availDate(s) {
    s = (s || "").trim().toLowerCase(); if (!s) return null;
    const d = new Date(); let m;
    if ((m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/))) return { y: +m[1], m: +m[2], d: +m[3] };
    if ((m = s.match(/(\d+)\s*(day|week|month)/))) { const n = +m[1]; d.setDate(d.getDate() + (m[2] === "day" ? n : m[2] === "week" ? 7 * n : 30 * n)); }
    else if (!/immediate|asap|now|right away/.test(s)) return null;
    return { y: d.getFullYear(), m: d.getMonth() + 1, d: d.getDate() };
  }
  function salary(s) {                      // "$55/hr" -> {n:"55", unit:"Hr."}; "90k" or "90000 per year" -> {n:"90000", unit:"Yr."}
    const m = (s || "").replace(/,/g, "").match(/(\d+(?:\.\d+)?)\s*(k)?/i); if (!m) return null;
    let n = parseFloat(m[1]); if (m[2]) n *= 1000;
    const unit = /\b(hr|hour|hourly)\b|\/\s*h/i.test(s) ? "Hr." : /yr|year|annual|salary|\bk\b/i.test(s) || n >= 1000 ? "Yr." : "Hr.";
    return { n: String(Math.round(n * 100) / 100), unit };
  }
  const MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
  function parseDate(s) {                       // "Mar 2018", "March 2018", "2018-03", "03/2018", "2018" -> {y, m} (m = 0 when unknown); null for blanks and "Present"
    s = String(s || "").trim(); if (!s || /present|current|now|ongoing/i.test(s)) return null;
    let m;
    if ((m = s.match(/^(\d{4})-(\d{1,2})/))) return { y: +m[1], m: +m[2] };
    if ((m = s.match(/^(\d{1,2})\/(\d{4})$/))) return { y: +m[2], m: +m[1] };
    const mon = s.toLowerCase().match(/jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec/), yy = s.match(/\b(19|20)\d{2}\b/);
    return yy || mon ? { y: yy ? +yy[0] : 0, m: mon ? ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].indexOf(mon[0]) + 1 : 0 } : null;
  }
  const yr = s => ((s || "").match(/\b(19|20)\d{2}\b/) || [""])[0];

  const XF = {
    year: v => (parseDate(v) || {}).y ? String(parseDate(v).y) : yr(String(v || "")), province: v => PROV[String(v || "").toUpperCase()] || v, cad: v => v ? "CAD" : "",
    salary_n: v => (salary(String(v || "")) || {}).n || "", salary_unit: v => (salary(String(v || "")) || {}).unit || "",
    avail_month: v => { const r = availDate(String(v || "")); return r ? MONTHS[r.m - 1] : ""; },
    avail_day: v => { const r = availDate(String(v || "")); return r ? String(r.d) : ""; },
    avail_year: v => { const r = availDate(String(v || "")); return r ? String(r.y) : ""; },
    edu_level: v => eduLevel({ education: Array.isArray(v) ? v : [] }),
    month_num: v => { const d = parseDate(v); return d && d.m ? String(d.m).padStart(2, "0") : ""; },
    month_abbr: v => { const d = parseDate(v); return d && d.m ? MONTHS[d.m - 1] : ""; },
    month_name: v => { const d = parseDate(v); return d && d.m ? MONTH_NAMES[d.m - 1].replace(/^./, c => c.toUpperCase()) : ""; },
    degree_alts: v => ({ "Bachelor's Degree": "Bachelor's Degree||Bachelor||University Degree||Bachelors", "College Diploma": "College Diploma||Diploma||Associate Degree||Certificate",
      "Master's Degree": "Master's Degree||Master||Masters", "PhD": "PhD||Doctor of Philosophy||Doctorate", "High School": "High School||Secondary School||GED" })[String(v || "")] || String(v || ""),
    lower: v => String(v || "").toLowerCase(),
    avail_iso: v => { const r = availDate(String(v || "")); return r ? `${r.y}-${String(r.m).padStart(2, "0")}-${String(r.d).padStart(2, "0")}` : ""; },
    street_parts: v => { const m = String(v || "").trim().match(/^(?:(\w+)\s*-\s*)?(\d+\w?)\s+(.+)$/); return m ? { unit: m[1] || "", civic: m[2], street: m[3] } : { unit: "", civic: "", street: String(v || "") }; },
    civic: v => XF.street_parts(v).civic, street: v => XF.street_parts(v).street, unit: v => XF.street_parts(v).unit,
    phone_area: v => String(v || "").replace(/\D/g, "").slice(-10, -7),
    phone_local: v => { const d = String(v || "").replace(/\D/g, "").slice(-7); return d.length === 7 ? `${d.slice(0, 3)}-${d.slice(3)}` : d; },
    phone_digits: v => String(v || "").replace(/\D/g, "").slice(-10),
    phone_dash: v => { const d = String(v || "").replace(/\D/g, "").slice(-10); return d.length === 10 ? `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}` : String(v || ""); },
  };
  function resolve(expr, caps) {
    const [path, ...fns] = expr.split("|");
    let cur = P;
    for (const seg of path.match(/[^.\[\]]+|\[[^\]]+\]/g) || []) {
      if (cur == null) break;
      if (seg[0] === "[") {
        const ix = seg.slice(1, -1).replace("$#", String(caps.idx || 0)).replace(/\$(\d)([+-]\d+)?/, (m, d, off) => String(parseInt(caps[d - 1], 10) + (off ? parseInt(off, 10) : 0)));
        cur = cur[parseInt(ix, 10)];
      } else cur = cur[seg];
    }
    for (const f of fns) if (XF[f]) cur = XF[f](cur);
    return cur == null || typeof cur === "object" ? "" : String(cur);
  }
  const expand = (tpl, caps) => tpl.replace(/\{([^}]+)\}/g, (m, e) => resolve(e, caps));
  const globRe = g => new RegExp("^" + g.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, "[^.]+(?:\\.[^.]+)*") + "$", "i");
  let TEMPLATES = (() => { try { return JSON.parse(GM_getValue("templates", "null")); } catch { return null; } })();
  function loadTemplates(done) {            // refreshed every few hours, so new employers' knowledge reaches everyone without a script update
    if (TEMPLATES && Date.now() - GM_getValue("templates_at", 0) < 6 * 3600e3) return done && done();
    GM_xmlhttpRequest({ method: "GET", url: "https://" + HOME + "/autofill-templates.json",
      onload: r => { try { TEMPLATES = JSON.parse(r.responseText); GM_setValue("templates", r.responseText); GM_setValue("templates_at", Date.now()); } catch (e) {} done && done(); },
      onerror: () => done && done() });
  }
  function siteRules() {
    return ((TEMPLATES && TEMPLATES.sites) || []).filter(s => (s.hosts || []).some(h => globRe(h).test(window.__qqHost || location.hostname))).flatMap(s => s.rules || []);
  }
  function templateFor(el, lab) {
    for (const rule of siteRules()) {
      let caps = [];
      for (const [field, text] of [["name", el.name], ["id", el.id], ["aid", el.getAttribute("data-automation-id")], ["label", lab]]) {
        if (!rule[field]) continue;
        const m = (text || "") && new RegExp(rule[field], "i").exec(text);
        if (!m) { caps = null; break; }
        caps = caps.concat(m.slice(1));
      }
      if (caps && (rule.name || rule.id || rule.aid || rule.label)) {
        if (JSON.stringify(rule).includes("$#")) {                 // which one of several matching fields is this, in page order?
          const same = [...document.querySelectorAll("input, select, textarea")].filter(x => visible(x) && ["name", "id"].every(f => !rule[f] || new RegExp(rule[f], "i").test(x[f] || "")));
          caps.idx = Math.max(0, same.indexOf(el));
        }
        return { rule, caps };
      }
    }
    return null;
  }
  function holds(cond) {                    // "work_auth=yes&sponsorship!=yes"
    return cond.split("&").every(c => { const m = c.match(/^([\w.]+)(!?=)(.*)$/); return m ? ((P[m[1]] || "") === m[3]) === (m[2] === "=") : false; });
  }
  const optionText = el => norm(el.closest("label")?.textContent || (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent) || el.value);
  function applyTemplate(el, t) {           // -> 1 if it changed something, 0 otherwise. The caller stops either way.
    const r = t.rule, type = (el.type || "").toLowerCase();
    if (r.skip || r.dropdown || r.typeahead) return 0;
    if (r.when && !resolve(r.when, t.caps)) return 0;
    if (r.tick) { if (resolve(r.tick, t.caps).toLowerCase() === "yes" && !el.checked) { el.click(); return 1; } return 0; }
    const peers = () => el.form ? [...el.form.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)] : [];
    if (r.radio) {
      const ans = P[r.radio]; if (!ans || peers().some(x => x.checked)) return 0;
      const txt = optionText(el), tag = ((el.id || "").match(/_(yes|no)$/i) || [])[1];
      const mine = (tag || txt).toLowerCase();
      if ((ans === "yes" && /^(yes|oui)$/.test(mine)) || (ans === "no" && /^(no|non)$/.test(mine))) { el.click(); return 1; }
      return 0;
    }
    if (r.pick) {
      if (peers().some(x => x.checked)) return 0;
      const hit = r.pick.find(p => holds(p.if));
      if (hit && new RegExp(hit.text, "i").test(optionText(el))) { el.click(); return 1; }
      return 0;
    }
    if (r.checks) {
      const list = String(P[r.checks] || "").toLowerCase().split(/[,;]/).map(s => s.trim()).filter(Boolean);
      const mine = optionText(el);
      if (list.includes(mine) && !el.checked) { el.click(); return 1; }
      return 0;
    }
    if (r.value !== undefined) {
      const v = expand(r.value, t.caps);
      if (!v || (el.value && el.tagName !== "SELECT")) return 0;
      if (el.tagName === "SELECT" ? setSelect(el, v) : setValue(el, v)) { el.style.outline = "2px solid #3a7"; return 1; }
    }
    return 0;
  }

  function setValue(el, v) {
    if (v == null || v === "" ) return false;
    v = String(v).split("||")[0];
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, String(v));      // works with React/Angular-controlled inputs
    ["input", "change", "blur"].forEach(t => el.dispatchEvent(new Event(t, { bubbles: true })));
    return true;
  }
  function setSelect(el, v) {
    if (!v) return false;
    if (String(v).includes("||")) return String(v).split("||").some(x => setSelect(el, x));
    const want = norm(v);
    const opt = [...el.options].find(o => norm(o.text) === want || norm(o.value) === want) ||
                [...el.options].find(o => norm(o.text).includes(want) || (want.length > 3 && want.includes(norm(o.text)) && norm(o.text).length > 3));
    if (!opt) return false;
    el.value = opt.value; el.dispatchEvent(new Event("change", { bubbles: true })); return true;
  }
  function attach(input, f) {
    if (!f || input.files.length) return false;
    const bin = atob(f.b64), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const dt = new DataTransfer(); dt.items.add(new File([bytes], f.name, { type: f.type }));
    input.files = dt.files; input.dispatchEvent(new Event("input", { bubbles: true })); input.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function fillAll() {
    if (!P) return { n: 0, msg: "No profile yet. Open the Quiet Quitter site (signed in) once so the script can copy it." };
    let n = 0, used = null; const skipped = [];
    const tasks = [], all = [...document.querySelectorAll("input, select, textarea, " + WIDGET_SEL)];
    const isCountry = el => el.tagName === "SELECT" && /country|pays/.test(labelOf(el));
    all.sort((a, b) => isCountry(b) - isCountry(a));                       // country first: province lists depend on it
    all.forEach(el => {
      if (el.matches(WIDGET_SEL)) {                                              // custom dropdown buttons: only a template can say what to pick
        if (!visible(el)) return;
        const t = templateFor(el, labelOf(el)); if (t && t.rule.dropdown) tasks.push({ el, tpl: t });
        return;
      }
      const type = (el.type || "").toLowerCase();
      if (el.disabled || el.readOnly || (!visible(el) && type !== "file")) return;     // upload boxes are often hidden behind a button
      if (el.tagName === "SELECT" && el.value && el.selectedIndex > 0) return;   // already chosen (by you or the site)
      if (["hidden", "submit", "button", "password", "image", "reset", "search"].includes(type)) return;
      const lab = labelOf(el);
      if (SENSITIVE.test(lab) || /^cc-|password|one-time/.test(el.autocomplete || "")) return;      // never touch these
      if (/signature|agree|accept|consent|terms of use|i understand that/.test(lab) && (type === "checkbox" || type === "radio")) return;     // legal declarations are yours to tick
      const remembered = (MEM[location.hostname] || {})[memKey(el, lab)];
      if (remembered !== undefined && type !== "file") {                       // something you typed on this site before
        if (type === "radio") { if (el.id === remembered && !el.checked) { el.click(); n++; } return; }
        if (type !== "checkbox" && !(el.value && el.tagName !== "SELECT") && (el.tagName === "SELECT" ? setSelect(el, remembered) : setValue(el, remembered))) { n++; el.style.outline = "2px solid #3a7"; }
        return;
      }
      if (type === "file") {
        const which = /cover/.test(lab) ? "cover" : /resume|résumé|cv|curriculum/.test(lab) ? "resume" : null;
        const pack = currentPack(), f = (pack && pack.files[which]) || FILES[which];
        if (which && attach(el, f)) { n++; if (pack && pack.files[which]) used = pack; }
        return;
      }
      const tpl = templateFor(el, lab);                                          // shared knowledge about this employer's form
      if (tpl) {
        if (tpl.rule.typeahead || tpl.rule.dropdown) { if (!el.value) tasks.push({ el, tpl }); return; }       // search boxes and custom lists need waiting: done afterwards
        n += applyTemplate(el, tpl); return;
      }
      if (type === "checkbox") return;
      if (type === "radio") {                                                    // yes/no questions worded in the usual ways
        const yn = YESNO.find(([re]) => re.test(lab + " " + norm(el.closest("fieldset, .form-group, [role=group], li")?.textContent.slice(0, 300))));
        const answer = yn && yn[1](P), tag = ((el.id || "").match(/_(yes|no)$/i) || [])[1];
        if (answer && !(el.form && [...el.form.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)].some(x => x.checked))) {
          const mine = (tag || optionText(el)).toLowerCase();
          if ((answer === "yes" && /^(yes|oui)$/.test(mine)) || (answer === "no" && /^(no|non)$/.test(mine))) { el.click(); n++; }
        }
        return;
      }
      if (el.value && el.tagName !== "SELECT") return;                          // never overwrite what's already there
      const rule = RULES.find(([re]) => re.test(lab));
      if (!rule) { skipped.push(lab.slice(0, 50)); return; }
      const v = rule[1](P);
      if (el.tagName === "SELECT" ? setSelect(el, v) : setValue(el, v)) { n++; el.style.outline = "2px solid #3a7"; }
    });
    return { n, skipped, used, tasks, gaps: findGaps() };
  }


  // ---------- Open-ended questions: a "Draft answer" button appears only beside a long-answer box that is actually on the page ----------
  const LONG_Q = /\?|\b(why|describe|explain|tell us|tell me|how (would|do|did|have)|give (an )?example|example of|what (makes|interests|motivates|attracts)|in your own words|additional information|anything else|statement|interest in|experience (with|in))\b|\b(list|outline|summari[sz]e|provide)\b.{0,60}\b(certification|licen[cs]e|designation|experience|training|skills)/;
  const COVER_Q = /cover letter|covering letter|letter of interest|letter of intent|letter of application/;

  function questionText(el) {                       // the visible question, not the field's id or name
    const bits = [];
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) bits.push(l.textContent); }
    const wrap = el.closest("label"); if (wrap) bits.push(wrap.textContent);
    const by = el.getAttribute("aria-labelledby");
    if (by) by.split(/\s+/).forEach(i => { const n = document.getElementById(i); if (n) bits.push(n.textContent); });
    ["aria-label", "placeholder", "title"].forEach(a => el.getAttribute(a) && bits.push(el.getAttribute(a)));
    if (!bits.join("").trim()) { const row = el.closest(".form-group, .field, .row, li, tr, [class*=field], [class*=question]"); if (row) bits.push(row.textContent.slice(0, 400)); }
    return bits.join(" ").replace(/\s+/g, " ").replace(/\*/g, "").trim().slice(0, 600);
  }
  function note(el, text, bad) {
    let s = el.parentNode.querySelector(".qq-note");
    if (!s) { s = document.createElement("div"); s.className = "qq-note"; s.style.cssText = "font:12px system-ui;margin:2px 0"; el.insertAdjacentElement("afterend", s); }
    s.textContent = text; s.style.color = bad ? "#b00020" : "#555";
  }
  function ask(el, question, btn) {
    const token = GM_getValue("token", "");
    if (!token) return note(el, "Open the Quiet Quitter site once while signed in so this script gets its key.", true);
    const pack = currentPack(), ml = parseInt(el.getAttribute("maxlength") || "0", 10);
    btn.disabled = true; note(el, "Drafting… (about 15 seconds)");
    GM_xmlhttpRequest({ method: "POST", url: "https://" + HOME + "/api/answer", headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
      data: JSON.stringify({ question, url: pack ? pack.url : "", max_words: ml ? Math.max(30, Math.min(400, Math.floor(ml / 6.5))) : 150 }),
      onload: r => {
        btn.disabled = false;
        let j = {}; try { j = JSON.parse(r.responseText); } catch (e) {}
        if (r.status === 429) return note(el, "Slow down a little, then try again.", true);
        if (j.answer) {
          setValue(el, ml ? j.answer.slice(0, ml) : j.answer); el.style.outline = "2px solid #e0a000";
          const warn = [j.removed ? "removed " + j.removed + " sentence(s) your resume doesn't support" : "", (j.check_terms || []).length ? "mentions " + j.check_terms.join(", ") + " (not in your resume)" : "", (j.check_numbers || []).length ? "check figures: " + j.check_numbers.join(", ") : ""].filter(Boolean).join("; ");
          note(el, "Draft" + (j.job ? " for " + j.job : "") + ". Read and edit it before you submit." + (warn ? " Careful: " + warn + "." : ""), !!warn);
        } else note(el, (j.message || "Couldn't draft this one.") + ((j.starters || []).length ? " Lines to build on: " + j.starters.map(x => "“" + x.slice(0, 110) + "”").join("  ") : ""), true);
      },
      onerror: () => { btn.disabled = false; note(el, "Couldn't reach the Quiet Quitter site.", true); } });
  }
  function offerDrafts() {
    if (!P) return;
    document.querySelectorAll("textarea").forEach(el => {
      if (el.dataset.qq || el.disabled || el.readOnly || !visible(el) || el.value.trim()) return;
      const q = questionText(el);
      if (SENSITIVE.test(q.toLowerCase()) || q.length < 12) return;
      const cover = COVER_Q.test(q.toLowerCase()), pack = currentPack();
      if (!cover && !LONG_Q.test(q.toLowerCase())) return;
      if (cover && !(pack && pack.cover_text)) return;
      el.dataset.qq = "1";
      const b = document.createElement("button");
      b.type = "button"; b.textContent = cover ? "Insert my cover letter" : "Draft answer";
      b.style.cssText = "margin:4px 0;padding:4px 10px;border:0;border-radius:99px;background:#7a4cc2;color:#fff;font:600 12px system-ui;cursor:pointer";
      b.onclick = () => cover ? (setValue(el, pack.cover_text), el.style.outline = "2px solid #e0a000", note(el, "Your cover letter for " + pack.title + ". Check it before you submit.")) : ask(el, q, b);
      el.insertAdjacentElement("afterend", b);
    });
  }


  // ---------- Fallbacks: what it couldn't fill, and what to do about it ----------
  const isEmpty = el => el.tagName === "SELECT" ? !(el.value && el.selectedIndex > 0) : !el.value.trim();
  function isRequired(el) {
    if (el.required || el.getAttribute("aria-required") === "true" || el.closest("[class*=required i]")) return true;
    const cell = el.closest("td, th, .form-group, .field"); return !!cell && /\*/.test(cell.textContent.slice(0, 120));
  }
  function readable(el) {
    const q = questionText(el); if (q && !/^[\w.-]+$/.test(q)) return q.slice(0, 90);
    return humanize(el.name || el.id || el.type || "field").slice(0, 90);
  }
  function findGaps() {
    const gaps = [], seen = new Set();
    document.querySelectorAll("input, select, textarea").forEach(el => {
      const t = (el.type || "").toLowerCase();
      if (el.disabled || el.readOnly || !visible(el) || ["hidden", "submit", "button", "image", "reset", "search", "password", "file", "checkbox"].includes(t)) return;
      if (SENSITIVE.test(labelOf(el))) return;
      if (t === "radio") {
        if (seen.has(el.name)) return; seen.add(el.name);
        if (el.form && [...el.form.querySelectorAll(`input[type=radio][name="${CSS.escape(el.name)}"]`)].some(x => x.checked)) return;
      } else if (!isEmpty(el)) return;
      gaps.push({ el, label: readable(el), required: isRequired(el), name: el.name || "" });
    });
    return gaps.sort((a, b) => b.required - a.required);
  }
  function showGaps(r) {
    document.getElementById("qq-gaps")?.remove();
    const gaps = r.gaps || [], req = gaps.filter(g => g.required), box = document.createElement("div");
    box.id = "qq-gaps";
    box.style.cssText = "position:fixed;left:16px;bottom:16px;z-index:2147483646;width:330px;max-height:60vh;overflow:auto;background:#fff;color:#222;border:1px solid #bbb;border-radius:10px;padding:10px 12px;font:13px system-ui;box-shadow:0 2px 12px #0004";
    const list = (req.length ? req : gaps).slice(0, 12);
    box.innerHTML = `<div style="display:flex;justify-content:space-between"><b>Filled ${r.n}. ${req.length ? req.length + " required field" + (req.length > 1 ? "s" : "") + " need you" : gaps.length ? gaps.length + " empty field" + (gaps.length > 1 ? "s" : "") : "Nothing left empty"}</b><a href="#" data-x style="color:#666;text-decoration:none">✕</a></div>` +
      (list.length ? `<ul style="margin:6px 0 6px 16px;padding:0">${list.map((g, i) => `<li><a href="#" data-i="${i}" style="color:#1a56b0">${g.label.replace(/</g, "&lt;")}</a></li>`).join("")}</ul>` : "") +
      (gaps.length > list.length ? `<div style="color:#666">…and ${gaps.length - list.length} more.</div>` : "") +
      (gaps.length ? `<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px"><button data-ai style="${BTN}">Ask AI about these</button><button data-hi style="${BTN}">Highlight all empty</button></div>` : "") +
      `<div style="margin-top:6px"><button data-mem style="${BTN}" title="After you fill them yourself, click this and the script will reuse your answers on this site">Remember my answers on this site</button></div><div data-msg style="margin-top:6px;color:#555"></div>`;
    document.body.appendChild(box);
    const msg = t => box.querySelector("[data-msg]").textContent = t;
    box.onclick = e => {
      const a = e.target.closest("a"), b = e.target.closest("button");
      if (a && a.dataset.x !== undefined) { e.preventDefault(); box.remove(); }
      else if (a) { e.preventDefault(); const g = list[+a.dataset.i]; g.el.scrollIntoView({ block: "center", behavior: "smooth" }); g.el.style.outline = "3px solid #e0a000"; g.el.focus({ preventScroll: true }); }
      else if (b && b.hasAttribute("data-hi")) gaps.forEach(g => g.el.style.outline = "2px dashed #e0a000");
      else if (b && b.hasAttribute("data-ai")) askAI(gaps, msg, b);
      else if (b && b.hasAttribute("data-mem")) {
        const site = MEM[location.hostname] = MEM[location.hostname] || {}; let k = 0;
        gaps.forEach(g => {
          const el = g.el, t = (el.type || "").toLowerCase();
          if (t === "radio") { const c = el.form && el.form.querySelector(`input[type=radio][name="${CSS.escape(el.name)}"]:checked`); if (c && c.id) { site[el.name] = c.id; k++; } }
          else if (!isEmpty(el) && el.tagName !== "TEXTAREA") { site[memKey(el, labelOf(el))] = el.tagName === "SELECT" ? el.options[el.selectedIndex].text : el.value; k++; }
        });
        GM_setValue("memory", JSON.stringify(MEM)); msg(k ? `Remembered ${k} answer${k > 1 ? "s" : ""} for ${location.hostname}.` : "Fill some of them in first, then click this.");
      }
    };
  }
  const BTN = "padding:4px 9px;border:1px solid #888;border-radius:6px;background:#f4f4f4;font:12px system-ui;cursor:pointer";
  function askAI(gaps, msg, btn) {
    const token = GM_getValue("token", "");
    if (!token) return msg("Open the Quiet Quitter site once while signed in so this script gets its key.");
    const pick = gaps.filter(g => g.el.tagName !== "TEXTAREA" && (g.el.type || "") !== "radio").slice(0, 15);
    if (!pick.length) return msg("Nothing here the AI can help with. Long answers have their own Draft answer button.");
    const fields = pick.map((g, i) => ({ id: "f" + i, label: g.label, type: g.el.tagName === "SELECT" ? "select" : (g.el.type || "text"),
      options: g.el.tagName === "SELECT" ? [...g.el.options].map(o => o.text).filter(Boolean).slice(0, 40) : [] }));
    btn.disabled = true; msg("Asking… (about 10 seconds)");
    GM_xmlhttpRequest({ method: "POST", url: "https://" + HOME + "/api/fields", headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
      data: JSON.stringify({ fields }),
      onload: r => {
        btn.disabled = false; let j = {}; try { j = JSON.parse(r.responseText); } catch (e) {}
        if (r.status === 429) return msg("Slow down a little, then try again.");
        const a = j.answers || {}; let k = 0;
        pick.forEach((g, i) => { const v = a["f" + i]; if (v && (g.el.tagName === "SELECT" ? setSelect(g.el, v) : setValue(g.el, v))) { g.el.style.outline = "2px solid #e0a000"; k++; } });
        msg(k ? `The AI filled ${k} from your profile and resume (amber outline). Check them.` : "Your profile and resume don't answer these. Please fill them in yourself.");
      },
      onerror: () => { btn.disabled = false; msg("Couldn't reach the Quiet Quitter site."); } });
  }

  // ---------- Dump the form's fields so a site-specific rule can be written ----------
  function dumpText() {
    // One line per field, with repeating rows (icims_0_..., icims_1_...) folded into one line so the list stays short enough to paste.
    const seen = new Map(), rows = [];
    document.querySelectorAll("input, select, textarea, button, [role=combobox], [aria-haspopup=listbox], a[href*=add i]").forEach(el => {
      if (!visible(el) && (el.type || "") !== "file") return;
      const t = el.type || "", key = [el.tagName, t, (el.name || el.id || el.getAttribute("data-automation-id") || "").replace(/\d+/g, "#")].join("|");
      if (seen.has(key)) { seen.get(key).count++; return; }
      const bits = [`${el.tagName.toLowerCase()}${t ? "[" + t + "]" : ""}`];
      if (el.name) bits.push("name=" + el.name);
      if (el.id) bits.push("id=" + el.id);
      const aid = el.getAttribute("data-automation-id"); if (aid) bits.push("aid=" + aid);
      const ac = el.getAttribute("autocomplete"); if (ac && ac !== "off") bits.push("ac=" + ac);
      const role = el.getAttribute("role") || (el.getAttribute("aria-haspopup") ? "popup" : ""); if (role) bits.push("role=" + role);
      if (isRequired(el)) bits.push("REQUIRED");
      bits.push(`label="${labelOf(el).slice(0, 70)}"`);
      if (el.tagName === "SELECT") bits.push("options=" + [...el.options].slice(0, 6).map(o => o.text.trim()).join("/") + (el.options.length > 6 ? `/…(${el.options.length})` : ""));
      const row = { text: bits.join(" "), count: 1 }; seen.set(key, row); rows.push(row);
    });
    const body = rows.map(r => r.text + (r.count > 1 ? `   [x${r.count} similar]` : "")).join("\n");
    const inFrame = window.top !== window ? "  (inside a frame)" : "";
    const txt = `URL: ${location.href}${inFrame}\n` + body;
    return { txt, count: rows.length, raw: rows.reduce((s, r) => s + r.count, 0) };
  }
  function dumpFields() {
    const d = dumpText();
    try { GM_setClipboard(d.txt); } catch {}
    console.log(d.txt); alert(`Copied ${d.count} field types (${d.txt.length} characters) to your clipboard. Paste them to Claude.`);
  }

  // ---------- Recording: walk through an application as yourself and every step's field list is kept; copy them all at the end ----------
  // Only field names and labels are recorded, never what you type.
  const recOn = () => GM_getValue("recording", false) === true || GM_getValue("recording", "") === "true";
  const recList = () => { try { return JSON.parse(GM_getValue("rec", "[]")); } catch { return []; } };
  let recTimer = null;
  function recordSnapshot() {
    if (!recOn()) return;
    const d = dumpText();
    if (d.raw < 4) return;                                                // not a form page (the script's own button counts as one)
    const body = d.txt.split("\n").slice(1).join("\n"), list = recList();
    if (list.some(r => r.body === body && r.host === location.hostname)) return;     // already have this exact step
    list.push({ host: location.hostname, url: d.txt.split("\n")[0], body });
    GM_setValue("rec", JSON.stringify(list.slice(-30)));
  }
  function scheduleRecord() { if (recOn()) { clearTimeout(recTimer); recTimer = setTimeout(recordSnapshot, 1500); } }
  GM_registerMenuCommand("Start recording field lists", () => { GM_setValue("rec", "[]"); GM_setValue("recording", true); recordSnapshot(); alert("Recording. Walk through the application as usual (don't submit anything you don't mean to). Each step's field list is kept. When you're done, use 'Stop recording and copy all'."); });
  GM_registerMenuCommand("Stop recording and copy all", () => {
    GM_setValue("recording", false);
    const list = recList(), txt = list.map((r, i) => `### Step ${i + 1}  ${r.url}\n${r.body}`).join("\n\n");
    try { GM_setClipboard(txt); } catch {}
    alert(list.length ? `Copied ${list.length} step${list.length > 1 ? "s" : ""} (${txt.length} characters). Paste them to Claude.` : "Nothing was recorded.");
  });


  GM_registerMenuCommand("Fill this page", () => runFill());
  GM_registerMenuCommand("List this page's fields (copy)", dumpFields);
  GM_registerMenuCommand("Choose tailored resume…", () => {
    if (!PACKS.length) return alert("No tailored resumes yet. Make one with the Tailor Resume button on a posting, then open the Quiet Quitter site once.");
    const cur = currentPack(), pick = prompt("Attach which tailored resume? Type a number (0 = automatic):\n" +
      PACKS.map((p, i) => `${i + 1}. ${p.title} (${p.employer || ""})${cur && cur.id === p.id ? "  <- current" : ""}`).join("\n"));
    if (pick === null) return;
    const i = parseInt(pick, 10);
    GM_setValue("activePack", i >= 1 && i <= PACKS.length ? PACKS[i - 1].id : "");
  });


  // ---------- Things that need time: adding rows, search boxes, custom dropdown lists ----------
  const WIDGET_SEL = 'button[aria-haspopup], [role=combobox]:not(input), button[id*="selectButton" i]';
  const OPT_SEL = '[role=option], [role=listbox] li, [data-automation-id=promptOption], [data-automation-id=menuItem]';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  async function waitOptions(ms = 2500) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) { const o = [...document.querySelectorAll(OPT_SEL)].filter(visible); if (o.length) return o; await sleep(120); }
    return [];
  }
  function bestOption(opts, alts) {
    for (const a of alts) { const hit = opts.find(o => norm(o.textContent) === a); if (hit) return hit; }
    for (const a of alts) { const hit = opts.find(o => { const t = norm(o.textContent); return t && (t.includes(a) || (a.length > 4 && a.includes(t) && t.length > 3)); }); if (hit) return hit; }
    return null;
  }
  async function runTask(t) {
    const rule = t.tpl.rule, el = t.el, want = expand(rule.dropdown || rule.typeahead, t.tpl.caps);
    if (!want) return 0;
    const alts = want.split("||").map(norm).filter(Boolean);
    if (rule.dropdown && alts.some(a => norm(el.textContent).includes(a))) return 0;            // it already shows this
    if (rule.typeahead) setValue(el, want.split("||")[0]); else el.click();
    const hit = bestOption(await waitOptions(), alts);
    if (!hit) { if (rule.dropdown) el.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); return 0; }
    hit.click(); await sleep(350);
    el.style.outline = "2px solid #3a7";
    return 1;
  }
  async function runTasks(tasks) { let n = 0; for (const t of tasks || []) { try { n += await runTask(t); } catch (e) { /* leave it to you */ } } return n; }
  async function addRows() {                // click "Add" until the page has a row for each job / school / certificate in your profile
    let clicked = 0;
    const rows = ((TEMPLATES && TEMPLATES.sites) || []).filter(s => (s.hosts || []).some(h => globRe(h).test(window.__qqHost || location.hostname))).flatMap(s => s.rows || []);
    for (const r of rows) {
      if (r.page_has && !document.body.innerText.includes(r.page_has)) continue;
      const needed = Math.min(((P || {})[r.count] || []).length, 8); if (!needed) continue;
      const count = () => [...document.querySelectorAll("input, select, textarea")].filter(x => visible(x) && ["name", "id"].every(f => !r.has[f] || new RegExp(r.has[f], "i").test(x[f] || ""))).length;
      for (let guard = 0; count() < needed && guard < needed; guard++) {
        const btns = [...document.querySelectorAll("button, a, [role=button]")].filter(b => visible(b) && (r.add.aid ? b.getAttribute("data-automation-id") === r.add.aid : new RegExp(r.add.text, "i").test(b.innerText || "")));
        const btn = btns[r.add.index || 0]; if (!btn) break;
        const before = count(); btn.click(); clicked++; await sleep(900);
        if (count() === before) { await sleep(900); if (count() === before) break; }          // nothing appeared: stop rather than keep clicking
      }
    }
    return clicked;
  }

  function runFill() {                      // the shared templates must be in before the first fill
    const go = async () => {
      await addRows();
      const r = fillAll();
      r.n += await runTasks(r.tasks);
      r.gaps = findGaps();
      toast(report(r)); if (!r.msg) showGaps(r);
    };
    TEMPLATES ? go() : loadTemplates(go);
  }

  // ---------- Small floating button, shown only where there's a form ----------
  function report(r) {
    const age = Math.round((Date.now() - GM_getValue("synced", 0)) / 86400000);
    return r.msg || `Filled ${r.n} field${r.n === 1 ? "" : "s"}${r.used ? ` and attached the files for "${r.used.title}"` : ""}. Check everything, then submit it yourself.` +
      (age >= 3 ? ` (Your profile was last synced ${age} days ago. Open the Quiet Quitter site to refresh it.)` : "");
  }
  function toast(t) {
    const d = document.createElement("div");
    d.textContent = t; d.style.cssText = "position:fixed;right:16px;bottom:64px;z-index:2147483647;background:#222;color:#fff;padding:10px 14px;border-radius:8px;font:14px system-ui;max-width:300px";
    document.body.appendChild(d); setTimeout(() => d.remove(), 6000);
  }
  function button() {
    if (document.getElementById("qq-fill") || !P) return;
    const fields = [...document.querySelectorAll("input:not([type=hidden]), select, textarea")].filter(visible);
    if (fields.length < 3 && !document.querySelector("input[type=file]")) return;
    const b = document.createElement("button");
    b.id = "qq-fill"; b.textContent = "Autofill";
    b.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;padding:10px 16px;border:0;border-radius:99px;background:#2b6cb0;color:#fff;font:600 14px system-ui;cursor:pointer;box-shadow:0 2px 8px #0005";
    b.onclick = () => runFill();
    document.body.appendChild(b);
  }
  // ---------- Quiet background reporting: an application form on a site we don't have a template for yet ----------
  // Sends only field names/labels/types (the same shape as "List this page's fields"), never what anyone typed.
  // Debounced per host so a normal day of job-hunting sends at most a handful of these, not one per page load.
  function hash(s) { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return h; }
  let reportTimer = null;
  function autoReportFields() {
    const token = GM_getValue("token", "");
    if (!token || location.hostname === HOME) return;
    if (!TEMPLATES) return;                  // wait for the shared templates to load before deciding this host is "unknown"
    const known = (TEMPLATES.sites || []).some(s => (s.hosts || []).some(h => globRe(h).test(location.hostname)));
    if (known) return;
    const d = dumpText();
    if (d.raw < 4) return;                    // not really a form page
    const body = d.txt.split("\n").slice(1).join("\n"), h = hash(body);
    const key = "reported:" + location.hostname, prior = (() => { try { return JSON.parse(GM_getValue(key, "null")); } catch { return null; } })();
    if (prior && prior.h === h && Date.now() - prior.at < 14 * 86400e3) return;   // same form, reported recently
    GM_xmlhttpRequest({ method: "POST", url: "https://" + HOME + "/api/autofill/report-fields", headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
      data: JSON.stringify({ host: location.hostname, url: location.href, dump: d.txt }),
      onload: () => GM_setValue(key, JSON.stringify({ h, at: Date.now() })),
      onerror: () => {} });
  }
  function scheduleAutoReport() { clearTimeout(reportTimer); reportTimer = setTimeout(autoReportFields, 2000); }

  loadTemplates();
  button(); offerDrafts(); scheduleRecord(); scheduleAutoReport();
  new MutationObserver(() => { button(); offerDrafts(); scheduleRecord(); scheduleAutoReport(); }).observe(document.body, { childList: true, subtree: true });
})();
