/* Client-side helpers for the React port: asset loading with probe fallback,
   wipes + zoom-through transitions, chrome (cursor/grain/sound), enter fade.
   Everything here touches the DOM directly, matching the static site 1:1. */

/* ---------- config-driven asset system (probe + fallback) ---------- */
const assetCache = new Map();

function probe(src) {
  return new Promise((resolve) => {
    const im = new Image();
    im.onload = () => resolve(true);
    im.onerror = () => resolve(false);
    im.src = src;
  });
}

export async function loadStageAssets(id, depth = 0) {
  const key = `${id}@${depth}`;
  if (assetCache.has(key)) return assetCache.get(key);
  const entry = { card: null, slides: [], label: null, fit: "cover" };
  assetCache.set(key, entry);
  try {
    const res = await fetch(`/assets/img/manifest.json`, { cache: "no-cache" });
    if (!res.ok) return entry;
    const manifest = await res.json();
    const st = manifest.stages && manifest.stages[id];
    if (!st) return entry;
    entry.fit = manifest.fit || "cover";
    entry.label = st.label || null;
    // manifest paths are written relative to the site root ("assets/...")
    const abs = (src) => (src.startsWith("assets/") ? "/" + src : src);
    const wants = [];
    if (st.card) wants.push({ kind: "card", src: abs(st.card), caption: "" });
    (st.slides || []).forEach((s) =>
      wants.push({ kind: "slide", src: abs(s.src), caption: s.caption || "" }));
    const checks = await Promise.all(wants.map((w) => probe(w.src)));
    wants.forEach((w, i) => {
      if (!checks[i]) return;
      if (w.kind === "card") entry.card = { src: w.src };
      else entry.slides.push({ src: w.src, caption: w.caption });
    });
  } catch {
    /* manifest missing or malformed → all generative fallback */
  }
  return entry;
}

/* ---------- direction-aware wipe ---------- */
export function wipe(direction = 1, dur = 620) {
  if (typeof document === "undefined") return null;
  const w = document.createElement("div");
  w.className = "wipe";
  w.style.setProperty("--wipe-dir", direction);
  w.style.setProperty("--wipe-dur", dur + "ms");
  document.body.appendChild(w);
  return w;
}

export function wipeNavigate(href, fromPage) {
  const to = href.includes("about") ? "about" : href.includes("results") ? "results"
    : href.includes("stage-") ? "work" : "home";
  const order = { home: 0, about: 1, results: 2, work: 3 };
  const dir = (order[to] ?? 0) >= (order[fromPage] ?? 0) ? 1 : -1;
  wipe(dir);
  setTimeout(() => { window.location.href = href; }, 260);
}

/* ---------- arriving-page handoff (wipe cover + zoom ghost) ---------- */
export function initArrival() {
  const zoom = sessionStorage.getItem("bow-zoom");
  const wipeDir = sessionStorage.getItem("bow-wipe");
  const lampHandoff = sessionStorage.getItem("bow-lamp");
  if (lampHandoff) {
    sessionStorage.removeItem("bow-lamp");
    /* the visitor pulled the light down from home: keep it travelling, drop the
       pendant in above it, then let the pulled light fade into it */
    let from = { x: window.innerWidth / 2, y: 0 };
    try { from = JSON.parse(lampHandoff); } catch { /* stale handoff */ }
    document.body.classList.add("arriving-lamp");
    const el = ensurePull();
    el.style.transform = `translate(${Math.round(from.x)}px, ${Math.round(from.y)}px)`;
    void el.offsetWidth;
    el.classList.add("on", "stretch");
    el.style.transform = `translate(${Math.round(from.x)}px, ${Math.round(window.innerHeight * 0.32)}px)`;
    setTimeout(() => el.classList.remove("on"), 720);
    setTimeout(() => {
      el.remove();
      pullEl = null;
      document.body.classList.remove("arriving-lamp");
    }, 1750);
  }
  if (wipeDir) {
    sessionStorage.removeItem("bow-wipe");
    const w = wipe(Number(wipeDir), 700);
    if (w) {
      void w.offsetWidth; /* reflow instead of rAF: rAF is throttled in some environments */
      w.classList.add("leave");
      setTimeout(() => w.remove(), 800);
    }
  }
  if (zoom) {
    sessionStorage.removeItem("bow-zoom");
    try {
      const { src, rect } = JSON.parse(zoom);
      const ghost = document.createElement("div");
      ghost.className = "zoom-ghost";
      Object.assign(ghost.style, {
        left: rect.left + "px", top: rect.top + "px",
        width: rect.width + "px", height: rect.height + "px",
      });
      const img = document.createElement("img");
      img.src = src;
      ghost.appendChild(img);
      document.body.appendChild(ghost);
      void ghost.offsetWidth; /* flush the initial frame, then let CSS transition it */
      ghost.classList.add("expand");
      setTimeout(() => ghost.classList.add("fade"), 640);
      setTimeout(() => ghost.remove(), 1150);
    } catch { /* stale handoff */ }
  }
}

