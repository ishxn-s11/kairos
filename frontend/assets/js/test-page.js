/* Test bench — wires the interactive shell in test.html.
   - quick-pick chips (no typing) + id input + random
   - Baseline tab: real engine output, optional diff vs output.csv
   - Live engine tab: live Python pipeline (live-ui.js)
   - custom test cases (collapsible) scored on the same invariants
   The shown decision IS the real engine output (baseline.json, double-run verified). */
(() => {
  const { $, $$ } = U;
  const D = Decisions;

  const state = {
    byId: new Map(),
    outputIndex: new Map(),
    custom: [],
    customSeq: 0,
  };

  const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
  const esc = (s) => String(s).replace(/[&<>\"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const QUICK = ["request_30", "request_28", "request_39", "request_47", "request_26"];

  /* ---------- quick-pick chips ---------- */
  function buildChips() {
    const host = $("#tb2Quick");
    const ids = QUICK.filter((id) => state.byId.has(id));
    host.innerHTML = ids.map((id) => `<button class="tb2-chip" data-id="${id}">${id.replace("request_", "#")}</button>`).join("");
    host.querySelectorAll(".tb2-chip").forEach((b) => {
      b.addEventListener("click", () => {
        $("#tb2Pick").value = b.dataset.id;
        run(b.dataset.id);
      });
    });
  }

  function markChip(id) {
    $$("#tb2Quick .tb2-chip").forEach((b) => b.classList.toggle("on", b.dataset.id === id));
  }

  /* ---------- tabs ---------- */
  function initTabs() {
    $$(".tb2-tab").forEach((t) => {
      t.addEventListener("click", () => {
        const name = t.dataset.tab;
        $$(".tb2-tab").forEach((x) => { const on = x === t; x.classList.toggle("on", on); x.setAttribute("aria-selected", on); });
        $$(".tb2-pane").forEach((p) => p.classList.toggle("on", p.dataset.pane === name));
      });
    });
  }

  /* ---------- decision card ---------- */
  function renderDecision(out, row, cmpRow) {
    const color = D.STATUS_COLOR[row.status] || "#fff";
    const plan = row.plan && row.plan !== "none"
      ? row.plan.split("|").map((p, i) => { const [d, a] = p.split(":"); return `<tr><td>${i + 1}</td><td>${d}</td><td>${fmt(a)}</td></tr>`; }).join("")
      : `<tr><td colspan="3" class="dec-none">none</td></tr>`;

    let cmp = "";
    if (cmpRow) {
      const checks = [
        ["status", row.status === cmpRow.affordability_status],
        ["method", row.method === cmpRow.recommended_payment_method],
        ["amount", Number(row.amount) === Number(cmpRow.amount_safe_to_pay)],
        ["plan", row.plan === cmpRow.payment_plan],
        ["earliest", (row.earliest || "") === (cmpRow.earliest_date_for_full_payment || "")],
      ];
      const ok = checks.every(([, p]) => p);
      cmp = `<div class="tb2-cmp ${ok ? "ok" : "diff"}">
        <span class="tb2-cmp-h">${ok ? "Matches output.csv" : "Differs from output.csv"}</span>
        <span class="tb2-cmp-list">${checks.map(([k, p]) => `<i class="${p ? "pass" : "fail"}">${k}</i>`).join("")}</span>
      </div>`;
    }

    out.innerHTML = `
      <div class="tb2-card">
        <div class="tb2-card-top">
          <b>${esc(row.request_id)}</b>
          <span class="dec-status" style="--sc:${color}">${row.status}</span>
        </div>
        <div class="tb2-stats">
          <div class="tb2-stat"><span class="k">Safe now</span><span class="v">${fmt(row.amount)}</span></div>
          <div class="tb2-stat"><span class="k">Method</span><span class="v">${row.method}</span></div>
          <div class="tb2-stat"><span class="k">Full by</span><span class="v">${row.earliest || "—"}</span></div>
          <div class="tb2-stat"><span class="k">Changes</span><span class="v">${esc(row.spending)}</span></div>
        </div>
        <table class="dec-plan"><thead><tr><th>#</th><th>Date</th><th>Amount</th></tr></thead><tbody>${plan}</tbody></table>
        <details class="tb2-why"><summary>Why</summary><p>${esc(row.explanation)}</p></details>
        ${cmp}
      </div>`;
  }

  function run(id) {
    const row = state.byId.get(id);
    const out = $("#tb2Out");
    if (!row) { out.innerHTML = `<div class="tb-hint">No such request — pick one from the list.</div>`; return; }
    const cmpRow = $("#tb2Cmp").checked ? state.outputIndex.get(id) : null;
    renderDecision(out, row, cmpRow);
    markChip(id);
    const p = new URLSearchParams(location.search);
    p.set("id", id);
    if ($("#tb2Cmp").checked) p.delete("cmp"); else p.set("cmp", "0");
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p.toString() : ""));
  }

  /* ---------- custom cases ---------- */
  function scoreCustom(c) {
    const row = state.byId.get(c.id);
    const results = [];
    if (!row) { results.push(["exists", false, "unknown id"]); return { ok: false, results }; }
    results.push(["exists", true, "known"]);
    const affordable = row.status !== "not_affordable";
    if (c.expect === "affordable") results.push(["verdict", affordable, row.status]);
    if (c.expect === "full_now") results.push(["verdict", row.status === "affordable_now", row.status]);
    if (c.expect === "not_affordable") results.push(["verdict", row.status === "not_affordable", row.status]);
    if (c.expect === "any") results.push(["verdict", true, row.status]);
    return { ok: results.every(([, p]) => p), results };
  }

  function syncCustomURL() {
    const p = new URLSearchParams(location.search);
    if (state.custom.length) p.set("cases", state.custom.map((c) => `${c.id}~${c.expect}`).join(","));
    else p.delete("cases");
    history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p.toString() : ""));
  }

  function renderCustom() {
    const host = $("#cfList");
    if (!state.custom.length) { host.innerHTML = ""; return; }
    host.innerHTML = state.custom.map((c) => {
      const s = scoreCustom(c);
      return `<div class="tb-case ${s.ok ? "ok" : "diff"}">
        <div class="dec-top"><b>${esc(c.id)}</b><span class="tb-badge ${s.ok ? "pass" : "fail"}">${s.ok ? "PASS" : "FAIL"}</span>
        <button class="tb-del" data-uid="${esc(c.uid)}">×</button></div>
        <div class="tb-case-meta">expect ${esc(c.expect)}</div>
        <ul class="tb-checks">${s.results.map(([k, p, n]) => `<li class="${p ? "pass" : "fail"}"><i>${k}</i>${esc(n)}</li>`).join("")}</ul>
      </div>`;
    }).join("");
    host.querySelectorAll(".tb-del").forEach((b) => {
      b.addEventListener("click", () => {
        const i = state.custom.findIndex((c) => c.uid === b.dataset.uid);
        if (i >= 0) { state.custom.splice(i, 1); renderCustom(); syncCustomURL(); }
      });
    });
  }

  /* ---------- boot ---------- */
  function boot(output) {
    window.BASELINE.forEach((row) => state.byId.set(row.request_id, row));
    if (output) {
      output.decisions.forEach((d) => state.outputIndex.set(d.request_id, {
        affordability_status: d.status, recommended_payment_method: d.method,
        amount_safe_to_pay: d.amount, payment_plan: d.plan.map((p) => `${p.date}:${p.amount}`).join("|") || "none",
        earliest_date_for_full_payment: d.earliest || "", decision_explanation: d.explanation,
      }));
    }

    const list = $("#tbList");
    [...state.byId.keys()].sort().forEach((id) => { const o = document.createElement("option"); o.value = id; list.appendChild(o); });

    if (window.LivePanel) window.LivePanel.mount($("#tbLive"));
    initTabs();
    buildChips();

    $("#tb2Run").addEventListener("click", () => run($("#tb2Pick").value.trim()));
    $("#tb2Pick").addEventListener("keydown", (e) => { if (e.key === "Enter") run(e.target.value.trim()); });
    $("#tb2Random").addEventListener("click", () => { const ids = [...state.byId.keys()]; run(ids[Math.floor(Math.random() * ids.length)]); });

    $("#cfAdd").addEventListener("click", () => {
      const id = $("#cfId").value.trim();
      if (!id) return;
      state.custom.push({ uid: "case_" + (++state.customSeq), id, expect: $("#cfExp").value });
      $("#cfId").value = "";
      renderCustom(); syncCustomURL();
    });

    const params = new URLSearchParams(location.search);
    if (params.get("cases")) {
      params.get("cases").split(",").forEach((tok) => { const [id, expect = "any"] = tok.split("~"); if (id) state.custom.push({ uid: "case_" + (++state.customSeq), id, expect }); });
      renderCustom();
    }
    if (params.get("cmp") === "0") $("#tb2Cmp").checked = false;
    run(params.get("id") || "request_30");
  }

  Promise.all([D.load("output.csv"), Promise.resolve(window.BASELINE)]).then(([output, baseline]) => {
    if (!baseline || !baseline.length) throw new Error("baseline missing");
    boot(output);
  }).catch((err) => {
    $$(".tb2-pane[data-pane='baseline']")[0].innerHTML = `<div class="tb-hint">${esc(String(err))} — the live engine tab still works.</div>`;
    if (window.LivePanel) window.LivePanel.mount($("#tbLive"));
  });

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.Transitions.initWipeLinks();
  U.initEnter();
})();
