"use client";

import { useEffect, useRef } from "react";

/* Workflow page: mounts the shared canvas engine (public/assets/js/workflow.js,
   identical file to the static frontend) and wires the side panel. */
export default function WorkflowPage() {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const kickerRef = useRef(null);
  const titleRef = useRef(null);
  const blurbRef = useRef(null);
  const dotsRef = useRef(null);
  const counterRef = useRef(null);
  const tourRef = useRef(null);
  const freeRef = useRef(null);
  const engineRef = useRef(null);

  useEffect(() => {
    const script = document.createElement("script");
    script.src = "/assets/js/workflow.js";
    let engine = null;

    const paint = (i, st) => {
      kickerRef.current.textContent = `STAGE 0${i + 1}/07`;
      titleRef.current.textContent = st.title;
      blurbRef.current.textContent = st.blurb;
      dotsRef.current.querySelectorAll("button").forEach((b, k) => b.classList.toggle("on", k === i));
      if (counterRef.current) counterRef.current.innerHTML = `<b>0${i + 1}</b><i>/</i>STAGE 07`;
    };

    function boot() {
      const W = window.Workflow;
      const dots = dotsRef.current;
      W.STAGES.forEach((st, i) => {
        const b = document.createElement("button");
        b.textContent = st.short;
        b.addEventListener("click", () => engine.setStep(i));
        dots.appendChild(b);
      });
      engine = W.mount(canvasRef.current, {
        host: wrapRef.current,
        stepDuration: 7,
        onStep: paint,
      });
      engineRef.current = engine;
      engine.start();
      paint(0, W.STAGES[0]);
    }

    script.onload = boot;
    document.body.appendChild(script);

    const onKey = (e) => {
      if (!engineRef.current) return;
      if (e.key === "ArrowRight") engineRef.current.next();
      if (e.key === "ArrowLeft") engineRef.current.prev();
    };
    addEventListener("keydown", onKey);
    return () => {
      removeEventListener("keydown", onKey);
      if (engineRef.current) engineRef.current.stop();
      script.remove();
    };
  }, []);

  const call = (fn, arg) => engineRef.current && engineRef.current[fn](arg);
  const setMode = (mode) => {
    call("mode", mode);
    tourRef.current.classList.toggle("on", mode === "tour");
    freeRef.current.classList.toggle("on", mode === "free");
  };

  return (
    <>
      <div className="sel-count rail tl2" ref={counterRef}><b>01</b><i>/</i>STAGE 07</div>
      <main id="stage">
        <div className="wf-wrap" ref={wrapRef}>
          <canvas id="flowCanvas" ref={canvasRef}></canvas>
          <aside className="wf-panel">
            <div className="wf-kicker" ref={kickerRef}>STAGE 01/07</div>
            <h2 className="wf-title" ref={titleRef}>INGEST &amp; EVIDENCE</h2>
            <p className="wf-blurb" ref={blurbRef}></p>
            <div className="wf-dots" ref={dotsRef}></div>
            <div className="wf-controls">
              <button className="hot" onClick={() => call("prev")}>&lt; PREV</button>
              <button className="hot" onClick={() => call("next")}>NEXT &gt;</button>
              <span className="wf-modes">
                <button ref={tourRef} className="hot on" onClick={() => setMode("tour")}>TOUR</button>
                <button ref={freeRef} className="hot" onClick={() => setMode("free")}>FREE RUN</button>
              </span>
            </div>
            <div className="wf-legend">
              <span className="lg lg-floor"></span> MINIMUM FLOOR — NEVER CROSSED
              <br /><span className="lg lg-line"></span> SIMULATED BALANCE, DAY 0 → 90
              <br /><span className="lg lg-pulse"></span> DATA PULSE — STAGE HANDOFF
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}
