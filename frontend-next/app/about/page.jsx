import Link from "next/link";

export const metadata = {
  title: "About — KAIROS — Financial Affordability Agent",
  description: "How Kairos turns financial evidence into safe, explainable purchase decisions.",
};

const PRINCIPLES = [
  ["01", "Protect the floor", "Every projected day must remain above the balance the user chose to protect."],
  ["02", "Evidence over optimism", "Pending debits count. Unconfirmed income and unrealized gains do not."],
  ["03", "Explain every answer", "Dates, amounts, constraints, and the selected payment route stay visible."],
];

const PIPELINE = [
  ["Read", "Profiles, events, messages, receipts, and payment options become typed evidence."],
  ["Rebuild", "Kairos resolves conflicts and reconstructs the financial state as of the request date."],
  ["Simulate", "A day-by-day forecast tests the next ninety days against the protected minimum."],
  ["Decide", "Full, partial, installment, and wait plans compete under the same safety rules."],
];

export default function AboutPage() {
  return (
    <main className="about-page-v2">
      <section className="about-hero-v2">
        <div className="about-orbit" aria-hidden="true">
          <span className="orbit-ring ring-one"></span><span className="orbit-ring ring-two"></span>
          <span className="about-token token-k">K</span><span className="about-token token-safe">SAFE</span><span className="about-token token-days">90<br /><small>DAYS</small></span>
        </div>
        <div className="about-hero-copy">
          <span className="section-kicker">About Kairos · Built for the expensive question</span>
          <h1>Clarity before<br /><em>commitment.</em></h1>
          <p>Kairos is a financial decision engine that tells you whether to buy now, split the payment, wait, or walk away—without losing sight of what comes next.</p>
          <div className="about-actions"><Link className="primary-cta" href="/test">Try the agent <span>↗</span></Link><Link className="text-link" href="/workflow">See how it works <span>→</span></Link></div>
        </div>
      </section>

      <section className="about-manifesto">
        <span className="section-kicker">The premise</span>
        <h2>Your balance is a snapshot.<br />Affordability is a <span>timeline.</span></h2>
        <p>A purchase that looks safe today can collide with rent, a pending debit, or an essential bill next week. Kairos rebuilds that timeline before it recommends a move.</p>
      </section>

      <section className="about-pipeline">
        <div className="about-section-head"><span className="section-kicker">One engine · four moves</span><h2>From messy context<br />to one grounded answer.</h2></div>
        <div className="pipeline-cards">
          {PIPELINE.map(([title, copy], index) => (
            <article key={title}><span>0{index + 1}</span><div className={`pipeline-icon icon-${index + 1}`} aria-hidden="true"><i></i><i></i><i></i></div><h3>{title}</h3><p>{copy}</p></article>
          ))}
        </div>
      </section>

      <section className="about-proof">
        <div className="proof-visual" aria-label="A sample Kairos decision">
          <div className="proof-window"><div className="window-bar"><span></span><span></span><span></span><i>decision · verified</i></div><div className="proof-answer"><span>KAIROS SAYS</span><strong>Wait 12 days.</strong><p>Pay in full on 31 Oct and remain ₹8,400 above your protected floor.</p><div className="proof-line"><i></i><b></b><em></em></div></div></div>
        </div>
        <div className="proof-copy"><span className="section-kicker">Built to be inspected</span><h2>The model reads.<br />The rules decide.</h2><p>AI helps understand unstructured evidence. Exact decimal arithmetic, dated exchange rates, and a deterministic simulator make the affordability call.</p><ul><li>Every candidate plan is independently verified</li><li>No unsupported future income is invented</li><li>Every recommendation includes its reasoning</li></ul></div>
      </section>

      <section className="about-principles">
        <div className="about-section-head"><span className="section-kicker">Non-negotiables</span><h2>Small rules.<br />Serious consequences.</h2></div>
        <div className="principle-list">
          {PRINCIPLES.map(([n, title, copy]) => <article key={n}><span>{n}</span><h3>{title}</h3><p>{copy}</p><i>↗</i></article>)}
        </div>
      </section>

      <section className="about-numbers">
        <article><strong>250</strong><span>requests processed</span></article><article><strong>90</strong><span>days simulated</span></article><article><strong>22</strong><span>validation checks</span></article><article><strong>0</strong><span>guesses required</span></article>
      </section>

      <section className="about-close">
        <span className="section-kicker">Your next decision starts here</span>
        <h2>Ask first.<br /><em>Spend second.</em></h2>
        <Link className="about-close-button" href="/test"><span>Run a decision</span><i>↗</i></Link>
      </section>
    </main>
  );
}
