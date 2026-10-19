/* About page: lamp, section content, quick-nav swing + blackout flash. */
(() => {
  const { $, $$ } = U;
  const SECTIONS = DATA.SECTIONS;

  function fromHash() {
    const h = (location.hash || "").replace("#", "");
    return SECTIONS.findIndex((s) => s.id === h);
  }

  let current = fromHash();
  if (current < 0) current = 0;
  const sec = SECTIONS[current];

  /* lamp */
  $("#lamp").innerHTML = `
    <svg width="220" height="200" viewBox="0 0 220 200">
      <g>
        <rect x="98" y="0" width="4" height="26" fill="#cfcfcf"/>
        <rect x="86" y="26" width="28" height="4" fill="#e6e6e6"/>
        <g class="bulb-glow">
          <circle cx="110" cy="86" r="9" fill="#fff"/>
          <circle cx="110" cy="86" r="16" fill="#fff" opacity=".35"/>
          <circle cx="110" cy="86" r="26" fill="#fff" opacity=".12"/>
        </g>
        <path d="M110 30 L88 74 L132 74 Z" fill="#d9d9d9"/>
        <rect x="86" y="72" width="48" height="5" fill="#efefef"/>
        <g class="chain">
          <line x1="126" y1="60" x2="150" y2="120" stroke="#bbb" stroke-width="1.4"/>
          <circle cx="150" cy="122" r="4" fill="#cfcfcf"/>
        </g>
      </g>
    </svg>`;

  /* content */
  const [pre, post] = sec.kicker.split("|");
  $("#aKicker").innerHTML = `${pre}<span class="u">${post}</span>`;
  const copyEl = $("#aCopy");
  if (sec.mail) {
    const idx = sec.copy.indexOf(sec.mail);
    copyEl.innerHTML =
      sec.copy.slice(0, idx) +
      `<a class="more" href="mailto:${sec.mail}">${sec.mail}</a>` +
      sec.copy.slice(idx + sec.mail.length);
  } else {
    copyEl.textContent = sec.copy;
  }
  $("#giant").textContent = sec.giant;
  document.body.classList.add("lights-dim");

  /* quick nav */
  const nav = $("#aNav");
  SECTIONS.forEach((s, i) => {
    const a = document.createElement("a");
    a.href = `#${s.id}`;
    a.textContent = s.nav;
    if (i === current) a.classList.add("active");
    a.addEventListener("click", (e) => {
      e.preventDefault();
      swingTo(i);
    });
    nav.appendChild(a);
  });

  function setContent(i) {
    const s = SECTIONS[i];
    const [pre, post] = s.kicker.split("|");
    $("#aKicker").innerHTML = `${pre}<span class="u">${post}</span>`;
    const copyEl = $("#aCopy");
    if (s.mail) {
      const idx = s.copy.indexOf(s.mail);
      copyEl.innerHTML =
        s.copy.slice(0, idx) +
        `<a class="more" href="mailto:${s.mail}">${s.mail}</a>` +
        s.copy.slice(idx + s.mail.length);
    } else {
      copyEl.textContent = s.copy;
    }
    $("#giant").textContent = s.giant;
    $$("#aNav a").forEach((a, k) => a.classList.toggle("active", k === i));
    history.replaceState(null, "", `#${s.id}`);
    document.title = `${s.giant} — Buy or Wait? Financial Affordability Agent`;
  }

  function swingTo(i) {
    if (i === current) return;
    current = i;
    const lamp = $("#lamp"), cone = $("#cone");
    const targetX = (i - (SECTIONS.length - 1) / 2) * 2.6;
    const flash = document.createElement("div");
    flash.className = "blackflash";
    document.body.appendChild(flash);
    requestAnimationFrame(() => flash.classList.add("on"));
    lamp.style.transform = `translateX(-50%) rotate(${targetX}deg)`;
    cone.style.transform = `translateX(-50%) rotate(${targetX * 1.15}deg)`;
    const content = $("#aContent");
    if (content) content.classList.add("swap");
    setTimeout(() => { setContent(i); content.classList.remove("swap"); }, 430);
    setTimeout(() => flash.remove(), 820);
  }

  /* deep link updates on back/forward */
  addEventListener("hashchange", () => {
    const i = fromHash();
    if (i >= 0) swingTo(i);
  });

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.initEnter();
})();
