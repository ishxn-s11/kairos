/* Shared helpers + custom cursor + chrome behavior (per-page, no router). */
(() => {
  const $  = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const TAU = Math.PI * 2;

  function cross(ctx, x, y, r, alpha) {
    ctx.save();
    ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x - r, y); ctx.lineTo(x + r, y);
    ctx.moveTo(x, y - r); ctx.lineTo(x, y + r);
    ctx.stroke();
    ctx.restore();
  }
  function quad(ctx, pts) {
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length - 1; i++) {
      const mx = (pts[i][0] + pts[i + 1][0]) / 2, my = (pts[i][1] + pts[i + 1][1]) / 2;
      ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
    }
    ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
  }

  /* ---------- chrome ---------- */
  function initChrome() {
    const sound = $("#soundToggle");
    if (sound) {
      sound.addEventListener("click", () => {
        document.body.classList.toggle("sound-on");
        const on = document.body.classList.contains("sound-on");
        $("#soundWord").textContent = on ? "ON" : "OFF";
        const amb = $("#ambience");
        if (amb) { amb.muted = !on; if (on) amb.play().catch(() => {}); else amb.pause(); }
      });
    }
    const lang = $(".lang");
    if (lang) {
      lang.addEventListener("click", () => {
        lang.style.opacity = .5;
        setTimeout(() => (lang.style.opacity = ""), 250);
      });
    }
  }

  /* ---------- custom cursor ---------- */
  function initCursor() {
    if (!window.matchMedia("(pointer: fine)").matches) return;
    document.body.classList.add("fine-pointer");
    const el = document.createElement("div");
    el.className = "cursor";
    el.innerHTML = `<div class="crest"></div><div class="cdot"></div>`;
    document.body.appendChild(el);
    let x = innerWidth / 2, y = innerHeight / 2, tx = x, ty = y;
    addEventListener("pointermove", (e) => {
      tx = e.clientX; ty = e.clientY;
      const t = e.target instanceof Element ? e.target.closest("a,button,.hot") : null;
      el.classList.toggle("is-hover", !!t);
    });
    addEventListener("pointerdown", () => el.classList.add("is-down"));
    addEventListener("pointerup", () => el.classList.remove("is-down"));
    (function tick() {
      x = lerp(x, tx, .35); y = lerp(y, ty, .35);
      el.style.transform = `translate(${x}px,${y}px)`;
      requestAnimationFrame(tick);
    })();

    /* coordinate readout (technical-drawing feel) */
    const coord = document.createElement("div");
    coord.className = "coord";
    document.body.appendChild(coord);
    addEventListener("pointermove", (e) => {
      coord.style.left = e.clientX + 18 + "px";
      coord.style.top = e.clientY + 18 + "px";
      coord.textContent = `x ${String(Math.round(e.clientX)).padStart(4, "0")}  y ${String(Math.round(e.clientY)).padStart(4, "0")}`;
    });
  }

  /* ---------- grain ---------- */
  function initGrain() {
    const g = document.createElement("div");
    g.className = "grain";
    document.body.appendChild(g);
  }

  /* ---------- page-enter fade ---------- */
  function initEnter() {
    document.documentElement.classList.add("entering");
    const revealed = () => document.documentElement.classList.remove("entering");
    requestAnimationFrame(() => requestAnimationFrame(revealed));
    setTimeout(revealed, 150); /* never stay hidden if rAF is throttled */
    if (window.U && U.Transitions) U.Transitions.initArrival();
  }

  window.U = { $, $$, clamp, lerp, TAU, cross, quad, initChrome, initCursor, initGrain, initEnter };
})();
