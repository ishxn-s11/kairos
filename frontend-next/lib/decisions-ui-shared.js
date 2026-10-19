/* Shared decision-explorer UI builder (ES-module copy of the static
   frontend's assets/js/decisions-ui.js for the Next.js frontend), with
   deterministic per-request 90-day balance sparklines. */
import { STATUSES, METHODS, STATUS_COLOR, fmtAmount } from "./decisions";

const D = { STATUSES, METHODS, STATUS_COLOR, fmtAmount };

export function renderDecisions(root, data, basePath) {
    const params = new URLSearchParams(location.search);
    const state = {
      status: D.STATUSES.includes(params.get("status")) ? params.get("status") : "all",
      method: D.METHODS.includes(params.get("method")) ? params.get("method") : "all",
      q: params.get("q") || "",
    };

    root.innerHTML = `
      <div class="dec-filters">
        <div class="dec-group" data-g="status"></div>
        <div class="dec-group" data-g="method"></div>
        <input class="dec-q" type="text" placeholder="SEARCH REQUEST ID…" />
      </div>
      <div class="dec-count"></div>
      <div class="dec-grid"></div>
      <div class="dec-empty" hidden>NO DECISIONS MATCH — LOOSEN THE FILTERS.</div>`;

    const grid = root.querySelector(".dec-grid");
    const countEl = root.querySelector(".dec-count");
    const emptyEl = root.querySelector(".dec-empty");

    /* ---------- deterministic 90-day balance sparkline ----------
       Same request id → same series, every render, no randomness leak.
       mulberry32 PRNG seeded by the numeric part of the request id. */
    function mulberry32(seed) {
      let t = seed >>> 0;
      return function () {
        t += 0x6D2B79F5;
        let r = Math.imul(t ^ (t >>> 15), 1 | t);
        r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
        return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
      };
    }

    function seedFrom(id) {
      const m = String(id).match(/(\d+)\s*$/);
      return m ? (Number(m[1]) * 2654435761 >>> 0) : 0x9E3779B9;
    }

    /* 91 daily balances shaped by the decision: salary steps up, rent/utilities
       dips, daily sawtooth; the request's payments drop on their plan dates;
       the series is floor-shifted so the minimum-gap day sits above zero. */
    function balanceSeries(d) {
      const rnd = mulberry32(seedFrom(d.request_id));
      /* plan arrives already parsed (array of {date, amount}) from Decisions.load */
      const payments = Array.isArray(d.plan)
        ? d.plan.map((p) => ({ day: (Number(String(p.date).slice(8, 10)) % 30) + 1, amount: Number(p.amount) || 0 }))
        : [];
      const pts = [];
      let bal = 1200 + rnd() * 600;
      const reqAmt = Math.max(0, Number(d.amount) || 0);
      void reqAmt; // amounts ride along via plan drops; kept for future shaping
      for (let day = 0; day <= 90; day++) {
        const cal = 1 + (day % 30);
        if (cal === 5) bal += 300 + rnd() * 180;                              // income
        if (cal === 8) bal -= 140 + rnd() * 60;                               // rent
        if (cal === 22) bal -= 60 + rnd() * 40;                               // utilities
        bal -= 6 + rnd() * 10;                                                // daily spend
        payments.forEach((p) => { if (p.day === cal) bal -= p.amount; });     // plan drops
        pts.push(bal);
      }
      // floor: the lowest point must read as the binding constraint
      const min = Math.min(...pts);
      const gap = 40 + rnd() * 260;
      const shift = min - gap;
      return pts.map((v) => v - shift);
    }

    function sparkSVG(d, w = 260, h = 40) {
      const pts = balanceSeries(d);
      const lo = Math.min(...pts), hi = Math.max(...pts);
      const span = hi - lo || 1;
      const step = w / (pts.length - 1);
      const y = (v) => h - 3 - ((v - lo) / span) * (h - 6);
      let line = "";
      pts.forEach((v, i) => { line += (i ? "L" : "M") + (i * step).toFixed(1) + " " + y(v).toFixed(1); });
      const color = D.STATUS_COLOR[d.status] || "#e8e8e8";
      const minIdx = pts.indexOf(lo);
      return `
        <svg class="dec-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
          <line x1="0" y1="${(h - 3).toFixed(1)}" x2="${w}" y2="${(h - 3).toFixed(1)}" stroke="rgba(245,106,106,.35)" stroke-dasharray="3 3" stroke-width="1"></line>
          <path d="${line}" fill="none" stroke="${color}" stroke-width="1.2"></path>
          <circle cx="${(minIdx * step).toFixed(1)}" cy="${y(lo).toFixed(1)}" r="1.8" fill="#f56a6a"></circle>
        </svg>`;
    }

    /* ---------- filter chips ---------- */
    function chipRow(groupEl, values, key) {
      groupEl.innerHTML = "";
      const all = [["all", "ALL"], ...values.map((v) => [v, v.toUpperCase()])];
      all.forEach(([val, label]) => {
        const b = document.createElement("button");
        b.className = "dec-chip" + (state[key] === val ? " on" : "");
        b.textContent = label;
        b.addEventListener("click", () => {
          state[key] = val;
          chipRow(groupEl, values, key);
          renderGrid();
          syncURL();
        });
        groupEl.appendChild(b);
      });
    }

    function renderGrid() {
      const list = data.decisions.filter((d) => {
        if (state.status !== "all" && d.status !== state.status) return false;
        if (state.method !== "all" && d.method !== state.method) return false;
        if (state.q && !d.request_id.includes(state.q)) return false;
        return true;
      });
      countEl.textContent = `${list.length} OF ${data.decisions.length} DECISIONS`;
      emptyEl.hidden = list.length > 0;
      grid.innerHTML = "";
      list.slice(0, 48).forEach((d) => {
        const card = document.createElement("button");
        card.className = "dec-card";
        card.innerHTML = `
          <div class="dec-top">
            <b>${d.request_id}</b>
            <span class="dec-status" style="--sc:${D.STATUS_COLOR[d.status] || '#fff'}">${d.status}</span>
          </div>
          <div class="dec-mid">
            <span class="dec-amt">${D.fmtAmount(d.amount)}</span>
            <span class="dec-method">${d.method}</span>
          </div>
          ${sparkSVG(d)}
          <div class="dec-expl">${escapeHTML(d.explanation)}</div>`;
        card.addEventListener("click", () => openDetail(d));
        grid.appendChild(card);
      });
      if (list.length > 48) {
        const more = document.createElement("div");
        more.className = "dec-more";
        more.textContent = `+ ${list.length - 48} MORE — NARROW THE FILTERS TO SEE THEM`;
        grid.appendChild(more);
      }
    }

    function openDetail(d) {
      const lb = document.createElement("div");
      lb.className = "lightbox";
      const planRows = d.plan.length
        ? d.plan.map((p, i) => `
            <tr><td>${i + 1}</td><td>${p.date}</td><td class="ev-amt">${D.fmtAmount(p.amount)}</td></tr>`).join("")
        : `<tr><td colspan="3" class="dec-none">none — ${d.status === "not_affordable" ? "the floor cannot be protected" : "no payments required"}</td></tr>`;
      lb.innerHTML = `
        <div class="lb-inner dec-detail">
          <div class="dec-top">
            <b>${d.request_id}</b>
            <span class="dec-status" style="--sc:${D.STATUS_COLOR[d.status] || '#fff'}">${d.status}</span>
          </div>
          <div class="dec-spark-big">${sparkSVG(d, 480, 72)}</div>
          <div class="dec-facts">
            <div><i>AMOUNT SAFE TO PAY</i><span class="ev-amt">${D.fmtAmount(d.amount)}</span></div>
            <div><i>METHOD</i><span>${d.method}</span></div>
            <div><i>EARLIEST FULL PAYMENT</i><span>${d.earliest || "—"}</span></div>
            <div><i>SPENDING CHANGES</i><span>${escapeHTML(d.spending)}</span></div>
          </div>
          <table class="dec-plan">
            <thead><tr><th>#</th><th>DATE</th><th>AMOUNT</th></tr></thead>
            <tbody>${planRows}</tbody>
          </table>
          <div class="dec-expl-full"><i>DECISION EXPLANATION (VERBATIM FROM OUTPUT.CSV)</i>${escapeHTML(d.explanation)}</div>
          <div class="dec-close">CLICK ANYWHERE TO CLOSE</div>
        </div>`;
      const p = new URLSearchParams(location.search);
      p.set("d", d.request_id);
      history.replaceState(null, "", location.pathname + "?" + p.toString());
      const clearDetail = () => {
        const p2 = new URLSearchParams(location.search);
        p2.delete("d");
        const qs = p2.toString();
        history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
      };
      lb.addEventListener("click", () => { clearDetail(); lb.remove(); });
      document.body.appendChild(lb);
    }

    function escapeHTML(s) {
      return String(s).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      }[c]));
    }

    function syncURL() {
      const p = new URLSearchParams(location.search);
      if (state.status !== "all") p.set("status", state.status); else p.delete("status");
      if (state.method !== "all") p.set("method", state.method); else p.delete("method");
      if (state.q) p.set("q", state.q); else p.delete("q");
      const qs = p.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
    }

    addEventListener("popstate", () => {
      const p = new URLSearchParams(location.search);
      state.status = D.STATUSES.includes(p.get("status")) ? p.get("status") : "all";
      state.method = D.METHODS.includes(p.get("method")) ? p.get("method") : "all";
      state.q = p.get("q") || "";
      const qEl = root.querySelector(".dec-q");
      if (qEl && qEl.value !== state.q) qEl.value = state.q;
      chipRow(root.querySelector('[data-g="status"]'), D.STATUSES, "status");
      chipRow(root.querySelector('[data-g="method"]'), D.METHODS, "method");
      renderGrid();
      const want = p.get("d");
      const row = want && data.decisions.find((x) => x.request_id === want);
      if (row) openDetail(row);
    });

    chipRow(root.querySelector('[data-g="status"]'), D.STATUSES, "status");
    chipRow(root.querySelector('[data-g="method"]'), D.METHODS, "method");
    const qInput = root.querySelector(".dec-q");
    qInput.value = state.q; /* reflect a shared ?q= link in the field itself */
    qInput.addEventListener("input", (e) => {
      state.q = e.target.value.trim();
      renderGrid();
      syncURL();
    });

    renderGrid();

    const dParam = params.get("d");
    if (dParam) {
      const row = data.decisions.find((x) => x.request_id === dParam);
      if (row) openDetail(row);
    }
}

