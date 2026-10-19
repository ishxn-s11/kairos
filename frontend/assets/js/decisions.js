/* Live decision explorer: loads the real output.csv and lets visitors browse
   actual agent decisions — filter by status/method, inspect the structured
   plan and the grounded explanation. No sample data: if output.csv cannot be
   fetched, the explorer shows an honest empty state.
   Shared by static + Next.js frontends (browser global: window.Decisions). */
(() => {
  const STATUSES = ["affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"];
  const METHODS = ["full_payment", "installments", "wait", "not_recommended"];
  const STATUS_COLOR = {
    affordable_now: "#c8f56a",
    affordable_with_plan: "#9fd8ff",
    affordable_later: "#f5d76a",
    not_affordable: "#f56a6a",
  };

  /* ---- RFC4180-ish CSV parser (handles quoted fields with commas/newlines) ---- */
  function parseCSV(text) {
    const rows = [];
    let row = [], field = "", inQ = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQ) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQ = false;
        } else field += c;
      } else if (c === '"') inQ = true;
      else if (c === ",") { row.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(field); field = "";
        if (row.length > 1 || row[0] !== "") rows.push(row);
        row = [];
      } else field += c;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    return rows;
  }

  function parsePlan(plan) {
    if (!plan || plan === "none") return [];
    return plan.split("|").map((p) => {
      const [date, amount] = p.split(":");
      return { date, amount };
    });
  }

  function fmtAmount(n) {
    return Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
  }

  /* ---- fetch + normalize the real run ---- */
  async function load(path) {
    const res = await fetch(path, { cache: "no-cache" });
    if (!res.ok) throw new Error(`output.csv fetch failed: ${res.status}`);
    const rows = parseCSV(await res.text());
    const header = rows[0];
    const idx = Object.fromEntries(header.map((h, i) => [h, i]));
    const decisions = rows.slice(1).map((r) => ({
      request_id: r[idx.request_id],
      amount: Number(r[idx.amount_safe_to_pay]),
      status: r[idx.affordability_status],
      method: r[idx.recommended_payment_method],
      plan: parsePlan(r[idx.payment_plan]),
      earliest: r[idx.earliest_date_for_full_payment] || null,
      spending: r[idx.spending_changes_needed] || "none",
      explanation: r[idx.decision_explanation],
    }));
    return {
      decisions,
      totals: {
        rows: decisions.length,
        byStatus: countBy(decisions, "status"),
        byMethod: countBy(decisions, "method"),
      },
    };
  }

  function countBy(list, key) {
    const m = {};
    list.forEach((d) => { m[d[key]] = (m[d[key]] || 0) + 1; });
    return m;
  }

  window.Decisions = { load, parseCSV, parsePlan, fmtAmount, STATUSES, METHODS, STATUS_COLOR };
})();
