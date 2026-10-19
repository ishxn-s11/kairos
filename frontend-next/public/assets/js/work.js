/* Work detail page: reads ?stage=NN, builds the 4 slides + carousel. */
(() => {
  const { $, $$ } = U;
  const params = new URLSearchParams(location.search);
  const id = (params.get("stage") || "01").padStart(2, "0").slice(0, 2);
  const WORKS = DATA.WORKS;
  const idx = Math.max(0, WORKS.findIndex((w) => w.id === id));
  const wk = WORKS[idx];

  document.title = `STAGE ${wk.id} ${wk.title} — Buy or Wait?`;
  $$("a.cardlink").forEach((a) => (a.href = `stage-${wk.id}.html`));

  $("#stage").innerHTML = `
    <div class="work-detail" data-id="${wk.id}">
      <div class="wd-top">
        <h1 class="wd-title">STAGE ${wk.id} — ${wk.title} <span class="dim">· ${wk.sub}</span></h1>
        <aside class="wd-desc">${wk.desc}
          <div class="wd-meta">${wk.meta}<br>SCOPE — ${wk.client}<br>RUN — ${wk.year}</div>
          <div class="wd-links">
            <a href="../results.html">VIEW RESULTS &gt;</a>
            <a href="../about.html">HOW IT WORKS &gt;</a>
          </div>
        </aside>
      </div>
      <div class="wd-side">STAGE ${wk.id} / 07</div>
      <div class="carousel" id="carousel"></div>
      <button class="cnav prev hot" data-d="-1"><i>&lt;</i></button>
      <button class="cnav next hot" data-d="1"><i>&gt;</i></button>
      <a class="wd-goback rail" href="../index.html">&lt; INDEX</a>
    </div>
    <div class="sideprev" id="sideprev"></div>`;

  /* word cloud behind */
  const bg = document.createElement("canvas");
  bg.className = "work-bg";
  bg.style.position = "fixed";
  $("#stage").prepend(bg);
  paintCloud(bg, wk);

  /* slides */
  const car = $("#carousel");
  const slides = [];
  function addSlide(node, caption) {
    const s = document.createElement("div");
    s.className = "slide";
    const f = document.createElement("div");
    f.className = "frame";
    f.appendChild(node);
    const c = document.createElement("div");
    c.className = "caption";
    c.textContent = caption;
    s.appendChild(f);
    s.appendChild(c);
    car.appendChild(s);
    slides.push(s);
  }

  // FIG 01: motif-specific concept diagram + story path overlay
  const diag = document.createElement("div");
  diag.className = "diag";
  const dcv = document.createElement("canvas");
  diag.appendChild(dcv);
  diag.appendChild(storyOverlay(wk.story));
  addSlide(diag, "FIG 01 — PIPELINE DIAGRAM");

  // FIG 1b: real evidence images (stage 01 shows the gallery, others a strip)
  if (window.EVIDENCE && window.EVIDENCE.length) {
    const gal = document.createElement("div");
    gal.className = "ev-strip";
    const picks = (wk.id === "01")
      ? window.EVIDENCE
      : window.EVIDENCE.slice(Number(wk.id) % 5, (Number(wk.id) % 5) + 5);
    picks.forEach((ev) => {
      const card = document.createElement("button");
      card.className = "ev-mini";
      card.innerHTML = `
        <div class="ev-img"><img loading="lazy" src="../${ev.src}" alt="${ev.id}"></div>
        <div class="ev-meta"><b>${ev.id}</b> · ${ev.doc}<br><span class="ev-amt">${ev.amount}</span></div>`;
      card.addEventListener("click", () => {
        const lb = document.createElement("div");
        lb.className = "lightbox";
        lb.innerHTML = `
          <div class="lb-inner">
            <img src="../${ev.src}" alt="${ev.id}">
            <div class="lb-meta"><b>${ev.id} — ${ev.doc}</b><br>extracted: <span class="ev-amt">${ev.amount}</span><br>${ev.note}<br>${ev.event} · ${ev.request}</div>
          </div>`;
        lb.addEventListener("click", () => lb.remove());
        document.body.appendChild(lb);
      });
      gal.appendChild(card);
    });
    const galWrap = document.createElement("div");
    galWrap.className = "frame frame-scroll";
    galWrap.appendChild(gal);
    addSlide(galWrap, "FIG 02 — REAL EVIDENCE");
  }

  // FIG 03: dashboard preview (laptop)
  const lap = ART.svgLaptop($("x"), 11 + Number(wk.id));
  addSlide(lap, "FIG 03 — CONSOLE PREVIEW");

  // FIG 04: density view (point cloud w/ stage title)
  addSlide(ART.svgScatterSlide($("x"), wk.story, `STAGE ${wk.id} — ${wk.title}`), "FIG 04 — DENSITY VIEW");

  // FIG 05: key visual poster
  addSlide(ART.svgPoster($("x"), wk.poster), "FIG 05 — KEY VISUAL");

  requestAnimationFrame(() => ART.paint(dcv, wk.motif, 31 + Number(wk.id) * 7));

  /* manifest-driven real-image slides (fallback-safe) */
  (async function addManifestSlides() {
    const a = await window.Assets.loadStageAssets(wk.id, 1);
    if (!a.slides.length) return;
    // insert right after FIG 01 (pipeline diagram)
    a.slides.forEach((s, i) => {
      const wrap = document.createElement("div");
      wrap.className = "imgslide";
      const im = document.createElement("img");
      im.src = s.src;
      im.alt = s.caption || wk.title;
      wrap.appendChild(im);
      addSlide(wrap, s.caption || `EXHIBIT ${i + 1}`);
      // move the newly added slide into position 1+i
      car.insertBefore(slides[slides.length - 1], slides[1 + i]);
      slides.splice(1 + i, 0, slides.pop());
    });
    show(0, 1);
  })();

  let cur = 0;
  function show(n, dir) {
    cur = (n + slides.length) % slides.length;
    slides.forEach((s, i) => {
      s.classList.toggle("on", i === cur);
      s.classList.toggle("out-l", dir < 0 && i === (cur + 1) % slides.length);
    });
    sidePreview();
  }
  $(".prev", document).addEventListener("click", () => show(cur - 1, -1));
  $(".next", document).addEventListener("click", () => show(cur + 1, 1));
  addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") show(cur + 1, 1);
    if (e.key === "ArrowLeft") show(cur - 1, -1);
    if (e.key === "Escape") location.href = "index.html";
  });

  function sidePreview() {
    const host = $("#sideprev");
    host.innerHTML = "";
    const f = document.createElement("div");
    f.className = "frame";
    f.appendChild(slides[(cur + 1) % slides.length].querySelector(".frame").firstChild.cloneNode(true));
    host.appendChild(f);
  }
  show(0, 1);

  /* story labels light progressively while a slide is active */
  let t0 = performance.now();
  (function tick(t) {
    requestAnimationFrame(tick);
    const labels = slides[cur].querySelectorAll(".storylabel");
    const sec = (t - t0) / 1000;
    labels.forEach((lb, i) => lb.classList.toggle("lit", sec > 1 + i * 0.55));
  })(t0);

  function storyOverlay(story) {
    const svg = ART.el("svg", { viewBox: "0 0 1200 700", preserveAspectRatio: "none", class: "overlay" });
    const pl = ART.el("polyline", {
      points: story.map((p) => `${p.x * 12},${p.y * 7}`).join(" "),
      fill: "none", stroke: "rgba(255,255,255,.55)", "stroke-width": 1,
    });
    svg.appendChild(pl);
    story.forEach((p, i) => {
      svg.appendChild(ART.el("circle", { cx: p.x * 12, cy: p.y * 7, r: 3, fill: "#fff" }));
      const t = ART.el("text", { x: p.x * 12 + 8, y: p.y * 7 - 6, class: "storylabel" });
      t.textContent = p.label;
      t.dataset.idx = i;
      svg.appendChild(t);
    });
    return svg;
  }

  function paintCloud(canvas, wk) {
    const ctx = canvas.getContext("2d");
    let W, H;
    const DPR = Math.min(devicePixelRatio || 1, 2);
    function resize() {
      W = innerWidth; H = innerHeight;
      canvas.width = W * DPR; canvas.height = H * DPR;
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      draw();
    }
    const words = [];
    const rnd = ART.mulberry(42 + Number(wk.id));
    const vocab = [...wk.tags, ...DATA.CLOUD_EXTRA];
    for (let i = 0; i < 130; i++) {
      words.push({
        x: rnd() * W, y: rnd() * H,
        w: vocab[Math.floor(rnd() * vocab.length)],
        s: 10 + rnd() * 4, a: .14 + rnd() * .2,
      });
    }
    function draw() {
      ctx.clearRect(0, 0, W, H);
      words.forEach((o) => {
        ctx.fillStyle = `rgba(255,255,255,${o.a})`;
        ctx.font = `${o.s}px IBM Plex Mono, monospace`;
        ctx.fillText(o.w, o.x, o.y);
      });
    }
    resize();
    addEventListener("resize", resize);
  }

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.Transitions.initWipeLinks();
  U.initEnter();
})();
