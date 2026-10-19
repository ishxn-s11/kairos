/* Generated artwork for the seven work cards + diagram slides.
   Each motif is a function (ctx, w, h, seed) that draws one still frame. */
const ART = (() => {
  const TAU = Math.PI * 2;

  function mulberry(seed) {
    let t = seed >>> 0;
    return function () {
      t += 0x6D2B79F5;
      let r = Math.imul(t ^ (t >>> 15), 1 | t);
      r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
      return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
  }

  function bg(ctx, w, h) {
    ctx.fillStyle = "#050505";
    ctx.fillRect(0, 0, w, h);
  }

  function dot(ctx, x, y, r, fill, alpha = 1) {
    ctx.globalAlpha = alpha;
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, TAU);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  /* ---------- 01: fan / core-axis expansion (green) ---------- */
  function fan(ctx, w, h, rnd) {
    bg(ctx, w, h);
    const green = "#b9f36a";
    const cx = w * 0.38, cy = h * 0.5;

    // left regular grid, hollow dots
    const lg = 5, lgn = 4, gapL = w * 0.045;
    for (let i = 0; i < lg; i++) {
      for (let j = 0; j < lgn; j++) {
        const x = w * 0.08 + i * gapL, y = cy + (j - (lgn - 1) / 2) * gapL;
        if (rnd() < .22) dot(ctx, x, y, 2.4, green);
        else {
          ctx.strokeStyle = "rgba(110,140,220,.9)";
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(x, y, 3, 0, TAU); ctx.stroke();
        }
      }
    }
    // curved convergence lines
    ctx.strokeStyle = "rgba(110,140,220,.55)";
    ctx.lineWidth = 1;
    for (let j = 0; j < lgn; j++) {
      const y0 = cy + (j - (lgn - 1) / 2) * gapL;
      ctx.beginPath();
      ctx.moveTo(w * 0.08 + (lg - 1) * gapL, y0);
      ctx.bezierCurveTo(cx - w * 0.1, y0, cx - w * 0.05, cy, cx, cy);
      ctx.stroke();
    }
    // core blob
    dot(ctx, cx, cy, w * 0.028, green);
    // right fan: rows curving up/down, solid green dots growing
    const rows = 7, cols = 12;
    for (let r = 0; r < rows; r++) {
      const t = (r - (rows - 1) / 2) / ((rows - 1) / 2);
      ctx.strokeStyle = "rgba(110,140,220,.4)";
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.bezierCurveTo(cx + w * .12, cy + t * h * .18, cx + w * .2, cy + t * h * .42, cx + w * .5, cy + t * h * .48);
      ctx.stroke();
      for (let c = 1; c <= cols; c++) {
        const u = c / cols;
        const x = cx + (w * 0.5) * u * (0.4 + 0.6 * u);
        const y = cy + t * h * .48 * (u * u * .6 + u * .4);
        dot(ctx, x, y, 2 + 3.4 * u, green, .55 + .45 * u);
      }
    }
  }

  /* ---------- 02: point cloud rectangle (pension pool) ---------- */
  function scatter(ctx, w, h, rnd) {
    bg(ctx, w, h);
    const N = 1500;
    for (let i = 0; i < N; i++) {
      const inCore = rnd() < .55;
      let x, y;
      if (inCore) {
        x = w * .18 + rnd() * w * .42;
        y = h * .22 + rnd() * h * .5;
      } else {
        x = rnd() * w; y = rnd() * h;
      }
      // carve a word-ish band
      const band = Math.abs(y - h * .45) < h * .07 && x > w * .3 && x < w * .75;
      if (band && rnd() < .8) continue;
      dot(ctx, x, y, rnd() < .9 ? .8 : 1.6, "#cfd4da", .25 + rnd() * .6);
    }
    // faint title bar
    ctx.fillStyle = "rgba(255,255,255,.06)";
    ctx.fillRect(w * .3, h * .38, w * .45, h * .14);
  }

  /* ---------- 03: concentric archival rings ---------- */
  function rings(ctx, w, h, rnd) {
    bg(ctx, w, h);
    const cx = w * .5, cy = h * .52;
    for (let r = 14; r < w * .42; r += 13) {
      const a0 = rnd() * TAU, a1 = a0 + 1.2 + rnd() * 3.6;
      ctx.strokeStyle = `rgba(200,205,215,${.08 + rnd() * .3})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, r, a0, a1);
      ctx.stroke();
      // tick at arc end
      const tx = cx + Math.cos(a1) * r, ty = cy + Math.sin(a1) * r;
      ctx.strokeStyle = "rgba(255,255,255,.5)";
      ctx.beginPath();
      ctx.moveTo(tx - 3, ty); ctx.lineTo(tx + 3, ty);
      ctx.stroke();
    }
    for (let i = 0; i < 40; i++) dot(ctx, rnd() * w, rnd() * h, rnd() * 1.2, "#cfd4da", .3);
  }

  /* ---------- 04: reading tree ---------- */
  function tree(ctx, w, h, rnd) {
    bg(ctx, w, h);
    const trunk = [[w * .5, h * .95], [w * .5, h * .6]];
    ctx.strokeStyle = "rgba(190,200,220,.7)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(trunk[0][0], trunk[0][1]);
    ctx.lineTo(trunk[1][0], trunk[1][1]);
    ctx.stroke();

    const branch = (x, y, ang, len, depth) => {
      if (depth === 0 || len < 8) return;
      const n = depth > 2 ? 2 : (rnd() < .7 ? 2 : 1);
      for (let i = 0; i < n; i++) {
        const a = ang + (i - (n - 1) / 2) * (.5 + rnd() * .3);
        const x2 = x + Math.cos(a) * len, y2 = y + Math.sin(a) * len;
        ctx.strokeStyle = `rgba(190,205,225,${.25 + depth * .12})`;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
        dot(ctx, x2, y2, 1.6 + depth * .4, "#dfe6ff", .8);
        branch(x2, y2, a, len * (.62 + rnd() * .12), depth - 1);
      }
    };
    branch(trunk[1][0], trunk[1][1], -Math.PI / 2, h * .16, 5);
  }

  /* ---------- 05: care signal waves ---------- */
  function wave(ctx, w, h, rnd) {
    bg(ctx, w, h);
    for (let s = 0; s < 3; s++) {
      ctx.strokeStyle = `rgba(150,220,180,${.5 - s * .13})`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      for (let x = 0; x <= w; x += 3) {
        const t = x / w;
        const y = h * (.4 + s * .12)
          + Math.sin(t * TAU * (1.2 + s * .7) + s * 2) * h * .1
          + Math.sin(t * TAU * 5.3 + s) * h * .016 * (0.4 + Math.sin(t * 9 + s) ** 2);
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();
      for (let i = 0; i < 24; i++) {
        const t = (i + .5) / 24;
        const x = t * w;
        const y = h * (.4 + s * .12) + Math.sin(t * TAU * (1.2 + s * .7) + s * 2) * h * .1;
        dot(ctx, x, y, 1.8, "#cdeedd", .8);
      }
    }
  }

  /* ---------- 06: modular grid skeleton ---------- */
  function grid(ctx, w, h, rnd) {
    bg(ctx, w, h);
    ctx.strokeStyle = "rgba(160,170,190,.4)";
    const cols = 12, rows = 7, cw = w / cols, rh = h / rows;
    for (let i = 0; i <= cols; i++) { ctx.beginPath(); ctx.moveTo(i * cw, 0); ctx.lineTo(i * cw, h); ctx.stroke(); }
    for (let j = 0; j <= rows; j++) { ctx.beginPath(); ctx.moveTo(0, j * rh); ctx.lineTo(w, j * rh); ctx.stroke(); }
    // highlighted modules
    for (let k = 0; k < 9; k++) {
      const c = Math.floor(rnd() * cols), r = Math.floor(rnd() * rows);
      const pw = 1 + Math.floor(rnd() * 3), ph = 1 + Math.floor(rnd() * 2);
      ctx.fillStyle = `rgba(210,220,240,${.12 + rnd() * .2})`;
      ctx.fillRect(c * cw + 1, r * rh + 1, pw * cw - 2, ph * rh - 2);
      if (rnd() < .5) {
        ctx.strokeStyle = "rgba(255,255,255,.55)";
        ctx.strokeRect(c * cw + 1, r * rh + 1, pw * cw - 2, ph * rh - 2);
      }
    }
    // baseline numbers
    ctx.fillStyle = "rgba(255,255,255,.35)";
    ctx.font = "9px monospace";
    for (let i = 0; i <= cols; i += 2) ctx.fillText(String(i * 100).padStart(4, "0"), i * cw + 3, h - 4);
  }

  /* ---------- 07: dotted golden spiral ---------- */
  function spiral(ctx, w, h, rnd) {
    bg(ctx, w, h);
    const cx = w * .5, cy = h * .52;
    const N = 560;
    for (let i = 0; i < N; i++) {
      const t = i / N;
      const a = t * TAU * 5.2;
      const r = 6 + Math.pow(t, .82) * w * .34;
      const x = cx + Math.cos(a) * r;
      const y = cy + Math.sin(a) * r * .92;
      dot(ctx, x, y, 1 + t * 2.2, "#e8dcc0", .25 + t * .65);
    }
    // radial ticks
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * TAU;
      const r0 = w * .4, r1 = r0 + 8;
      ctx.strokeStyle = "rgba(232,220,192,.25)";
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
      ctx.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
      ctx.stroke();
    }
  }

  const MOTIFS = { fan, scatter, rings, tree, wave, grid, spiral };

  function paint(canvas, motif, seed = 7) {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const w = canvas.clientWidth || canvas.width, h = canvas.clientHeight || canvas.height;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    (MOTIFS[motif] || fan)(ctx, w, h, mulberry(seed));
  }

  /* ---------- SVG diagram builders for the work-detail slides ---------- */
  const NS = "http://www.w3.org/2000/svg";
  function el(name, attrs = {}) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  function svgFan(host, storyLabels) {
    const svg = el("svg", { viewBox: "0 0 1200 700", preserveAspectRatio: "xMidYMid meet" });
    svg.appendChild(el("rect", { width: 1200, height: 700, fill: "#070707" }));
    const cx = 470, cy = 350;
    // left grid
    for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) {
      const x = 130 + i * 60, y = 230 + j * 60;
      if ((i + j) % 3 === 0) svg.appendChild(el("circle", { cx: x, cy: y, r: 4, fill: "#b9f36a" }));
      else svg.appendChild(el("circle", { cx: x, cy: y, r: 4, fill: "none", stroke: "#6e8cdc", "stroke-width": 1.4 }));
    }
    // curves to core
    for (let j = 0; j < 5; j++) {
      const y = 230 + j * 60;
      const p = el("path", { d: `M 370 ${y} C 440 ${y}, 440 ${cy}, ${cx} ${cy}`, stroke: "#6e8cdc", fill: "none", "stroke-width": 1.2, opacity: .7 });
      svg.appendChild(p);
    }
    svg.appendChild(el("circle", { cx, cy, r: 34, fill: "#b9f36a" }));
    // fan right
    for (let r = 0; r < 7; r++) {
      const t = (r - 3) / 3;
      const ex = 1100, ey = cy + t * 300;
      svg.appendChild(el("path", { d: `M ${cx} ${cy} C ${cx + 160} ${cy + t * 90}, ${cx + 300} ${cy + t * 200}, ${ex} ${ey}`, stroke: "#6e8cdc", fill: "none", opacity: .5 }));
      for (let c = 1; c <= 11; c++) {
        const u = c / 11;
        const x = cx + (ex - cx) * u * (.35 + .65 * u);
        const y = cy + t * 300 * (u * u * .55 + u * .45);
        svg.appendChild(el("circle", { cx: x, cy: y, r: 3 + 4.6 * u, fill: "#b9f36a", opacity: .5 + .5 * u }));
      }
    }
    // story path with labels
    const pl = el("polyline", { points: storyLabels.map(s => `${s.x * 12},${s.y * 7}`).join(" "), fill: "none", stroke: "rgba(255,255,255,.55)", "stroke-width": 1 });
    svg.appendChild(pl);
    storyLabels.forEach((s, idx) => {
      const x = s.x * 12, y = s.y * 7;
      svg.appendChild(el("circle", { cx: x, cy: y, r: 3, fill: "#fff" }));
      const t = el("text", { x: x + 8, y: y - 6, class: "storylabel", fill: "#bbb" });
      t.textContent = s.label;
      t.dataset.idx = idx;
      svg.appendChild(t);
    });
    // captions
    [["Asset", 200], ["Core axis", 600], ["Expansion", 990]].forEach(([txt, x]) => {
      const t = el("text", { x, y: 660, fill: "#eee", "font-size": 26, "font-weight": 700 });
      t.textContent = txt;
      svg.appendChild(t);
    });
    return svg;
  }

  function svgScatterSlide(host, storyLabels, titleText) {
    const svg = el("svg", { viewBox: "0 0 1200 700" });
    svg.appendChild(el("rect", { width: 1200, height: 700, fill: "#070707" }));
    const rnd = mulberry(99);
    for (let i = 0; i < 2600; i++) {
      const x = rnd() * 1200, y = rnd() * 700;
      const band = y > 250 && y < 420 && x > 300 && x < 900;
      if (band && rnd() < .85) continue;
      svg.appendChild(el("circle", { cx: x, cy: y, r: rnd() < .92 ? 1 : 1.9, fill: "#cfd4da", opacity: .15 + rnd() * .5 }));
    }
    const t = el("text", { x: 600, y: 355, "text-anchor": "middle", fill: "#eaeaea", "font-size": 30, "letter-spacing": 6, "font-weight": 700 });
    t.textContent = titleText || "KAIROS";
    svg.appendChild(t);
    const path = el("polyline", { points: storyLabels.map(s => `${s.x * 12},${s.y * 7}`).join(" "), fill: "none", stroke: "rgba(255,255,255,.5)" });
    svg.appendChild(path);
    storyLabels.forEach(s => {
      svg.appendChild(el("circle", { cx: s.x * 12, cy: s.y * 7, r: 3, fill: "#fff" }));
      const lb = el("text", { x: s.x * 12 + 8, y: s.y * 7 - 6, class: "storylabel" });
      lb.textContent = s.label;
      svg.appendChild(lb);
    });
    return svg;
  }

  function svgPoster(host, text) {
    const svg = el("svg", { viewBox: "0 0 1200 700" });
    svg.appendChild(el("rect", { width: 1200, height: 700, fill: "#0a0a0a" }));
    svg.appendChild(el("line", { x1: 60, y1: 60, x2: 1140, y2: 60, stroke: "#222" }));
    svg.appendChild(el("line", { x1: 60, y1: 640, x2: 1140, y2: 640, stroke: "#222" }));
    text.split("\n").forEach((line, i) => {
      const t = el("text", { x: 600, y: 300 + i * 74, "text-anchor": "middle", fill: "#f2f2f2", "font-size": 54, "font-weight": 800, "letter-spacing": 2 });
      t.textContent = line;
      svg.appendChild(t);
    });
    return svg;
  }

  function svgLaptop(host, motifSeed) {
    // laptop screen content: mini fan viz
    const wrap = document.createElement("div");
    wrap.className = "laptop";
    const screen = document.createElement("div");
    screen.className = "screen";
    const svg = el("svg", { viewBox: "0 0 640 400" });
    svg.appendChild(el("rect", { width: 640, height: 400, fill: "#04070a" }));
    const rnd = mulberry(motifSeed);
    // dashboard: header bar + aurora viz + stat lines
    svg.appendChild(el("rect", { x: 0, y: 0, width: 640, height: 44, fill: "#0a0f12" }));
    svg.appendChild(el("text", { x: 20, y: 28, fill: "#dfe8e4", "font-size": 13, "letter-spacing": 2, "font-weight": 700 }));
    svg.lastChild.textContent = "KAIROS — DECISION CONSOLE";
    ["#3f7f6f", "#4f9f8f"].forEach((c, ci) => {
      for (let i = 0; i < 900; i++) {
        const a = rnd() * TAU, r = 26 + rnd() * 130;
        const x = 320 + Math.cos(a) * r * 1.35, y = 205 + Math.sin(a) * r * .6;
        svg.appendChild(el("circle", { cx: x, cy: y, r: rnd() * 1.8, fill: c, opacity: .18 + rnd() * .5 }));
      }
    });
    for (let i = 0; i < 3; i++) {
      const y = 300 + i * 26;
      svg.appendChild(el("rect", { x: 60, y, width: 120 + rnd() * 300, height: 5, fill: "#16221e" }));
      svg.appendChild(el("rect", { x: 60, y, width: 60 + rnd() * 160, height: 5, fill: "#3f7f6f", opacity: .8 }));
    }
    screen.appendChild(svg);
    const base = document.createElement("div");
    base.className = "base";
    wrap.append(screen, base);
    return wrap;
  }

  return { paint, MOTIFS, svgFan, svgScatterSlide, svgPoster, svgLaptop, el, mulberry };
})();

export default ART;
