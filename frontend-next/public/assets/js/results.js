/* Results page: the real run's numbers + the 16 evidence images. */
(() => {
  const { $, $$ } = U;

  const RUN = {
    rows: 250,
    statuses: [
      ["affordable_now", 29, "#c8f56a"],
      ["affordable_with_plan", 32, "#9fd8ff"],
      ["affordable_later", 65, "#f5d76a"],
      ["not_affordable", 124, "#f56a6a"],
    ],
    methods: [
      ["full_payment", 30],
      ["installments", 31],
      ["wait", 4],
      ["not_recommended", 185],
    ],
    facts: [
      ["250", "requests decided"],
      ["25,342", "financial events read"],
      ["275", "user profiles rebuilt"],
      ["215", "messages interpreted"],
      ["3", "languages understood"],
      ["16", "receipt images extracted"],
      ["4", "currencies converted (dated FX)"],
      ["90", "days simulated per decision"],
      ["22", "final validation checks passed"],
      ["0", "model calls needed (deterministic core)"],
    ],
  };

  $("#stage").innerHTML = `
    <div class="results">
      <div class="res-hero">
        <div class="res-kicker">FINAL RUN — 2026-09-13</div>
        <h1 class="res-title">250 REQUESTS.<br>EVERY ROW VALIDATED.</h1>
        <p class="res-sub">The deterministic engine read every dataset row, resolved every conflict,
        simulated the 90-day horizon for every candidate plan, and wrote one decision per request —
        then an independent 22-point validator checked the whole table.</p>
      </div>

      <div class="res-grid">
        ${RUN.facts.map(([n, l]) => `
          <div class="fact"><div class="fact-n">${n}</div><div class="fact-l">${l}</div></div>`).join("")}
      </div>

      <div class="res-cols">
        <section class="res-block">
          <h2>AFFORDABILITY STATUS MIX</h2>
          ${RUN.statuses.map(([k, v, c]) => `
            <div class="bar-row">
              <div class="bar-k">${k}</div>
              <div class="bar-t"><i style="width:${(v / 250) * 100}%;background:${c}"></i></div>
              <div class="bar-v">${v}</div>
            </div>`).join("")}
        </section>
        <section class="res-block">
          <h2>RECOMMENDED METHOD MIX</h2>
          ${RUN.methods.map(([k, v]) => `
            <div class="bar-row">
              <div class="bar-k">${k}</div>
              <div class="bar-t"><i style="width:${(v / 250) * 100}%;background:#e8e8e8"></i></div>
              <div class="bar-v">${v}</div>
            </div>`).join("")}
        </section>
      </div>

      <section class="res-block res-evidence">
        <h2>EVIDENCE THE AGENT READS <span class="res-hint">— 16 images, OCR + vision extraction (click to inspect)</span></h2>
        <div class="ev-grid" id="evGrid"></div>
      </section>

      <section class="res-block">
        <h2>THE 22-POINT FINAL VALIDATION</h2>
        <ol class="checks">
          ${["exactly 250 output rows plus header","every request id appears exactly once","no unexpected request ids",
             "column order exact","no unintentionally blank decision fields","0 ≤ amount_safe_to_pay ≤ requested_amount",
             "allowed enum values only","payment-plan syntax valid","payment dates chronological",
             "partial plans contain exactly two payments and sum correctly","installment plans match supplied offers exactly",
             "recommended payments all payable safely","minimum balance preserved throughout the forecast",
             "spending changes target only eligible flexible events","no more than three spending changes",
             "earliest full-payment dates are genuinely the first safe dates","affordable_now uses request_date",
             "not_recommended plans use none","every explanation agrees with the structured decision",
             "usage report corresponds to the final run","chat transcript maintained per AGENTS.md",
             "no API keys or secrets in any artifact"].map((c) => `<li>${c}</li>`).join("")}
        </ol>
      </section>

      <section class="res-block res-artifacts">
        <h2>SUBMISSION ARTIFACTS</h2>
        <div class="arts">
          <div class="art"><b>output.csv</b><span>250 predictions, 8 columns</span></div>
          <div class="art"><b>code.zip</b><span>source · prompts · tests · evaluation</span></div>
          <div class="art"><b>log.txt</b><span>full build transcript</span></div>
          <div class="art"><b>usage_report.md</b><span>model usage + cache stats</span></div>
        </div>
      </section>
    </div>`;

  /* evidence gallery */
  const grid = $("#evGrid");
  window.EVIDENCE.forEach((ev) => {
    const card = document.createElement("button");
    card.className = "ev-card";
    card.innerHTML = `
      <div class="ev-img"><img loading="lazy" src="${ev.src}" alt="${ev.id} ${ev.doc}"></div>
      <div class="ev-meta">
        <b>${ev.id}</b> · ${ev.doc}<br>
        <span class="ev-amt">${ev.amount}</span><br>
        ${ev.event} · ${ev.request}
      </div>`;
    card.addEventListener("click", () => openLightbox(ev));
    grid.appendChild(card);
  });

  function openLightbox(ev) {
    const lb = document.createElement("div");
    lb.className = "lightbox";
    lb.innerHTML = `
      <div class="lb-inner">
        <img src="${ev.src}" alt="${ev.id}">
        <div class="lb-meta">
          <b>${ev.id} — ${ev.doc}</b><br>
          extracted amount: <span class="ev-amt">${ev.amount}</span><br>
          ${ev.note}<br>${ev.event} · ${ev.user} · ${ev.request}
        </div>
      </div>`;
    lb.addEventListener("click", () => lb.remove());
    document.body.appendChild(lb);
  }

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.initEnter();
})();
