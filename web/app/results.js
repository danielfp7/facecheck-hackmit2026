// Results screen (plain script, not a module). app.js calls renderResults(r) with the /verify JSON.
// Uses two globals from app.js: $ (getElementById) and show(name). Everything else lives in this
// closure so no top-level name can collide with app.js.
//
// Layout built inside #results .resultsWrap (index.html owns the markup, this file fills it):
//   #verdict   hero: drawn check/cross, verdict, plain-English reason, "Analyzed in X s" (#timing moves here)
//   .compare   "face recognition alone" vs "FaceCheck" strip (created here, before #tiles)
//   #tiles     one evidence card per r.tiles entry, enriched by name from r.signals
//   #btnDone   kept last; app.js owns its click handler
(function () {
  "use strict";

  const PASS_MARK = 0.35;                                   // server THRESHOLDS: face similarity pass mark
  // What the screen showed, from server/challenge.py COLORS. Anything the server adds and
  // this map misses would silently draw as grey, so fall back to grey rather than to a
  // colour that is wrong: a blue flash drawn as green is worse than one drawn as unknown.
  const FLASH = {
    red: "rgb(255,80,40)", green: "rgb(0,255,0)", blue: "rgb(35,110,245)",
    white: "rgb(255,255,255)", black: "rgb(20,20,20)",
  };
  const flashFill = (name) => FLASH[name] || "rgb(140,146,158)";
  const SHAPE_SPAN = 0.75;                                  // web client: shape spans 75% of the screen height
  const TITLE = { verified: "Verified", unverified: "Not verified", unverifiable: "Couldn't verify" };
  const TONE = { verified: "ok", unverified: "bad", unverifiable: "warn" };
  const FALLBACK_REASON = { verified: "Live human, matching the profile picture.", unverified: "This check did not pass.", unverifiable: "The check couldn't be completed." };
  const STATUS = { green: "ok", yellow: "warn", red: "bad" };
  const STATUS_WORD = { ok: "Pass", warn: "Inconclusive", bad: "Fail" };
  const WIDE = new Set(["Light response", "Eye reflection"]);

  // What each check looks at, and why a face swap fails it.
  const EXPLAIN = {
    "Light response": "Skin lights up the instant the screen does. A deepfake has to see the flash, redraw the face and send it, so it arrives late.",
    "Face match": "The selfie against this account's profile picture. This is the one check a face swap is built to pass, which is why it is never enough on its own.",
    "Continuity": "The same face has to stay on camera from the selfie all the way in to the eye check. A swap that holds at arm's length falls apart when the eye fills the frame.",
    "Vibration": "The phone buzzes at random moments and the camera has to see the shake the motion sensor felt. A video fed into the phone never shakes.",
    "Heartbeat": "Skin colour pulses faintly with every heartbeat. Weak evidence on its own, so it never decides a check.",
  };

  // 24x24 outline icons, stroke 1.75 (set in CSS).
  const ICON = {
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    cross: '<path d="M6 6l12 12M18 6L6 18"/>',
    question: '<path d="M9.3 9.3a2.8 2.8 0 1 1 4 2.6c-.9.5-1.3 1.1-1.3 2v.4"/><path d="M12 17.6h.01"/>',
    "Light response": '<circle cx="12" cy="12" r="3.5"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "Eye reflection": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    "Face match": '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c0-3.9 3.4-6.5 7.5-6.5s7.5 2.6 7.5 6.5"/>',
    "Continuity": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "Vibration": '<rect x="8" y="3.5" width="8" height="17" rx="2"/><path d="M4.5 8.5v7M19.5 8.5v7M1.5 10.5v3M22.5 10.5v3"/>',
    "Heartbeat": '<path d="M12 20s-7.5-4.6-7.5-10A4 4 0 0 1 12 8a4 4 0 0 1 7.5 2c0 5.4-7.5 10-7.5 10z"/>',
    generic: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/>',
    arrow: '<path d="M4 12h15M13.5 6.5L19 12l-5.5 5.5"/>',
  };

  // ---------- small helpers ----------
  const byId = (id) => document.getElementById(id);
  const fin = (v) => (typeof v === "number" && isFinite(v) ? v : null);
  const clamp01 = (v) => Math.min(1, Math.max(0, v));
  const fix2 = (v) => (Math.abs(v) < 0.005 ? "0.00" : v.toFixed(2));       // no "-0.00"
  const lower = (s) => String(s || "").trim().replace(/^[A-Z]/, (c) => c.toLowerCase());
  const sentence = (s) => { s = String(s || "").trim(); return s ? s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".") : ""; };
  const reducedMotion = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  const cssVar = (name, el) => getComputedStyle(el || document.documentElement).getPropertyValue(name).trim();

  /** h("div", "cls", child, "text", ...) */
  function h(tag, cls, ...kids) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    for (const k of kids) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
    return e;
  }
  function svg(inner, viewBox = "0 0 24 24", cls = "") {
    const t = document.createElement("template");
    t.innerHTML = `<svg class="${cls}" viewBox="${viewBox}" aria-hidden="true" focusable="false">${inner}</svg>`;
    return t.content.firstElementChild;
  }
  const icon = (name, cls = "ico") => svg(ICON[name] || ICON.generic, "0 0 24 24", cls);

  /** Big number with a small mono unit after it. */
  function figure(value, unit, cls = "headline num") {
    const e = h("div", cls, value);
    if (unit) e.append(h("small", "", unit));
    return e;
  }

  // ---------- things that must stop when a new result renders ----------
  const live = { timers: [], rafs: [], observers: [] };
  function stopAll() {
    live.timers.forEach(clearTimeout); live.rafs.forEach(cancelAnimationFrame); live.observers.forEach((o) => o.disconnect());
    live.timers = []; live.rafs = []; live.observers = [];
  }
  const later = (fn, ms) => { const id = setTimeout(fn, ms); live.timers.push(id); return id; };
  const frame = (fn) => { const id = requestAnimationFrame(fn); live.rafs.push(id); return id; };

  // ---------- 1. verdict hero ----------
  function buildHero(v, r, verdict, tone, tiles) {
    v.className = `verdict hero in tone-${tone} ${verdict}`;
    v.style.setProperty("--d", "0ms");
    v.innerHTML = "";
    const mark = { ok: "check", bad: "cross", warn: "question" }[tone];
    const badge = svg(
      `<circle class="badgeRing" cx="24" cy="24" r="22.5" pathLength="100"/><g class="badgeMark">${ICON[mark]}</g>`,
      "0 0 48 48", "badge");
    // the mark is drawn in 24-unit space; centre it in the 48-unit badge
    badge.querySelector(".badgeMark").setAttribute("transform", "translate(12 12)");
    v.append(
      h("div", "badgeWrap", badge),
      h("div", "label heroKicker", "FaceCheck · liveness check"),
      h("h2", "heroTitle", TITLE[verdict]),
      h("p", "heroReason", sentence(r.reason) || FALLBACK_REASON[verdict]),
    );
    const timing = byId("timing") || h("p", "", "");
    timing.id = "timing";
    timing.className = "heroMeta";
    const secs = fin(r.processing_s);
    const parts = [];
    if (secs != null) parts.push(`Analyzed in ${secs.toFixed(1)} s`);
    if (tiles.length) parts.push(`${tiles.length} checks`);
    timing.textContent = parts.join("  ·  ");
    timing.hidden = !parts.length;
    v.append(timing);
  }

  // ---------- 2. face recognition alone vs FaceCheck ----------
  function gauge(value, tone) {
    const g = h("div", "gauge");
    const fill = h("div", `fill t-${tone}`);
    fill.style.width = value == null ? "0%" : `${(clamp01(value) * 100).toFixed(1)}%`;
    const tick = h("div", "tick");
    tick.style.left = `${PASS_MARK * 100}%`;
    tick.append(h("span", "", `pass mark ${PASS_MARK}`));
    g.append(h("div", "track", fill), tick);
    return g;
  }

  function buildCompare(strip, r, verdict, tone, tiles, sig) {
    const sim = fin(sig.identity && sig.identity.similarity);
    const faceTile = tiles.find((t) => t.name === "Face match");
    const facePass = sim != null ? sim >= PASS_MARK : faceTile ? (faceTile.status === "green" ? true : faceTile.status === "red" ? false : null) : null;
    const failed = tiles.filter((t) => t.status === "red").map((t) => lower(t.name));
    const unsure = tiles.filter((t) => t.status === "yellow").map((t) => lower(t.name));
    const passed = tiles.filter((t) => t.status === "green").length;
    const simText = sim != null ? fix2(sim) : "—";

    let mode = "unknown";
    if (facePass === true) mode = verdict === "verified" ? "agree-pass" : "fooled";
    else if (facePass === false) mode = "agree-fail";
    strip.className = "compare in";
    strip.dataset.mode = mode;
    strip.style.setProperty("--d", "120ms");
    strip.innerHTML = "";

    // left: what face recognition alone would have done
    const left = h("div", "cell face");
    let leftTag, leftLine;
    if (mode === "fooled") { leftTag = ["bad", "Fooled"]; leftLine = "Match · would have let them in"; }
    else if (mode === "agree-pass") { leftTag = ["ok", "Match"]; leftLine = "Would have let them in"; }
    else if (mode === "agree-fail") { leftTag = ["bad", "No match"]; leftLine = "Would have rejected"; }
    else { leftTag = ["warn", "No score"]; leftLine = sentence(faceTile && faceTile.detail) || "Nothing to compare"; }
    left.append(
      h("div", "label", "Face recognition alone"),
      figure(simText, sim != null ? "similarity" : "", "big num"),
      gauge(sim, facePass === false ? "bad" : mode === "fooled" ? "bad" : "ok"),
      h("div", "line", h("span", `tag t-${leftTag[0]}`, leftTag[1]), h("span", "lineText", leftLine)),
    );

    // right: FaceCheck
    const right = h("div", "cell facecheck");
    let rightTag;
    if (verdict === "verified") rightTag = ["ok", "Live human"];
    else if (verdict === "unverified") rightTag = ["ok", mode === "fooled" ? "Caught it" : "Rejected"];
    else rightTag = ["warn", "Held back"];
    if (verdict === "unverified" && mode !== "fooled") rightTag = ["bad", "Rejected"];
    const cap = (s) => s.replace(/^[a-z]/, (c) => c.toUpperCase());
    let rightLine;
    if (verdict === "verified") rightLine = unsure.length ? `${passed} checks passed, ${unsure.join(" and ")} inconclusive` : `All ${passed} checks passed`;
    else if (verdict === "unverified") rightLine = failed.length ? `${mode === "fooled" ? "Caught by" : "Rejected on"} ${failed.join(" and ")}` : sentence(r.reason);
    else rightLine = unsure.length ? cap(`${unsure.join(" and ")} couldn't be checked`) : sentence(r.reason);
    right.append(
      h("div", "label", "FaceCheck"),
      h("div", `big verdictWord t-${tone}`, TITLE[verdict]),
      h("div", "checkRow", ...tiles.map((t) => { const s = STATUS[t.status] || "warn"; const c = h("span", `chip t-${s}`, h("i", "dot"), t.name); c.title = `${t.name}: ${STATUS_WORD[s]}`; return c; })),
      h("div", "line", h("span", `tag t-${rightTag[0]}`, rightTag[1]), h("span", "lineText", rightLine)),
    );

    // one sentence that says what just happened
    let note;
    if (mode === "fooled") note = `Face recognition scored this face ${simText} against a ${PASS_MARK} pass mark and would have let them in. FaceCheck ${verdict === "unverified" ? "rejected it" : "held it back"}: ${lower(sentence(r.reason)) || "a liveness check did not pass."}`;
    else if (mode === "agree-pass") note = `Both agree. The selfie matches the profile picture (${simText} against a ${PASS_MARK} pass mark) and ${unsure.length ? "no liveness check failed" : "every liveness check passed"}.`;
    else if (mode === "agree-fail") note = `Face recognition would have rejected this too: ${simText} against a ${PASS_MARK} pass mark.`;
    else note = `Face recognition had nothing to score${faceTile && faceTile.detail ? ` (${lower(faceTile.detail)})` : ""}, so only the liveness checks count here.`;

    strip.append(
      left,
      h("div", "vs", h("span", "", mode === "agree-pass" || mode === "agree-fail" ? "=" : "vs")),
      right,
      h("p", "compareNote", note),
    );
  }

  // ---------- 3. evidence cards ----------
  function buildCard(t, i, r, sig) {
    const status = STATUS[t.status] || "warn";
    const card = h("article", `ev tile in s-${status}${WIDE.has(t.name) ? " wide" : ""}`);
    card.dataset.name = t.name;
    card.style.setProperty("--d", `${240 + i * 70}ms`);
    card.append(
      h("header", "evHead", icon(t.name), h("span", "label evName name", t.name),
        h("span", `state t-${status}`, h("i", "dot"), STATUS_WORD[status])),
      figure(t.headline || "—", ""),
      h("p", "why", EXPLAIN[t.name] || ""),
    );
    try {
      const enrich = ENRICH[t.name];
      if (enrich) enrich(card, t, r, sig);
    } catch (e) {
      console.warn("results: could not enrich", t.name, e);
    }
    // the server's terse numbers, unless a plain-English line above already says the same thing
    if (t.detail && !card.noReadout) card.append(h("p", "readout", t.detail));
    return card;
  }

  const ENRICH = {
    "Light response": (card, t, r, sig) => {
      const lag = sig.lag;
      if (lag && lag.ok !== false && fin(lag.lag_ms) != null && t.status !== "red") {
        card.querySelector(".headline").replaceWith(figure(String(Math.round(lag.lag_ms)), "ms lag"));
      } else if (lag && lag.ok === false && lag.reason) {
        card.append(h("p", "reasonLine", sentence(lag.reason)));
      }
      const plot = lag && lag.plot;
      if (!plot || !Array.isArray(plot.t) || !Array.isArray(plot.expected) || !Array.isArray(plot.measured) || plot.t.length < 2) return;
      const box = h("div", "chartBox");
      const canvas = h("canvas", "lagChart");
      box.append(canvas, h("div", "legend",
        h("span", "", h("i", "sw solid"), "skin, measured"),
        h("span", "", h("i", "sw dashed"), "screen, expected")));
      card.append(box);
      pending.push(() => animateChart(canvas, plot, card));
    },

    "Eye reflection": (card, t, r, sig) => {
      const c = sig.cornea || {};
      const states = Array.isArray(c.states) ? c.states.filter((s) => s && typeof s === "object") : [];
      if (!states.length) {
        const why = t.detail && t.detail.length >= String(c.reason || "").length ? t.detail : c.reason;
        card.append(h("p", "reasonLine", sentence(why) || "No eye reflection to replay."));
        card.noReadout = true;
        return;
      }
      const matched = states.filter(isMatch).length;
      card.querySelector(".headline").replaceWith(figure(`${matched} / ${states.length}`, "flashes read back from the eye"));
      card.append(buildReplay(states, c.position_axis === "x", t.status === "red"));
    },

    "Face match": (card, t, r, sig) => {
      const sim = fin(sig.identity && sig.identity.similarity);
      if (sim != null) {
        card.querySelector(".headline").replaceWith(figure(fix2(sim), `similarity · pass mark ${PASS_MARK}`));
        card.noReadout = /^needs\b/i.test(t.detail || "");        // "needs 0.35" is already in the headline
      }
      const row = h("div", "faceRow");
      if (r.capture) {
        const img = h("img", "selfieThumb");
        img.alt = "";
        img.src = `/captures/${encodeURIComponent(r.capture)}/selfie.jpg`;
        img.onerror = () => img.remove();
        row.append(img);
      }
      row.append(h("div", "faceGauge", gauge(sim, sim == null ? "warn" : sim >= PASS_MARK ? "ok" : "bad")));
      card.append(row);
    },

    "Continuity": (card, t, r, sig) => {
      const c = sig.continuity, tr = sig.transit;
      const chips = [];
      if (c && c.ok !== false && fin(c.similarity) != null) chips.push([`${c.similarity.toFixed(2)}`, "selfie vs eye check"]);
      if (tr && tr.ok !== false) {
        if (fin(tr.duration_s) != null) chips.push([`${tr.duration_s.toFixed(1)} s`, "watched, selfie to eye"]);
        if (fin(tr.cuts) != null) chips.push([String(tr.cuts), tr.cuts === 1 ? "cut in the feed" : "cuts in the feed"]);
        if (typeof tr.identity_held === "boolean" && !tr.identity_held) chips.push(["lost", "identity on the way in"]);
      }
      if (chips.length) card.append(h("div", "stats", ...chips.map(([v, l]) => h("div", "stat", h("div", "statV num", v), h("div", "statL", l)))));
      if (c && c.ok === false && (c.reason || t.detail)) {
        const why = t.detail && t.detail.length >= String(c.reason || "").length ? t.detail : c.reason;
        card.append(h("p", "reasonLine", sentence(why)));
        card.noReadout = true;
      }
    },

    "Vibration": (card, t, r, sig) => {
      const v = sig.vibration;
      if (!v) return;
      if (v.ok === false && v.reason) { card.append(h("p", "reasonLine", sentence(v.reason))); return; }
      const chips = [];
      if (fin(v.imu_detected) != null && fin(v.n_bursts) != null) chips.push([`${v.imu_detected} / ${v.n_bursts}`, "bursts the sensor felt"]);
      if (fin(v.video_detected) != null && fin(v.n_bursts) != null) chips.push([`${v.video_detected} / ${v.n_bursts}`, "bursts the camera saw"]);
      if (fin(v.motion_corr) != null) chips.push([v.motion_corr.toFixed(2), "video-gyro agreement"]);
      if (chips.length) card.append(h("div", "stats", ...chips.map(([val, l]) => h("div", "stat", h("div", "statV num", val), h("div", "statL", l)))));
    },
  };

  // ---------- eye reflection replay ----------
  const isMatch = (s) => (typeof s.match === "boolean" ? s.match : !!s.decoded_shape && s.decoded_shape === s.sent_shape);
  const SHAPES = new Set(["circle", "square", "triangle"]);
  const POS = { top: 0.25, middle: 0.5, bottom: 0.75 };
  const POS_NAME_X = { top: "left", middle: "middle", bottom: "right" };

  /** A tiny rendering of what the screen displayed for one flash. */
  function miniScreen(s, axisX) {
    const fill = flashFill(s.sent_color);
    const shape = SHAPES.has(s.sent_shape) ? s.sent_shape : "circle";
    const p = POS[s.sent_position] != null ? POS[s.sent_position] : 0.5;
    const W = axisX ? 160 : 100, H = axisX ? 100 : 160;
    const span = axisX ? SHAPE_SPAN * H : 0.6 * W, rr = span / 2;
    const cx = axisX ? W * p : W / 2, cy = axisX ? H / 2 : H * p;
    let body;
    if (shape === "circle") body = `<circle cx="${cx}" cy="${cy}" r="${rr}" fill="${fill}"/>`;
    else if (shape === "square") body = `<rect x="${cx - rr}" y="${cy - rr}" width="${span}" height="${span}" fill="${fill}"/>`;
    else { const th = (span * Math.sqrt(3)) / 2; body = `<polygon points="${cx},${cy - th / 2} ${cx - rr},${cy + th / 2} ${cx + rr},${cy + th / 2}" fill="${fill}"/>`; }
    return svg(`<rect class="screenBg" x="0.5" y="0.5" width="${W - 1}" height="${H - 1}" rx="5"/>${body}`, `0 0 ${W} ${H}`, `mini ${axisX ? "wide" : "tall"}`);
  }

  /** 12px glyph of the sent shape in its colour, for the thumbnail strip. */
  function glyph(s) {
    const fill = flashFill(s.sent_color);
    const shape = SHAPES.has(s.sent_shape) ? s.sent_shape : "circle";
    const body = shape === "circle" ? `<circle cx="6" cy="6" r="5" fill="${fill}"/>`
      : shape === "square" ? `<rect x="1" y="1" width="10" height="10" fill="${fill}"/>`
      : `<polygon points="6,1 11,10.5 1,10.5" fill="${fill}"/>`;
    return svg(body, "0 0 12 12", "glyph");
  }

  function describe(s, axisX) {
    return [s.sent_color, s.sent_shape].filter(Boolean).join(" ");
  }

  function buildReplay(states, axisX, failed) {
    const replay = h("div", "replay");
    const screens = h("div", "stack screenStack"), eyes = h("div", "stack eyeStack");
    const thumbs = h("div", "thumbs");
    thumbs.setAttribute("role", "listbox");
    thumbs.setAttribute("aria-label", "Flashes");
    const frames = states.map((s, i) => {
      const ok = isMatch(s);
      const scr = miniScreen(s, axisX);
      screens.append(scr);
      let eye;
      if (typeof s.crop_jpeg_b64 === "string" && s.crop_jpeg_b64.length > 50) {
        eye = h("img", "crop"); eye.alt = ""; eye.decoding = "async";
        eye.src = `data:image/jpeg;base64,${s.crop_jpeg_b64}`;
        eye.onerror = () => { const ph = h("div", "crop missing", "no crop"); eye.replaceWith(ph); frames[i].eye = ph; };
      } else eye = h("div", "crop missing", "no crop");
      eyes.append(eye);
      const th = h("button", `thumb ${ok ? "t-ok" : "t-bad"}`);
      th.type = "button";
      th.setAttribute("role", "option");
      th.setAttribute("aria-label", `Flash ${i + 1}: ${describe(s, axisX)}, ${ok ? "read back" : "mismatch"}`);
      const face = typeof s.crop_jpeg_b64 === "string" && s.crop_jpeg_b64.length > 50 ? h("img", "") : h("i", "noCrop");
      if (face.tagName === "IMG") { face.alt = ""; face.src = eye.src; }
      th.append(h("span", "thumbImg", face, h("i", `dot ${ok ? "t-ok" : "t-bad"}`)), glyph(s));
      th.onclick = () => { stopAuto(); select(i); };
      thumbs.append(th);
      return { s, ok, scr, eye, th };
    });

    const status = h("div", "frameStatus");
    const counter = h("span", "label counter", "");
    const what = h("span", "what", "");
    const mark = h("span", "readMark", "");
    status.append(counter, what, mark);

    const feature = h("div", "feature",
      h("figure", "shot", screens, h("figcaption", "label", "Screen showed")),
      icon("arrow", "ico arrow"),
      h("figure", "shot", eyes, h("figcaption", "label", "Eye reflected")),
    );
    const progress = h("div", "progress");
    const bar = h("i", "");
    progress.append(bar);
    replay.append(feature, status, thumbs, progress);

    let cur = -1, auto = null;
    function select(i) {
      if (i === cur) return;
      cur = i;
      frames.forEach((f, k) => {
        f.scr.classList.toggle("on", k === i);
        f.eye.classList.toggle("on", k === i);
        f.th.classList.toggle("on", k === i);
        f.th.setAttribute("aria-selected", k === i ? "true" : "false");
      });
      const f = frames[i];
      counter.textContent = `Flash ${i + 1} of ${frames.length}`;
      what.textContent = describe(f.s, axisX);
      mark.className = `readMark ${f.ok ? "t-ok" : "t-bad"}`;
      mark.innerHTML = "";
      let readAs = "";
      if (!f.ok) {
        const dp = f.s.decoded_position && f.s.decoded_position !== f.s.sent_position
          ? (axisX ? POS_NAME_X[f.s.decoded_position] || f.s.decoded_position : f.s.decoded_position) : "";
        const ds = f.s.decoded_shape && f.s.decoded_shape !== "?" && f.s.decoded_shape !== f.s.sent_shape ? f.s.decoded_shape : "";
        const parts = [ds, dp].filter(Boolean);
        readAs = parts.length ? ` · eye showed ${parts.join(", ")}` : "";
      }
      mark.append(icon(f.ok ? "check" : "cross", "ico"), f.ok ? "read back" : `mismatch${readAs}`);
      bar.style.width = `${((i + 1) / frames.length) * 100}%`;
    }
    function stopAuto() { if (auto) { clearTimeout(auto); auto = null; } replay.classList.remove("playing"); }

    // After playing through, rest on the first mismatch when the check failed, else on the last flash.
    const restAt = () => { const k = failed ? frames.findIndex((f) => !f.ok) : -1; return k >= 0 ? k : frames.length - 1; };
    replay.play = () => {
      if (reducedMotion() || frames.length < 2) { select(restAt()); return; }
      replay.classList.add("playing");
      let i = 0;
      select(0);
      const step = () => {
        i += 1;
        if (i < frames.length) { select(i); auto = later(step, 560); }
        else { auto = later(() => { stopAuto(); select(restAt()); }, 700); }
      };
      auto = later(step, 700);
    };
    select(0);
    pending.push(() => replay.play());
    return replay;
  }

  // ---------- light response chart ----------
  function animateChart(canvas, plot, card) {
    const colors = { r: cssVar("--bad", card) || "#ff5d5d", g: cssVar("--ok", card) || "#35d49a", grid: cssVar("--line", card) || "#232936", text: cssVar("--text-3", card) || "#5f6878" };
    let progress = 1;
    const draw = () => drawChart(canvas, plot, colors, progress);
    if (reducedMotion()) { draw(); }
    else {
      const t0 = performance.now(), dur = 1200;
      const tick = (now) => {
        const x = Math.min(1, (now - t0) / dur);
        progress = 1 - Math.pow(1 - x, 3);
        draw();
        if (x < 1) frame(tick);
      };
      progress = 0;
      frame(tick);
    }
    if ("ResizeObserver" in window) {
      const ro = new ResizeObserver(() => draw());
      ro.observe(canvas);
      live.observers.push(ro);
    }
  }

  function drawChart(canvas, plot, colors, progress) {
    const dpr = Math.min(2, devicePixelRatio || 1);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const t = plot.t, n = Math.min(t.length, plot.expected.length, plot.measured.length);
    const t0 = fin(t[0]) || 0, t1 = fin(t[n - 1]) || t0 + 1;
    const padL = 18, padR = 4, padT = 4, padB = 14, gap = 10;
    const paneH = (h - padT - padB - gap) / 2;
    const plotW = w - padL - padR;
    const X = (i) => padL + ((t[i] - t0) / (t1 - t0 || 1)) * plotW;
    g.font = `500 10px ${cssVar("--mono") || "ui-monospace, monospace"}`;
    g.textBaseline = "middle";

    // seconds grid
    g.strokeStyle = colors.grid; g.lineWidth = 1;
    for (let s = Math.ceil(t0); s <= t1; s += 1) {
      const x = Math.round(padL + ((s - t0) / (t1 - t0 || 1)) * plotW) + 0.5;
      g.beginPath(); g.moveTo(x, padT); g.lineTo(x, h - padB); g.stroke();
      g.fillStyle = colors.text; g.textAlign = "center";
      g.fillText(`${s} s`, x, h - padB / 2 + 1);
    }

    [{ ch: 0, label: "R", color: colors.r }, { ch: 1, label: "G", color: colors.g }].forEach((p, k) => {
      const top = padT + k * (paneH + gap);
      const ev = [], mv = [];
      for (let i = 0; i < n; i++) { ev.push(fin(plot.expected[i] && plot.expected[i][p.ch])); mv.push(fin(plot.measured[i] && plot.measured[i][p.ch])); }
      const vals = ev.concat(mv).filter((v) => v != null);
      if (!vals.length) return;
      let lo = Math.min(...vals), hi = Math.max(...vals);
      if (hi - lo < 1e-6) { lo -= 0.01; hi += 0.01; }
      const pad = (hi - lo) * 0.12;
      const Y = (v) => top + paneH - ((v - lo + pad) / (hi - lo + 2 * pad)) * paneH;
      // pane baseline + label
      g.strokeStyle = colors.grid; g.beginPath(); g.moveTo(padL, top + paneH + 0.5); g.lineTo(w - padR, top + paneH + 0.5); g.stroke();
      g.fillStyle = p.color; g.textAlign = "left"; g.fillText(p.label, 2, top + paneH / 2);
      // series, clipped to the draw head
      g.save();
      g.beginPath(); g.rect(0, 0, padL + plotW * progress + 1, h); g.clip();
      const line = (ys, dashed) => {
        g.beginPath();
        g.setLineDash(dashed ? [3, 3] : []);
        g.lineWidth = dashed ? 1 : 1.6;
        g.strokeStyle = p.color;
        g.globalAlpha = dashed ? 0.5 : 1;
        let pen = false;
        for (let i = 0; i < n; i++) {
          if (ys[i] == null) { pen = false; continue; }
          const x = X(i), y = Y(ys[i]);
          pen ? g.lineTo(x, y) : g.moveTo(x, y);
          pen = true;
        }
        g.stroke();
        g.globalAlpha = 1; g.setLineDash([]);
      };
      line(ev, true);
      line(mv, false);
      g.restore();
    });

    if (progress < 1) {
      const x = Math.round(padL + plotW * progress) + 0.5;
      g.strokeStyle = colors.text; g.lineWidth = 1;
      g.beginPath(); g.moveTo(x, padT); g.lineTo(x, h - padB); g.stroke();
    }
  }

  // ---------- render ----------
  let pending = [];

  function render(r) {
    stopAll();
    pending = [];
    r = r && typeof r === "object" ? r : {};
    const verdict = TITLE[r.verdict] ? r.verdict : "unverifiable";
    const tone = TONE[verdict];
    const tiles = (Array.isArray(r.tiles) ? r.tiles : []).filter((t) => t && typeof t === "object").map((t) => ({ ...t, name: String(t.name || "Check") }));
    const sig = r.signals && typeof r.signals === "object" ? r.signals : {};

    const section = byId("results");
    const wrap = (section && section.querySelector(".resultsWrap")) || section;
    const v = byId("verdict");
    const grid = byId("tiles");
    if (!wrap || !v || !grid) { console.error("results: #results markup is missing"); return; }
    section.className = `screen tone-${tone}`;

    buildHero(v, r, verdict, tone, tiles);

    let strip = wrap.querySelector(".compare");
    if (!strip) { strip = h("section", "compare"); grid.before(strip); }
    buildCompare(strip, r, verdict, tone, tiles, sig);

    grid.className = "tiles";
    grid.innerHTML = "";
    tiles.forEach((t, i) => grid.append(buildCard(t, i, r, sig)));
    if (!tiles.length) grid.append(h("article", "ev tile in wide s-warn", h("p", "why", "No individual checks were reported for this result.")));

    const done = byId("btnDone");
    if (done) { done.classList.add("in"); done.style.setProperty("--d", `${240 + tiles.length * 70 + 80}ms`); wrap.append(done); }

    // Every check ever run, genuine and attack, in one place.
    let log = byId("attackLogLink");
    if (!log) {
      log = h("a", "attackLog", "See every attack we threw at it \u2192");
      log.id = "attackLogLink";
      log.href = "attacks.html";
    }
    log.style.setProperty("--d", `${240 + tiles.length * 70 + 160}ms`);
    log.classList.add("in");
    wrap.append(log);

    if (typeof show === "function") show("results"); else section.hidden = false;
    // visuals need layout (canvas size), so they start once the screen is showing
    frame(() => { for (const fn of pending) { try { fn(); } catch (e) { console.warn("results: visual failed", e); } } pending = []; });
  }

  window.renderResults = function renderResults(r) {
    try { render(r); }
    catch (e) {
      console.error("results: render failed", e);
      // never leave the user on the spinner
      const v = byId("verdict");
      if (v) { v.className = "verdict hero in tone-warn unverifiable"; v.innerHTML = ""; v.append(h("h2", "heroTitle", TITLE[r && TITLE[r.verdict] ? r.verdict : "unverifiable"]), h("p", "heroReason", sentence(r && r.reason) || "")); }
      if (typeof show === "function") show("results");
    }
  };
})();