/* ---------- zoom-through from the strip ---------- */
export function zoomThrough(cardEl, url) {
  const holder = cardEl.querySelector(".cimg");
  const img = holder ? holder.querySelector("canvas") : null;
  const realImg = holder ? holder.querySelector("img.card-img") : null;
  let src = null;
  if (realImg && realImg.complete) src = realImg.src;
  else if (img) src = img.toDataURL();
  const rect = (holder || cardEl).getBoundingClientRect();
  sessionStorage.setItem("bow-zoom", JSON.stringify({
    src, rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
  }));
  const ghost = document.createElement("div");
  ghost.className = "zoom-ghost";
  Object.assign(ghost.style, {
    left: rect.left + "px", top: rect.top + "px",
    width: rect.width + "px", height: rect.height + "px",
  });
  if (src) {
    const im = document.createElement("img");
    im.src = src;
    ghost.appendChild(im);
  }
  document.body.appendChild(ghost);
  void ghost.offsetWidth;
  ghost.classList.add("expand");
  setTimeout(() => { window.location.href = url; }, 480);
}

/* ---------- chrome: sound toggle ---------- */
export function initChrome() {
  const sound = document.querySelector("#soundToggle");
  if (sound && !sound.dataset.bound) {
    sound.dataset.bound = "1";
    sound.addEventListener("click", () => {
      document.body.classList.toggle("sound-on");
      const on = document.body.classList.contains("sound-on");
      const word = document.querySelector("#soundWord");
      if (word) word.textContent = on ? "ON" : "OFF";
      const amb = document.querySelector("#ambience");
      if (amb) { amb.muted = !on; if (on) amb.play().catch(() => {}); else amb.pause(); }
    });
  }
}

/* ---------- chrome: custom cursor + coordinate readout ---------- */
export function initCursor() {
  if (typeof window === "undefined") return;
  if (!window.matchMedia("(pointer: fine)").matches) return;
  document.body.classList.add("fine-pointer");
  if (document.querySelector(".cursor")) return;
  const el = document.createElement("div");
  el.className = "cursor";
  el.innerHTML = `<div class="crest"></div><div class="cdot"></div>`;
  document.body.appendChild(el);
  let x = innerWidth / 2, y = innerHeight / 2, tx = x, ty = y;
  const lerp = (a, b, t) => a + (b - a) * t;
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

  const coord = document.createElement("div");
  coord.className = "coord";
  document.body.appendChild(coord);
  addEventListener("pointermove", (e) => {
    coord.style.left = e.clientX + 18 + "px";
    coord.style.top = e.clientY + 18 + "px";
    coord.textContent = `x ${String(Math.round(e.clientX)).padStart(4, "0")}  y ${String(Math.round(e.clientY)).padStart(4, "0")}`;
  });
}

/* ---------- trace-pen light ----------
   While the pen draws, a lamp-head light follows the tip (vertical-down gesture
   only) and a downward release stretches it toward the About page, which picks
   it up through the "bow-lamp" handoff. Mirrors the static transitions.js. */
let pullEl = null;
let penPts = [];

function ensurePull() {
  if (pullEl) return pullEl;
  pullEl = document.createElement("div");
  pullEl.className = "pull-light";
  pullEl.innerHTML = '<span class="beam"></span><span class="core"></span>';
  document.body.appendChild(pullEl);
  return pullEl;
}

function placePull(x, y) {
  ensurePull().style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}

function showPull(x, y) {
  placePull(x, y);
  ensurePull().classList.add("on");
}

function hidePull() {
  if (pullEl) pullEl.classList.remove("on", "stretch");
}

export function penStart(x, y) {
  penPts = [{ x, y }];
  hidePull();
}

export function penMove(x, y) {
  penPts.push({ x, y });
  if (penPts.length > 48) penPts.shift();
  const xs = penPts.map((p) => p.x);
  const ys = penPts.map((p) => p.y);
  const xR = Math.max(...xs) - Math.min(...xs);
  const yR = Math.max(...ys) - Math.min(...ys);
  if (yR > 60 && yR > xR * 1.4) showPull(x, y);
  else hidePull();
}

