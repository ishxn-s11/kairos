/* Page-transition system.
   - wipe(direction): full-screen column wipe that slides left/right across the
     viewport during navigation; direction is derived from nav relationship.
   - zoomThrough(cardEl, url): the clicked card's artwork clones, scales up to
     fill the screen, then the page navigates underneath; the arriving page
     removes the clone on load (sessionStorage handoff). */
(() => {
  const { $, $$ } = U;

  /* ---------- direction-aware wipe ---------- */
  function wipe(direction = 1, dur = 620) {
    const w = document.createElement("div");
    w.className = "wipe";
    w.style.setProperty("--wipe-dir", direction);
    w.style.setProperty("--wipe-dur", dur + "ms");
    document.body.appendChild(w);
    return w;
  }

  function directionFor(fromPage, toPage) {
    // home(0) <-> about(1) <-> results(2) : lateral wipe; into a stage: zoom handles it
    const order = { home: 0, about: 1, results: 2, work: 3 };
    return (order[toPage] ?? 0) >= (order[fromPage] ?? 0) ? 1 : -1;
  }

  /* intercept standard link navigations for wipe transitions */
  let wipeLinksBound = false;
  function initWipeLinks() {
    if (wipeLinksBound) return;
    wipeLinksBound = true;
    document.addEventListener("click", (e) => {
      const a = e.target instanceof Element && e.target.closest("a[href]");
      if (!a || e.metaKey || e.ctrlKey || e.shiftKey || a.target === "_blank") return;
      const href = a.getAttribute("href");
      if (!href || href.startsWith("mailto:") || href.startsWith("#")) return;
      if (a.closest(".card")) return; // cards use zoom-through
      e.preventDefault();
      const from = document.body.dataset.page || "home";
      const to = href.includes("about") ? "about" : href.includes("results") ? "results"
        : href.includes("stage-") ? "work" : "home";
      const dir = directionFor(from, to);
      wipe(dir);
      setTimeout(() => { location.href = href; }, 260);
    });
  }

  /* ---------- arriving-page handoff for zoom-through + wipe cover ---------- */
  function initArrival() {
    const zoom = sessionStorage.getItem("bow-zoom");
    const wipeDir = sessionStorage.getItem("bow-wipe");
    const lampHandoff = sessionStorage.getItem("bow-lamp");
    if (lampHandoff) {
      sessionStorage.removeItem("bow-lamp");
      /* the visitor just pulled the light down from home: keep it travelling,
         drop the pendant in above it, then let the pulled light fade into it */
      let from = { x: innerWidth / 2, y: 0 };
      try { from = JSON.parse(lampHandoff); } catch { /* stale handoff */ }
      document.body.classList.add("arriving-lamp");
      const el = ensurePull();
      el.style.transform = `translate(${Math.round(from.x)}px, ${Math.round(from.y)}px)`;
      void el.offsetWidth;
      el.classList.add("on", "stretch");
      el.style.transform = `translate(${Math.round(from.x)}px, ${Math.round(innerHeight * 0.32)}px)`;
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
      // start covered, then reveal in the travel direction (reflow, not rAF)
      void w.offsetWidth;
      w.classList.add("leave");
      setTimeout(() => w.remove(), 800);
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
        // flush the initial frame, then let the CSS transition expand it
        // (a synchronous reflow, not rAF: rAF is throttled in some environments)
        void ghost.offsetWidth;
        ghost.classList.add("expand");
        setTimeout(() => ghost.classList.add("fade"), 640);
        setTimeout(() => ghost.remove(), 1150);
      } catch { /* stale handoff */ }
    }
  }

  /* ---------- zoom-through from the strip ---------- */
  function zoomThrough(cardEl, url) {
    const img = cardEl.querySelector("canvas");
    let src = null;
    if (img) src = img.toDataURL();
    const rect = cardEl.querySelector(".cimg").getBoundingClientRect();
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
    setTimeout(() => { location.href = url; }, 480);
  }

  function initZoomCards() {
    $$(".card").forEach((card) => {
      if (card.dataset.zoomBound) return;
      card.dataset.zoomBound = "1";
      card.addEventListener("click", (e) => {
        if (pulledRecently()) return; /* a downward pull already took this card */
        e.preventDefault();
        e.stopPropagation();
        sessionStorage.setItem("bow-wipe", "1");
        zoomThrough(card, card.getAttribute("href"));
      }, true);
    });
  }

  /* ---------- trace-pen light ----------
     While the pen draws, a lamp-head light follows the tip (only for the
     vertical-down gesture) and a downward release stretches it toward About. */
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

  function penStart(x, y) {
    penPts = [{ x, y }];
    hidePull();
  }

  function penMove(x, y) {
    penPts.push({ x, y });
    if (penPts.length > 48) penPts.shift();
    const xs = penPts.map((p) => p.x);
    const ys = penPts.map((p) => p.y);
    const xR = Math.max(...xs) - Math.min(...xs);
    const yR = Math.max(...ys) - Math.min(...ys);
    if (yR > 60 && yR > xR * 1.4) showPull(x, y);
    else hidePull();
  }

  function penEnded() {
    if (sessionStorage.getItem("bow-lamp")) return; /* a handoff is in flight */
    hidePull();
  }

  function pullLightThrough(x, y, href = "about.html") {
    const el = ensurePull();
    placePull(x, y);
    void el.offsetWidth;
    el.classList.add("on", "stretch");
    el.style.transform = `translate(${Math.round(x)}px, ${Math.round(y + 170)}px)`;
    sessionStorage.setItem("bow-lamp", JSON.stringify({ x: Math.round(x), y: Math.round(y) }));
    setTimeout(() => { location.href = href; }, 430);
  }

  /* ---------- pull a stage card down ----------
     Dragging a card downward lifts its artwork out of the strip, the lamp light
     rides with it, and the release hands the artwork to the stage page, whose
     own zoom-through arrival expands it in place. */
  let lastPull = 0;
  const pulledRecently = () => Date.now() - lastPull < 700;
  let cardPullsBound = false;

  function initCardPulls(cancelStripDrag) {
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
      if (!card || e.button !== 0) return;
      drag = { card, href: card.getAttribute("href"), startX: e.clientX, startY: e.clientY, ghost: null, rect: null, pulling: false };
    }, true);

    document.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dy = e.clientY - drag.startY;
      const dx = e.clientX - drag.startX;
      if (!drag.pulling) {
        /* only a mostly-vertical downward drag becomes a pull; sideways stays a strip drag */
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
      showPull(e.clientX, e.clientY); /* the lamp light rides along */
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
      const src = artworkSrc(d.card);
      const r = d.rect;
      sessionStorage.setItem("bow-zoom", JSON.stringify({
        src,
        rect: { left: r.left, top: r.top, width: r.width, height: r.height },
      }));
      /* let the artwork keep dropping away while the stage page takes over */
      d.ghost.classList.add("commit");
      d.ghost.style.opacity = ".9";
      d.ghost.style.transform = `translateY(${Math.round(dy + 190)}px) scale(1.22)`;
      setTimeout(() => { location.href = d.href; }, 380);
    };

    document.addEventListener("pointerup", (e) => finish(e, true), true);
    document.addEventListener("pointercancel", (e) => finish(e, false), true);
  }

  U.Transitions = {
    wipe, zoomThrough, initWipeLinks, initArrival, initZoomCards,
    penStart, penMove, penEnded, pullLightThrough, initCardPulls,
  };
})();
