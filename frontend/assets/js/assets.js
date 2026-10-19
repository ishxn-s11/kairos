/* Config-driven asset system.
   Reads assets/img/manifest.json; for each stage exposes card/slide images.
   loadStageAssets(id, depth) resolves to { card, slides } containing ONLY
   entries whose images actually load (Image() probe), so a missing file or
   404 silently falls back to the generative art. Depth-relative: pages in
   work/ pass depth=1 so "assets/..." resolves to "../assets/...". */
(() => {
  const cache = new Map();

  function manifestURL(depth) {
    const pre = depth ? "../".repeat(depth) : "";
    return `${pre}assets/img/manifest.json`;
  }
  function assetURL(src, depth) {
    const pre = depth ? "../".repeat(depth) : "";
    // manifest paths are written relative to frontend root (assets/...)
    return src.startsWith("assets/") ? pre + src : src;
  }

  function probe(src) {
    return new Promise((resolve) => {
      const im = new Image();
      im.onload = () => resolve(true);
      im.onerror = () => resolve(false);
      im.src = src;
    });
  }

  async function loadStageAssets(id, depth = 0) {
    const key = `${id}@${depth}`;
    if (cache.has(key)) return cache.get(key);
    const entry = { card: null, slides: [], label: null, fit: "cover" };
    cache.set(key, entry);
    try {
      const res = await fetch(manifestURL(depth), { cache: "no-cache" });
      if (!res.ok) return entry;
      const manifest = await res.json();
      const st = manifest.stages && manifest.stages[id];
      if (!st) return entry;
      entry.fit = manifest.fit || "cover";
      entry.label = st.label || null;
      const wants = [];
      if (st.card) wants.push({ kind: "card", src: assetURL(st.card, depth), caption: "" });
      (st.slides || []).forEach((s) =>
        wants.push({ kind: "slide", src: assetURL(s.src, depth), caption: s.caption || "" }));
      const checks = await Promise.all(wants.map((w) => probe(w.src)));
      wants.forEach((w, i) => {
        if (!checks[i]) return;
        if (w.kind === "card") entry.card = { src: w.src };
        else entry.slides.push({ src: w.src, caption: w.caption });
      });
    } catch {
      /* manifest missing or malformed → all generative fallback */
    }
    return entry;
  }

  window.Assets = { loadStageAssets };
})();
