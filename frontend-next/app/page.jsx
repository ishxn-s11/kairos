"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { WORKS } from "../lib/data";
import ART from "../lib/art";
import ThemeToggle from "../components/ThemeToggle";
import AccountNav from "../components/AccountNav";

const DECISIONS = ["buy today", "wait a little", "split it safely", "skip it"];
const PROOF = [
  ["250", "requests decided"],
  ["90", "days simulated"],
  ["22", "validation checks"],
  ["0", "guesses required"],
];

const SERVICES = [
  ["01", "Rebuild", "Profiles, balances, events, messages, and receipts become one dated financial state."],
  ["02", "Forecast", "Every confirmed inflow and outflow is simulated across a conservative 90-day horizon."],
  ["03", "Compare", "Full payment, partial payment, installments, and waiting are tested against the same floor."],
  ["04", "Verify", "An independent pass rejects any plan that breaks the user’s protected minimum balance."],
];

export default function Home() {
  const trackRef = useRef(null);
  const [decision, setDecision] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const cards = trackRef.current?.querySelectorAll(".work-card canvas") || [];
    cards.forEach((canvas, index) => {
      const work = WORKS[index];
      if (work) ART.paint(canvas, work.motif, 7 + Number(work.id) * 13);
    });
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setDecision((index) => (index + 1) % DECISIONS.length), 2400);
    return () => clearInterval(timer);
  }, []);

  return (
    <>
      <header className="page-header">
        <Link className="brand" href="/" aria-label="Kairos home">Kairos<span>.</span></Link>
        <nav className="menu" aria-label="Primary navigation">
          <Link href="/workflow">Workflow</Link>
          <Link href="/results">Results</Link>
          <Link href="/test">Test bench</Link>
          <Link href="/about">About</Link>
        </nav>
        <div className="home-header-actions"><AccountNav /><ThemeToggle compact /><Link className="get-in-touch" href="/test">Try the agent</Link></div>
        <button className="burger" aria-label="Toggle menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
          <span></span><span></span>
        </button>
      </header>

      <div className={`dropdown-menu${menuOpen ? " open" : ""}`}>
        {[["Workflow", "/workflow"], ["Results", "/results"], ["Test bench", "/test"], ["About", "/about"], ["Account", "/account"]].map(([label, href]) => (
          <Link key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</Link>
        ))}
        <div className="mobile-utilities"><AccountNav /><ThemeToggle /></div>
      </div>

      <main className="pages" data-page="home">
        <section className="hero_title">
          <div className="hero-object" aria-hidden="true">
            <div className="hero-cord"></div>
            <div className="hero-charm charm-card"><span>SAFE</span><b>₹</b></div>
            <div className="hero-charm charm-coin">K</div>
            <div className="hero-charm charm-pill">90<span>DAYS</span></div>
            <div className="hero-charm charm-spark">✦</div>
          </div>
          <p className="eyebrow">A financial decision engine</p>
          <h1 className="title">Engineered for decisions.</h1>
          <p className="hero-copy">Kairos rebuilds your cash flow, tests every way to pay, and tells you what is safe—before money leaves your account.</p>
          <Link className="primary-cta" href="/test">Run a decision <span>↗</span></Link>
        </section>

        <section className="proof-strip" aria-label="Product facts">
          <p>Built for real financial context</p>
          <div className="proof-marquee">
            {[...PROOF, ...PROOF].map(([number, label], index) => (
              <div className="proof-item" key={`${label}-${index}`}><strong>{number}</strong><span>{label}</span></div>
            ))}
          </div>
        </section>

        <section className="simple_text">
          <h2 className="big-title">
            Kairos is the decision layer where balances <span className="inline-glyph glyph-balance">₹</span> commitments, dates <span className="inline-glyph glyph-date">90</span> and payment plans <span className="inline-glyph glyph-plan">✓</span> finally make sense together.
          </h2>
        </section>

        <section className="decision-stage">
          <div className="decision-window">
            <div className="window-bar"><span></span><span></span><span></span><i>request_042 · simulation</i></div>
            <div className="decision-grid">
              <div className="decision-card card-request"><i>REQUEST</i><strong>New laptop</strong><span>Needed by 28 Oct</span></div>
              <div className="decision-card card-balance"><i>AVAILABLE</i><strong>₹84,200</strong><span>₹35,000 protected</span></div>
              <div className="decision-path"><span></span><span></span><span></span></div>
              <div className="decision-card card-answer"><i>KAIROS SAYS</i><strong key={decision}>{DECISIONS[decision]}</strong><span>Every future day stays above your floor.</span></div>
            </div>
          </div>
        </section>

        <section className="featured_work_slider">
          <div className="module-head">
            <div><span className="section-kicker">The engine, step by step</span><h2>Seven stages. One answer.</h2></div>
            <Link className="view-all" href="/workflow">Explore workflow ↗</Link>
          </div>
          <div className="work-track" ref={trackRef}>
            {WORKS.map((work) => (
              <Link className="work-card" key={work.id} href={`/work/stage-${work.id}/`}>
                <div className="thumb"><canvas></canvas><span className="card-number">{work.id}</span></div>
                <div className="work-name">{work.title}</div>
                <div className="work-sub">{work.sub}</div>
              </Link>
            ))}
          </div>
        </section>

        <section className="services_module">
          <div className="module-head"><div><span className="section-kicker">What Kairos does</span><h2>From raw evidence to a safe plan.</h2></div></div>
          <div className="services">
            {SERVICES.map(([number, title, description]) => (
              <div className="service-row" key={number}>
                <span className="n">{number}</span>
                <h3>{title}</h3>
                <span className="d">{description}</span>
                <span className="service-arrow">↗</span>
              </div>
            ))}
          </div>
        </section>

        <section className="open_source" aria-label="Open source and private by design">
          <div className="os-intro">
            <span className="section-kicker">Made to be trusted</span>
            <h2>Open source.<br />Private by default.</h2>
            <p>The rules, prompts, and arithmetic are available to inspect. Run it locally with deterministic decisions at the core.</p>
          </div>
          <div className="os-grid">
            <div className="os-cell lime"><span className="os-n">01</span><h3>Auditable</h3><p>Every recommendation carries its dates, assumptions, and evidence.</p></div>
            <div className="os-cell lilac"><span className="os-n">02</span><h3>Local-first</h3><p>Financial context can stay on the machine where it belongs.</p></div>
            <div className="os-cell coral"><span className="os-n">03</span><h3>Deterministic</h3><p>Models read messy evidence. Exact Python arithmetic makes the decision.</p></div>
          </div>
        </section>

        <section className="background_video_cta_variation">
          <div className="cta-orbit" aria-hidden="true"><span>K</span></div>
          <div className="cta-inner">
            <span className="section-kicker">Ready when you are</span>
            <h2 className="big-title">Ask the expensive question before making the expensive decision.</h2>
            <Link className="cta-btn" href="/test">Open the test bench <span>↗</span></Link>
          </div>
        </section>
      </main>

      <footer className="page-footer">
        <div className="footer-top"><span className="footer-say">Buy or wait? <em>Now you’ll know.</em></span></div>
        <nav className="footer-links">
          <Link href="/workflow">Workflow</Link><Link href="/results">Results</Link><Link href="/test">Test bench</Link><Link href="/about">About</Link>
        </nav>
        <div className="wordmark" aria-hidden="true">KAIROS</div>
        <div className="footer-legal"><span>Small is beautiful.</span><span>MIT open source</span><span>Local-first · deterministic · private</span><span>© KAIROS 2026</span></div>
      </footer>
    </>
  );
}
