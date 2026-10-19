/* Live engine panel for the test bench (static frontend).

   Mounts the control panel that executes modified requests through the real
   Python pipeline (code/serve_api.py) and diffs the result against the
   submitted baseline. Falls back honestly (and inertly) when the endpoint is
   not running — the baseline test bench above keeps working.

   Markup + behavior mirror components/LiveEnginePanel.jsx in the Next.js port. */
(() => {
  const esc = (s) => String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
  const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });

  function mount(host) {
    const API = window.LiveAPI;
    const D = window.Decisions || {};
    const params = new URLSearchParams(location.search);
    const state = { online: false, index: new Map(), loaded: false };

    host.innerHTML = `
      <h2>LIVE ENGINE <span class="tb-live-state" data-state="checking">CHECKING…</span></h2>
      <p class="res-sub">The same real Python pipeline, executed on demand. Change the requested
      amount, move the request date, or toggle partial payment and the engine decides again — then
      diff the answer against the submitted baseline. Start it with
      <code>${API.START_CMD}</code>; without it the bench stays on baseline.json.</p>
      <div class="tb-controls">
        <input id="lvPick" list="tbList" placeholder="request id (e.g. request_26)" />
        <input id="lvAmt" type="number" min="0" step="0.01" placeholder="requested amount" />
        <input id="lvDate" type="date" />
        <label class="tb-toggle"><input type="checkbox" id="lvPartial" /> ALLOW PARTIAL PAYMENT</label>
        <button id="lvHalf">×0.5</button><button id="lvDouble">×2</button><button id="lvFive">×5</button>
        <button id="lvReset">DATASET VALUES</button>
        <button id="lvRun" class="hot">RUN LIVE &gt;</button>
      </div>
      <div class="tb-out" id="lvOut"></div>`;

    const pick = host.querySelector("#lvPick");
    const amt = host.querySelector("#lvAmt");
    const dateEl = host.querySelector("#lvDate");
    const partial = host.querySelector("#lvPartial");
    const out = host.querySelector("#lvOut");
    const pill = host.querySelector(".tb-live-state");

    const hint = (html) => { out.innerHTML = `<div class="tb-hint">${html}</div>`; };
    const setPill = (name, text) => { pill.dataset.state = name; pill.textContent = text; };

    async function loadIndex() {
      if (state.loaded) return;
      state.loaded = true;
      try {
        (await API.requests()).forEach((r) => state.index.set(r.request_id, r));
      } catch { /* keep the form usable even if the index call fails */ }
    }

    function prefill(row) {
      amt.value = row.requested_amount;
      dateEl.value = row.request_date;
      partial.checked = !!row.allows_partial_payment;
    }

    function writeURL(payload) {
      const p = new URLSearchParams(location.search);
      p.set("lv", "1");
      p.set("id", payload.request_id);
      if (payload.requested_amount !== undefined) p.set("amt", payload.requested_amount); else p.delete("amt");
      if (payload.request_date) p.set("date", payload.request_date); else p.delete("date");
      if (payload.allows_partial_payment !== undefined) p.set("partial", payload.allows_partial_payment ? "1" : "0"); else p.delete("partial");
      const qs = p.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
    }

    function render(result) {
      const d = result.decision;
      const color = (D.STATUS_COLOR && D.STATUS_COLOR[d.status]) || "#fff";
      const planRows = d.plan && d.plan !== "none"
        ? d.plan.split("|").map((p, i) => {
            const [date, value] = p.split(":");
            return `<tr><td>${i + 1}</td><td>${esc(date)}</td><td class="ev-amt">${fmt(value)}</td></tr>`;
          }).join("")
        : `<tr><td colspan="3" class="dec-none">none</td></tr>`;
      const changes = API.deltas(result);
      const overrides = result.modified || [];
      const delta = changes.length
        ? `<div class="tb-cmp diff lv-delta-panel">
             <b>LIVE ENGINE — ${changes.length} FIELD${changes.length === 1 ? "" : "S"} CHANGED VS SUBMITTED BASELINE</b>
             <ul class="lv-delta">${changes.map((c) => `
               <li><i>${esc(c.label)}</i>
                 <span class="lv-from">${esc(c.from)}</span>
                 <span class="lv-arrow">→</span>
                 <span class="lv-to">${esc(c.to)}</span>
               </li>`).join("")}</ul>
             <pre>${esc(result.baseline ? result.baseline.explanation : "")}</pre>
           </div>`
        : `<div class="tb-cmp ok lv-delta-panel">
             <b>LIVE ENGINE — IDENTICAL TO THE SUBMITTED BASELINE</b>
             <p class="lv-note">${overrides.length
                ? "The override did not change the decision — the ledger absorbs it."
                : "No overrides applied: this is the same request the agent answered."}</p>
           </div>`;

      out.innerHTML = `
        <div class="tb-decision">
          <div class="dec-top">
            <b>${esc(d.request_id)}</b>
            <span class="lv-tag">LIVE</span>
            <span class="dec-status" style="--sc:${color}">${esc(d.status)}</span>
          </div>
          <div class="dec-facts">
            <div><i>AMOUNT SAFE TO PAY</i><span class="ev-amt">${esc(d.amount)}</span></div>
            <div><i>METHOD</i><span>${esc(d.method)}</span></div>
            <div><i>EARLIEST FULL PAYMENT</i><span>${esc(d.earliest || "—")}</span></div>
            <div><i>SPENDING CHANGES</i><span>${esc(d.spending)}</span></div>
          </div>
          <div class="lv-request">
            <i>REQUEST AS EXECUTED</i>
            <span>${esc(result.request.request_date)} · ${fmt(result.request.requested_amount)} ${esc(result.request.home_currency)}
            · partial ${result.request.allows_partial_payment ? "allowed" : "not allowed"}${
              overrides.length ? ` · overridden: ${esc(overrides.join(", "))}` : ""
            }</span>
          </div>
          <table class="dec-plan">
            <thead><tr><th>#</th><th>DATE</th><th>AMOUNT</th></tr></thead>
            <tbody>${planRows}</tbody>
          </table>
          <div class="dec-expl-full"><i>DECISION EXPLANATION (LIVE ENGINE)</i>${esc(d.explanation)}</div>
          ${delta}
          <div class="lv-usage">engine report — model calls: ${result.usage.calls_for_this_run} · tokens: ${result.usage.tokens_total} · cost: $${result.usage.cost_usd_total} · deterministic pipeline</div>
        </div>`;
    }

    async function run() {
      const id = pick.value.trim();
      if (!id) { hint("PICK A REQUEST ID FIRST."); return; }
      await loadIndex();
      const row = state.index.get(id);
      if (!row) { hint(`UNKNOWN REQUEST <b>${esc(id)}</b> — PICK ONE FROM THE LIST.`); return; }

      const payload = { request_id: id };
      const amount = amt.value.trim();
      const reqDate = dateEl.value;
      if (amount && Number(amount) !== Number(row.requested_amount)) payload.requested_amount = amount;
      if (reqDate && reqDate !== row.request_date) payload.request_date = reqDate;
      if (partial.checked !== !!row.allows_partial_payment) payload.allows_partial_payment = partial.checked;

      hint("RUNNING THE REAL PIPELINE…");
      let result;
      try {
        result = await API.decide(payload);
      } catch (err) {
        hint(`ENGINE ERROR — ${esc(String((err && err.message) || err))}`);
        return;
      }
      render(result);
      writeURL(payload);
    }

    const multiply = (k) => {
      const value = Number(amt.value);
      if (!value) return;
      amt.value = String(Math.round(value * k * 100) / 100);
    };

    pick.addEventListener("change", async () => {
      await loadIndex();
      const row = state.index.get(pick.value.trim());
      if (row) { prefill(row); hint("DATASET VALUES LOADED — CHANGE ANYTHING, THEN RUN LIVE."); }
    });
    host.querySelector("#lvRun").addEventListener("click", run);
    [amt, dateEl].forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); }));
    host.querySelector("#lvHalf").addEventListener("click", () => multiply(0.5));
    host.querySelector("#lvDouble").addEventListener("click", () => multiply(2));
    host.querySelector("#lvFive").addEventListener("click", () => multiply(5));
    host.querySelector("#lvReset").addEventListener("click", async () => {
      await loadIndex();
      const row = state.index.get(pick.value.trim());
      if (row) { prefill(row); hint("DATASET VALUES RESTORED — RUN LIVE TO RE-DECIDE."); }
    });

    (async () => {
      hint("PROBING THE LIVE ENGINE…");
      const health = await API.health();
      if (!health) {
        setPill("offline", "OFFLINE");
        hint(`LIVE ENGINE OFFLINE — start it with <code>${API.START_CMD}</code> (expected at ${API.BASE}). The baseline bench above still works.`);
        host.querySelectorAll("input, button").forEach((el) => { el.disabled = true; });
        return;
      }
      state.online = true;
      setPill("online", `ONLINE · ${health.requests} REQUESTS · ${API.BASE.replace(/^https?:\/\//, "")}`);
      hint("SHAREABLE RUNS: the URL records the request, amount, date and partial flag. Try <b>request_26</b> ×5 (affordable_now → not_affordable) or <b>request_28</b> ×0.5 (not_affordable → affordable_later).");

      /* deep link: ?lv=1&id=…&amt=…&date=…&partial=0 re-runs the shared view */
      if (params.get("lv") === "1" && params.get("id")) {
        pick.value = params.get("id");
        await loadIndex();
        const row = state.index.get(pick.value.trim());
        if (row) {
          prefill(row);
          if (params.get("amt")) amt.value = params.get("amt");
          if (params.get("date")) dateEl.value = params.get("date");
          if (params.get("partial")) partial.checked = params.get("partial") === "1";
          run();
        } else {
          hint(`UNKNOWN REQUEST <b>${esc(params.get("id"))}</b> IN THIS LINK.`);
        }
      }
    })();
  }

  window.LivePanel = { mount };
})();
