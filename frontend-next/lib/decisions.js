/* ES-module port of the decision loader for the Next.js frontend.
   Fetches the real /output.csv (copied to /public at build time) and parses it. */
export const STATUSES = ["affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"];
export const METHODS = ["full_payment", "installments", "wait", "not_recommended"];
export const STATUS_COLOR = {
  affordable_now: "#c8f56a",
  affordable_with_plan: "#9fd8ff",
  affordable_later: "#f5d76a",
  not_affordable: "#f56a6a",
};

export function parseCSV(text) {
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

export function parsePlan(plan) {
  if (!plan || plan === "none") return [];
  return plan.split("|").map((p) => {
    const [date, amount] = p.split(":");
    return { date, amount };
  });
}

export function fmtAmount(n) {
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export async function loadDecisions() {
  try {
    const res = await fetch("/output.csv", { cache: "no-cache" });
    if (!res.ok) return null;
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
    return { decisions };
  } catch {
    return null;
  }
}
