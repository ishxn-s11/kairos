"use client";

import { useEffect, useRef } from "react";
import { EVIDENCE } from "../../lib/evidence";
import DecisionExplorer from "../../components/DecisionExplorer";

/* Results page: the real run's numbers + the 16 evidence images. */
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

const CHECKS = [
  "exactly 250 output rows plus header", "every request id appears exactly once", "no unexpected request ids",
  "column order exact", "no unintentionally blank decision fields", "0 ≤ amount_safe_to_pay ≤ requested_amount",
  "allowed enum values only", "payment-plan syntax valid", "payment dates chronological",
  "partial plans contain exactly two payments and sum correctly", "installment plans match supplied offers exactly",
  "recommended payments all payable safely", "minimum balance preserved throughout the forecast",
  "spending changes target only eligible flexible events", "no more than three spending changes",
  "earliest full-payment dates are genuinely the first safe dates", "affordable_now uses request_date",
  "not_recommended plans use none", "every explanation agrees with the structured decision",
  "usage report corresponds to the final run", "chat transcript maintained per AGENTS.md",
  "no API keys or secrets in any artifact",
];

export default function ResultsPage() {
  const stageRef = useRef(null);

  useEffect(() => {
    /* evidence lightboxes (delegated) */
    const stage = stageRef.current;
    const onClick = (e) => {
      const card = e.target instanceof Element ? e.target.closest("[data-ev]") : null;
      if (!card) return;
      const ev = EVIDENCE[Number(card.dataset.ev)];
      if (!ev) return;
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
    };
    stage.addEventListener("click", onClick);
    return () => stage.removeEventListener("click", onClick);
  }, []);

  return (
    <main id="stage" ref={stageRef}>
      <div className="results">
        <div className="res-hero">
          <div className="res-kicker">FINAL RUN — 2026-09-13</div>
          <h1 className="res-title">250 REQUESTS.<br />EVERY ROW VALIDATED.</h1>
          <p className="res-sub">The deterministic engine read every dataset row, resolved every conflict,
          simulated the 90-day horizon for every candidate plan, and wrote one decision per request —
          then an independent 22-point validator checked the whole table.</p>
        </div>

        <div className="res-grid">
          {RUN.facts.map(([n, l]) => (
            <div className="fact" key={l}><div className="fact-n">{n}</div><div className="fact-l">{l}</div></div>
          ))}
        </div>

        <div className="res-cols">
          <section className="res-block">
            <h2>AFFORDABILITY STATUS MIX</h2>
            {RUN.statuses.map(([k, v, c]) => (
              <div className="bar-row" key={k}>
                <div className="bar-k">{k}</div>
                <div className="bar-t"><i style={{ width: `${(v / 250) * 100}%`, background: c }}></i></div>
                <div className="bar-v">{v}</div>
              </div>
            ))}
          </section>
          <section className="res-block">
            <h2>RECOMMENDED METHOD MIX</h2>
            {RUN.methods.map(([k, v]) => (
              <div className="bar-row" key={k}>
                <div className="bar-k">{k}</div>
                <div className="bar-t"><i style={{ width: `${(v / 250) * 100}%`, background: "#e8e8e8" }}></i></div>
                <div className="bar-v">{v}</div>
              </div>
            ))}
          </section>
        </div>

        <section className="res-block res-evidence">
          <h2>EVIDENCE THE AGENT READS <span className="res-hint">— 16 images, OCR + vision extraction (click to inspect)</span></h2>
          <div className="ev-grid">
            {EVIDENCE.map((ev, i) => (
              <button className="ev-card" data-ev={i} key={ev.id}>
                <div className="ev-img"><img loading="lazy" src={ev.src} alt={`${ev.id} ${ev.doc}`} /></div>
                <div className="ev-meta">
                  <b>{ev.id}</b> · {ev.doc}<br />
                  <span className="ev-amt">{ev.amount}</span><br />
                  {ev.event} · {ev.request}
                </div>
              </button>
            ))}
          </div>
        </section>

        <DecisionExplorer />

        <section className="res-block">
          <h2>THE 22-POINT FINAL VALIDATION</h2>
          <ol className="checks">
            {CHECKS.map((c) => <li key={c}>{c}</li>)}
          </ol>
        </section>

        <section className="res-block res-artifacts">
          <h2>SUBMISSION ARTIFACTS</h2>
          <div className="arts">
            <div className="art"><b>output.csv</b><span>250 predictions, 8 columns</span></div>
            <div className="art"><b>code.zip</b><span>source · prompts · tests · evaluation</span></div>
            <div className="art"><b>log.txt</b><span>full build transcript</span></div>
            <div className="art"><b>usage_report.md</b><span>model usage + cache stats</span></div>
          </div>
        </section>
      </div>
    </main>
  );
}
