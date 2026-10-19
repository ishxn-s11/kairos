/* studio-size.com home: hero rotator · featured-work slider · rotating words · services.
   Stage content comes from the shared DATA (data.js) so the 7 decision stages stay in sync. */
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const WORKS = (window.DATA && window.DATA.WORKS) || [];

  /* ---------- header: burger toggles the dropdown ---------- */
  const burger = $("#burger"), dropdown = $("#dropdown");
  if (burger && dropdown) {
    burger.addEventListener("click", () => dropdown.classList.toggle("open"));
    dropdown.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => dropdown.classList.remove("open")));
  }

  /* ---------- hero rotator ---------- */
  const heroWords = ["cash flow", "the price", "the moment", "installments"];
  const rot = $("#heroRotator");
  if (rot) {
    let hi = 0;
    const inner = rot.querySelector("em");
    setInterval(() => {
      rot.classList.add("swap");
      setTimeout(() => {
        hi = (hi + 1) % heroWords.length;
        inner.innerHTML = heroWords[hi].replace(/ /g, "&nbsp;");
        rot.classList.remove("swap");
      }, 400);
    }, 2600);
  }

  /* ---------- featured work slider (7 stages) ---------- */
  const track = $("#workTrack");
  if (track && WORKS.length) {
    WORKS.forEach((wk) => {
      const a = document.createElement("a");
      a.className = "work-card";
      a.href = `work/stage-${wk.id}.html`;
      a.innerHTML = `
        <div class="thumb"><canvas></canvas></div>
        <div class="work-name">${wk.title}</div>
        <div class="work-sub">${wk.sub}</div>`;
      track.appendChild(a);
      if (window.ART && window.ART.paint) window.ART.paint(a.querySelector("canvas"), wk.motif, 7 + Number(wk.id) * 13);
    });
    /* drag-to-scroll */
    let down = false, startX = 0, startL = 0;
    track.addEventListener("pointerdown", (e) => { down = true; startX = e.clientX; startL = track.scrollLeft; track.classList.add("dragging"); });
    addEventListener("pointerup", () => { down = false; track.classList.remove("dragging"); });
    track.addEventListener("pointermove", (e) => { if (!down) return; track.scrollLeft = startL - (e.clientX - startX); });
  }

  /* ---------- rotating words ---------- */
  const rotWords = $("#rotatingWords");
  if (rotWords) {
    const spans = [...rotWords.querySelectorAll("span")];
    let ri = 0;
    spans[0].classList.add("in");
    setInterval(() => {
      spans[ri].classList.remove("in"); spans[ri].classList.add("out");
      const prev = ri;
      ri = (ri + 1) % spans.length;
      spans[ri].classList.remove("out"); spans[ri].classList.add("in");
      setTimeout(() => spans[prev].classList.remove("out"), 500);
    }, 2200);
  }

  /* ---------- services ---------- */
  const SERVICES = [
    ["01", "Affordability", "Can I afford this today without breaking my reserve?"],
    ["02", "Cash-flow forecast", "A 90-day deterministic simulation of every inflow and outflow."],
    ["03", "Payment options", "Full, partial, or installments — each re-simulated and verified."],
    ["04", "Wait or buy", "The earliest date a full payment is safe, if it isn't today."],
    ["05", "Freelancer mode", "Variable income and pending invoices, never counted as guaranteed."],
    ["06", "Explainability", "A dated cash-flow table behind every recommendation."],
  ];
  const svc = $("#services");
  if (svc) {
    SERVICES.forEach(([n, t, d]) => {
      const row = document.createElement("div");
      row.className = "service-row";
      row.innerHTML = `<span class="n">${n}</span><h3>${t}</h3><span class="d">${d}</span>`;
      svc.appendChild(row);
    });
  }

  /* ---------- loader (first visit only) ---------- */
  if (!sessionStorage.getItem("bow-loaded")) {
    sessionStorage.setItem("bow-loaded", "1");
    const l = document.createElement("div");
    l.className = "loader";
    l.innerHTML = `<div class="name">KAIROS</div><div class="bar"><i></i></div><div class="pct">00%</div>`;
    document.body.appendChild(l);
    const name = l.querySelector(".name");
    name.innerHTML = [..."KAIROS"].map((c, i) => `<span style="animation-delay:${0.4 + i * 0.05}s">${c}</span>`).join("");
    const pct = l.querySelector(".pct");
    const t0 = performance.now(), dur = 2200;
    (function step(t) {
      const p = Math.min(1, (t - t0) / dur);
      pct.textContent = String(Math.round(p * 100)).padStart(2, "0") + "%";
      if (p < 1) requestAnimationFrame(step);
      else setTimeout(() => { l.classList.add("done"); setTimeout(() => l.remove(), 800); }, 200);
    })(t0);
  }
})();
