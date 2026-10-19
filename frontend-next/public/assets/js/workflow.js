/* Animated workflow diagram: the agent's seven-stage pipeline drawn as a living
   technical schematic on canvas. Ingest → Resolve → State feed the FORECAST
   simulator (center, larger); the forecast's balance line is drawn live; SAFE
   → PLAN → VERIFY fan out and converge on AUDIT. Data pulses travel the pipes;
   the active stage lights up. A guided tour steps through the stages with the
   blurb box + forecast visual; free-run loops everything continuously.
   Shared by static + Next.js frontends (browser global: window.Workflow). */
(() => {
  const TAU = Math.PI * 2;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const lerp = (a, b, t) => a + (b - a) * t;

  /* stage copy (mirrors lib/data.js WORKS, shortened for the diagram) */
  const STAGES = [
    { id: "01", short: "INGEST", title: "INGEST & EVIDENCE",
      blurb: "250 requests arrive with multilingual messages, 16 receipt images and profile CSVs. Everything is normalized into typed facts with provenance and hash-cached." },
    { id: "02", short: "RESOLVE", title: "RESOLUTION & CONFLICTS",
      blurb: "Messages amend history. Amendments fold onto base events, failed and cancelled transactions retire, linked-event lifecycles settle — only what is still true remains." },
    { id: "03", short: "STATE", title: "STATE RECONSTRUCTION",
      blurb: "One balance across four currencies, converted at dated FX rates. Recurring flows project only when evidence confirms them; unconfirmed income is never counted." },
    { id: "04", short: "FORECAST", title: "90-DAY FORECAST",
      blurb: "A day-by-day simulation walks every debit, credit and reserved pending item across the horizon. The balance may never cross the minimum floor — not even for one day." },
    { id: "05", short: "SAFE", title: "SAFE AMOUNT & TIMING",
      blurb: "Bisection finds the largest amount payable today that keeps every future day safe; a calendar walk finds the first date the full request clears." },
    { id: "06", short: "PLAN", title: "PLANS & VERIFIER",
      blurb: "Every legal strategy is generated — full, partial, installments, wait, spending changes — then independently re-simulated. Unsafe plans are rejected, survivors ranked." },
    { id: "07", short: "AUDIT", title: "OUTPUT & AUDIT",
      blurb: "One row per request lands in output.csv, then a 22-point validator checks the whole table: schema, enums, plan syntax, floor preservation, explanation agreement." },
  ];

  const FLOOR = 600;           // minimum_balance_to_keep (diagram units)
  const START_BAL = 2400;      // diagram opening balance

  /* a deterministic pseudo-balance curve: salary steps, rent/expense dips,
     groceries sawtooth, one pending-debit spike — hand-tuned to stay safe */
  function balanceSeries() {
    const pts = [];
    let bal = START_BAL;
    for (let d = 0; d <= 90; d++) {
      if (d === 5 || d === 35 || d === 65) bal += 1850;          // salary
      if (d === 8 || d === 38 || d === 68) bal -= 980;           // rent
      if (d === 22 || d === 52 || d === 82) bal -= 410;          // utilities
      bal -= 14 * (1 + Math.sin(d * 2.1));                       // daily spend
      if (d === 30) bal -= 320;                                  // pending debit
      pts.push(bal);
    }
    return pts;
  }

  /* diagram layout, computed from canvas size */
  function layout(W, H) {
    const top = H * 0.24, midY = H * 0.56, bot = H * 0.82;
    const boxW = Math.min(150, W * 0.115), boxH = Math.max(34, H * 0.075);
    const lbox = { x: W * 0.055, y: midY - boxH / 2, w: boxW, h: boxH };
    const mbox = { x: W * 0.245, y: midY - boxH / 2, w: boxW, h: boxH };
    const sbox = { x: W * 0.435, y: midY - boxH / 2, w: boxW, h: boxH };
    const fc = { x: W * 0.665, y: midY };                        // forecast center
    const fw = Math.min(180, W * 0.16), fh = Math.max(96, H * 0.21);
    const fbox = { x: fc.x - fw / 2, y: fc.y - fh / 2, w: fw, h: fh };
    const pbox = { x: W * 0.845, y: top - boxH * 0.6, w: boxW * 0.9, h: boxH * 0.82 };
    const vbox = { x: W * 0.845, y: bot - boxH * 0.2, w: boxW * 0.9, h: boxH * 0.82 };
    const abox = { x: W * 0.955 - boxW * 0.45, y: midY - boxH * 0.45, w: boxW * 0.9, h: boxH * 0.9 };
    return { top, midY, bot, lbox, mbox, sbox, fbox, pbox, vbox, abox, fw, fh, fc };
  }

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function pipePts(L) {
    const { lbox, mbox, sbox, fbox, pbox, vbox, abox, top, bot } = L;
    return {
      inA: [[lbox.x + lbox.w, lbox.y + lbox.h * 0.3], [mbox.x, mbox.y + mbox.h * 0.3]],
      inB: [[mbox.x + mbox.w, mbox.y + mbox.h * 0.7], [sbox.x, sbox.y + sbox.h * 0.7]],
      toF: [[sbox.x + sbox.w, L.midY], [fbox.x, L.midY]],
      safe: [[fbox.x + fbox.w, L.midY - 26], [pbox.x, pbox.y + pbox.h / 2]],
      plan: [[fbox.x + fbox.w, L.midY + 26], [vbox.x, vbox.y + vbox.h / 2]],
      va: [[vbox.x + vbox.w * 0.5, vbox.y], [abox.x + abox.w * 0.5, abox.y + abox.h]],
      pa: [[pbox.x + pbox.w * 0.5, pbox.y + pbox.h], [abox.x + abox.w * 0.5, abox.y]],
    };
  }

  function drawPipe(ctx, pts, alpha, flow) {
    ctx.save();
    ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.stroke();
    if (flow > 0) {
      // traveling pulse along the polyline
      const total = pts.length - 1;
      const t = flow % 1;
      const seg = Math.min(total - 1, Math.floor(t * total));
      const lt = t * total - seg;
      const a = pts[seg], b = pts[seg + 1];
      const x = lerp(a[0], b[0], lt), y = lerp(a[1], b[1], lt);
      ctx.fillStyle = "rgba(200,245,106,.95)";
      ctx.beginPath();
      ctx.arc(x, y, 2.2, 0, TAU);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawBox(ctx, b, label, active, t) {
    ctx.save();
    const glow = active ? 0.9 : 0.28 + 0.08 * Math.sin(t * 1.4 + b.x);
    ctx.strokeStyle = `rgba(255,255,255,${glow})`;
    ctx.lineWidth = active ? 1.6 : 1;
    rr(ctx, b.x, b.y, b.w, b.h, 3);
    ctx.stroke();
    if (active) {
      ctx.fillStyle = "rgba(200,245,106,.08)";
      ctx.fill();
      // corner brackets
      ctx.strokeStyle = "rgba(200,245,106,.9)";
      const c = 7;
      const corners = [
        [b.x, b.y, 1, 1], [b.x + b.w, b.y, -1, 1],
        [b.x, b.y + b.h, 1, -1], [b.x + b.w, b.y + b.h, -1, -1],
      ];
      corners.forEach(([x, y, sx, sy]) => {
        ctx.beginPath();
        ctx.moveTo(x + sx * c, y); ctx.lineTo(x, y); ctx.lineTo(x, y + sy * c);
        ctx.stroke();
      });
    }
    ctx.fillStyle = `rgba(255,255,255,${active ? 1 : 0.6})`;
    ctx.font = "10px IBM Plex Mono, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, b.x + b.w / 2, b.y + b.h / 2 + 0.5);
    ctx.restore();
  }

  /* main factory: mount(canvas, opts) → controller */
  function mount(canvas, opts = {}) {
    const ctx = canvas.getContext("2d");
    const host = opts.host || canvas.parentElement || document.body;
    let W = 0, H = 0, DPR = Math.min(devicePixelRatio || 1, 2);
    const series = balanceSeries();
    let raf = 0, running = false;

    const state = {
      t: 0,
      mode: "tour",             // tour | free
      step: 0,                  // active stage index (tour + lighting)
      freeT: 0,
      pulses: { inA: 0, inB: 0, toF: 0, safe: 0, plan: 0, va: 0, pa: 0 },
      forecastProg: 0,          // 0..1 draw of the balance line
      forecastCursor: 0,
      worst: null,              // {d, gap} min-gap marker
      userHold: false,
    };

    function resize() {
      W = host.clientWidth || innerWidth;
      H = host.clientHeight || 480;
      canvas.width = W * DPR; canvas.height = H * DPR;
      canvas.style.width = W + "px";
      canvas.style.height = H + "px";
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    resize();
    const onResize = () => resize();
    addEventListener("resize", onResize);

    /* forecast line geometry inside the forecast box */
    function fgeom(L) {
      const pad = 14;
      const x0 = L.fbox.x + pad, x1 = L.fbox.x + L.fbox.w - pad;
      const y0 = L.fbox.y + L.fbox.h - pad - 8, y1 = L.fbox.y + pad + 4;
      const lo = Math.min(...series, FLOOR) - 60;
      const hi = Math.max(...series) + 60;
      const mx = (d) => x0 + ((x1 - x0) * d) / 90;
      const my = (v) => y0 - ((v - lo) / (hi - lo)) * (y0 - y1);
      return { x0, x1, y0, y1, lo, hi, mx, my };
    }

    function frame() {
      raf = requestAnimationFrame(frame);
      state.t += 1 / 60;
      const L = layout(W, H);
      const P = pipePts(L);
      const st = STAGES[state.step];
      const activeShort = st.short;

      /* advance animation states */
      const inTour = state.mode === "tour";
      const stageT = state.freeT;
      if (!state.userHold) state.freeT += 1 / 60;

      const pulsesOn = {
        inA: state.step >= 1 || !inTour,
        inB: state.step >= 2 || !inTour,
        toF: state.step >= 3 || !inTour,
        safe: state.step >= 5 || (!inTour && stageT % 6 > 3),
        plan: state.step >= 6 || (!inTour && stageT % 6 > 3.4),
        va: state.step >= 7 || !inTour,
        pa: state.step >= 7 || !inTour,
      };
      Object.keys(state.pulses).forEach((k) => {
        const speed = k === "toF" ? 0.55 : 0.4;
        state.pulses[k] = (state.pulses[k] + (pulsesOn[k] ? speed / 60 : 0)) % 1;
      });

      /* forecast progress: animates while FORECAST/SAFE/PLAN active, in free-run loops */
      const fActive = inTour
        ? (state.step === 3 || state.step === 4 || state.step === 5 || state.step === 6)
        : true;
      if (fActive) state.forecastProg = Math.min(1, state.forecastProg + 0.005);
      else state.forecastProg = Math.max(0, state.forecastProg - 0.02);
      if (!inTour && state.forecastProg >= 1) {
        state.forecastProg = 0; // loop the line draw in free-run
      }
      state.forecastCursor = state.forecastProg;

      /* worst-day marker (static: computed once) */
      if (!state.worst) {
        let bd = 0, bg = 1e9;
        series.forEach((v, d) => { const g = v - FLOOR; if (g < bg) { bg = g; bd = d; } });
        state.worst = { d: bd, gap: bg };
      }

      /* ---------- draw ---------- */
      ctx.clearRect(0, 0, W, H);

      // baseline grid
      ctx.strokeStyle = "rgba(255,255,255,.045)";
      ctx.lineWidth = 1;
      for (let gx = 0; gx < W; gx += 48) {
        ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke();
      }
      for (let gy = 0; gy < H; gy += 48) {
        ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke();
      }

      // pipes
      drawPipe(ctx, P.inA, pulsesOn.inA ? 0.5 : 0.2, pulsesOn.inA ? state.pulses.inA : 0);
      drawPipe(ctx, P.inB, pulsesOn.inB ? 0.5 : 0.2, pulsesOn.inB ? state.pulses.inB : 0);
      drawPipe(ctx, P.toF, pulsesOn.toF ? 0.6 : 0.2, pulsesOn.toF ? state.pulses.toF : 0);
      drawPipe(ctx, P.safe, pulsesOn.safe ? 0.55 : 0.18, pulsesOn.safe ? state.pulses.safe : 0);
      drawPipe(ctx, P.plan, pulsesOn.plan ? 0.55 : 0.18, pulsesOn.plan ? state.pulses.plan : 0);
      drawPipe(ctx, P.pa, pulsesOn.pa ? 0.5 : 0.18, pulsesOn.pa ? state.pulses.pa : 0);
      drawPipe(ctx, P.va, pulsesOn.va ? 0.5 : 0.18, pulsesOn.va ? state.pulses.va : 0);

      // boxes
      drawBox(ctx, L.lbox, "01 INGEST", activeShort === "INGEST", state.t);
      drawBox(ctx, L.mbox, "02 RESOLVE", activeShort === "RESOLVE", state.t);
      drawBox(ctx, L.sbox, "03 STATE", activeShort === "STATE", state.t);

      // FORECAST — hero box with the live balance line
      const F = L.fbox;
      ctx.save();
      ctx.strokeStyle = `rgba(255,255,255,${activeShort === "FORECAST" ? 0.95 : 0.5})`;
      ctx.lineWidth = activeShort === "FORECAST" ? 1.6 : 1;
      rr(ctx, F.x, F.y, F.w, F.h, 3);
      ctx.stroke();
      if (activeShort === "FORECAST") {
        ctx.fillStyle = "rgba(200,245,106,.06)";
        ctx.fill();
      }
      ctx.fillStyle = "rgba(255,255,255,.75)";
      ctx.font = "10px IBM Plex Mono, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      ctx.fillText("04 FORECAST — 90-DAY SIMULATION", F.x + 8, F.y + 14);

      const G = fgeom(L);
      // floor line
      ctx.strokeStyle = "rgba(245,106,106,.8)";
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(G.x0, G.my(FLOOR));
      ctx.lineTo(G.x1, G.my(FLOOR));
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "rgba(245,106,106,.9)";
      ctx.font = "8px IBM Plex Mono, monospace";
      ctx.fillText("MIN", G.x1 - 20, G.my(FLOOR) - 4);

      // balance line, drawn progressively
      const upto = Math.max(2, Math.floor(90 * state.forecastProg));
      ctx.strokeStyle = "rgba(159,216,255,.95)";
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (let d = 0; d <= upto; d++) {
        const x = G.mx(d), y = G.my(series[d]);
        if (d === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      // cursor dot + day readout
      if (upto <= 90) {
        const cx = G.mx(upto), cy = G.my(series[upto]);
        ctx.fillStyle = "#fff";
        ctx.beginPath(); ctx.arc(cx, cy, 2.4, 0, TAU); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,.7)";
        ctx.font = "8px IBM Plex Mono, monospace";
        ctx.fillText(`DAY ${upto}`, Math.min(cx + 6, G.x1 - 34), cy - 6);
      }
      // worst-day marker
      if (state.forecastProg >= 1) {
        const wx = G.mx(state.worst.d), wy = G.my(series[state.worst.d]);
        ctx.strokeStyle = "rgba(200,245,106,.9)";
        ctx.beginPath();
        ctx.moveTo(wx, wy); ctx.lineTo(wx, G.my(FLOOR));
        ctx.stroke();
        ctx.fillStyle = "rgba(200,245,106,.95)";
        ctx.fillText(`MIN GAP ${Math.round(state.worst.gap)}`, wx + 5, (wy + G.my(FLOOR)) / 2);
      }
      ctx.restore();

      drawBox(ctx, L.pbox, "05 SAFE", activeShort === "SAFE", state.t);
      drawBox(ctx, L.vbox, "06 PLAN", activeShort === "PLAN", state.t);
      drawBox(ctx, L.abox, "07 AUDIT", activeShort === "AUDIT", state.t);

      // stage caption bottom-left
      ctx.fillStyle = "rgba(255,255,255,.55)";
      ctx.font = "11px IBM Plex Mono, monospace";
      ctx.textAlign = "left";
      ctx.fillText(
        inTour
          ? `TOUR ${state.step + 1}/7 — ${STAGES[state.step].title}`
          : `FREE RUN — ${STAGES[state.step].title.toUpperCase()}`,
        18, H - 16
      );

      /* tour auto-advance + free-run rotation */
      if (inTour) {
        const dur = (opts.stepDuration || 7);
        if (state.freeT > dur) { state.freeT = 0; setStep((state.step + 1) % 7, opts); }
      } else if (state.freeT > 4) {
        state.freeT = 0;
        setStep((state.step + 1) % 7, opts);
      }
    }

    function setStep(i, o = opts) {
      state.step = ((i % 7) + 7) % 7;
      state.freeT = 0;
      if (state.step >= 3) state.forecastProg = 0;
      if (o && o.onStep) o.onStep(state.step, STAGES[state.step]);
    }

    function start() {
      if (running) return;
      running = true;
      raf = requestAnimationFrame(frame);
    }
    function stop() {
      running = false;
      cancelAnimationFrame(raf);
    }

    return {
      start, stop, resize,
      setStep: (i) => setStep(i),
      next: () => setStep(state.step + 1),
      prev: () => setStep(state.step - 1),
      mode: (m) => { state.mode = m; state.freeT = 0; },
      get step() { return state.step; },
      STAGES,
    };
  }

  window.Workflow = { mount, STAGES };
})();
