/* Home page: loader, word constellation, trace-pen hint, work strip (7 stages). */
(() => {
  const { $, $$, clamp, lerp, cross, quad, TAU } = U;
  const WORKS = DATA.WORKS;

  /* config-driven card art: real images when the manifest provides them */
  (async function applyManifestCards() {
    for (const wk of WORKS) {
      const a = await window.Assets.loadStageAssets(wk.id, 0);
      const card = $$('.card').find((c) => c.href.includes(`stage-${wk.id}`));
      if (!card || !a.card) continue;
      const holder = card.querySelector('.cimg');
      const im = document.createElement('img');
      im.src = a.card.src;
      im.alt = wk.title;
      im.className = 'card-img';
      holder.prepend(im);
    }
  })();

  /* ---------- loader (first visit only) ---------- */
  function runLoader(done) {
    if (sessionStorage.getItem("bow-loaded")) { done(); return; }
    sessionStorage.setItem("bow-loaded", "1");
    const l = document.createElement("div");
    l.className = "loader";
    l.innerHTML = `
      <svg class="spark" viewBox="0 0 24 24"><path d="M12 1v22M1 12h22M4.2 4.2l15.6 15.6M19.8 4.2L4.2 19.8" stroke="#fff" stroke-width="1.4"/></svg>
      <div class="name" aria-label="KAIROS">KAIROS</div>
      <div class="bar"><i></i></div>
      <div class="pct">00%</div>`;
    document.body.appendChild(l);
    const name = l.querySelector(".name");
    name.innerHTML = [..."KAIROS"].map((c, i) =>
      `<span style="animation-delay:${0.5 + i * 0.045}s">${c === " " ? "&nbsp;" : c}</span>`).join("");
    const pct = l.querySelector(".pct");
    const t0 = performance.now(), dur = 2400;
    (function step(t) {
      const p = clamp((t - t0) / dur, 0, 1);
      pct.textContent = String(Math.round(p * 100)).padStart(2, "0") + "%";
      if (p < 1) requestAnimationFrame(step);
      else setTimeout(() => { l.classList.add("done"); setTimeout(() => l.remove(), 800); done(); }, 200);
    })(t0);
  }

  /* ---------- build strip ---------- */
  const strip = $("#strip");
  WORKS.forEach((wk) => {
    const c = document.createElement("a");
    c.className = "card";
    c.href = `work/stage-${wk.id}.html`;
    c.dataset.go = `work/stage-${wk.id}.html`;
    c.innerHTML = `
      <div class="cimg">
        <div class="corner tl"></div><div class="corner tr"></div>
        <div class="corner bl"></div><div class="corner br"></div>
        <div class="ctag">[ STAGE ${wk.id} ]</div>
        <canvas></canvas>
      </div>
      <div class="ctitle">${wk.title}</div>
      <div class="csub">${wk.sub}</div>`;
    strip.appendChild(c);
    ART.paint(c.querySelector("canvas"), wk.motif, 7 + Number(wk.id) * 13);
  });
  /* correct initial state before the first rAF tick: center card 1,
     mark it active, set the counter (fixes stale-class flash) */
  strip.querySelectorAll(".card")[0].classList.add("is-active");
  const initCnt = $(".sel-count");
  if (initCnt) initCnt.innerHTML = `<b>01</b><i>/</i>STAGE 07`;

  /* ---------- drag / inertia ---------- */
  let x = 0, vx = 0, dragging = false, lastX = 0, lastT = 0;
  const maxX = () => Math.max(0, strip.scrollWidth - innerWidth);
  function onDown(e) { dragging = true; lastX = e.clientX; lastT = performance.now(); vx = 0; }
  function onMove(e) {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    x -= dx;
    if (x < 0) x *= .35; else if (x > maxX()) x = maxX() + (x - maxX()) * .35;
    const dt = Math.max(8, performance.now() - lastT);
    vx = clamp((-dx / dt) * 16, -120, 120);
    lastX = e.clientX; lastT = performance.now();
  }
  function onUp() { dragging = false; }
  const wrap = $(".strip-wrap");
  wrap.addEventListener("pointerdown", onDown);
  addEventListener("pointermove", onMove);
  addEventListener("pointerup", onUp);

  /* ---------- stars + pen ---------- */
  const canvas = $("#stars");
  const ctx = canvas.getContext("2d");
  let W, H, DPR = Math.min(devicePixelRatio || 1, 2);
  function resize() {
    W = innerWidth; H = innerHeight;
    canvas.width = W * DPR; canvas.height = H * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  resize();
  addEventListener("resize", resize);

  const vocab = [];
  WORKS.forEach((w) => w.tags.forEach((t) => { if (!vocab.includes(t)) vocab.push(t); }));
  DATA.CLOUD_EXTRA.forEach((t) => { if (!vocab.includes(t)) vocab.push(t); });

  const stars = [];
  for (let i = 0; i < 190; i++) {
    stars.push({
      x: Math.random() * W, y: Math.random() * H,
      word: vocab[Math.floor(Math.random() * vocab.length)],
      size: 9 + Math.random() * 4,
      tw: Math.random() * TAU,
      drift: (Math.random() - .5) * .05,
      lit: 0,
    });
  }

  let mouse = { x: W / 2, y: H / 2 }, down = false, stroke = [], last = null;
  addEventListener("pointermove", (e) => {
    mouse.x = e.clientX; mouse.y = e.clientY;
    if (down) U.Transitions.penMove(e.clientX, e.clientY); /* the pen carries the light */
  });
  addEventListener("pointerdown", (e) => {
    if (e.target instanceof Element && e.target.closest("a,button,.card")) return;
    mouse.x = e.clientX; mouse.y = e.clientY;
    down = true; stroke = []; last = null;
    U.Transitions.penStart(e.clientX, e.clientY);
  });
  addEventListener("pointerup", () => {
    if (down && stroke.length >= 4) maybeMatch();
    if (down) U.Transitions.penEnded();
    down = false; last = null;
  });

  function maybeMatch() {
    const xs = stroke.map((p) => p.x), ys = stroke.map((p) => p.y);
    const xR = Math.max(...xs) - Math.min(...xs);
    const yR = Math.max(...ys) - Math.min(...ys);
    let turns = 0, dir = 0, acc = 0;
    for (let i = 1; i < stroke.length; i++) {
      const d = stroke[i].x - stroke[i - 1].x;
      if (dir === 0) { if (Math.abs(d) > 8) dir = Math.sign(d); }
      else if (Math.sign(d) === -dir) {
        acc += d;
        if (Math.abs(acc) > 40) { turns++; dir = -dir; acc = 0; }
      } else acc = 0;
    }
    // zig-zag N shape = open the nearest stage
    if (turns >= 2 && xR > 70) {
      const mid = stroke[Math.floor(stroke.length / 2)];
      let best = null, bd = 1e9;
      $$(".card").forEach((c, i) => {
        const r = c.getBoundingClientRect();
        const cx = r.left + r.width / 2, d = Math.abs(cx - mid.x);
        if (d < bd) { bd = d; best = i; }
      });
      if (best != null && bd < 380) { location.href = `work/stage-${WORKS[best].id}.html`; }
      return;
    }
    // vertical-ish downward draw = pull the light down into the About page
    if (yR > 90 && yR > xR * 1.6) {
      const tip = last || stroke[stroke.length - 1];
      U.Transitions.pullLightThrough(tip.x, tip.y);
    }
  }

  window.__strip = {
    get x() { return x; }, set x(v) { x = v; },
    get dragging() { return dragging; }, set dragging(v) { dragging = v; },
  };
  window.__pen = { get down() { return down; }, get stroke() { return stroke; } };

  let raf;
  function frame(t) {
    raf = requestAnimationFrame(frame);
    if (!dragging) {
      x += vx; vx *= .94;
      if (Math.abs(vx) < .05) vx = 0;
      if (x < 0) x = lerp(x, 0, .18);
      if (x > maxX()) x = lerp(x, maxX(), .18);
    }
    x = clamp(x, 0, maxX());
    strip.style.transform = `translateX(${-x}px)`;

    const mid = innerWidth / 2;
    let activeIdx = 0, bd = 1e9;
    $$(".card").forEach((c, i) => {
      const r = c.getBoundingClientRect();
      const d = Math.abs(r.left + r.width / 2 - mid);
      if (d < bd) { bd = d; activeIdx = i; }
      c.classList.toggle("is-side", d > 260 && d < 620);
      c.classList.toggle("is-far", d >= 620);
    });
    $$(".card").forEach((c, i) => c.classList.toggle("is-active", i === activeIdx));
    const cnt = $(".sel-count");
    if (cnt) cnt.innerHTML = `<b>0${activeIdx + 1}</b><i>/</i>STAGE 07`;

    ctx.clearRect(0, 0, W, H);
    stars.forEach((s) => {
      s.tw += .02; s.x += s.drift;
      if (s.x < -80) s.x = W + 80; if (s.x > W + 80) s.x = -80;
      const px = s.x - x * .25;
      const wrapped = ((px % (W + 160)) + W + 160) % (W + 160) - 80;
      const near = Math.hypot(wrapped - mouse.x, s.y - mouse.y) < 130;
      s.lit = lerp(s.lit, near ? 1 : 0, .12);
      const alpha = .10 + .10 * Math.sin(s.tw) + s.lit * .75;
      ctx.fillStyle = s.lit > .04
        ? `rgba(255,255,255,${.85 * s.lit + .1})`
        : `rgba(255,255,255,${alpha})`;
      ctx.font = `${s.size}px IBM Plex Mono, monospace`;
      ctx.textAlign = "center";
      ctx.fillText(s.word, wrapped, s.y);
    });
    if (down && stroke.length) {
      ctx.strokeStyle = "rgba(255,255,255,.5)";
      ctx.lineWidth = 1.2;
      quad(ctx, stroke);
      ctx.stroke();
      const p = stroke[stroke.length - 1];
      cross(ctx, p.x, p.y, 7, .9);
    }
    if (down) {
      const p = { x: mouse.x, y: mouse.y };
      if (!last || Math.hypot(p.x - last.x, p.y - last.y) > 6) { stroke.push(p); last = p; }
    }
  }
  raf = requestAnimationFrame(frame);

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.Transitions.initWipeLinks();
  U.Transitions.initZoomCards();
  /* dragging a card downward pulls its artwork out of the strip (cancels the strip drag) */
  U.Transitions.initCardPulls(() => { dragging = false; vx = 0; });
  U.initEnter();

  /* hero: per-letter register reveal (studio-size) — glyphs slide up from
     behind the .line's overflow mask, staggered left-to-right */
  document.querySelectorAll('.hero-title .line').forEach((line) => {
    line.childNodes.forEach((node) => {
      if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) return;
      const frag = document.createDocumentFragment();
      [...node.textContent].forEach((ch, i) => {
        const w = document.createElement('span');
        w.className = 'word';
        w.textContent = ch === ' ' ? '\u00A0' : ch;
        w.style.animationDelay = (0.04 * i) + 's';
        frag.appendChild(w);
      });
      line.replaceChild(frag, node);
    });
  });

  runLoader(() => {});
})();
