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
    if (wipeDir) {
      sessionStorage.removeItem("bow-wipe");
      const w = wipe(Number(wipeDir), 700);
      // start covered, then reveal in the travel direction
      requestAnimationFrame(() => w.classList.add("leave"));
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
        // settle the frame border, then fade the ghost out
        requestAnimationFrame(() => requestAnimationFrame(() => {
          ghost.classList.add("expand");
          setTimeout(() => ghost.classList.add("fade"), 640);
          setTimeout(() => ghost.remove(), 1150);
        }));
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
    requestAnimationFrame(() => ghost.classList.add("expand"));
    setTimeout(() => { location.href = url; }, 480);
  }

  function initZoomCards() {
    $$(".card").forEach((card) => {
      if (card.dataset.zoomBound) return;
      card.dataset.zoomBound = "1";
      card.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        sessionStorage.setItem("bow-wipe", "1");
        zoomThrough(card, card.getAttribute("href"));
      }, true);
    });
  }

  U.Transitions = { wipe, zoomThrough, initWipeLinks, initArrival, initZoomCards };
})();
