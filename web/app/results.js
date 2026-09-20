// Results screen (plain script, not a module). app.js calls renderResults(r) with the /verify response.
// Reads the globals $, show and reset from app.js (loaded first). Exposes renderResults and lineChart.
// Everything else lives inside this closure so it can never collide with app.js's top-level names.
//
// The four elements index.html puts inside .resultsWrap (#verdict, #tiles, #timing, #btnDone) are
// kept and reused, so app.js's bindings on them (Done -> reset) survive every render.
(function () {
  "use strict";

  const PASS_MARK = 0.35;                                  // server: THRESHOLDS.face_similarity_min
  const SENT_RGB = { red: "rgb(255,80,40)", green: "rgb(0,255,0)" };   // server: challenge.COLORS
  const TRACE = ["#ff6a45", "#4ade80"];                    // chart colours for the red and green channels
  const MONO = 'ui-monospace, "SF Mono", Menlo, monospace';
  const STATUS = { green: "ok", yellow: "warn", red: "bad" };
  const SHOWN_ELSEWHERE = ["Light response", "Eye reflection", "Face match"];

  const byId = (id) => document.getElementById(id);
  const fin = (v) => (typeof v === "number" && isFinite(v) ? v : null);
  const clamp01 = (v) => Math.min(1, Math.max(0, v));
  const reducedMotion = () => !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fix2 = (v) => (Math.abs(v) < 0.005 ? "0.00" : v.toFixed(2));
  const sentence = (s) => { s = String(s || "").trim(); return s ? s[0].toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".") : ""; };

  // ---------- copy: server reason -> plain English ----------
  // [substring of the server's reason, full sentence, short label]. First match wins, so the more
  // specific keys come first.
  const COPY = [
    ["live human, matching", "A live person, and the same person who enrolled.", "Live, and the enrolled person"],
    ["flat screen or print", "The reflection is far too large for a human eye. This is a flat screen or a print.", "Reflection too large for an eye"],
    ["reflection is far too large", "The reflection is far too large for a human eye. This is a flat screen or a print.", "Reflection too large for an eye"],
    ["not inside an iris", "The reflection isn't inside an iris, so it isn't coming from an eye.", "Reflection isn't inside an iris"],
    ["no iris around it", "Something reflected the screen, but there was no iris around it. On a real eye the reflection sits inside the iris.", "No iris around the reflection"],
    ["missing in too many flashes", "The reflection in the eye went missing during too many flashes. Keep the eye open and still.", "Reflection missing in too many flashes"],
    ["too few usable states", "Too few flashes could be read from the eye.", "Too few flashes could be read"],
    ["no eye reflection found", "No reflection of the screen was found in the eye. A real cornea mirrors the screen in front of it; a generated face doesn't.", "No reflection found in the eye"],
    ["eye reflection does not match", "The reflection in the eye didn't move with the shapes on screen.", "Reflection didn't follow the screen"],
    ["no light response", "The face didn't change colour with the screen's flashes, so this video isn't of someone sitting in front of this screen.", "Skin didn't follow the screen's light"],
    ["response delayed", "The face reacted to the flashes too late. That delay is the time a computer needs to draw a fake face.", "Skin reacted too late"],
    ["delayed by", "The face reacted to the flashes too late. That delay is the time a computer needs to draw a fake face.", "Skin reacted too late"],
    ["not the person in the selfie", "The face that took the selfie isn't the face that did the eye check.", "Different face in the eye check"],
    ["a different face appeared", "A different face appeared between the selfie and the eye check.", "A different face appeared"],
    ["camera view jumped", "The camera view jumped between the selfie and the eye check, so it wasn't one continuous move.", "Camera view jumped"],
    ["frames are missing", "The camera feed was interrupted between the selfie and the eye check, so it wasn't one continuous sitting.", "Camera feed was interrupted"],
    ["camera was interrupted", "The app was left, or the camera was interrupted, between the selfie and the eye check.", "The sitting was interrupted"],
    ["too long between", "Too much time passed between the selfie and the eye check.", "Too long after the selfie"],
    ["selfie does not match", "The selfie doesn't match the enrolled face.", "Selfie doesn't match the enrolled face"],
    ["no selfie uploaded", "No selfie came with this check, so there was no face to compare with the enrolled one.", "No selfie to compare"],
    ["no face found in the selfie", "No face was found in the selfie.", "No face in the selfie"],
    ["not enrolled", "This user hasn't enrolled a face yet.", "User isn't enrolled"],
    ["ambient light", "The room is too bright for the screen's light to show on the face. Try somewhere dimmer.", "Room too bright"],
    ["too few frames", "The camera didn't deliver enough frames during the flashes.", "Too few camera frames"],
    ["dropped camera frames", "Too many camera frames were dropped during the check.", "Too many dropped frames"],
    ["no eye was found", "No eye was found, so the selfie couldn't be compared with the eye check.", "No eye to compare with the selfie"],
    ["no face was visible right after", "No face was visible right after the selfie, so the move to the eye couldn't be followed.", "Move to the eye wasn't visible"],
    ["too fast to follow", "The move to the eye was too fast to follow. Bring the camera in steadily.", "Move to the eye was too fast"],
    ["was not recorded", "The move from the selfie to the eye wasn't recorded.", "Move to the eye wasn't recorded"],
    ["could not be measured", "The face's response to the screen's light couldn't be measured.", "Light response not measured"],
    ["no motion sensor", "The phone didn't record any motion sensor data.", "No motion sensor data"],
    ["denied", "The sign-in request was denied.", "Request denied"],
  ];
  function lookup(reason) {
    const s = String(reason || "").toLowerCase();
    for (const row of COPY) if (s.includes(row[0])) return row;
    return null;
  }
  const friendly = (reason) => { const row = lookup(reason); return row ? row[1] : sentence(reason); };
  const friendlyShort = (reason) => { const row = lookup(reason); return row ? row[2] : sentence(reason).replace(/\.$/, ""); };

  const TILE_BLURB = {
    "Continuity": "The selfie and the eye check have to be the same person, in one uninterrupted sitting.",
    "Heartbeat": "A pulse read from tiny colour changes in the skin. Supporting evidence only.",
    "Vibration": "The phone buzzes during the check. A real camera shakes with it; an injected video doesn't.",
  };

  // ---------- small SVG pieces ----------

  const ICON = {
    ok: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5 6.5 11.5 12.5 4.8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    bad: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.2 4.2 11.8 11.8M11.8 4.2 4.2 11.8" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    warn: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.6v5.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="8" cy="11.9" r="1.15" fill="currentColor"/></svg>',
  };

  /** The big animated verdict mark: a gauge ring that draws itself, then the glyph. */
  function markSvg(kind) {
    const glyph = {
      ok: '<path class="mk-glyph" pathLength="100" d="M31 49.5 43 61.5 66 36"/>',
      bad: '<path class="mk-glyph" pathLength="100" d="M35.5 35.5 60.5 60.5"/><path class="mk-glyph mk-late" pathLength="100" d="M60.5 35.5 35.5 60.5"/>',
      warn: '<path class="mk-glyph" pathLength="100" d="M38.5 39.5a9.5 9.5 0 1 1 14.6 8c-3.4 2.2-5.1 4.2-5.1 8.5"/><circle class="mk-dot" cx="48" cy="66" r="2.9"/>',
    }[kind];
    return `<svg class="mark" viewBox="0 0 96 96" aria-hidden="true">
      <circle class="mk-ticks" cx="48" cy="48" r="45.5"/>
      <circle class="mk-disc" cx="48" cy="48" r="39"/>
      <circle class="mk-ring" pathLength="100" cx="48" cy="48" r="39" transform="rotate(-90 48 48)"/>
      ${glyph}</svg>`;
  }

  /** A tiny picture of the screen during one flash: the sent shape, in the sent colour, where it was shown. */
  function screenGlyph(shape, color, position, axis) {
    const fill = SENT_RGB[color] || "#8b96a8";
    const slot = { top: 0, middle: 1, bottom: 2 }[position];
    const wide = axis === "x";
    const W = wide ? 40 : 22, H = wide ? 24 : 38, s = 5.2;
    const cx = wide ? (slot == null ? W / 2 : 9 + slot * 11) : W / 2;
    const cy = wide ? H / 2 : (slot == null ? H / 2 : 9 + slot * 10);
    let mark;
    if (shape === "circle") mark = `<circle cx="${cx}" cy="${cy}" r="${s}" fill="${fill}"/>`;
    else if (shape === "square") mark = `<rect x="${cx - s}" y="${cy - s}" width="${2 * s}" height="${2 * s}" rx=".6" fill="${fill}"/>`;
    else if (shape === "triangle") mark = `<polygon points="${cx},${cy - s} ${cx - s * 1.1},${cy + s * 0.85} ${cx + s * 1.1},${cy + s * 0.85}" fill="${fill}"/>`;
    else mark = `<circle cx="${cx}" cy="${cy}" r="2" fill="${fill}"/>`;
    return `<svg class="screenGlyph" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true">
      <rect x=".5" y=".5" width="${W - 1}" height="${H - 1}" rx="3.5" fill="#05070a" stroke="#2c3544"/>${mark}</svg>`;
  }

  function sparkline(values) {
    const v = (values || []).filter((q) => fin(q) != null);
    if (v.length < 8) return "";
    const step = Math.max(1, Math.floor(v.length / 90)), pts = [];
    let lo = Infinity, hi = -Infinity;
    for (const q of v) { if (q < lo) lo = q; if (q > hi) hi = q; }
    for (let i = 0; i < v.length; i += step) {
      pts.push(`${((i / (v.length - 1)) * 120).toFixed(1)},${(25 - ((v[i] - lo) / (hi - lo || 1)) * 22).toFixed(1)}`);
    }
    return `<svg class="spark" viewBox="0 0 120 28" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts.join(" ")}" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
  }

  // ---------- the chart ----------

  /**
   * Draws series onto a canvas, clipped to the first `progress` (0..1) of the time axis.
   * series: [{ x[], y[], color, lo?, hi?, dash?, width?, alpha?, lane?, label?, glow?, head? }]
   * Series with different `lane` numbers are stacked like oscilloscope channels.
   */
  function lineChart(canvas, series, progress) {
    if (!canvas || !Array.isArray(series) || !series.length) return;
    const p = progress == null ? 1 : clamp01(progress);
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 320, h = canvas.clientHeight || 120;
    const W = Math.round(w * dpr), H = Math.round(h * dpr);
    if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);

    let x0 = Infinity, x1 = -Infinity, lanes = 1;
    for (const s of series) {
      if (!s.x || !s.x.length) continue;
      x0 = Math.min(x0, s.x[0]); x1 = Math.max(x1, s.x[s.x.length - 1]);
      lanes = Math.max(lanes, (s.lane || 0) + 1);
    }
    if (!isFinite(x0) || !isFinite(x1)) return;
    const padL = 26, padR = 8, padT = 8, padB = 22, gap = 14;
    const plotW = Math.max(10, w - padL - padR), laneH = (h - padT - padB - gap * (lanes - 1)) / lanes;
    const laneTop = (i) => padT + i * (laneH + gap);
    const X = (t) => padL + ((t - x0) / (x1 - x0 || 1)) * plotW;

    // Grid: one hairline per second, a frame per lane, channel letters on the left.
    g.font = `10px ${MONO}`;
    g.textBaseline = "alphabetic";
    g.lineWidth = 1;
    for (let sec = Math.ceil(x0 - 0.2); sec <= x1 + 1e-6; sec++) {
      const px = Math.round(X(Math.max(sec, x0))) + 0.5;
      g.strokeStyle = "rgba(255,255,255,.045)";
      g.beginPath(); g.moveTo(px, padT); g.lineTo(px, h - padB + 4); g.stroke();
      g.fillStyle = "rgba(139,150,168,.85)";
      g.textAlign = sec <= x0 + 0.2 ? "left" : "center";
      g.fillText(`${sec}s`, sec <= x0 + 0.2 ? px - 1 : px, h - 5);
    }
    for (let i = 0; i < lanes; i++) {
      g.strokeStyle = "rgba(255,255,255,.07)";
      g.beginPath(); g.moveTo(padL, Math.round(laneTop(i) + laneH) + 0.5); g.lineTo(w - padR, Math.round(laneTop(i) + laneH) + 0.5); g.stroke();
    }
    g.textAlign = "left";
    for (const s of series) {
      if (!s.label) continue;
      g.fillStyle = s.color;
      g.fillText(s.label, 4, laneTop(s.lane || 0) + laneH / 2 + 3.5);
    }

    const geometry = (s) => {
      const ys = s.y.filter((q) => fin(q) != null);
      const lo = s.lo != null ? s.lo : Math.min.apply(null, ys), hi = s.hi != null ? s.hi : Math.max.apply(null, ys);
      const top = laneTop(s.lane || 0) + 5, inner = laneH - 10, span = hi - lo;
      return (y) => (span > 1e-9 ? top + inner - ((y - lo) / span) * inner : top + inner / 2);
    };

    const cutT = x0 + (x1 - x0) * p;
    g.save();
    g.beginPath(); g.rect(0, 0, X(cutT) + 0.5, h); g.clip();
    g.lineJoin = "round"; g.lineCap = "round";
    for (const s of series) {
      if (!s.x || s.x.length < 2) continue;
      const Y = geometry(s);
      g.beginPath();
      g.setLineDash(s.dash || []);
      g.lineWidth = s.width || 2;
      g.strokeStyle = s.color;
      g.globalAlpha = s.alpha == null ? 1 : s.alpha;
      g.shadowColor = s.glow ? s.color : "transparent";
      g.shadowBlur = s.glow ? 7 : 0;
      let pen = false;
      for (let i = 0; i < s.x.length; i++) {
        if (fin(s.y[i]) == null) { pen = false; continue; }
        const px = X(s.x[i]), py = Y(s.y[i]);
        pen ? g.lineTo(px, py) : g.moveTo(px, py);
        pen = true;
      }
      g.stroke();
    }
    g.restore();
    g.setLineDash([]);

    // The sweep: a faint cursor line and a bright dot riding each measured trace.
    if (p > 0 && p < 1) {
      const cx = X(cutT);
      g.strokeStyle = "rgba(255,255,255,.16)";
      g.lineWidth = 1;
      g.beginPath(); g.moveTo(cx, padT); g.lineTo(cx, h - padB); g.stroke();
      for (const s of series) {
        if (!s.head || !s.x || s.x.length < 2) continue;
        let i = 1;
        while (i < s.x.length - 1 && s.x[i] < cutT) i++;
        const a = fin(s.y[i - 1]), b = fin(s.y[i]);
        if (a == null || b == null) continue;
        const k = clamp01((cutT - s.x[i - 1]) / (s.x[i] - s.x[i - 1] || 1));
        g.fillStyle = s.color; g.shadowColor = s.color; g.shadowBlur = 12;
        g.beginPath(); g.arc(cx, geometry(s)(a + (b - a) * k), 3, 0, Math.PI * 2); g.fill();
        g.shadowBlur = 0;
      }
    }
  }

  /** r.signals.lag.plot -> dashed "sent" and solid "measured" traces for the red and green channels. */
  function lagSeries(plot) {
    if (!plot || !Array.isArray(plot.t) || !Array.isArray(plot.expected) || !Array.isArray(plot.measured)) return null;
    const n = Math.min(plot.t.length, plot.expected.length, plot.measured.length);
    if (n < 2) return null;
    const t = plot.t.slice(0, n), out = [];
    [0, 1].forEach((ch) => {
      const sent = [], seen = [];
      let lo = Infinity, hi = -Infinity;
      for (let i = 0; i < n; i++) {
        const a = fin(plot.expected[i] && plot.expected[i][ch]), b = fin(plot.measured[i] && plot.measured[i][ch]);
        sent.push(a); seen.push(b);
        for (const q of [a, b]) if (q != null) { if (q < lo) lo = q; if (q > hi) hi = q; }
      }
      if (!isFinite(lo)) return;
      out.push({ x: t, y: sent, lo, hi, color: TRACE[ch], dash: [5, 4], width: 1.25, alpha: 0.75, lane: ch, label: ch ? "G" : "R" });
      out.push({ x: t, y: seen, lo, hi, color: TRACE[ch], width: 2, lane: ch, glow: true, head: true });
    });
    return out.length ? out : null;
  }

  let liveChart = null;                         // { canvas, series, done } for redraws on resize
  function sweepChart(canvas, series, delayMs) {
    liveChart = { canvas, series, done: false };
    const mine = liveChart;
    if (reducedMotion()) { mine.done = true; lineChart(canvas, series, 1); return; }
    const DURATION = 1700, ease = (k) => 1 - Math.pow(1 - k, 2.2);
    lineChart(canvas, series, 0);
    setTimeout(() => {
      const t0 = performance.now();
      const frame = (now) => {
        if (liveChart !== mine || !canvas.isConnected) return;
        const k = clamp01((now - t0) / DURATION);
        lineChart(canvas, series, ease(k));
        if (k < 1) requestAnimationFrame(frame); else mine.done = true;
      };
      requestAnimationFrame(frame);
    }, delayMs);
  }
  window.addEventListener("resize", () => {
    if (liveChart && liveChart.done && liveChart.canvas.isConnected) lineChart(liveChart.canvas, liveChart.series, 1);
  });

  // ---------- sections ----------

  const VERDICT = {
    verified: { kind: "ok", title: "Live human verified", word: "Verified" },
    unverified: { kind: "bad", title: "Not a live human", word: "Rejected" },
    unverifiable: { kind: "warn", title: "Couldn't verify", word: "Couldn't verify" },
  };

  function heroHtml(r, V) {
    const secs = fin(r.processing_s);
    const raw = String(r.reason || "").trim();
    const plain = friendly(raw) || (V.kind === "ok" ? COPY[0][1] : "");
    return `
      <div class="heroGlow" aria-hidden="true"></div>
      ${markSvg(V.kind)}
      <h2 class="heroTitle">${esc(V.title)}</h2>
      <p class="heroWhy">${esc(plain)}</p>
      <div class="heroMeta">
        ${secs != null ? `<span class="chip num">checked in ${secs.toFixed(1)} s</span>` : ""}
        ${raw && raw !== plain ? `<span class="tech"><span class="techKey">technical detail</span> <span class="num">${esc(raw)}</span></span>` : ""}
      </div>`;
  }

  function punchlineHtml(r, V, tiles) {
    const faceTile = tiles.find((t) => t.name === "Face match");
    let sim = fin(r.signals && r.signals.identity && r.signals.identity.similarity);
    if (sim == null && faceTile && /^-?\d*\.?\d+$/.test(String(faceTile.headline || "").trim())) sim = parseFloat(faceTile.headline);
    const approves = sim != null && sim >= PASS_MARK;
    const noFace = (r.signals && r.signals.identity && r.signals.identity.reason) || (faceTile && faceTile.detail) || "no face found in the selfie";

    const selfie = r.capture ? `<img class="selfie" alt="The selfie from this check" src="/captures/${encodeURIComponent(r.capture)}/selfie.jpg">` : "";
    const face = sim != null ? `
        <div class="cellMain">${selfie}
          <div><div class="big num">${fix2(sim)}</div><div class="unit">similarity to the enrolled face</div></div>
        </div>
        <div class="meter">
          <div class="bar"><i class="fill" style="width:${(clamp01(sim) * 100).toFixed(1)}%"></i><i class="tick" style="left:${PASS_MARK * 100}%"></i></div>
          <div class="scale num"><span>0</span><span class="pass" style="left:${PASS_MARK * 100}%">${PASS_MARK} pass mark</span><span>1</span></div>
        </div>
        <div class="say ${approves ? "ok" : "bad"}">${ICON[approves ? "ok" : "bad"]}<span>${approves ? "would approve" : "would reject"}</span></div>` : `
        <div class="cellMain">${selfie}
          <div><div class="big num dim">n/a</div><div class="unit">${esc(sentence(noFace).replace(/\.$/, ""))}</div></div>
        </div>
        <div class="meter">
          <div class="bar"><i class="tick" style="left:${PASS_MARK * 100}%"></i></div>
          <div class="scale num"><span>0</span><span class="pass" style="left:${PASS_MARK * 100}%">${PASS_MARK} pass mark</span><span>1</span></div>
        </div>
        <div class="say warn">${ICON.warn}<span>nothing to compare</span></div>`;

    const lights = tiles.filter((t) => t.name).map((t) =>
      `<span class="sig ${STATUS[t.status] || "warn"}"><i></i>${esc(t.name)}</span>`).join("");
    const why = V.kind === "ok" ? "Live, and the enrolled person" : friendlyShort(r.reason);

    let strip = "";
    if (V.kind === "ok") strip = `<div class="strip ok">${ICON.ok}<span>Both agree: this is the enrolled person, and they are live.</span></div>`;
    else if (approves && V.kind === "bad") strip = `<div class="strip bad">${ICON.warn}<span>Face recognition was fooled. InHuman caught it.</span></div>`;
    else if (approves) strip = `<div class="strip warn">${ICON.warn}<span>Face recognition would approve. InHuman won't until it sees proof of a live person.</span></div>`;
    else if (sim != null) strip = `<div class="strip flat"><span>Both reject: the selfie doesn't match the enrolled face.</span></div>`;

    return `
      <div class="versus">
        <div class="cell">
          <div class="eyebrow">Face recognition alone</div>
          ${face}
        </div>
        <div class="vs" aria-hidden="true"><span>vs</span></div>
        <div class="cell ours st-${V.kind}">
          <div class="eyebrow">InHuman</div>
          <div class="oursWord"><span class="badge">${ICON[V.kind]}</span>${esc(V.word)}</div>
          <div class="oursWhy">${esc(why)}</div>
          ${lights ? `<div class="sigs">${lights}</div>` : ""}
        </div>
      </div>${strip}`;
  }

  function stateMatched(s) {
    if (typeof s.match === "boolean") return s.match;
    if (s.decoded_shape && s.decoded_shape !== "?" && s.sent_shape) return s.decoded_shape === s.sent_shape;
    return null;
  }

  function eyeHtml(r, tiles) {
    const tile = tiles.find((t) => t.name === "Eye reflection");
    const cornea = (r.signals && r.signals.cornea) || null;
    if (!tile && !cornea) return "";
    const states = cornea && Array.isArray(cornea.states) ? cornea.states.filter((s) => s && s.crop_jpeg_b64) : [];
    const axis = cornea && cornea.position_axis === "x" ? "x" : "y";
    const where = axis === "x" ? { top: "left", middle: "middle", bottom: "right" } : { top: "top", middle: "middle", bottom: "bottom" };
    const st = tile ? STATUS[tile.status] || "warn" : cornea && cornea.ok ? "ok" : "warn";

    let body;
    if (states.length) {
      const good = states.filter((s) => stateMatched(s) === true).length;
      const film = states.map((s, i) => {
        const m = stateMatched(s), cls = m === true ? "ok" : m === false ? "bad" : "unk";
        const label = `${s.sent_color || ""} ${s.sent_shape || "shape"}, ${where[s.sent_position] || s.sent_position || ""}`.trim();
        return `<figure class="crop ${cls}" style="--j:${i}" title="${esc(`Screen showed a ${label}`)}">
          <div class="cropImg"><img alt="${esc(`Eye during flash ${i + 1}`)}" src="data:image/jpeg;base64,${esc(s.crop_jpeg_b64)}">
            ${m == null ? "" : `<span class="stamp">${ICON[m ? "ok" : "bad"]}</span>`}</div>
          <figcaption>${screenGlyph(s.sent_shape, s.sent_color, s.sent_position, axis)}<span class="num">${esc(where[s.sent_position] || s.sent_position || "")}</span></figcaption>
        </figure>`;
      }).join("");
      const facts = [];
      if (cornea) {
        if (fin(cornea.reflection_width_mm) != null) facts.push(`reflection ${cornea.reflection_width_mm.toFixed(1)} mm wide`);
        if (fin(cornea.distance_mm) != null) facts.push(`eye ${Math.round(cornea.distance_mm)} mm from the camera`);
        if (fin(cornea.position_corr) != null) facts.push(`position match ${fix2(cornea.position_corr)}`);
        if (fin(cornea.color_score) != null) facts.push(`colour match ${fix2(cornea.color_score)}`);
      }
      body = `
        <div class="film">${film}</div>
        <div class="readout">
          <span class="num strong">${good} of ${states.length} flashes read correctly</span>
          <span class="legendGlyph">${screenGlyph("circle", "green", "middle", axis)}<span>what the screen showed, and where</span></span>
        </div>
        ${facts.length ? `<div class="facts num">${facts.map((f) => `<span>${esc(f)}</span>`).join("")}</div>` : ""}`;
    } else {
      const raw = (cornea && cornea.reason) || (tile && tile.detail) || (tile && tile.headline) || "";
      body = `
        <div class="empty">
          <svg viewBox="0 0 64 40" aria-hidden="true"><path d="M3 20C11 8 21 3 32 3s21 5 29 17c-8 12-18 17-29 17S11 32 3 20Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="32" cy="20" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 36 52 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <div><p>${esc(friendly(raw) || "The eye check didn't produce a reading.")}</p>${raw ? `<p class="tech"><span class="techKey">technical detail</span> <span class="num">${esc(raw)}</span></p>` : ""}</div>
        </div>`;
    }
    return `
      <header class="cardHead">
        <div><div class="eyebrow">Evidence 01</div><h3>Reflection read from the eye</h3>
          <p class="lede">A real cornea mirrors the screen. Each flash should show up as a small bright reflection, in the colour and place the screen showed it.</p></div>
        ${tile && tile.headline ? `<div class="headStat st-${st}"><i class="dot"></i><span>${esc(tile.headline)}</span></div>` : ""}
      </header>${body}`;
  }

  function lightHtml(r, tiles, hasPlot) {
    const tile = tiles.find((t) => t.name === "Light response");
    const lag = (r.signals && r.signals.lag) || null;
    if (!tile && !lag) return "";
    const st = tile ? STATUS[tile.status] || "warn" : "ok";
    const head = String((tile && tile.headline) || "");
    const hasLag = tile ? /^lag\b/i.test(head) : !!(lag && lag.ok !== false);
    const lagMs = hasLag ? fin(lag && lag.lag_ms) ?? fin(parseFloat(head.replace(/[^\d.]/g, ""))) : null;
    const limitMatch = /limit\s+(\d+(?:\.\d+)?)\s*ms/i.exec(String((tile && tile.detail) || ""));
    const limit = limitMatch ? parseFloat(limitMatch[1]) : null;
    const matchScore = fin(lag && lag.response_r2);

    let stat;
    if (lagMs != null) {
      const scaleMax = Math.max((limit || 0) * 1.6, lagMs * 1.15, 1);
      stat = `
        <div class="big num">${Math.round(lagMs)}<small>ms</small></div>
        <div class="unit">delay between the screen and the skin</div>
        ${limit != null ? `<div class="meter">
          <div class="bar"><i class="fill ${st}" style="width:${(clamp01(lagMs / scaleMax) * 100).toFixed(1)}%"></i><i class="tick" style="left:${((limit / scaleMax) * 100).toFixed(1)}%"></i></div>
          <div class="scale num"><span>0</span><span class="pass" style="left:${((limit / scaleMax) * 100).toFixed(1)}%">limit ${Math.round(limit)} ms</span><span></span></div>
        </div>` : ""}`;
    } else {
      stat = `<div class="big word">${esc(head || "Not measured")}</div>
        <div class="unit">${esc(st === "bad" ? "The skin's colour didn't follow the screen." : friendly((lag && lag.reason) || (tile && tile.detail)) || "")}</div>`;
    }
    const chart = hasPlot ? `
        <div class="scopeBox">
          <canvas class="scope" aria-label="Chart: what the screen sent against what the skin did"></canvas>
          <div class="legend"><span><i class="ln dash"></i>what the screen sent</span><span><i class="ln"></i>what the skin did</span></div>
        </div>` : `<div class="scopeBox none"><p>No light trace was recorded for this check.</p></div>`;
    return `
      <header class="cardHead">
        <div><div class="eyebrow">Evidence 02</div><h3>Skin follows the screen's light</h3>
          <p class="lede">The flashes light up the face. Live skin follows them at once. A generated face needs time to be drawn, so it falls behind.</p></div>
        ${tile && tile.headline ? `<div class="headStat st-${st}"><i class="dot"></i><span>${esc(tile.headline)}</span></div>` : ""}
      </header>
      <div class="lightBody">
        ${chart}
        <div class="lagStat st-${st}">${stat}${matchScore != null ? `<div class="facts num"><span>signal match ${fix2(matchScore)}</span></div>` : ""}</div>
      </div>`;
  }

  function rowsHtml(r, tiles) {
    const rest = tiles.filter((t) => t.name && !SHOWN_ELSEWHERE.includes(t.name));
    if (!rest.length) return "";
    const wave = r.signals && r.signals.rppg && r.signals.rppg.plot && r.signals.rppg.plot.wave;
    return `<div class="eyebrow pad">Also checked</div>` + rest.map((t) => `
      <div class="row st-${STATUS[t.status] || "warn"}">
        <i class="dot"></i>
        <div class="rowMain"><div class="rowName">${esc(t.name)}</div>
          <div class="rowBlurb">${esc(TILE_BLURB[t.name] || "")}</div>
          ${t.detail ? `<div class="rowDetail num">${esc(t.detail)}</div>` : ""}</div>
        ${t.name === "Heartbeat" && wave ? sparkline(wave) : ""}
        <div class="rowHead num">${esc(t.headline || "")}</div>
      </div>`).join("");
  }

  // ---------- render ----------

  function ensure(parent, id, tag, className) {
    let el = byId(id);
    if (!el) { el = document.createElement(tag); el.id = id; parent.appendChild(el); }
    if (className != null) el.className = className;
    return el;
  }

  function renderResults(r) {
    r = r && typeof r === "object" ? r : {};
    const tiles = (Array.isArray(r.tiles) ? r.tiles : []).filter((t) => t && typeof t === "object");
    const V = VERDICT[r.verdict] || { kind: "warn", title: sentence(r.verdict || "No result").replace(/\.$/, ""), word: "No verdict" };
    if (V.kind === "bad" && /selfie does not match/i.test(r.reason || "")) V.title = "Not the enrolled person";

    const section = byId("results");
    const wrap = section.querySelector(".resultsWrap") || section.appendChild(Object.assign(document.createElement("div"), { className: "resultsWrap" }));

    const hero = ensure(wrap, "verdict", "div", `verdict hero rv st-${V.kind}`);
    hero.style.setProperty("--i", 0);
    hero.innerHTML = heroHtml(r, V);

    const stack = ensure(wrap, "tiles", "div", "tiles stack");
    const series = lagSeries(r.signals && r.signals.lag && r.signals.lag.plot);
    const cards = [
      ["punch", punchlineHtml(r, V, tiles)],
      ["eye", eyeHtml(r, tiles)],
      ["light", lightHtml(r, tiles, !!series)],
      ["rows", rowsHtml(r, tiles)],
    ].filter((c) => c[1]);
    stack.innerHTML = cards.map((c, i) => `<section class="panel ${c[0]} rv" style="--i:${i + 1}">${c[1]}</section>`).join("");
    for (const img of stack.querySelectorAll("img")) img.addEventListener("error", () => img.remove());

    const timing = ensure(wrap, "timing", "p", "fine muted center");
    timing.textContent = "";
    timing.hidden = true;

    const done = ensure(wrap, "btnDone", "button", "primary rv");
    done.style.setProperty("--i", cards.length + 1);
    if (!done.textContent.trim()) done.textContent = "Done";
    if (!done.onclick) done.onclick = () => reset();
    let link = byId("attackLogLink");
    if (!link) {
      link = document.createElement("a");
      link.id = "attackLogLink";
      link.href = "/app/attacks.html";
      link.innerHTML = 'See the attack log <span aria-hidden="true">&rarr;</span>';
    }
    link.className = "logLink rv";
    link.style.setProperty("--i", cards.length + 2);
    wrap.append(done, link);                       // keeps both last, in order, on every render

    section.scrollTop = 0;
    window.scrollTo(0, 0);
    const canvas = stack.querySelector("canvas.scope");
    liveChart = null;
    // The canvas has no size until the screen is visible, so the sweep starts on the next frame.
    if (canvas && series) requestAnimationFrame(() => sweepChart(canvas, series, reducedMotion() ? 0 : 120 * cards.findIndex((c) => c[0] === "light") + 350));
    show("results");
  }

  window.lineChart = lineChart;
  window.renderResults = renderResults;
})();
