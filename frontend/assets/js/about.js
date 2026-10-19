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
    <svg width="260" height="210" viewBox="0 0 260 210">
      <g>
        <rect x="127" y="0" width="6" height="22" fill="#cfcfcf"/>
        <rect x="108" y="20" width="44" height="5" fill="#e6e6e6"/>
        <path d="M130 25 L74 80 L186 80 Z" fill="#e8e8e8"/>
        <rect x="70" y="78" width="120" height="6" fill="#f2f2f2"/>
        <g class="bulb-glow">
          <circle cx="130" cy="97" r="48" fill="#fff" opacity=".07"/>
          <circle cx="130" cy="97" r="34" fill="#fff" opacity=".16"/>
          <circle cx="130" cy="97" r="22" fill="#fff" opacity=".42"/>
          <circle cx="130" cy="97" r="13" fill="#fff"/>
        </g>
        <g class="chain">
          <line x1="168" y1="84" x2="197" y2="150" stroke="#bbb" stroke-width="1.6"/>
          <circle cx="197" cy="154" r="5" fill="#d9d9d9"/>
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
    document.title = `${s.giant} — KAIROS — Financial Affordability Agent`;
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

  /* cursor torch: the darkness is a masked layer, the pointer carries the hole.
     The mask/glow gradients are re-written inline on every move, so the light
     lands exactly under the cursor (no rAF dependency — this must work even
     where rAF is throttled). */
  const dark = $("#torchDark");
  const glow = $(".torch-glow");

  const darkMask = (x, y) => `radial-gradient(circle clamp(270px, 32vw, 470px) at ${x}px ${y}px,
    rgba(0,0,0,0) 0 52%, rgba(0,0,0,.28) 70%, rgba(0,0,0,.74) 87%, #000 100%)`;
  const glowLight = (x, y) => `radial-gradient(circle clamp(220px, 27vw, 400px) at ${x}px ${y}px,
    rgba(255,244,212,.19) 0 32%, rgba(255,236,188,.085) 58%, rgba(255,230,180,0) 82%)`;

  const paintTorch = (x, y) => {
    const cx = Math.round(x);
    const cy = Math.round(y);
    dark.style.maskImage = darkMask(cx, cy);
    dark.style.webkitMaskImage = darkMask(cx, cy);
    if (glow) glow.style.background = glowLight(cx, cy);
  };

  paintTorch(innerWidth / 2, innerHeight * 0.46);
  addEventListener("pointermove", (e) => {
    paintTorch(e.clientX, e.clientY);
  }, { passive: true });
  addEventListener("resize", () => paintTorch(innerWidth / 2, innerHeight * 0.46));

  U.initChrome();
  U.initCursor();
  U.initGrain();
  U.initEnter();
})();
