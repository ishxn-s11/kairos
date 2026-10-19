/* Workflow page boot: mounts the shared engine, wires the side panel. */
(() => {
  const { $ } = U;
  const kicker = $("#wfKicker"), title = $("#wfTitle"), blurb = $("#wfBlurb"), dots = $("#wfDots");

  function paint(i, st) {
    kicker.textContent = `STAGE 0${i + 1}/07`;
    title.textContent = st.title;
    blurb.textContent = st.blurb;
    dots.querySelectorAll("button").forEach((b, k) => b.classList.toggle("on", k === i));
    const cnt = $(".sel-count");
    if (cnt) cnt.innerHTML = `<b>0${i + 1}</b><i>/</i>STAGE 07`;
  }

  /* dots */
  Workflow.STAGES.forEach((st, i) => {
    const b = document.createElement("button");
    b.textContent = st.short;
    b.addEventListener("click", () => engine.setStep(i));
    dots.appendChild(b);
  });

  const engine = Workflow.mount($("#flowCanvas"), {
    host: $("#flowCanvas").parentElement,
    stepDuration: 7,
    onStep: paint,
  });

  $("#wfPrev").addEventListener("click", () => engine.prev());
  $("#wfNext").addEventListener("click", () => engine.next());
  $("#wfTour").addEventListener("click", () => {
    engine.mode("tour");
    $("#wfTour").classList.add("on");
    $("#wfFree").classList.remove("on");
  });
  $("#wfFree").addEventListener("click", () => {
    engine.mode("free");
    $("#wfFree").classList.add("on");
    $("#wfTour").classList.remove("on");
  });
  addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") engine.next();
    if (e.key === "ArrowLeft") engine.prev();
  });

  paint(0, Workflow.STAGES[0]);
  engine.start();

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.Transitions.initWipeLinks();
  U.initEnter();
})();