export function penEnded() {
  if (sessionStorage.getItem("bow-lamp")) return; /* a handoff is in flight */
  hidePull();
}

export function pullLightThrough(x, y, href = "/about/") {
  const el = ensurePull();
  placePull(x, y);
  void el.offsetWidth;
  el.classList.add("on", "stretch");
  el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y + 170)}px)`;
  sessionStorage.setItem("bow-lamp", JSON.stringify({ x: Math.round(x), y: Math.round(y) }));
  setTimeout(() => { window.location.href = href; }, 430);
}

/* ---------- pull a stage card down ----------
   Dragging a card downward lifts its artwork out of the strip with the lamp
   light riding along, and the release hands the artwork to the stage page,
   whose zoom-through arrival expands it in place. Mirrors transitions.js. */
let lastPull = 0;

export const pulledRecently = () => Date.now() - lastPull < 700;

let cardPullsBound = false;

export function initCardPulls(cancelStripDrag) {
  if (cardPullsBound) return;
  cardPullsBound = true;
  let drag = null;

  const artworkSrc = (card) => {
    const canvas = card.querySelector("canvas");
    if (canvas) { try { return canvas.toDataURL(); } catch { return null; } }
    const img = card.querySelector("img.card-img");
    return img && img.src ? img.src : null;
  };

  document.addEventListener("pointerdown", (e) => {
    const card = e.target instanceof Element ? e.target.closest(".card") : null;
    if (!card || (e.button !== undefined && e.button !== 0)) return;
    drag = { card, href: card.getAttribute("href"), startX: e.clientX, startY: e.clientY, ghost: null, rect: null, pulling: false };
  }, true);

  document.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dy = e.clientY - drag.startY;
    const dx = e.clientX - drag.startX;
    if (!drag.pulling) {
      if (dy < 14 || Math.abs(dy) < Math.abs(dx) * 1.25) return;
      if (typeof cancelStripDrag === "function") cancelStripDrag();
      const holder = drag.card.querySelector(".cimg") || drag.card;
      const r = holder.getBoundingClientRect();
      const ghost = document.createElement("div");
      ghost.className = "pull-ghost";
      Object.assign(ghost.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" });
      const src = artworkSrc(drag.card);
      if (src) {
        const im = document.createElement("img");
        im.src = src;
        ghost.appendChild(im);
      }
      document.body.appendChild(ghost);
      drag.ghost = ghost;
      drag.rect = r;
      drag.pulling = true;
      drag.card.classList.add("is-pulling");
    }
    const lift = Math.min(1, dy / 420);
    drag.ghost.style.transform = `translateY(${Math.round(dy)}px) scale(${(1 + lift * 0.35).toFixed(3)})`;
    drag.ghost.style.boxShadow = `0 ${Math.round(20 + lift * 60)}px ${Math.round(50 + lift * 70)}px rgba(0,0,0,.72)`;
    showPull(e.clientX, e.clientY);
  }, true);

  const finish = (e, commit) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.pulling) return;
    const dy = e && typeof e.clientY === "number" ? e.clientY - d.startY : 0;
    hidePull();
    d.card.classList.remove("is-pulling");
    if (!commit || dy < 70) { d.ghost.remove(); return; }
    lastPull = Date.now();
    sessionStorage.setItem("bow-zoom", JSON.stringify({
      src: artworkSrc(d.card),
      rect: { left: d.rect.left, top: d.rect.top, width: d.rect.width, height: d.rect.height },
    }));
    d.ghost.classList.add("commit");
    d.ghost.style.opacity = ".9";
    d.ghost.style.transform = `translateY(${Math.round(dy + 190)}px) scale(1.22)`;
    setTimeout(() => { window.location.href = d.href; }, 380);
  };

  document.addEventListener("pointerup", (e) => finish(e, true), true);
  document.addEventListener("pointercancel", (e) => finish(e, false), true);
}

/* ---------- chrome: film grain ---------- */
export function initGrain() {
  if (typeof document === "undefined") return;
  if (document.querySelector(".grain")) return;
  const g = document.createElement("div");
  g.className = "grain";
  document.body.appendChild(g);
}

/* ---------- page-enter fade ---------- */
export function initEnter() {
  document.documentElement.classList.add("entering");
  const revealed = () => document.documentElement.classList.remove("entering");
  requestAnimationFrame(() => requestAnimationFrame(revealed));
  setTimeout(revealed, 150); /* never stay hidden if rAF is throttled */
  initArrival();
}
