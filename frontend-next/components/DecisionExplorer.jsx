"use client";

import { useEffect, useRef } from "react";
import { loadDecisions } from "../lib/decisions";
import { renderDecisions } from "../lib/decisions-ui";

/* Decision explorer (client): browse the real output.csv rows. */
export default function DecisionExplorer() {
  const rootRef = useRef(null);

  useEffect(() => {
    let dead = false;
    const root = rootRef.current;
    loadDecisions().then((data) => {
      if (dead || !data) return;
      renderDecisions(root, data, "");
    });
    return () => { dead = true; };
  }, []);

  return (
    <section className="res-block" id="decisionExplorer">
      <h2>LIVE DECISION EXPLORER <span className="res-hint">— the real output.csv, one decision per request</span></h2>
      <div ref={rootRef}></div>
    </section>
  );
}
