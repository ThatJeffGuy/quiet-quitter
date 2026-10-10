// SPDX-FileCopyrightText: 2026 That Scottish Guy
// SPDX-License-Identifier: AGPL-3.0-only
/* "I'm at work now": a boss key. Esc twice (or the briefcase button) covers the whole page with a believable
 * spreadsheet or a Windows XP desktop. Nothing here touches your data; it is all pretend. Press the same keys to come back. */
(function () {
  "use strict";
  var W = window, D = document;
  var S = { on: false, skin: "excel", saved: null, sheet: null, timers: [], z: 10 };

  // ------------------------------------------------------------------ helpers
  function h(tag, attrs, kids) {
    var e = D.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "class") e.className = attrs[k]; else if (k === "text") e.textContent = attrs[k]; else if (k === "html") e.innerHTML = attrs[k];
      else if (k.slice(0, 2) === "on") e.addEventListener(k.slice(2), attrs[k]); else e.setAttribute(k, attrs[k]);
    });
    [].concat(kids || []).forEach(function (c) { if (c != null) e.appendChild(typeof c === "string" ? D.createTextNode(c) : c); });
    return e;
  }
  function later(fn, ms) { var t = setTimeout(fn, ms); S.timers.push(t); return t; }
  function every(fn, ms) { var t = setInterval(fn, ms); S.timers.push(t); return t; }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function typing(t) { return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable); }
  var ICON = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="4" fill="#217346"/><path d="M8 8l16 16M24 8L8 24" stroke="#fff" stroke-width="4"/></svg>');
  var ICON_XP = "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#245edb"/><path d="M4 6h11v10H4zM17 4h11v12H17zM4 18h11v10H4zM17 18h11v12H17z" fill="#fff"/></svg>');

  // ------------------------------------------------------------------ styles
  var CSS = [
    "#qqwork{position:fixed;inset:0;z-index:2147483000;background:#fff;color:#000;font:13px 'Segoe UI',Tahoma,Arial,sans-serif;-webkit-user-select:none;user-select:none;cursor:default;overflow:hidden}",
    "#qqwork *{box-sizing:border-box}",
    ":where(#qqwork) :is(button,input,textarea,select){color:#000;font:inherit;background:#fff;padding:0;margin:0;border:0;border-radius:0;box-shadow:none}",
    "#qqwork{color-scheme:light}",
    "#qqwork input,#qqwork textarea{font:inherit;color:inherit;-webkit-user-select:text;user-select:text}",
    /* excel */
    ".xl{position:absolute;inset:0;display:flex;flex-direction:column;background:#fff}",
    ".xl-title{background:#217346;color:#fff;height:30px;display:flex;align-items:center;padding:0 0 0 10px;gap:10px;flex:none}",
    ".xl-title .xl-name{flex:1;text-align:center;font-size:12px}",
    "@keyframes xlflash{0%,100%{box-shadow:inset 0 0 0 0 rgba(255,235,59,0);background:#217346}50%{box-shadow:inset 0 0 0 4px #ffeb3b;background:#2e9a5d}}",
    "@keyframes xlpulse{0%,100%{background:#fffbe0;transform:translateY(0)}50%{background:#ffeb3b;transform:translateY(3px)}}",
    ".xl-title.flash{animation:xlflash .55s ease-in-out infinite}",
    ".xl-hint{position:absolute;top:34px;left:50%;margin-left:-190px;width:380px;z-index:40;background:#fffbe0;border:2px solid #d4a800;color:#222;padding:9px 14px;font-size:13px;line-height:1.35;text-align:center;box-shadow:2px 3px 8px rgba(0,0,0,.35);animation:xlpulse .55s ease-in-out infinite;pointer-events:none}",
    ".xl-hint:before{content:'';position:absolute;top:-9px;left:50%;margin-left:-8px;border-left:8px solid transparent;border-right:8px solid transparent;border-bottom:9px solid #d4a800}",
    "@media (prefers-reduced-motion:reduce){.xl-title.flash,.xl-hint{animation:none}.xl-title.flash{box-shadow:inset 0 0 0 4px #ffeb3b}}",
    ".xl-btn{width:46px;height:30px;border:0;background:transparent;color:#fff;font-size:14px;cursor:pointer}.xl-btn:hover{background:rgba(255,255,255,.18)}.xl-btn.x:hover{background:#e81123}",
    ".xl-tabs{background:#217346;display:flex;gap:2px;padding:0 6px;flex:none}",
    ".xl-tab{color:#fff;padding:6px 12px;font-size:12px;cursor:pointer;border-radius:3px 3px 0 0}.xl-tab.on{background:#f3f3f3;color:#217346}.xl-tab:not(.on):hover{background:rgba(255,255,255,.18)}",
    ".xl-ribbon{background:#f3f3f3;border-bottom:1px solid #d4d4d4;height:84px;display:flex;gap:14px;padding:6px 10px;flex:none;overflow:hidden}",
    ".xl-group{display:flex;flex-direction:column;align-items:center;border-right:1px solid #dadada;padding-right:14px;min-width:70px}",
    ".xl-group .row{display:flex;gap:4px;flex:1;align-items:center}.xl-group .lab{font-size:11px;color:#555}",
    ".xl-rb{border:1px solid transparent;background:transparent;border-radius:3px;padding:4px 8px;cursor:pointer;font-size:12px;min-width:34px;text-align:center}.xl-rb:hover{background:#e1e1e1;border-color:#c6c6c6}",
    ".xl-fbar{display:flex;align-items:center;gap:6px;padding:3px 6px;border-bottom:1px solid #d4d4d4;background:#fff;flex:none}",
    ".xl-namebox{width:70px;border:1px solid #c6c6c6;padding:2px 6px;background:#fff}.xl-fx{color:#217346;font-style:italic;font-weight:600;padding:0 6px}",
    ".xl-fin{flex:1;border:1px solid #c6c6c6;padding:2px 6px;background:#fff}",
    ".xl-gridwrap{flex:1;overflow:auto;position:relative;background:#fff}",
    "table.xl-grid{border-collapse:collapse;table-layout:fixed;font-size:13px;font-family:Calibri,'Segoe UI',Arial,sans-serif}",
    ".xl-grid th{background:#e6e6e6;border:1px solid #bdbdbd;font-weight:400;color:#444;height:21px;position:sticky;top:0;z-index:2}",
    ".xl-grid th.rh{position:sticky;left:0;z-index:1;width:42px;top:auto}.xl-grid th.corner{left:0;z-index:3}",
    ".xl-grid td{border:1px solid #d9d9d9;height:21px;padding:0 4px;white-space:nowrap;overflow:hidden;text-overflow:clip;position:relative}",
    ".xl-grid td.sel{outline:2px solid #217346;outline-offset:-2px;background:#fff}.xl-grid td.num{text-align:right}.xl-grid td.b{font-weight:700}.xl-grid td.hd{background:#d9e1f2;font-weight:700}",
    ".xl-grid td.cm::after{content:'';position:absolute;right:0;top:0;border-top:7px solid #d00;border-left:7px solid transparent}",
    ".xl-grid td.neg{color:#c00}.xl-grid td.ov{overflow:visible}",
    ".xl-cellin{position:absolute;inset:0;width:100%;height:100%;border:2px solid #217346;padding:0 3px;background:#fff;outline:none}",
    ".xl-sheets{display:flex;align-items:center;gap:2px;background:#f3f3f3;border-top:1px solid #d4d4d4;padding:2px 6px;flex:none}",
    ".xl-sh{padding:3px 14px;border:1px solid #c6c6c6;border-top:0;background:#e6e6e6;cursor:pointer;font-size:12px}.xl-sh.on{background:#fff;color:#217346;font-weight:600}",
    ".xl-status{background:#217346;color:#fff;height:22px;display:flex;align-items:center;padding:0 10px;gap:20px;font-size:12px;flex:none}.xl-status .grow{flex:1}",
    ".xl-menu{position:fixed;background:#fff;border:1px solid #bbb;box-shadow:2px 2px 6px rgba(0,0,0,.3);padding:3px 0;z-index:30;min-width:200px}.xl-menu div{padding:5px 22px;cursor:pointer}.xl-menu div:hover{background:#e5f1e9}",
    ".mb{position:fixed;inset:0;background:rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;z-index:50}",
    ".mb-box{background:#fff;border:1px solid #888;box-shadow:0 8px 30px rgba(0,0,0,.4);min-width:320px;max-width:440px}.mb-t{background:#217346;color:#fff;padding:6px 10px}",
    ".mb-b{padding:18px 18px 8px;line-height:1.4}.mb-f{padding:10px 14px 14px;display:flex;gap:8px;justify-content:flex-end}.mb-f button{padding:5px 18px;border:1px solid #888;background:#f0f0f0;cursor:pointer}.mb-f button:hover{background:#e5f1e9}",
    /* xp */
    ".xp{position:absolute;inset:0;overflow:hidden;font-family:Tahoma,'Segoe UI',Arial,sans-serif;font-size:11px;background:#3a6ea5}",
    ".xp-bg{position:absolute;inset:0 0 30px 0}.xp-bg svg{width:100%;height:100%;display:block}",
    ".xp-icons{position:absolute;left:14px;top:14px;display:flex;flex-direction:column;gap:14px;flex-wrap:wrap;height:calc(100% - 70px);align-content:flex-start;column-gap:22px}",
    ".xp-ic{width:74px;text-align:center;color:#fff;text-shadow:1px 1px 2px #000;cursor:pointer}.xp-ic .g{font-size:34px;line-height:40px}.xp-ic .l{padding:1px 3px;word-wrap:break-word}.xp-ic.sel .l{background:#316ac5;text-shadow:none}",
    ".xp-task{position:absolute;left:0;right:0;bottom:0;height:30px;background:linear-gradient(#245edb,#3f8cf3 12%,#245edb 88%,#1941a5);display:flex;align-items:center;z-index:900;border-top:1px solid #0c3b99}",
    ".xp-start{height:30px;padding:0 22px 0 12px;border:0;border-radius:0 12px 12px 0;background:linear-gradient(#3c9a3c,#5ec45e 15%,#2e8b2e 85%,#256d25);color:#fff;font:italic 700 17px Tahoma,Arial,sans-serif;text-shadow:1px 1px 2px #000;cursor:pointer;display:flex;align-items:center;gap:6px}",
    ".xp-start:hover{filter:brightness(1.1)}",
    ".xp-tasks{flex:1;display:flex;gap:3px;padding:0 6px;overflow:hidden}.xp-tb{min-width:120px;max-width:170px;height:24px;border:1px solid #1941a5;border-radius:3px;background:#3f7fe0;color:#fff;text-align:left;padding:0 8px;cursor:pointer;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.xp-tb.on{background:#1e49b8;box-shadow:inset 1px 1px 3px #0a2a80}",
    ".xp-tray{height:30px;background:linear-gradient(#0f9cf0,#12a4f5 10%,#0b84d9);border-left:1px solid #0a5fb0;color:#fff;display:flex;align-items:center;gap:8px;padding:0 12px;font-size:11px}",
    ".xp-win{position:absolute;background:#ece9d8;border:3px solid #0a3fd6;border-radius:8px 8px 0 0;box-shadow:3px 3px 14px rgba(0,0,0,.5);display:flex;flex-direction:column;min-width:220px}",
    ".xp-wt{height:26px;background:linear-gradient(#0a5cf5,#3d95ff 10%,#0a5cf5 88%,#0842c8);color:#fff;font-weight:700;display:flex;align-items:center;gap:6px;padding:0 3px 0 6px;border-radius:5px 5px 0 0;cursor:move;text-shadow:1px 1px 1px #000}.xp-wt .t{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}",
    ".xp-wb{width:21px;height:21px;border:1px solid #fff;border-radius:3px;background:linear-gradient(#5b95ff,#2a60dc);color:#fff;font-size:11px;line-height:17px;cursor:pointer;padding:0}.xp-wb.x{background:linear-gradient(#e8845f,#c5381b)}.xp-wb:hover{filter:brightness(1.15)}",
    ".xp-wc{flex:1;overflow:auto;background:#fff;min-height:0;position:relative;display:flex;flex-direction:column}",
    ".xp-menu{position:absolute;left:0;bottom:30px;width:380px;background:#fff;border:2px solid #0a3fd6;border-radius:8px 8px 0 0;overflow:hidden;z-index:950;box-shadow:3px -3px 12px rgba(0,0,0,.45)}",
    ".xp-mh{background:linear-gradient(#0a5cf5,#3d95ff 20%,#0a5cf5);color:#fff;font-size:15px;font-weight:700;padding:10px 12px;text-shadow:1px 1px 2px #000}",
    ".xp-mb{display:flex}.xp-ml,.xp-mr{padding:6px 0;flex:1}.xp-mr{background:#d3e5fa;border-left:1px solid #95bdee}",
    ".xp-mi{padding:6px 12px;cursor:pointer;display:flex;gap:8px;align-items:center;font-size:12px}.xp-mi:hover{background:#316ac5;color:#fff}",
    ".xp-mf{background:linear-gradient(#0a5cf5,#0842c8);padding:6px 10px;display:flex;justify-content:flex-end;gap:12px;color:#fff}.xp-mf button{background:transparent;border:0;color:#fff;cursor:pointer;font-size:11px}",
    ".xp-dlg{position:absolute;inset:0;background:rgba(0,0,0,.15);display:flex;align-items:center;justify-content:center;z-index:980}",
    ".xp-balloon{position:absolute;right:14px;bottom:40px;width:250px;background:#ffffe1;border:1px solid #000;border-radius:6px;padding:10px 12px;box-shadow:2px 2px 6px rgba(0,0,0,.4);z-index:960;color:#000}",
    ".xp-clip{position:absolute;right:30px;bottom:110px;width:240px;z-index:955;display:flex;flex-direction:column;align-items:flex-end;gap:4px}.xp-clip .bub{background:#ffffe1;border:1px solid #000;border-radius:8px;padding:10px;color:#000;font-size:12px;line-height:1.35}.xp-clip .face{font-size:46px;line-height:48px}",
    ".xp-clip button{margin:6px 6px 0 0;padding:2px 12px}",
    ".cmd{background:#000;color:#c0c0c0;font:13px 'Lucida Console',Consolas,monospace;padding:6px;height:100%;overflow:auto;-webkit-user-select:text;user-select:text}.cmd input{background:transparent;border:0;outline:none;color:#c0c0c0;font:inherit;width:70%}",
    ".xp-list{padding:8px;display:flex;flex-direction:column;gap:6px;font-size:12px}.xp-list div{display:flex;gap:8px;align-items:center}",
    ".off{position:absolute;inset:0;background:#000;color:#f90;display:flex;align-items:center;justify-content:center;font:16px monospace;z-index:999;text-align:center;padding:20px}"
  ].join("\n");

  // ------------------------------------------------------------------ the spreadsheet engine (a very small Excel)
  var COLS = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"], ROWS = 36;
  function seed() {
    var r = {}, rows = [
      ["Facilities (Plants)", 18000, 21450, "Greg", "Pending"], ["Morale", 5000, 940, "Dave", "Needs Greg"], ["Snacks (Emergency)", 2400, 3980, "Priya", "FINAL"],
      ["Whiteboard Markers", 600, 2210, "Dave", "Reviewed"], ["Synergy", 40000, 41000, "Legal (don't ask)", "Pending"], ["Printer Ink (Cursed)", 9000, 14320, "Priya", "FINAL-final"],
      ["Team Building (Postponed)", 12000, 0, "Greg", "Pending"], ["Disaster Recovery (Optimistic)", 22000, 3100, "IT", "Reviewed"], ["Quiet Quitting Fund", 1, 1, "Everyone", "Confidential"],
      ["Standing Desks (Unused)", 15500, 15500, "HR", "Final"], ["Coffee", 3200, 6875, "Everyone", "Critical"], ["Consultants (Who?)", 64000, 71250, "Greg", "Pending"],
      ["Mandatory Fun", 4800, 5150, "HR", "Reviewed"], ["Misc.", 700, 9300, "Dave", "Ask Dave"]
    ];
    r.A1 = "Q3 Budget Variance - FINAL (v7) (2)"; r.A2 = "Prepared by: Facilities & Synergy   |   Do not forward"; r.A3 = "Department"; r.B3 = "Budget"; r.C3 = "Actual"; r.D3 = "Variance"; r.E3 = "% Var"; r.F3 = "Owner"; r.G3 = "Status"; r.H3 = "Notes";
    var notes = ["see email", "TBD", "per Greg", "ask Dave", "see tab 4", "pending approval", "n/a", "re-forecast", "per my last email", "circle back"];
    rows.forEach(function (d, i) { var n = 4 + i; r["A" + n] = d[0]; r["B" + n] = String(d[1]); r["C" + n] = String(d[2]); r["D" + n] = "=C" + n + "-B" + n; r["E" + n] = "=IF0(B" + n + ",D" + n + ")"; r["F" + n] = d[3]; r["G" + n] = d[4]; r["H" + n] = pick(notes); });
    r.A19 = "TOTAL"; r.B19 = "=SUM(B4:B17)"; r.C19 = "=SUM(C4:C17)"; r.D19 = "=C19-B19"; r.E19 = "=IF0(B19,D19)";
    r.A21 = "Average department variance"; r.D21 = "=AVERAGE(D4:D17)";
    r.A23 = "Largest overrun"; r.D23 = "=MAX(D4:D17)"; r.A24 = "Largest underspend"; r.D24 = "=MIN(D4:D17)";
    r.A26 = "Notes: numbers are preliminary and may change. Please do not rely on them. Please do not look at them."; return r;
  }
  var COMMENTS = { D7: "Dave: why is this one so big??", G5: "Priya: this was approved verbally.", H12: "Greg: let's take this offline.", B12: "Legal: please delete this comment." };

  function num(raw) { var s = String(raw).replace(/[$,\s]/g, ""); if (/^-?\d*\.?\d+%$/.test(s)) return parseFloat(s) / 100; return /^-?\d*\.?\d+$/.test(s) ? parseFloat(s) : null; }
  function Calc(raw) {
    var cache = {};
    function refOf(s) { var m = /^([A-K])(\d{1,3})$/.exec(s); return m ? m : null; }
    function cell(ref, stack) {
      if (cache[ref] !== undefined) return cache[ref];
      if (stack.indexOf(ref) >= 0) throw "#REF!";
      var v = raw[ref]; if (v == null || v === "") return (cache[ref] = "");
      if (v.charAt(0) !== "=") { var n = num(v); return (cache[ref] = n === null ? v : n); }
      var out; try { out = run(v.slice(1), stack.concat(ref)); } catch (e) { out = typeof e === "string" ? e : "#NAME?"; }
      return (cache[ref] = out);
    }
    function range(a, b, stack) {
      var A = refOf(a), B = refOf(b), out = [];
      if (!A || !B) throw "#REF!";
      for (var c = Math.min(A[1].charCodeAt(0), B[1].charCodeAt(0)); c <= Math.max(A[1].charCodeAt(0), B[1].charCodeAt(0)); c++)
        for (var r = Math.min(+A[2], +B[2]); r <= Math.max(+A[2], +B[2]); r++) out.push(cell(String.fromCharCode(c) + r, stack));
      return out;
    }
    function run(src, stack) {
      var t = src.replace(/\s+/g, "").toUpperCase(), i = 0;
      function peek() { return t.charAt(i); }
      function expr() { var v = term(); while (peek() === "+" || peek() === "-") { var op = t.charAt(i++), w = term(); v = op === "+" ? n(v) + n(w) : n(v) - n(w); } return v; }
      function term() { var v = unary(); while (peek() === "*" || peek() === "/") { var op = t.charAt(i++), w = unary(); if (op === "/") { if (n(w) === 0) throw "#DIV/0!"; v = n(v) / n(w); } else v = n(v) * n(w); } return v; }
      function unary() { if (peek() === "-") { i++; return -n(unary()); } if (peek() === "+") { i++; return unary(); } return atom(); }
      function n(v) { if (typeof v === "number") return v; if (v === "" || v == null) return 0; var m = num(v); if (m === null) throw "#VALUE!"; return m; }
      function atom() {
        var m, rest = t.slice(i);
        if (peek() === "(") { i++; var v = expr(); if (peek() !== ")") throw "#NAME?"; i++; return v; }
        if ((m = /^\d*\.?\d+/.exec(rest))) { i += m[0].length; return parseFloat(m[0]); }
        if ((m = /^([A-Z]+0?)\(/.exec(rest))) {
          var fn = m[1]; i += m[0].length; var args = [];
          while (peek() !== ")") {
            var rm = /^([A-K]\d{1,3}):([A-K]\d{1,3})/.exec(t.slice(i));
            if (rm) { i += rm[0].length; args.push(range(rm[1], rm[2], stack)); } else args.push(expr());
            if (peek() === ",") i++; else if (peek() !== ")") throw "#NAME?";
          }
          i++; return call(fn, args);
        }
        if ((m = /^[A-K]\d{1,3}/.exec(rest))) { i += m[0].length; return cell(m[0], stack); }
        throw "#NAME?";
      }
      function flat(args) { var o = []; args.forEach(function (a) { if (Array.isArray(a)) a.forEach(function (x) { o.push(x); }); else o.push(a); }); return o; }
      function nums(args) { return flat(args).filter(function (x) { return typeof x === "number"; }); }
      function call(fn, a) {
        var xs = nums(a);
        switch (fn) {
          case "SUM": return xs.reduce(function (p, c) { return p + c; }, 0);
          case "AVERAGE": if (!xs.length) throw "#DIV/0!"; return xs.reduce(function (p, c) { return p + c; }, 0) / xs.length;
          case "MIN": return xs.length ? Math.min.apply(null, xs) : 0;
          case "MAX": return xs.length ? Math.max.apply(null, xs) : 0;
          case "COUNT": return xs.length;
          case "ABS": return Math.abs(n(a[0]));
          case "ROUND": return Math.round(n(a[0]) * Math.pow(10, n(a[1] || 0))) / Math.pow(10, n(a[1] || 0));
          case "IF0": return n(a[0]) === 0 ? 0 : n(a[1]) / n(a[0]);      // internal: variance % without a divide-by-zero
          default: throw "#NAME?";
        }
      }
      var res = expr(); if (i < t.length) throw "#NAME?"; return res;
    }
    return function (ref) { try { return cell(ref, []); } catch (e) { return typeof e === "string" ? e : "#NAME?"; } };
  }
  function fmt(ref, v) {
    if (typeof v !== "number") return v == null ? "" : String(v);
    var c = ref.charAt(0), r = +ref.slice(1);
    if (r >= 4 && (c === "B" || c === "C" || c === "D")) return (v < 0 ? "-$" : "$") + Math.abs(Math.round(v)).toLocaleString("en-US");
    if (r >= 4 && c === "E") return (v * 100).toFixed(1) + "%";
    return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
  }

  function box(title, body, buttons, onDone, skin) {
    var ov = h("div", { class: skin === "xp" ? "xp-dlg" : "mb" });
    var done = function (i) { ov.remove(); if (onDone) onDone(i); };
    var btns = buttons.map(function (b, i) { return h("button", { text: b, onclick: function () { done(i); } }); });
    var win = skin === "xp"
      ? h("div", { class: "xp-win", style: "position:relative;min-width:300px;max-width:420px" }, [h("div", { class: "xp-wt" }, [h("span", { class: "t", text: title })]), h("div", { class: "mb-b", style: "background:#ece9d8", html: body }), h("div", { class: "mb-f", style: "background:#ece9d8" }, btns)])
      : h("div", { class: "mb-box" }, [h("div", { class: "mb-t", text: title }), h("div", { class: "mb-b", html: body }), h("div", { class: "mb-f" }, btns)]);
    ov.appendChild(win); return ov;
  }

  function buildSheet(host, opts) {
    opts = opts || {};
    var raw = seed(), calc = Calc(raw), sel = "A1", cellEls = {}, editing = null;
    function recalc() { calc = Calc(raw); Object.keys(cellEls).forEach(paint); formula(); }
    function paint(ref) {
      var td = cellEls[ref]; if (!td || (editing && editing.ref === ref)) return;
      var v = calc(ref), raws = raw[ref];
      td.textContent = fmt(ref, v);
      td.className = ([1, 2, 26].indexOf(+ref.slice(1)) >= 0 ? "ov " : "") + (typeof v === "number" ? "num " : "") + (ref === sel ? "sel " : "") + (+ref.slice(1) === 3 ? "hd " : "") + (+ref.slice(1) === 1 || ref.charAt(0) === "A" && +ref.slice(1) === 19 ? "b " : "") + (COMMENTS[ref] ? "cm " : "") + (typeof v === "number" && v < 0 && +ref.slice(1) >= 4 ? "neg" : "");
      if (COMMENTS[ref]) td.title = COMMENTS[ref];
    }
    var nameBox = h("div", { class: "xl-namebox", text: "A1" }), fin = h("input", { class: "xl-fin", spellcheck: "false" });
    function formula() { nameBox.textContent = sel; if (!editing) fin.value = raw[sel] == null ? "" : raw[sel]; }
    function select(ref) {
      var old = sel; sel = ref; if (cellEls[old]) paint(old); if (cellEls[sel]) { paint(sel); cellEls[sel].scrollIntoView({ block: "nearest", inline: "nearest" }); } formula();
    }
    function move(dc, dr) {
      var c = Math.max(0, Math.min(COLS.length - 1, COLS.indexOf(sel.charAt(0)) + dc)), r = Math.max(1, Math.min(ROWS, +sel.slice(1) + dr)); select(COLS[c] + r);
    }
    function commit(val, dc, dr) {
      if (!editing) return; var ref = editing.ref; editing = null;
      if (val === "") delete raw[ref]; else raw[ref] = val;
      recalc(); paint(ref); status("Ready"); move(dc || 0, dr || 0);
    }
    function edit(ref, init) {
      if (editing) return; select(ref);
      var td = cellEls[ref], inp = h("input", { class: "xl-cellin", spellcheck: "false" });
      inp.value = init != null ? init : (raw[ref] == null ? "" : raw[ref]); editing = { ref: ref, input: inp };
      td.textContent = ""; td.appendChild(inp); inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); status("Edit");
      inp.addEventListener("keydown", function (e) {
        e.stopPropagation();
        if (e.key === "Enter") { e.preventDefault(); commit(inp.value, 0, 1); grid.focus(); }
        else if (e.key === "Tab") { e.preventDefault(); commit(inp.value, 1, 0); grid.focus(); }
        else if (e.key === "Escape") { e.preventDefault(); editing = null; paint(ref); status("Ready"); formula(); grid.focus(); }
      });
      inp.addEventListener("input", function () { fin.value = inp.value; });
      inp.addEventListener("blur", function () { if (editing && editing.input === inp) commit(inp.value, 0, 0); });
    }
    var statusEl = h("span", { text: "Ready" }); function status(t) { statusEl.textContent = t; }
    var table = h("table", { class: "xl-grid" }), colgroup = h("colgroup"), head = h("tr"), tbody = h("tbody");
    colgroup.appendChild(h("col", { style: "width:42px" })); head.appendChild(h("th", { class: "rh corner" }));
    var widths = { A: 230, B: 92, C: 92, D: 92, E: 70, F: 130, G: 100, H: 110, I: 80, J: 80, K: 80 };
    COLS.forEach(function (c) { colgroup.appendChild(h("col", { style: "width:" + widths[c] + "px" })); head.appendChild(h("th", { text: c })); });
    for (var r = 1; r <= ROWS; r++) {
      var tr = h("tr"); tr.appendChild(h("th", { class: "rh", text: String(r) }));
      COLS.forEach(function (c) { var ref = c + r, td = h("td", { "data-ref": ref }); cellEls[ref] = td; tr.appendChild(td); });
      tbody.appendChild(tr);
    }
    table.appendChild(colgroup); table.appendChild(h("thead", {}, head)); table.appendChild(tbody);
    var grid = h("div", { class: "xl-gridwrap", tabindex: "0" }, table);
    grid.addEventListener("mousedown", function (e) { var td = e.target.closest("td[data-ref]"); if (td && !e.target.classList.contains("xl-cellin")) { if (editing) commit(editing.input.value, 0, 0); select(td.dataset.ref); grid.focus(); } });
    grid.addEventListener("dblclick", function (e) { var td = e.target.closest("td[data-ref]"); if (td) edit(td.dataset.ref); });
    grid.addEventListener("contextmenu", function (e) {
      e.preventDefault(); var td = e.target.closest("td[data-ref]"); if (td) select(td.dataset.ref);
      var items = ["Cut", "Copy", "Paste", "Insert Coffee Break", "Delete Meeting", "Hide Row (From Boss)", "Format Cells... (Make It Look Busy)", "Add Comment: \"per my last email\""];
      var m = h("div", { class: "xl-menu", style: "left:" + Math.min(e.clientX, innerWidth - 230) + "px;top:" + Math.min(e.clientY, innerHeight - 240) + "px" },
        items.map(function (t) { return h("div", { text: t, onclick: function () { m.remove(); status(pick(["Done. (Nothing happened.)", "Compiling feelings...", "Action queued behind 14 other meetings.", "Saved to the cloud (a cloud of regret)."])); } }); }));
      host.appendChild(m); var away = function () { m.remove(); D.removeEventListener("mousedown", away, true); }; setTimeout(function () { D.addEventListener("mousedown", away, true); }, 0);
    });
    grid.addEventListener("keydown", function (e) {
      if (editing) return;
      var k = e.key;
      if (k === "ArrowDown") { e.preventDefault(); move(0, 1); } else if (k === "ArrowUp") { e.preventDefault(); move(0, -1); } else if (k === "ArrowLeft") { e.preventDefault(); move(-1, 0); } else if (k === "ArrowRight") { e.preventDefault(); move(1, 0); }
      else if (k === "Enter" || k === "F2") { e.preventDefault(); edit(sel); } else if (k === "Delete" || k === "Backspace") { e.preventDefault(); delete raw[sel]; recalc(); }
      else if (k.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); edit(sel, k); }
    });
    fin.addEventListener("keydown", function (e) { e.stopPropagation(); if (e.key === "Enter") { var v = fin.value; if (v === "") delete raw[sel]; else raw[sel] = v; recalc(); grid.focus(); move(0, 1); } else if (e.key === "Escape") { formula(); grid.focus(); } });
    var tabNames = ["Sheet1", "Q3 Final (2)", "Sheet3", "Do Not Open"], tabs = h("div", { class: "xl-sheets" }, tabNames.map(function (t, i) {
      return h("div", { class: "xl-sh" + (i === 0 ? " on" : ""), text: t, onclick: function () {
        if (t === "Do Not Open") host.appendChild(box("Microsoft Excel", "<b>Are you sure?</b><br><br>There is nothing in this sheet but regret and one unsent resignation letter.", ["Open anyway", "Wise choice"], function (b) {
          if (b === 1) return status("Excel is proud of you.");
          host.appendChild(box("Microsoft Excel", "Opening <b>Do Not Open</b>...<br><br>Found: 14 unsent emails, 3 resignation drafts, and a stapler (it is Milton's).<br><br>The contents have been quarantined.", ["OK", "Return the stapler"], function (c) {
            status(c === 0 ? "Contents quarantined. Please stop looking." : "Stapler returned. Milton sends his thanks.");
          }, opts.skin));
        }, opts.skin));
        else status(t === "Sheet1" ? "Ready" : "This sheet is also Sheet1, but sadder.");
      } });
    }));
    var calcEl = h("span", { text: "" }), pct = 0;
    every(function () { if (Math.random() < 0.25 && !pct) pct = 1; if (pct) { pct += Math.floor(Math.random() * 18) + 4; if (pct >= 100) { pct = 0; calcEl.textContent = ""; } else calcEl.textContent = "Calculating (" + (1 + Math.floor(Math.random() * 7)) + " processors): " + pct + "%"; } }, 900);
    var el = h("div", { style: "display:flex;flex-direction:column;flex:1;min-height:0;position:relative" }, [
      h("div", { class: "xl-fbar" }, [nameBox, h("span", { class: "xl-fx", text: "fx" }), fin]), grid, tabs,
      h("div", { class: "xl-status" }, [statusEl, h("span", { class: "grow" }), calcEl, h("span", { text: "Normal View   100%" })])
    ]);
    Object.keys(cellEls).forEach(paint); formula();
    return { el: el, focus: function () { grid.focus(); }, status: status };
  }

  // ------------------------------------------------------------------ Excel skin
  function excelSkin() {
    var root = h("div", { class: "xl" }), sheet = buildSheet(root, { skin: "excel" }), ribbonBody = h("div", { class: "xl-ribbon" });
    function group(name, btns) { return h("div", { class: "xl-group" }, [h("div", { class: "row" }, btns.map(function (b) { return rb(b); })), h("div", { class: "lab", text: name })]); }
    function rb(b) { return h("button", { class: "xl-rb", text: b, onclick: function () { sheet.status(b === "Windows XP Mode" ? "Starting Windows XP Mode..." : pick(["Done. (Nothing happened.)", "Working on it...", "Formatting applied to your hopes."])); if (b === "Windows XP Mode") later(function () { setSkin("xp"); }, 400); } }); }
    var ribbons = {
      Home: [group("Clipboard", ["Paste", "Cut", "Copy"]), group("Font", ["Calibri", "11", "B", "I", "U"]), group("Alignment", ["Left", "Center", "Right", "Wrap"]), group("Number", ["$", "%", ",", ".00"]), group("Editing", ["\u03A3 AutoSum", "Sort", "Find"])],
      Insert: [group("Tables", ["PivotTable", "Table"]), group("Charts", ["Column", "Line", "Pie (Pi)"]), group("Text", ["Text Box", "Header"])],
      "Page Layout": [group("Themes", ["Themes", "Colors"]), group("Page Setup", ["Margins", "Orientation", "Size"])],
      Formulas: [group("Function Library", ["\u03A3 AutoSum", "Recent", "Financial", "Logical"]), group("Defined Names", ["Name Manager"])],
      Data: [group("Get Data", ["From Text", "From Web"]), group("Sort & Filter", ["Sort", "Filter"])],
      Review: [group("Proofing", ["Spelling", "Thesaurus"]), group("Comments", ["New Comment", "Resolve Existential Dread"])],
      View: [group("Workbook Views", ["Normal", "Page Break"]), group("Show", ["Gridlines", "Formula Bar"]), group("Window", ["Freeze Panes", "Windows XP Mode"])]
    }, tabNames = Object.keys(ribbons), tabsEl = h("div", { class: "xl-tabs" });
    function showTab(n) { [].forEach.call(tabsEl.children, function (c) { c.classList.toggle("on", c.textContent === n); }); ribbonBody.innerHTML = ""; ribbons[n].forEach(function (g) { ribbonBody.appendChild(g); }); }
    tabNames.forEach(function (n) { tabsEl.appendChild(h("div", { class: "xl-tab", text: n, onclick: function () { showTab(n); } })); });
    var title = h("div", { class: "xl-title" }, [h("span", { text: "\u2597X" }), h("div", { class: "xl-name", text: "Q3_Budget_Variance_FINAL_v7.xlsx - Excel" }),
      h("button", { class: "xl-btn", text: "\u2013", onclick: function () { sheet.status("Minimised... (nowhere to go)"); } }), h("button", { class: "xl-btn", text: "\u25A1", onclick: function () { sheet.status("Already maximised. Nice try."); } }),
      h("button", { class: "xl-btn x", text: "\u2715", onclick: function () { root.appendChild(box("Microsoft Excel", "Do you want to save the changes you made to <b>Q3_Budget_Variance_FINAL_v7.xlsx</b>?", ["Save", "Don't Save", "Cancel"], function (b) { sheet.status(["Saved as Q3_Budget_Variance_FINAL_v7_(1).xlsx. Obviously.", "Unsaved changes are the only honest ones.", "Cancelled. Nothing was ever happening."][b]); })); } })]);
    root.appendChild(title); root.appendChild(tabsEl); root.appendChild(ribbonBody); root.appendChild(sheet.el); showTab("Home");
    // the way back: double-click the green bar (the title bar, or the empty part of the tab strip)
    title.setAttribute("title", "Double-click to go back");
    title.addEventListener("dblclick", function (e) { if (!e.target.closest("button")) exit(); });
    tabsEl.addEventListener("dblclick", function (e) { if (e.target === tabsEl) exit(); });
    var hint = h("div", { class: "xl-hint", html: "<b>Double-click the green bar</b> to go back<br><span style='font-size:11px;color:#555'>(or press Esc twice)</span>" });
    root.appendChild(hint); title.classList.add("flash");
    later(function () { hint.remove(); title.classList.remove("flash"); }, 5000);
    later(function () { sheet.focus(); }, 50);
    return root;
  }

  // ------------------------------------------------------------------ Windows XP skin
  function xpSkin() {
    var root = h("div", { class: "xp" }), bgSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 560" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a6fd4"/><stop offset="1" stop-color="#9fd0f7"/></linearGradient><linearGradient id="hill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6fc23a"/><stop offset="1" stop-color="#2f7d1c"/></linearGradient></defs><rect width="800" height="560" fill="url(#sky)"/><g fill="#fff" opacity=".9"><ellipse cx="170" cy="120" rx="90" ry="26"/><ellipse cx="230" cy="105" rx="60" ry="24"/><ellipse cx="560" cy="170" rx="110" ry="28"/><ellipse cx="640" cy="152" rx="70" ry="24"/><ellipse cx="380" cy="70" rx="70" ry="18"/></g><path d="M0 380 C 180 300 360 330 520 360 C 640 380 720 350 800 330 L800 560 L0 560Z" fill="url(#hill)"/><path d="M0 470 C 200 420 420 450 800 410 L800 560 L0 560Z" fill="#3a8e1f" opacity=".85"/></svg>';
    root.appendChild(h("div", { class: "xp-bg", html: bgSvg }));
    var desktop = h("div", { class: "xp-icons" }), tasks = h("div", { class: "xp-tasks" }), wins = {}, startMenu = null;
    function win(id, title, glyph, w, hgt, content, onClose) {
      if (wins[id]) { wins[id].show(); return wins[id]; }
      var x = 90 + Object.keys(wins).length * 34, y = 40 + Object.keys(wins).length * 30;
      var el = h("div", { class: "xp-win", style: "left:" + x + "px;top:" + y + "px;width:" + w + "px;height:" + hgt + "px;z-index:" + (++S.z) });
      var tb = h("button", { class: "xp-tb on", text: glyph + " " + title }), api = {};
      var bar = h("div", { class: "xp-wt" }, [h("span", { text: glyph }), h("span", { class: "t", text: title }),
        h("button", { class: "xp-wb", text: "_", onclick: function () { api.hide(); } }), h("button", { class: "xp-wb", text: "\u25A1", onclick: function () { el.style.left = "0"; el.style.top = "0"; el.style.width = "100%"; el.style.height = "calc(100% - 30px)"; } }),
        h("button", { class: "xp-wb x", text: "\u2715", onclick: function () { api.close(); } })]);
      el.appendChild(bar); el.appendChild(h("div", { class: "xp-wc" }, content)); root.appendChild(el);
      api.show = function () { el.style.display = "flex"; el.style.zIndex = ++S.z; tb.classList.add("on"); }; api.hide = function () { el.style.display = "none"; tb.classList.remove("on"); };
      api.close = function () { el.remove(); tb.remove(); delete wins[id]; if (onClose) onClose(); };
      tb.addEventListener("click", function () { if (el.style.display === "none") api.show(); else api.hide(); }); tasks.appendChild(tb);
      el.addEventListener("mousedown", function () { el.style.zIndex = ++S.z; });
      bar.addEventListener("mousedown", function (e) {
        if (e.target.tagName === "BUTTON") return; var ox = e.clientX - el.offsetLeft, oy = e.clientY - el.offsetTop;
        function mv(ev) { el.style.left = Math.max(-200, ev.clientX - ox) + "px"; el.style.top = Math.max(0, ev.clientY - oy) + "px"; }
        function up() { D.removeEventListener("mousemove", mv); D.removeEventListener("mouseup", up); } D.addEventListener("mousemove", mv); D.addEventListener("mouseup", up);
      });
      wins[id] = api; return api;
    }
    function dialog(title, body, buttons, done) { var d = box(title, body, buttons, done, "xp"); root.appendChild(d); return d; }
    function listWin(id, title, glyph, rows) { win(id, title, glyph, 420, 280, h("div", { class: "xp-list" }, rows.map(function (r) { return h("div", {}, [h("span", { text: r[0], style: "font-size:22px" }), h("span", { text: r[1] })]); }))); }
    function cmdWin() {
      var out = h("div"), inp = h("input", { spellcheck: "false" }), wrap = h("div", { class: "cmd" }, [out, h("div", {}, [h("span", { text: "C:\\Documents and Settings\\Administrator>" }), inp])]);
      function print(t) { out.appendChild(h("div", { text: t })); wrap.scrollTop = 1e6; }
      print("Microsoft Windows XP [Version 5.1.2600]"); print("(C) Copyright 1985-2001 Microsoft Corp."); print("");
      inp.addEventListener("keydown", function (e) {
        e.stopPropagation(); if (e.key !== "Enter") return; var c = inp.value.trim(), l = c.toLowerCase(); print("C:\\Documents and Settings\\Administrator>" + c); inp.value = "";
        var cmds = { help: "Commands: dir, cls, ver, date, time, whoami, coffee, exit. Everything else is a mystery.", ver: "Microsoft Windows XP [Version 5.1.2600]", whoami: "corporate\\drone", date: new Date().toDateString(), time: new Date().toLocaleTimeString(),
          dir: "Volume in drive C has no label.\n\n05/09/2003  09:00 AM  <DIR>  Motivation (deleted)\n05/09/2003  09:00 AM  <DIR>  Meetings That Could Have Been Emails\n07/22/2026  04:59 PM        14,208  resignation_letter_DRAFT_v14.txt",
          coffee: "Error 418: I'm a teapot.", "format c:": "Nice try.", sudo: "This is Windows. Nobody here can help you.", hello: "Hello. Please return to your spreadsheet." };
        if (l === "cls") out.innerHTML = ""; else if (l === "exit") wins.cmd && wins.cmd.close(); else if (!l) return;
        else if (cmds[l]) cmds[l].split("\n").forEach(print); else print("'" + c + "' is not recognized as an internal or external command, operable program or batch file.");
      });
      var w = win("cmd", "C:\\WINDOWS\\system32\\cmd.exe", "\u2B1B", 560, 320, wrap); later(function () { inp.focus(); }, 60); return w;
    }
    var letter = "Dear Greg,\n\nPer my last email, I wanted to touch base about something I have been quietly working up to.\n\nI regret to inform you that I have been quietly quitting for some time now. You may not have noticed. That is sort of the point.\n\nPlease find attached my unused vacation days.\n\nSincerely,\n\n(Draft 14 - DO NOT SEND)";
    var apps = {
      excel: function () { var s = buildSheet(root, { skin: "xp" }); win("excel", "Microsoft Excel - Q3_Budget_Variance_FINAL_v7.xlsx", "\u2597", 760, 430, s.el); later(s.focus, 50); },
      notepad: function () { var ta = h("textarea", { style: "flex:1;border:0;outline:none;resize:none;padding:6px;font:13px 'Lucida Console',monospace", spellcheck: "false" }); ta.value = letter; win("notepad", "resignation_letter_DRAFT_v14.txt - Notepad", "\uD83D\uDCDD", 440, 300, ta); },
      cmd: cmdWin,
      computer: function () { listWin("computer", "My Computer", "\uD83D\uDDA5", [["\uD83D\uDCBF", "Local Disk (C:)   3.2 GB free of 40 GB"], ["\uD83D\uDCBE", "3\u00BD Floppy (A:)   Please insert a disk"], ["\uD83D\uDCC0", "Quiet Quitter (Q:)   100% free of motivation"], ["\uD83D\uDCC1", "Shared Documents   (access denied: try believing in yourself)"]]); },
      docs: function () { listWin("docs", "My Documents", "\uD83D\uDCC1", [["\uD83D\uDCC4", "Q3_Budget_Variance_FINAL_v7.xlsx"], ["\uD83D\uDCC4", "Q3_Budget_Variance_FINAL_v6_USE_THIS_ONE.xlsx"], ["\uD83D\uDCC4", "meeting_notes_(none).txt"], ["\uD83D\uDCC4", "TPS_report_cover_sheet.doc"], ["\uD83D\uDCC4", "resume_UPDATED_final_final.doc"]]); },
      bin: function () { listWin("bin", "Recycle Bin", "\uD83D\uDDD1", [["\uD83D\uDCC4", "motivation.exe"], ["\uD83D\uDCC4", "Monday_enthusiasm.dll"], ["\uD83D\uDCC4", "work_life_balance.xls"], ["\uD83D\uDCC4", "synergy_v1.ppt"]]); },
      ie: function () { win("ie", "Internet Explorer", "\uD83C\uDF10", 480, 300, h("div", { style: "padding:20px;font-size:13px;line-height:1.5", html: "<b>The page cannot be displayed</b><br><br>The page you are looking for is currently unavailable.<br><br>Please try the following:<ul><li>Open the www.work-related-things.com home page and look for links to the information you want.</li><li>Click Refresh, or try again later.</li><li>Stop browsing for jobs on company time.</li></ul>" })); },
      crash: function (n) {
        dialog(n, "This program has performed an illegal operation and will be shut down.<br><br>If the problem persists, contact the program vendor (they have also quit).", ["Details >>", "Close"], function (b) {
          if (b === 0) dialog(n + " - Error Details", "Error: motivation.dll not found.<br>Offset: 0x0000DEAD<br>Reason: it is Monday.<br>Suggested fix: a long weekend.", ["Copy to clipboard", "Close"], function (c) { if (c === 0) dialog(n, "Copied. (Nothing was actually copied.)", ["OK"]); });
        });
      }
    };
    function icon(g, label, fn) {
      var el = h("div", { class: "xp-ic", ondblclick: fn, onclick: function () { [].forEach.call(desktop.children, function (c) { c.classList.remove("sel"); }); el.classList.add("sel"); } }, [h("div", { class: "g", text: g }), h("div", { class: "l", text: label })]);
      desktop.appendChild(el);
    }
    icon("\uD83D\uDDA5", "My Computer", apps.computer); icon("\uD83D\uDCC1", "My Documents", apps.docs); icon("\uD83C\uDF10", "Internet Explorer", apps.ie); icon("\uD83D\uDDD1", "Recycle Bin", apps.bin);
    icon("\uD83D\uDCCA", "Q3_Budget_Variance_FINAL_v7.xlsx", apps.excel); icon("\uD83D\uDCDD", "resignation_letter_DRAFT_v14.txt", apps.notepad);
    function logOff() { dialog("Log Off Windows", "Are you sure you want to log off?<br><br>Your session will end and the real work will resume.", ["Log Off", "Cancel"], function (b) { if (b === 0) exit(); }); }
    function turnOff() { var off = h("div", { class: "off", html: "It is now safe to turn off your computer.<br><br>(Press Esc twice to wake it up.)" }); root.appendChild(off); off.addEventListener("click", function () { off.remove(); }); }
    function toggleStart() {
      if (startMenu) { startMenu.remove(); startMenu = null; return; }
      function mi(g, t, fn) { return h("div", { class: "xp-mi", onclick: function () { toggleStart(); fn(); } }, [h("span", { text: g, style: "font-size:18px" }), h("span", { text: t })]); }
      startMenu = h("div", { class: "xp-menu" }, [h("div", { class: "xp-mh", text: "\uD83D\uDC64 Administrator" }), h("div", { class: "xp-mb" }, [
        h("div", { class: "xp-ml" }, [mi("\uD83C\uDF10", "Internet Explorer", apps.ie), mi("\uD83D\uDCE7", "E-mail (Overbooked)", function () { apps.crash("Outlook"); }), mi("\uD83D\uDCCA", "Microsoft Excel", apps.excel), mi("\uD83D\uDCDD", "Notepad", apps.notepad),
          mi("\u2B1B", "Command Prompt", apps.cmd), mi("\uD83C\uDCCF", "Solitaire (don't)", function () { apps.crash("Solitaire"); }), mi("\uD83D\uDCA3", "Minesweeper (it's a metaphor)", function () { apps.crash("Minesweeper"); }), mi("\uD83C\uDFA8", "Paint", function () { apps.crash("Paint"); })]),
        h("div", { class: "xp-mr" }, [mi("\uD83D\uDCC1", "My Documents", apps.docs), mi("\uD83D\uDDA5", "My Computer", apps.computer), mi("\u2699", "Control Panel", function () { apps.crash("Control Panel"); }), mi("\u2753", "Help and Support", function () { clip(true); })])]),
        h("div", { class: "xp-mf" }, [h("button", { text: "\uD83D\uDD11 Log Off", onclick: function () { toggleStart(); logOff(); } }), h("button", { text: "\u23FB Turn Off Computer", onclick: function () { toggleStart(); turnOff(); } })])]);
      root.appendChild(startMenu);
    }
    var clock = h("span", { text: "" }); function tick() { clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); } tick(); every(tick, 15000);
    root.appendChild(desktop);
    root.appendChild(h("div", { class: "xp-task" }, [h("button", { class: "xp-start", onclick: toggleStart }, [h("span", { text: "\u229E" }), "start"]), tasks, h("div", { class: "xp-tray" }, [h("span", { text: "\uD83D\uDD0A" }), h("span", { text: "\uD83D\uDEE1" }), clock])]));
    root.addEventListener("mousedown", function (e) { if (startMenu && !e.target.closest(".xp-menu") && !e.target.closest(".xp-start")) { startMenu.remove(); startMenu = null; } });
    var tips = ["It looks like you're writing a resignation letter. Would you like help?", "It looks like you're pretending to work. Would you like help pretending harder?", "It looks like you've been in this spreadsheet for 4 minutes without typing. Impressive.", "Tip: a meeting is just an email that is out of breath."];
    var clipEl = null;
    function clip(force) {
      if (clipEl) return;
      clipEl = h("div", { class: "xp-clip" }, [h("div", { class: "bub" }, [pick(tips), h("div", {}, [h("button", { text: "Yes please", onclick: function () { clipEl.firstChild.firstChild.textContent = "Too late. You're already quiet quitting."; }}), h("button", { text: "No thanks", onclick: function () { clipEl.remove(); clipEl = null; } })])]), h("div", { class: "face", text: "\uD83D\uDCCE" })]);
      root.appendChild(clipEl); later(function () { if (clipEl) { clipEl.remove(); clipEl = null; } }, force ? 20000 : 14000);
    }
    later(function () { var b = h("div", { class: "xp-balloon", html: "<b>Unused vacation days</b><br>You have 14 unused vacation days. Click to ignore them." }); b.addEventListener("click", function () { b.remove(); }); root.appendChild(b); later(function () { b.remove(); }, 9000); }, 9000);
    later(function () { clip(false); }, 16000); every(function () { if (Math.random() < 0.35) clip(false); }, 70000);
    apps.excel();
    return root;
  }

  // ------------------------------------------------------------------ switching on and off
  function build() {
    var ov = D.getElementById("qqwork"); if (ov) ov.remove();
    ov = h("div", { id: "qqwork", tabindex: "-1" }); ov.appendChild(S.skin === "xp" ? xpSkin() : excelSkin()); D.body.appendChild(ov);
    D.title = S.skin === "xp" ? "My Computer" : "Q3_Budget_Variance_FINAL_v7.xlsx - Excel"; icons(S.skin === "xp" ? ICON_XP : ICON);
  }
  function icons(href) { [].forEach.call(D.querySelectorAll("link[rel~='icon'],link[rel='shortcut icon']"), function (l) { l.setAttribute("href", href); l.removeAttribute("sizes"); l.removeAttribute("type"); }); }
  function stopTimers() { S.timers.forEach(function (t) { clearTimeout(t); clearInterval(t); }); S.timers = []; }
  function setSkin(skin) { S.skin = skin; try { localStorage.setItem("qq_work_skin", skin); } catch (e) {} stopTimers(); build(); }
  function enter() {
    if (S.on) return; S.on = true;
    try { S.skin = localStorage.getItem("qq_work_skin") || "excel"; } catch (e) { S.skin = "excel"; }
    var links = [].map.call(D.querySelectorAll("link[rel~='icon'],link[rel='shortcut icon']"), function (l) { return [l, l.getAttribute("href"), l.getAttribute("sizes"), l.getAttribute("type")]; });
    S.saved = { title: D.title, links: links, overflow: D.body.style.overflow, focus: D.activeElement };
    if (!D.getElementById("qqwork-css")) D.head.appendChild(h("style", { id: "qqwork-css", text: CSS }));
    var main = D.querySelector("main"); if (main) main.setAttribute("inert", ""); D.body.style.overflow = "hidden";
    build();
  }
  function exit() {
    if (!S.on) return; S.on = false; stopTimers();
    var ov = D.getElementById("qqwork"); if (ov) ov.remove();
    var main = D.querySelector("main"); if (main) main.removeAttribute("inert"); D.body.style.overflow = S.saved.overflow;
    D.title = S.saved.title; S.saved.links.forEach(function (l) { l[0].setAttribute("href", l[1]); if (l[2]) l[0].setAttribute("sizes", l[2]); if (l[3]) l[0].setAttribute("type", l[3]); });
    try { if (S.saved.focus && S.saved.focus.focus) S.saved.focus.focus(); } catch (e) {}
  }
  function toggle() { if (S.on) exit(); else enter(); }

  var lastEsc = 0;
  D.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !e.repeat) { var now = Date.now(); if (now - lastEsc < 450) { e.preventDefault(); toggle(); lastEsc = 0; } else lastEsc = now; }
  }, true);
  W.QQWork = { toggle: toggle, enter: enter, exit: exit, skin: setSkin, on: function () { return S.on; } };
})();
