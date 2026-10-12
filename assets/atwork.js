// SPDX-FileCopyrightText: 2026 That Scottish Guy
// SPDX-License-Identifier: AGPL-3.0-only
/* "I'm at work now": a boss key. Esc twice (or the briefcase button) covers the whole page with a believable
 * spreadsheet or a Windows 11 / 10 desktop. Nothing here touches your data; it is all pretend. Press the same keys to come back. */
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
    /* windows 10/11 */
    ".xp{--tb:48px;position:absolute;inset:0;overflow:hidden;font-family:'Segoe UI Variable','Segoe UI',system-ui,Arial,sans-serif;font-size:12px;background:#0a3a8c;color:#1a1a1a}",
    ".xp.w10{--tb:40px}",
    ".xp-bg{position:absolute;inset:0}.xp-bg svg{width:100%;height:100%;display:block}",
    ".xp-icons{position:absolute;left:8px;top:8px;display:flex;flex-direction:column;gap:6px;flex-wrap:wrap;height:calc(100% - var(--tb) - 20px);align-content:flex-start;column-gap:6px}",
    ".xp-ic{width:80px;padding:6px 2px 4px;border:1px solid transparent;border-radius:4px;text-align:center;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.9);cursor:default}.xp-ic .g{font-size:34px;line-height:40px}.xp-ic .l{padding:1px 3px;word-wrap:break-word;font-size:12px}.xp-ic:hover{background:rgba(255,255,255,.14)}.xp-ic.sel{background:rgba(255,255,255,.25);border-color:rgba(255,255,255,.4)}",
    ".xp-task{position:absolute;left:0;right:0;bottom:0;height:var(--tb);display:flex;align-items:center;z-index:900}",
    ".xp.w11 .xp-task{background:rgba(243,243,243,.88);backdrop-filter:blur(20px);border-top:1px solid rgba(0,0,0,.08);color:#1a1a1a}",
    ".xp.w10 .xp-task{background:rgba(16,16,16,.93);color:#fff}",
    ".xp-sp{flex:1}",
    ".xp-start{height:var(--tb);width:var(--tb);flex:none;border:0;background:transparent;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0}.xp-start svg{width:20px;height:20px;display:block}.xp.w11 .xp-start{border-radius:6px;height:40px;width:44px;margin:0 2px}.xp.w11 .xp-start:hover{background:rgba(255,255,255,.7)}.xp.w10 .xp-start:hover{background:rgba(255,255,255,.15)}",
    ".xp-tasks{display:flex;gap:2px;padding:0 4px;overflow:hidden;align-items:center;height:100%}.xp.w10 .xp-tasks{flex:1}",
    ".xp-tb{min-width:44px;max-width:170px;height:calc(var(--tb) - 8px);border:0;border-bottom:3px solid transparent;background:transparent;color:inherit;text-align:left;padding:0 10px;cursor:default;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font:inherit;font-size:12px}",
    ".xp.w11 .xp-tb{border-radius:6px;background:rgba(255,255,255,.55)}.xp.w11 .xp-tb.on{background:#fff;border-bottom-color:#0067c0;box-shadow:0 1px 3px rgba(0,0,0,.15)}.xp.w11 .xp-tb:hover{background:#fff}",
    ".xp.w10 .xp-tb{background:#2d2d2d}.xp.w10 .xp-tb.on{background:#464646;border-bottom-color:#76b9ed}.xp.w10 .xp-tb:hover{background:#555}",
    ".xp-tray{height:100%;display:flex;align-items:center;gap:10px;padding:0 12px;font-size:12px}.xp.w11 .xp-tray{flex:1;justify-content:flex-end}",
    ".xp-win{position:absolute;background:#fff;color:#1a1a1a;border:1px solid #6b6b6b;display:flex;flex-direction:column;min-width:220px}",
    ".xp.w11 .xp-win{border-radius:8px;border-color:rgba(0,0,0,.35);box-shadow:0 8px 32px rgba(0,0,0,.35);overflow:hidden}.xp.w10 .xp-win{border-color:#1e78d4;box-shadow:0 4px 18px rgba(0,0,0,.45)}",
    ".xp-wt{height:32px;color:#1a1a1a;font-weight:400;display:flex;align-items:center;gap:8px;padding:0 0 0 10px;cursor:move;user-select:none}.xp.w11 .xp-wt{background:#f3f3f3}.xp.w10 .xp-wt{background:#fff}.xp-wt .t{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}",
    ".xp-wb{width:46px;height:32px;border:0;background:transparent;color:#1a1a1a;font-size:12px;cursor:default;padding:0}.xp-wb:hover{background:rgba(0,0,0,.08)}.xp-wb.x:hover{background:#c42b1c;color:#fff}",
    ".xp-wc{flex:1;overflow:auto;background:#fff;min-height:0;position:relative;display:flex;flex-direction:column}",
    ".xp-menu{position:absolute;bottom:calc(var(--tb) + 8px);width:540px;background:rgba(243,243,243,.96);backdrop-filter:blur(24px);border:1px solid rgba(0,0,0,.15);overflow:hidden;z-index:950;box-shadow:0 8px 32px rgba(0,0,0,.35);color:#1a1a1a}",
    ".xp.w11 .xp-menu{left:50%;transform:translateX(-50%);border-radius:10px}.xp.w10 .xp-menu{left:0;bottom:var(--tb);width:480px;background:rgba(32,32,32,.97);color:#fff;border-color:#333}",
    ".xp-mh{padding:12px 16px;font-size:14px;font-weight:600}",
    ".xp-mb{display:flex}.xp-ml,.xp-mr{padding:4px 6px;flex:1}.xp.w11 .xp-mr{background:rgba(0,0,0,.03)}.xp.w10 .xp-mr{background:rgba(255,255,255,.05)}",
    ".xp-mi{padding:7px 10px;cursor:default;display:flex;gap:10px;align-items:center;font-size:12.5px;border-radius:5px}.xp-mi:hover{background:rgba(0,103,192,.14)}.xp.w10 .xp-mi:hover{background:rgba(255,255,255,.15)}",
    ".xp-mf{padding:8px 14px;display:flex;justify-content:flex-end;gap:14px;background:rgba(0,0,0,.05)}.xp.w10 .xp-mf{background:rgba(255,255,255,.07)}.xp-mf button{background:transparent;border:0;color:inherit;cursor:pointer;font:inherit}",
    ".xp-dlg{position:absolute;inset:0;background:rgba(0,0,0,.25);display:flex;align-items:center;justify-content:center;z-index:980}",
    ".xp-balloon,.xp-clip .bub{background:#fff;color:#1a1a1a;border:1px solid rgba(0,0,0,.15);border-radius:8px;padding:12px 14px;box-shadow:0 6px 24px rgba(0,0,0,.35);font-size:12.5px;line-height:1.4}",
    ".xp-balloon{position:absolute;right:14px;bottom:calc(var(--tb) + 12px);width:290px;z-index:960}",
    ".xp-clip{position:absolute;right:14px;bottom:calc(var(--tb) + 12px);width:290px;z-index:955;display:flex;flex-direction:column;align-items:flex-end;gap:4px}.xp-clip .face{display:none}.xp-clip button{margin:8px 6px 0 0;padding:3px 12px}",
    ".xp .xq,.xp .xq-in,.xp .xq-b{font-family:'Segoe UI',system-ui,Arial,sans-serif}.xp .xq{background:#f9f9f9;font-size:12px}.xp .xq-tools{border-bottom-color:#ddd}.xp .xq-in{border:1px solid #bbb;border-radius:4px;padding:3px 6px}",
    ".xp .xq-list{border-color:#ddd;border-radius:4px}.xp .xq-r.sel{background:#0067c0}.xp .xq-r:hover{background:#eef4fb}.xp .xq-r.sel:hover{background:#0067c0}.xp .xq-r.hd{background:#f3f3f3;border-bottom-color:#ddd}.xp .xq-grp{background:#eef4fb;border-bottom-color:#cfe0f3}",
    ".xp .xq-pane{border-top-color:#ddd}.xp .xq-b{background:#fdfdfd;border:1px solid #bbb;border-radius:4px;padding:3px 12px}.xp .xq-b:hover{background:#eef4fb;border-color:#0067c0}.xp .xq-fav{background:#f3f3f3;color:#1a1a1a}.xp .xq-fav .xq-grp{background:#e6eef8;color:#1a1a1a}.xp .xq-fl:hover{background:#e0ecf9;text-decoration:none}",
    ".xp-list{padding:10px;display:flex;flex-direction:column;gap:8px;font-size:13px}.xp-list div{display:flex;gap:8px;align-items:center}",
    ".cmd{background:#000;color:#c0c0c0;font:13px 'Lucida Console',Consolas,monospace;padding:6px;height:100%;overflow:auto;-webkit-user-select:text;user-select:text}.cmd input{background:transparent;border:0;outline:none;color:#c0c0c0;font:inherit;width:70%}",
    ".xq{display:flex;flex-direction:column;flex:1;min-height:0;background:#ece9d8;font-size:11px;color:#000}.xq-tools{display:flex;gap:8px;align-items:center;padding:5px 6px;border-bottom:1px solid #aca899;flex-wrap:wrap}.xq-in{font:11px Tahoma,Arial,sans-serif;border:1px solid #7f9db9;padding:2px 4px;background:#fff}.xq-tools .xq-in:first-child{flex:1;min-width:150px}.xq-count{margin-left:auto;color:#444}",
    ".xq-list{flex:1;overflow:auto;background:#fff;border:1px solid #7f9db9;margin:4px;min-height:80px}.xq-r{display:grid;grid-template-columns:3fr 2fr 1.4fr 1fr;gap:6px;padding:2px 6px;cursor:default;white-space:nowrap}.xq-r span{overflow:hidden;text-overflow:ellipsis}.xq-r.t{grid-template-columns:3fr 2fr 1.3fr 1.6fr}.xq-r:hover{background:#e8f0fd}.xq-r.sel{background:#316ac5;color:#fff}.xq-r.hd{position:sticky;top:0;background:linear-gradient(#fff,#ece9d8);border-bottom:1px solid #aca899;font-weight:700}",
    ".xq-grp{background:#d8e4f8;font-weight:700;padding:3px 6px;border-bottom:1px solid #95bdee}.xq-more{padding:8px;color:#555}.xq-pane{padding:6px 8px 8px;border-top:1px solid #aca899;display:flex;flex-direction:column;gap:5px;min-height:150px}.xq-title{font-size:13px;font-weight:700}.xq-meta{color:#444}.xq-act{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.xq-hint{color:#555;padding:10px}.xq-msg{color:#060}.xq-match{color:#222}",
    ".xq-b{font:11px Tahoma,Arial,sans-serif;background:linear-gradient(#fff,#ece9d8);border:1px solid #003c74;border-radius:3px;padding:2px 10px;cursor:pointer}.xq-b:hover{background:#fff4c4;border-color:#e5a010}.xq-fav{width:190px;background:#6b8fd6;background:linear-gradient(#7ba2e7,#6375d6);color:#fff;overflow:auto}.xq-fav .xq-grp{background:rgba(255,255,255,.2);color:#fff;border:0}.xq-fl{padding:4px 8px;cursor:pointer}.xq-fl:hover{background:rgba(255,255,255,.3);text-decoration:underline}",
    ".off{position:absolute;inset:0;background:#000;color:#fff;display:flex;align-items:center;justify-content:center;font:16px monospace;z-index:999;text-align:center;padding:20px}"
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
    function rb(b) { return h("button", { class: "xl-rb", text: b, onclick: function () { var uv = { "Auto Update": "auto", "Win 11": "w11", "Win 10": "w10", "macOS": "mac", "Ubuntu": "ubuntu" }[b]; if (uv) return showUpdate(uv); var sk = { "Windows 11 Mode": "w11", "Windows 10 Mode": "w10" }[b]; sheet.status(sk ? "Starting " + b + "..." : pick(["Done. (Nothing happened.)", "Working on it...", "Formatting applied to your hopes."])); if (sk) later(function () { setSkin(sk); }, 400); } }); }
    var ribbons = {
      Home: [group("Clipboard", ["Paste", "Cut", "Copy"]), group("Font", ["Calibri", "11", "B", "I", "U"]), group("Alignment", ["Left", "Center", "Right", "Wrap"]), group("Number", ["$", "%", ",", ".00"]), group("Editing", ["\u03A3 AutoSum", "Sort", "Find"])],
      Insert: [group("Tables", ["PivotTable", "Table"]), group("Charts", ["Column", "Line", "Pie (Pi)"]), group("Text", ["Text Box", "Header"])],
      "Page Layout": [group("Themes", ["Themes", "Colors"]), group("Page Setup", ["Margins", "Orientation", "Size"])],
      Formulas: [group("Function Library", ["\u03A3 AutoSum", "Recent", "Financial", "Logical"]), group("Defined Names", ["Name Manager"])],
      Data: [group("Get Data", ["From Text", "From Web"]), group("Sort & Filter", ["Sort", "Filter"])],
      Review: [group("Proofing", ["Spelling", "Thesaurus"]), group("Comments", ["New Comment", "Resolve Existential Dread"])],
      View: [group("Workbook Views", ["Normal", "Page Break"]), group("Show", ["Gridlines", "Formula Bar"]), group("Window", ["Freeze Panes", "Windows 11 Mode", "Windows 10 Mode"]), group("Updates (full screen)", ["Auto Update", "Win 11", "Win 10", "macOS", "Ubuntu"])]
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

  // ------------------------------------------------------------------ Windows 11 / 10 desktop skin
  function winSkin(ver) {
    var w11 = ver !== "w10", build_no = ["10", "0", w11 ? "22631" : "19045", w11 ? "4037" : "4651"].join(".");
    var root = h("div", { class: "xp " + (w11 ? "w11" : "w10") }), bgSvg = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 800 500\" preserveAspectRatio=\"xMidYMid slice\"><defs><radialGradient id=\"g\" cx=\".5\" cy=\".55\" r=\".7\"><stop offset=\"0\" stop-color=\"#7fb8ff\"/><stop offset=\".5\" stop-color=\"#2a6fd8\"/><stop offset=\"1\" stop-color=\"#0a2a78\"/></radialGradient></defs><rect width=\"800\" height=\"500\" fill=\"url(#g)\"/><g transform=\"translate(400 270)\" fill-opacity=\".55\"><g fill=\"#1757c9\"><ellipse rx=\"70\" ry=\"190\" transform=\"rotate(25)\"/><ellipse rx=\"70\" ry=\"190\" transform=\"rotate(-25)\"/></g><g fill=\"#5ca0ff\"><ellipse rx=\"60\" ry=\"170\" transform=\"rotate(70)\"/><ellipse rx=\"60\" ry=\"170\" transform=\"rotate(-70)\"/></g><ellipse rx=\"55\" ry=\"150\" fill=\"#a8d0ff\" fill-opacity=\".6\"/></g></svg>";
    if (!w11) bgSvg = "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 800 500\" preserveAspectRatio=\"xMidYMid slice\"><defs><linearGradient id=\"g\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop offset=\"0\" stop-color=\"#05204f\"/><stop offset=\"1\" stop-color=\"#1d7be0\"/></linearGradient><linearGradient id=\"b\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\"><stop offset=\"0\" stop-color=\"#6cc0ff\" stop-opacity=\".55\"/><stop offset=\"1\" stop-color=\"#6cc0ff\" stop-opacity=\"0\"/></linearGradient></defs><rect width=\"800\" height=\"500\" fill=\"url(#g)\"/><path d=\"M330 120L560 60V440L330 380Z\" fill=\"url(#b)\"/><g fill=\"#0b3a7e\" fill-opacity=\".55\"><path d=\"M370 140L440 122V240L370 236Z\"/><path d=\"M452 120L520 103V240L452 240Z\"/><path d=\"M370 260L440 262V376L370 360Z\"/><path d=\"M452 262L520 262V420L452 392Z\"/></g></svg>";
    root.appendChild(h("div", { class: "xp-bg", html: bgSvg }));
    var desktop = h("div", { class: "xp-icons" }), tasks = h("div", { class: "xp-tasks" }), wins = {}, startMenu = null;
    function win(id, title, glyph, w, hgt, content, onClose) {
      if (wins[id]) { wins[id].show(); return wins[id]; }
      var x = 90 + Object.keys(wins).length * 34, y = 40 + Object.keys(wins).length * 30;
      var el = h("div", { class: "xp-win", style: "left:" + x + "px;top:" + y + "px;width:" + w + "px;height:" + hgt + "px;z-index:" + (++S.z) });
      var tb = h("button", { class: "xp-tb on", text: glyph + " " + title }), api = {};
      var bar = h("div", { class: "xp-wt" }, [h("span", { text: glyph }), h("span", { class: "t", text: title }),
        h("button", { class: "xp-wb", text: "_", onclick: function () { api.hide(); } }), h("button", { class: "xp-wb", text: "\u25A1", onclick: function () { el.style.left = "0"; el.style.top = "0"; el.style.width = "100%"; el.style.height = "calc(100% - var(--tb))"; } }),
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
      var out = h("div"), inp = h("input", { spellcheck: "false" }), wrap = h("div", { class: "cmd" }, [out, h("div", {}, [h("span", { text: "C:\\Users\\Administrator>" }), inp])]);
      function print(t) { out.appendChild(h("div", { text: t })); wrap.scrollTop = 1e6; }
      print("Microsoft Windows [Version " + build_no + "]"); print("(c) Microsoft Corporation. All rights reserved."); print("");
      inp.addEventListener("keydown", function (e) {
        e.stopPropagation(); if (e.key !== "Enter") return; var c = inp.value.trim(), l = c.toLowerCase(); print("C:\\Users\\Administrator>" + c); inp.value = "";
        var cmds = { help: "Commands: jobs [text], find <text>, new, tracker, dir, cls, ver, date, time, whoami, coffee, exit. Everything else is a mystery.", ver: "Microsoft Windows [Version " + build_no + "]", whoami: "corporate\\drone", date: new Date().toDateString(), time: new Date().toLocaleTimeString(),
          dir: "Volume in drive C has no label.\n\n05/09/2003  09:00 AM  <DIR>  Motivation (deleted)\n05/09/2003  09:00 AM  <DIR>  Meetings That Could Have Been Emails\n07/22/2026  04:59 PM        14,208  resignation_letter_DRAFT_v14.txt",
          coffee: "Error 418: I'm a teapot.", "format c:": "Nice try.", sudo: "This is Windows. Nobody here can help you.", hello: "Hello. Please return to your spreadsheet." };
        if (l === "cls") out.innerHTML = ""; else if (l === "exit") wins.cmd && wins.cmd.close(); else if (!l) return; else if (qcmd(l, c, print)) { }
        else if (cmds[l]) cmds[l].split("\n").forEach(print); else print("'" + c + "' is not recognized as an internal or external command, operable program or batch file.");
      });
      var w = win("cmd", "C:\\WINDOWS\\system32\\cmd.exe", "\u2B1B", 560, 320, wrap); later(function () { inp.focus(); }, 60); return w;
    }
    // ---- real Quiet Quitter features, dressed as Windows programs (data comes from the same endpoints as the page)
    var Q = { data: null, track: {}, me: null, p: null }, STAT = ["applied", "interview", "offer", "rejected", "withdrawn"];
    function qload(force) {
      if (Q.p && !force) return Q.p;
      function j(u) { return fetch(u, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }); }
      return (Q.p = Promise.all([j("jobs.json"), j("api/track"), j("api/me")]).then(function (a) { Q.data = a[0]; Q.track = a[1] || {}; Q.me = a[2]; return Q; }));
    }
    function qsave(body) {
      return fetch("api/track", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (t) { Q.track = t; return t; });
    }
    function live() { return ((Q.data && Q.data.jobs) || []).filter(function (j) { return !j.closed; }); }
    function byUrl(u) { var a = live(); for (var i = 0; i < a.length; i++) if (a[i].url === u) return a[i]; return null; }
    function due() { var t = new Date().toISOString().slice(0, 10); return Object.keys(Q.track).filter(function (u) { var e = Q.track[u]; return e.follow_up && e.follow_up <= t && (e.status === "applied" || e.status === "interview"); }); }
    function openUrl(u) { var a = h("a", { href: u, target: "_blank", rel: "noopener noreferrer" }); D.body.appendChild(a); a.click(); a.remove(); }
    function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1).replace("_", " "); }
    function btn(t, fn) { return h("button", { class: "xq-b", text: t, onclick: fn }); }

    function jobBoard(selectUrl) {
      if (selectUrl && wins.jobs) wins.jobs.close();
      var shell = h("div", { class: "xq" }), list = h("div", { class: "xq-list" }), pane = h("div", { class: "xq-pane" });
      var q = h("input", { class: "xq-in", placeholder: "Search title, employer, place...", spellcheck: "false" }), src = h("select", { class: "xq-in" }), it = h("input", { type: "checkbox" }), hide = h("input", { type: "checkbox" });
      hide.checked = true;
      var tools = h("div", { class: "xq-tools" }, [q, src, h("label", {}, [it, " IT only"]), h("label", {}, [hide, " Hide tracked"])]);
      shell.appendChild(tools); shell.appendChild(list); shell.appendChild(pane);
      var sel = selectUrl || null, count = h("span", { class: "xq-count" }); tools.appendChild(count);
      function status(u) { var e = Q.track[u]; return e ? e.status : ""; }
      function rows() {
        var t = q.value.trim().toLowerCase();
        return live().filter(function (j) {
          if (src.value && j.source !== src.value) return false;
          if (it.checked && j.it !== 1) return false;
          var s = status(j.url); if (s === "not_interested") return false; if (hide.checked && s && j.url !== sel) return false;
          return !t || (j.title + " " + j.source + " " + (j.location || "")).toLowerCase().indexOf(t) >= 0;
        });
      }
      function paint() {
        var r = rows(); list.innerHTML = ""; count.textContent = r.length + " object(s)";
        var head = h("div", { class: "xq-r hd" }, [h("span", { text: "Title" }), h("span", { text: "Employer" }), h("span", { text: "Pay" }), h("span", { text: "Status" })]); list.appendChild(head);
        r.slice(0, 250).forEach(function (j) {
          var row = h("div", { class: "xq-r" + (j.url === sel ? " sel" : ""), onclick: function () { sel = j.url; paint(); detail(); } }, [h("span", { text: j.title, title: j.title }), h("span", { text: j.source }), h("span", { text: j.pay || "" }), h("span", { text: status(j.url) ? cap(status(j.url)) : "" })]);
          list.appendChild(row);
        });
        if (r.length > 250) list.appendChild(h("div", { class: "xq-more", text: "Showing 250 of " + r.length + ". Narrow the search to see the rest." }));
        if (!r.length) list.appendChild(h("div", { class: "xq-more", text: "Nothing here. (That is either a filter or a very quiet market.)" }));
      }
      function detail() {
        pane.innerHTML = ""; var j = sel && byUrl(sel);
        if (!j) { pane.appendChild(h("div", { class: "xq-hint", text: "Select a posting to see its details." })); return; }
        var e = Q.track[j.url] || {}, msg = h("span", { class: "xq-msg" });
        var st = h("select", { class: "xq-in" }, [["", "Not tracked"]].concat(STAT.map(function (s) { return [s, cap(s)]; })).map(function (o) { return h("option", { value: o[0], text: o[1] }); }));
        st.value = STAT.indexOf(e.status) >= 0 ? e.status : "";
        var notes = h("textarea", { class: "xq-in", placeholder: "Notes", rows: "2" }), fu = h("input", { class: "xq-in", type: "date" });
        notes.value = e.notes || ""; fu.value = e.follow_up || "";
        function fail() { msg.textContent = "Could not save that."; }
        st.addEventListener("change", function () { qsave({ url: j.url, status: st.value || "none" }).then(function () { msg.textContent = "Saved."; paint(); updateTray(); }, fail); });
        var match = h("div", { class: "xq-match" });
        pane.appendChild(h("div", { class: "xq-title", text: j.title }));
        pane.appendChild(h("div", { class: "xq-meta", text: [j.source, j.location, j.pay, j.closes ? "closes " + j.closes : ""].filter(Boolean).join("  \u00B7  ") }));
        pane.appendChild(h("div", { class: "xq-act" }, [
          btn("View job post", function () { openUrl(j.url); }),
          btn("Resume match", function () {
            match.textContent = "Comparing against your resume...";
            fetch("api/match?url=" + encodeURIComponent(j.url), { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (m) {
              if (m.error || !m.terms) { match.textContent = m.error ? "Could not compare." : "Not enough text in this posting to compare."; return; }
              match.textContent = m.score + "% of the key terms are in your resume." + (m.missing && m.missing.length ? " Missing: " + m.missing.slice(0, 12).join(", ") + "." : "");
            }).catch(function () { match.textContent = "Could not compare."; });
          }),
          btn("Not interested", function () { qsave({ url: j.url, status: "not_interested" }).then(function () { sel = null; paint(); detail(); updateTray(); }, fail); }),
          st]));
        pane.appendChild(h("div", { class: "xq-act" }, [h("span", { text: "Follow up:" }), fu, btn("Save notes", function () { qsave({ url: j.url, notes: notes.value, follow_up: fu.value }).then(function () { msg.textContent = "Saved."; updateTray(); }, fail); }), msg]));
        pane.appendChild(notes); pane.appendChild(match);
      }
      [q, it, hide].forEach(function (c) { c.addEventListener("input", paint); c.addEventListener("change", paint); });
      src.addEventListener("change", paint); q.addEventListener("keydown", function (e) { e.stopPropagation(); });
      var w = win("jobs", "Job Board - Quiet Quitter", "\uD83D\uDCBC", 780, 500, shell);
      list.appendChild(h("div", { class: "xq-more", text: "Loading postings..." }));
      qload().then(function () {
        if (!Q.data) { list.innerHTML = ""; list.appendChild(h("div", { class: "xq-more", text: "Could not load jobs.json." })); return; }
        var names = {}; live().forEach(function (j) { names[j.source] = 1; });
        src.appendChild(h("option", { value: "", text: "All employers" })); Object.keys(names).sort().forEach(function (n) { src.appendChild(h("option", { value: n, text: n })); });
        paint(); detail(); updateTray();
      });
      if (selectUrl) { sel = selectUrl; }
      return w;
    }

    function trackerWin() {
      var box = h("div", { class: "xq" }), body = h("div", { class: "xq-list" });
      box.appendChild(body);
      function paint() {
        body.innerHTML = ""; var t = new Date().toISOString().slice(0, 10), any = false;
        STAT.forEach(function (s) {
          var us = Object.keys(Q.track).filter(function (u) { return Q.track[u].status === s; }); if (!us.length) return; any = true;
          body.appendChild(h("div", { class: "xq-grp", text: cap(s) + " (" + us.length + ")" }));
          us.sort(function (a, b) { return (Q.track[b].applied_at || "").localeCompare(Q.track[a].applied_at || ""); }).forEach(function (u) {
            var e = Q.track[u], j = byUrl(u), late = e.follow_up && e.follow_up <= t && (s === "applied" || s === "interview");
            body.appendChild(h("div", { class: "xq-r t", onclick: function () { jobBoard(u); } }, [h("span", { text: j ? j.title : u }), h("span", { text: j ? j.source : "(posting no longer listed)" }),
              h("span", { text: e.applied_at ? "applied " + e.applied_at.slice(0, 10) : "" }), h("span", { text: e.follow_up ? (late ? "FOLLOW UP DUE " : "follow up ") + e.follow_up : "", style: late ? "color:#c00;font-weight:700" : "" })]));
          });
        });
        if (!any) body.appendChild(h("div", { class: "xq-more", text: "Nothing tracked yet. Mark a posting in the Job Board and it shows up here." }));
      }
      var w = win("tracker", "Application Tracker", "\uD83D\uDCCB", 700, 380, box);
      qload().then(paint); return w;
    }

    function docsWin() {
      var box = h("div", { class: "xp-list" }, [h("div", { text: "Loading your documents..." })]);
      var w = win("docs", "Documents", "\uD83D\uDCC1", 520, 340, box);
      function sz(n) { return n < 1048576 ? Math.round(n / 1024) + " KB" : (n / 1048576).toFixed(1) + " MB"; }
      fetch("api/docs", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
        box.innerHTML = "";
        [["resume", "Resume"], ["cover", "Cover letter"]].forEach(function (k) {
          var f = d && d[k[0]] && d[k[0]].file;
          box.appendChild(h("div", {}, [h("span", { text: "\uD83D\uDCC4", style: "font-size:22px" }), h("span", { text: f ? k[1] + ": " + f.name + " (" + sz(f.size) + ")" : k[1] + ": none uploaded yet" }),
            f ? btn("Download", function () { location.href = "api/docs/file?name=" + k[0]; }) : null]));
        });
        box.appendChild(h("div", { text: "Upload or replace them on the real page (Esc twice, then My documents).", style: "color:#555;font-size:11px" }));
        [["\uD83D\uDCC4", "Q3_Budget_Variance_FINAL_v7.xlsx"], ["\uD83D\uDCC4", "meeting_notes_(none).txt"], ["\uD83D\uDCC4", "TPS_report_cover_sheet.doc"]].forEach(function (r) { box.appendChild(h("div", {}, [h("span", { text: r[0], style: "font-size:22px" }), h("span", { text: r[1] })])); });
      }).catch(function () { box.textContent = "Could not load your documents."; });
      return w;
    }

    function favWin() {
      var fav = h("div", { class: "xq-fav" }, [h("div", { class: "xq-grp", text: "Favorites: check manually" })]);
      var main = h("div", { style: "padding:20px;font-size:13px;line-height:1.5;flex:1", html: "<b>The page cannot be displayed</b><br><br>The page you are looking for is currently unavailable.<br><br>Pick a favorite on the left. These employers block automated checks, so they are worth a look by hand. They open in a new tab." });
      var w = win("ie", "Microsoft Edge", "\uD83C\uDF10", 640, 340, h("div", { style: "display:flex;flex:1;min-height:0" }, [fav, main]));
      qload().then(function () { ((Q.data && Q.data.manual) || []).forEach(function (m) { fav.appendChild(h("div", { class: "xq-fl", title: m.why || "", text: "\u2605 " + m.name, onclick: function () { openUrl(m.url); } })); }); });
      return w;
    }

    function taskMgr() {
      var box = h("div", { class: "xp-list" });
      function paint() {
        var n = live().length, tr = Object.keys(Q.track).length, d = due().length;
        box.innerHTML = "";
        [["System Idle Process", "94%"], ["job_hunt.exe", n + " postings"], ["tracker.exe", tr + " tracked"], ["followups.exe", d ? d + " DUE" : "all caught up"], ["pretend_busy.exe", Math.floor(Math.random() * 6 + 3) + "% CPU"], ["quiet_quit.exe", "0% effort"], ["teams.exe", "1.2 GB, doing nothing"]].forEach(function (r) {
          box.appendChild(h("div", { style: "justify-content:space-between" }, [h("span", { text: r[0] }), h("span", { text: r[1], style: "color:#555" })]));
        });
      }
      paint(); var w = win("tm", "Windows Task Manager", "\uD83D\uDCCA", 380, 260, box); qload().then(paint); return w;
    }

    function updateTray() { if (trayJobs) { var d = due().length, n = Object.keys(Q.track).filter(function (u) { return STAT.indexOf(Q.track[u].status) >= 0; }).length; trayJobs.textContent = "\uD83D\uDCBC " + (d ? d + " due" : n); trayJobs.title = d ? d + " follow-up(s) due" : n + " application(s) tracked"; } }
    var trayJobs = null;
    function qcmd(l, c, print) {
      var m = l.match(/^(jobs|find|tracker|new)\b\s*(.*)$/); if (!m) return false;
      var arg = c.replace(/^\S+\s*/, "").trim().toLowerCase();
      qload().then(function () {
        if (!Q.data) { print("Network error: the job list is not available."); return; }
        if (m[1] === "tracker") { var ks = Object.keys(Q.track); if (!ks.length) print("File Not Found"); ks.forEach(function (u) { var j = byUrl(u); print((Q.track[u].status + "          ").slice(0, 11) + (j ? j.title + " - " + j.source : u)); }); return; }
        var r = live();
        if (m[1] === "new") { var d = new Date(); d.setDate(d.getDate() - 3); var cut = d.toISOString(); r = r.filter(function (j) { return j.first_seen && j.first_seen > cut; }); }
        if (arg && m[1] !== "new") r = r.filter(function (j) { return (j.title + " " + j.source + " " + (j.location || "")).toLowerCase().indexOf(arg) >= 0; });
        print(r.length + " file(s)"); r.slice(0, 15).forEach(function (j) { print(j.title + "  <" + j.source + ">"); }); if (r.length > 15) print("... " + (r.length - 15) + " more. Use the Job Board.");
      });
      return true;
    }
    var letter = "Dear Greg,\n\nPer my last email, I wanted to touch base about something I have been quietly working up to.\n\nI regret to inform you that I have been quietly quitting for some time now. You may not have noticed. That is sort of the point.\n\nPlease find attached my unused vacation days.\n\nSincerely,\n\n(Draft 14 - DO NOT SEND)";
    var apps = {
      excel: function () { var s = buildSheet(root, { skin: "xp" }); win("excel", "Microsoft Excel - Q3_Budget_Variance_FINAL_v7.xlsx", "\u2597", 760, 430, s.el); later(s.focus, 50); },
      notepad: function () { var ta = h("textarea", { style: "flex:1;border:0;outline:none;resize:none;padding:6px;font:13px 'Lucida Console',monospace", spellcheck: "false" }); ta.value = letter; win("notepad", "resignation_letter_DRAFT_v14.txt - Notepad", "\uD83D\uDCDD", 440, 300, ta); },
      cmd: cmdWin,
      computer: function () { listWin("computer", "This PC", "\uD83D\uDDA5", [["\uD83D\uDCBF", "Local Disk (C:)   3.2 GB free of 40 GB"], ["\uD83D\uDCBE", "3\u00BD Floppy (A:)   Please insert a disk"], ["\uD83D\uDCC0", "Quiet Quitter (Q:)   100% free of motivation"], ["\uD83D\uDCC1", "Shared Documents   (access denied: try believing in yourself)"]]); },
      docs: docsWin,
      jobs: function () { jobBoard(); },
      tracker: trackerWin,
      taskmgr: taskMgr,
      bin: function () { listWin("bin", "Recycle Bin", "\uD83D\uDDD1", [["\uD83D\uDCC4", "motivation.exe"], ["\uD83D\uDCC4", "Monday_enthusiasm.dll"], ["\uD83D\uDCC4", "work_life_balance.xls"], ["\uD83D\uDCC4", "synergy_v1.ppt"]]); },
      ie: favWin,
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
    icon("\uD83D\uDDA5", "This PC", apps.computer); icon("\uD83D\uDCC1", "Documents", apps.docs); icon("\uD83C\uDF10", "Microsoft Edge", apps.ie); icon("\uD83D\uDDD1", "Recycle Bin", apps.bin);
    icon("\uD83D\uDD04", "Windows 11 Update", function () { showUpdate("w11"); }); icon("\uD83D\uDD04", "Windows 10 Update", function () { showUpdate("w10"); }); icon("\uD83C\uDF4E", "macOS Update", function () { showUpdate("mac"); }); icon("\uD83D\uDC27", "Ubuntu Update", function () { showUpdate("ubuntu"); }); icon("\uD83D\uDCBC", "Job Board", apps.jobs); icon("\uD83D\uDCCB", "Application Tracker", apps.tracker); icon("\uD83D\uDCCA", "Back to Excel", function () { setSkin("excel"); }); icon("\uD83D\uDCCA", "Q3_Budget_Variance_FINAL_v7.xlsx", apps.excel); icon("\uD83D\uDCDD", "resignation_letter_DRAFT_v14.txt", apps.notepad);
    function logOff() { dialog("Sign out", "Are you sure you want to sign out?<br><br>Your session will end and the real work will resume.", ["Sign out", "Cancel"], function (b) { if (b === 0) exit(); }); }
    function turnOff() { var off = h("div", { class: "off", html: "Shutting down...<br><br>(Press Esc twice to go back to The Quiet Quitter.)" }); root.appendChild(off); off.addEventListener("click", function () { off.remove(); }); }
    function toggleStart() {
      if (startMenu) { startMenu.remove(); startMenu = null; return; }
      function mi(g, t, fn) { return h("div", { class: "xp-mi", onclick: function () { toggleStart(); fn(); } }, [h("span", { text: g, style: "font-size:18px" }), h("span", { text: t })]); }
      startMenu = h("div", { class: "xp-menu" }, [h("div", { class: "xp-mh", text: "\uD83D\uDC64 Administrator" }), h("div", { class: "xp-mb" }, [
        h("div", { class: "xp-ml" }, [mi("\uD83D\uDCBC", "Job Board", apps.jobs), mi("\uD83D\uDCCB", "Application Tracker", apps.tracker), mi("\uD83C\uDF10", "Microsoft Edge (Favorites)", apps.ie), mi("\uD83D\uDCE7", "E-mail (Overbooked)", function () { apps.crash("Outlook"); }), mi("\uD83D\uDCCA", "Microsoft Excel", apps.excel), mi("\uD83E\uDE9F", w11 ? "Switch to Windows 10 look" : "Switch to Windows 11 look", function () { setSkin(w11 ? "w10" : "w11"); }), mi("\u21A9", "Back to the Excel spreadsheet", function () { setSkin("excel"); }), mi("\uD83D\uDCDD", "Notepad", apps.notepad),
          mi("\u2B1B", "Command Prompt", apps.cmd), mi("\uD83C\uDCCF", "Solitaire (don't)", function () { apps.crash("Solitaire"); }), mi("\uD83D\uDCA3", "Minesweeper (it's a metaphor)", function () { apps.crash("Minesweeper"); }), mi("\uD83D\uDCCA", "Task Manager", apps.taskmgr), mi("\uD83D\uDD04", "Fake update: Windows 11", function () { showUpdate("w11"); }), mi("\uD83D\uDD04", "Fake update: Windows 10", function () { showUpdate("w10"); }), mi("\uD83C\uDF4E", "Fake update: macOS", function () { showUpdate("mac"); }), mi("\uD83D\uDC27", "Fake update: Ubuntu", function () { showUpdate("ubuntu"); }), mi("\uD83C\uDFA8", "Paint", function () { apps.crash("Paint"); })]),
        h("div", { class: "xp-mr" }, [mi("\uD83D\uDCC1", "Documents", apps.docs), mi("\uD83D\uDDA5", "This PC", apps.computer), mi("\u2699", "Settings", function () { apps.crash("Settings"); }), mi("\u2753", "Get Help", function () { clip(true); })])]),
        h("div", { class: "xp-mf" }, [h("button", { text: "\uD83D\uDD11 Sign out", onclick: function () { toggleStart(); logOff(); } }), h("button", { text: "\u23FB Shut down", onclick: function () { toggleStart(); turnOff(); } })])]);
      root.appendChild(startMenu);
    }
    var clock = h("span", { text: "" }); function tick() { clock.textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); } tick(); every(tick, 15000);
    root.appendChild(desktop);
    root.appendChild(h("div", { class: "xp-task" }, [w11 ? h("div", { class: "xp-sp" }) : null, h("button", { class: "xp-start", title: "Start", onclick: toggleStart, html: w11 ? "<svg viewBox=\"0 0 20 20\"><path fill=\"#0078d4\" d=\"M0 0h9.5v9.5H0zM10.5 0H20v9.5h-9.5zM0 10.5h9.5V20H0zM10.5 10.5H20V20h-9.5z\"/></svg>" : "<svg viewBox=\"0 0 20 20\"><path fill=\"#fff\" d=\"M0 2.8L8.2 1.7v7.5H0zM9.2 1.5L20 0v9.2H9.2zM0 10.2h8.2v7.5L0 16.6zM9.2 10.2H20V20L9.2 18.5z\"/></svg>" }), tasks, h("div", { class: "xp-tray" }, [trayJobs = h("span", { text: "\uD83D\uDCBC", style: "cursor:pointer", onclick: function () { trackerWin(); } }), h("span", { text: "Esc Esc = back", title: "Press Esc twice to leave work mode", style: "opacity:.9" }), h("span", { text: "\uD83D\uDD0A" }), clock])]));
    root.addEventListener("mousedown", function (e) { if (startMenu && !e.target.closest(".xp-menu") && !e.target.closest(".xp-start")) { startMenu.remove(); startMenu = null; } });
    var tips = ["It looks like you're writing a resignation letter. Would you like help?", "It looks like you're pretending to work. Would you like help pretending harder?", "It looks like you've been in this spreadsheet for 4 minutes without typing. Impressive.", "Tip: a meeting is just an email that is out of breath."];
    var clipEl = null;
    function clip(force) {
      if (clipEl) return;
      clipEl = h("div", { class: "xp-clip" }, [h("div", { class: "bub" }, [pick(tips), h("div", {}, [h("button", { text: "Yes please", onclick: function () { clipEl.firstChild.firstChild.textContent = "Too late. You're already quiet quitting."; }}), h("button", { text: "No thanks", onclick: function () { clipEl.remove(); clipEl = null; } })])]), h("div", { class: "face", text: "\uD83D\uDCCE" })]);
      root.appendChild(clipEl); later(function () { if (clipEl) { clipEl.remove(); clipEl = null; } }, force ? 20000 : 14000);
    }
    later(function () { var b = h("div", { class: "xp-balloon", html: "<b>Tip</b><br>Press <b>Esc twice</b> to go back to The Quiet Quitter. Double-click <b>Back to Excel</b> for the spreadsheet." }); b.addEventListener("click", function () { b.remove(); }); root.appendChild(b); later(function () { b.remove(); }, 8000); }, 1200);
    later(function () { var b = h("div", { class: "xp-balloon", html: "<b>Unused vacation days</b><br>You have 14 unused vacation days. Click to ignore them." }); b.addEventListener("click", function () { b.remove(); }); root.appendChild(b); later(function () { b.remove(); }, 9000); }, 11000);
    qload().then(function () { if (!Q.data) return; updateTray(); var d = due().length, n = live().length;
      later(function () { var b = h("div", { class: "xp-balloon", style: "bottom:130px", html: "<b>Quiet Quitter</b><br>" + n + " open postings." + (d ? " <b>" + d + " follow-up(s) due.</b>" : "") + " Double-click Job Board." }); b.addEventListener("click", function () { b.remove(); trackerWin(); }); root.appendChild(b); later(function () { b.remove(); }, 9000); }, 3500); });
    later(function () { clip(false); }, 16000); every(function () { if (Math.random() < 0.35) clip(false); }, 70000);
    apps.excel();
    return root;
  }

  // ------------------------------------------------------------------ fake "installing updates" screens
  var U = { el: null, timers: [] };
  var UCSS = "#qqupd{position:fixed;inset:0;z-index:2147483000;cursor:none;user-select:none;overflow:hidden;display:flex;align-items:center;justify-content:center;text-align:center;font-family:'Segoe UI',Tahoma,Arial,sans-serif;color:#fff}" +
    "#qqupd.w11{background:#000}#qqupd.w10{background:#0a4f9c;background:radial-gradient(circle at 50% 40%,#0f6cc4,#0a4f9c 70%)}#qqupd.mac{background:#000;font-family:-apple-system,'SF Pro Text','Helvetica Neue',Helvetica,Arial,sans-serif}#qqupd.ubuntu{background:#000;font-family:Ubuntu,'Noto Sans','DejaVu Sans',Arial,sans-serif}" +
    "#qqupd .u-in{display:flex;flex-direction:column;align-items:center;gap:18px;padding:20px}#qqupd .u-t{font-size:26px;font-weight:300}#qqupd .u-s{font-size:17px;font-weight:300;line-height:1.5}#qqupd .u-s.sm{font-size:15px;opacity:.9}" +
    "#qqupd .u-sp{position:relative;width:46px;height:46px;margin-bottom:10px}#qqupd .u-sp i{position:absolute;inset:0;opacity:0;animation:uorb 2.6s infinite cubic-bezier(.35,.1,.65,.9)}#qqupd .u-sp i::before{content:'';position:absolute;top:0;left:50%;width:6px;height:6px;margin-left:-3px;background:#fff;border-radius:50%}" +
    "#qqupd .u-sp i:nth-child(2){animation-delay:.18s}#qqupd .u-sp i:nth-child(3){animation-delay:.36s}#qqupd .u-sp i:nth-child(4){animation-delay:.54s}#qqupd .u-sp i:nth-child(5){animation-delay:.72s}" +
    "@keyframes uorb{0%{transform:rotate(0);opacity:1}15%{transform:rotate(90deg);opacity:1}55%{transform:rotate(250deg);opacity:1}75%{transform:rotate(330deg);opacity:1}100%{transform:rotate(540deg);opacity:1}}" +
    "#qqupd .u-mb{width:200px;height:6px;border-radius:3px;background:#3a3a3c;overflow:hidden;margin-top:18px}#qqupd .u-mb i{display:block;height:100%;background:#fff;border-radius:3px;transition:width 1.5s linear}#qqupd .u-mt{font-size:13px;color:#a1a1a6;margin-top:2px}" +
    "#qqupd .u-ud{display:flex;gap:12px;margin-top:26px}#qqupd .u-ud i{width:9px;height:9px;border-radius:50%;background:#e95420;opacity:.25;animation:udot 1.6s infinite}#qqupd .u-ud i:nth-child(2){animation-delay:.2s}#qqupd .u-ud i:nth-child(3){animation-delay:.4s}#qqupd .u-ud i:nth-child(4){animation-delay:.6s}#qqupd .u-ud i:nth-child(5){animation-delay:.8s}@keyframes udot{0%,100%{opacity:.25}40%{opacity:1}}#qqupd .u-un{font-size:34px;font-weight:300;letter-spacing:1px;margin-top:6px}#qqupd .u-us{font-size:13px;color:#9a9a9a;margin-top:10px}";
  function stopUpdateTimers() { U.timers.forEach(function (t) { clearTimeout(t); clearInterval(t); }); U.timers = []; }
  function closeUpdate() {
    if (!U.el) return; stopUpdateTimers(); U.el.remove(); U.el = null;
    try { if (D.fullscreenElement && D.exitFullscreen) D.exitFullscreen(); } catch (e) {}
  }
  function detectOS() {
    var ua = (W.navigator.userAgentData && W.navigator.userAgentData.platform) || "", u = W.navigator.userAgent || "", pl = W.navigator.platform || "", t = (ua + " " + u + " " + pl).toLowerCase();
    if (/android/.test(t)) return "w11";
    if (/iphone|ipad|ipod|mac/.test(t)) return "mac";          // Macs and iOS
    if (/linux|x11|cros/.test(t)) return "ubuntu";
    return "w11";                                              // Windows 10 and 11 both report NT 10.0 in Firefox, so 11 it is
  }
  function showUpdate(ver) {
    if (ver === "auto" || !ver) {
      var d = detectOS(), uad = W.navigator.userAgentData;
      if (d === "w11" && uad && uad.getHighEntropyValues && /windows/i.test(uad.platform || "")) {          // Chromium can tell 10 from 11
        uad.getHighEntropyValues(["platformVersion"]).then(function (v) { showUpdate(parseInt(v.platformVersion, 10) >= 13 ? "w11" : "w10"); }, function () { showUpdate("w11"); }); return;
      }
      ver = d;
    }
    if (U.el) closeUpdate();
    if (!D.getElementById("qqupd-css")) D.head.appendChild(h("style", { id: "qqupd-css", text: UCSS }));
    var el = h("div", { id: "qqupd", class: ver }), inner = h("div", { class: "u-in" }), pct = 0, stage = 1, stages = 3, tries = 0;
    var title = h("div", { class: "u-t" }), pctEl = h("div", { class: "u-s" }), note = h("div", { class: "u-s sm" }), mtxt = null, utxt = null, mbar = null;
    function spinner() { return h("div", { class: "u-sp" }, [h("i"), h("i"), h("i"), h("i"), h("i")]); }
    if (ver === "mac") {
      inner.style.gap = "0"; inner.appendChild(h("div", { html: '<svg viewBox="0 0 100 120" width="74" height="89" fill="#fff"><path d="M52 24c-2-12 6-22 18-24 2 12-6 23-18 24z"/><path d="M50 33c-9-7-34-9-34 24 0 28 17 52 30 52 5 0 5-3 4-3s0 3 5 3c13 0 30-24 30-52 0-33-25-31-35-24z"/></svg>' })); mbar = h("i"); inner.appendChild(h("div", { class: "u-mb" }, [mbar])); inner.appendChild(h("div", { class: "u-mt" })); mtxt = inner.lastChild;
    } else if (ver === "ubuntu") {
      inner.style.gap = "0"; inner.appendChild(h("div", { html: '<svg viewBox="0 0 100 100" width="96" height="96"><circle cx="50" cy="50" r="26" fill="none" stroke="#e95420" stroke-width="9"/><g fill="#e95420" stroke="#000" stroke-width="3"><circle cx="50" cy="16" r="10"/><circle cx="20.5" cy="67" r="10"/><circle cx="79.5" cy="67" r="10"/></g></svg>' })); inner.appendChild(h("div", { class: "u-un", text: "ubuntu" })); inner.appendChild(h("div", { class: "u-ud" }, [h("i"), h("i"), h("i"), h("i"), h("i")])); inner.appendChild(h("div", { class: "u-us" })); utxt = inner.lastChild;
    } else { inner.appendChild(spinner()); inner.appendChild(title); inner.appendChild(pctEl); inner.appendChild(note); }
    el.appendChild(inner); el.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    function paint(restarting) {
      var n = ["Installing", "Configuring", "Finalizing"][stage - 1];
      if (ver === "mac") { mbar.style.width = Math.max(2, pct) + "%"; mtxt.textContent = restarting ? "Restarting..." : "Installing macOS update. About " + Math.max(1, Math.round((100 - pct) * 0.6)) + " minutes remaining..."; return; }
      if (ver === "ubuntu") { utxt.textContent = restarting ? "Restarting..." : "Installing updates... " + pct + "%  (do not power off)"; return; }
      if (restarting) { title.textContent = "Restarting"; pctEl.textContent = ""; note.textContent = ""; return; }
      title.textContent = ver === "w11" ? "Working on updates" : "Working on updates";
      pctEl.textContent = pct + "% complete";
      note.innerHTML = ver === "w11" ? "Don't turn off your computer.<br>This will take a while. Your PC will restart several times." : "Don't turn off your PC. This will take a while.<br>Your PC will restart several times. (" + stage + " of " + stages + ")";
    }
    function step() {
      if (!U.el) return;
      if (pct >= 100 || (pct >= 97 && Math.random() < 0.5)) {                           // it "finishes", restarts, then starts over from a different stage
        paint(true); U.timers.push(setTimeout(function () { if (!U.el) return; pct = Math.floor(Math.random() * 12); stage = stage % stages + 1; tries++; paint(); U.timers.push(setTimeout(step, 6000)); }, 7000 + Math.random() * 4000)); return;
      }
      if (Math.random() < 0.75) pct += 1;                                                // mostly +1, sometimes stalls
      paint(); U.timers.push(setTimeout(step, 4000 + Math.random() * 14000));
    }
    D.body.appendChild(el); U.el = el; paint(); U.timers.push(setTimeout(step, 5000));
    try { if (el.requestFullscreen) el.requestFullscreen().catch(function () {}); } catch (e) {}
  }
  function updateMenu(anchor) {
    var old = D.getElementById("qqupd-menu"); if (old) { old.remove(); return; }
    var r = anchor.getBoundingClientRect(), m = h("div", { id: "qqupd-menu", style: "position:fixed;z-index:2147482000;top:" + (r.bottom + 6) + "px;right:" + Math.max(8, W.innerWidth - r.right) + "px;background:#fff;color:#111;border:1px solid #888;border-radius:6px;box-shadow:0 4px 14px rgba(0,0,0,.3);font:13px system-ui,sans-serif;padding:4px;min-width:200px" });
    [["auto", "Match this computer (" + ({ w11: "Windows", mac: "macOS", ubuntu: "Ubuntu" }[detectOS()]) + ")"], ["w11", "Windows 11 update"], ["w10", "Windows 10 update"], ["mac", "macOS update"], ["ubuntu", "Ubuntu update"]].forEach(function (o) {
      m.appendChild(h("div", { text: "\uD83D\uDD04 " + o[1], style: "padding:7px 10px;cursor:pointer;border-radius:4px", onmouseenter: function (e) { e.target.style.background = "#e6eefc"; }, onmouseleave: function (e) { e.target.style.background = ""; }, onclick: function () { m.remove(); showUpdate(o[0]); } }));
    });
    m.appendChild(h("div", { text: "Full screen. Press Esc twice to leave.", style: "padding:5px 10px;font-size:11px;color:#666;border-top:1px solid #ddd;margin-top:3px" }));
    D.body.appendChild(m);
    setTimeout(function () { function away(e) { if (!m.contains(e.target)) { m.remove(); D.removeEventListener("mousedown", away, true); } } D.addEventListener("mousedown", away, true); }, 0);
  }

  // ------------------------------------------------------------------ switching on and off
  function build() {
    var ov = D.getElementById("qqwork"); if (ov) ov.remove();
    ov = h("div", { id: "qqwork", tabindex: "-1" }); ov.appendChild(S.skin === "excel" ? excelSkin() : winSkin(S.skin)); D.body.appendChild(ov);
    D.title = S.skin === "excel" ? "Q3_Budget_Variance_FINAL_v7.xlsx - Excel" : "This PC"; icons(S.skin === "excel" ? ICON : ICON_XP);
  }
  function icons(href) { [].forEach.call(D.querySelectorAll("link[rel~='icon'],link[rel='shortcut icon']"), function (l) { l.setAttribute("href", href); l.removeAttribute("sizes"); l.removeAttribute("type"); }); }
  function stopTimers() { S.timers.forEach(function (t) { clearTimeout(t); clearInterval(t); }); S.timers = []; }
  function setSkin(skin) { S.skin = skin; try { localStorage.setItem("qq_work_skin", skin); } catch (e) {} stopTimers(); build(); }
  function enter() {
    if (S.on) return; S.on = true;
    try { S.skin = localStorage.getItem("qq_work_skin") || "excel"; if (S.skin === "xp") S.skin = "w11"; } catch (e) { S.skin = "excel"; }
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
    if (e.key === "Escape" && !e.repeat) { var now = Date.now(); if (now - lastEsc < 450) { e.preventDefault(); if (U.el) closeUpdate(); else toggle(); lastEsc = 0; } else lastEsc = now; }
  }, true);
  W.QQWork = { update: showUpdate, updateMenu: updateMenu, toggle: toggle, enter: enter, exit: exit, skin: setSkin, on: function () { return S.on; } };
})();
