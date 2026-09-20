// Results screen (plain script). renderResults(r) takes the /verify response; app.js calls it.
// Reads: $, show, S from app.js (loaded first).

function lineChart(canvas, series) {
  const dpr = devicePixelRatio || 1, w = canvas.clientWidth || 320, h = 120;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  for (const s of series) {
    const xs = s.x, ys = s.y, x0 = xs[0], x1 = xs[xs.length - 1];
    const lo = s.lo ?? Math.min(...ys), hi = s.hi ?? Math.max(...ys), span = hi - lo || 1;
    g.beginPath();
    g.setLineDash(s.dash || []);
    g.lineWidth = s.width || 2;
    g.strokeStyle = s.color;
    ys.forEach((y, i) => {
      const px = ((xs[i] - x0) / (x1 - x0 || 1)) * (w - 8) + 4, py = h - 6 - ((y - lo) / span) * (h - 12);
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    });
    g.stroke();
  }
}

function renderResults(r) {
  const title = { verified: "Verified", unverified: "Not verified", unverifiable: "Couldn't verify" }[r.verdict] || r.verdict;
  const mark = { verified: "✓", unverified: "✕", unverifiable: "?" }[r.verdict] || "";
  const v = $("verdict");
  v.className = "verdict " + r.verdict;
  v.innerHTML = `<div class="mark">${mark}</div><div><h2>${title}</h2><p></p></div>`;
  v.querySelector("p").textContent = r.reason;

  const tiles = $("tiles");
  tiles.innerHTML = "";
  const sig = r.signals || {};
  for (const t of r.tiles) {
    const el = document.createElement("div");
    el.className = "tile";
    el.innerHTML = `<div class="name"><span class="dot ${t.status}"></span><span></span></div><div class="headline"></div><div class="detail"></div>`;
    el.querySelector(".name span:last-child").textContent = t.name;
    el.querySelector(".headline").textContent = t.headline;
    el.querySelector(".detail").textContent = t.detail;
    tiles.appendChild(el);

    if (t.name === "Light response" && sig.lag?.plot) {
      const c = el.appendChild(document.createElement("canvas")), p = sig.lag.plot, series = [];
      [[0, "#e5484d"], [1, "#30a46c"]].forEach(([ch, color]) => {
        const m = p.measured.map((q) => q[ch]), lo = Math.min(...m), hi = Math.max(...m);
        series.push({ x: p.t, y: p.expected.map((q) => q[ch]), lo, hi, color, dash: [5, 4], width: 1 });
        series.push({ x: p.t, y: m, lo, hi, color });
      });
      requestAnimationFrame(() => lineChart(c, series));
    }
    if (t.name === "Eye reflection" && sig.cornea?.states) {
      const grid = el.appendChild(document.createElement("div"));
      grid.className = "crops";
      const where = { top: "left", middle: "middle", bottom: "right" };
      for (const s of sig.cornea.states) {
        const ok = s.match ?? s.decoded_shape === s.sent_shape;
        const d = document.createElement("div");
        d.className = "crop";
        d.innerHTML = `<img alt="" src="data:image/jpeg;base64,${s.crop_jpeg_b64}"><div class="cap"></div>`;
        const pos = sig.cornea.position_axis === "x" ? where[s.sent_position] : s.sent_position;
        d.querySelector(".cap").innerHTML = `<span>${s.sent_color} ${s.sent_shape}, ${pos}</span><span class="${ok ? "ok" : "bad"}">${ok ? "✓" : "✕"}</span>`;
        grid.appendChild(d);
      }
    }
    if (t.name === "Face match" && r.capture) {
      const img = el.appendChild(document.createElement("img"));
      img.className = "selfieThumb";
      img.alt = "";
      img.src = `/captures/${encodeURIComponent(r.capture)}/selfie.jpg`;
    }
  }
  $("timing").textContent = r.processing_s ? `Analyzed in ${r.processing_s.toFixed(1)} s` : "";
  show("results");
}

