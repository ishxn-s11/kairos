"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "kairos-theme";

function currentTheme() {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export default function ThemeToggle({ compact = false }) {
  const [theme, setTheme] = useState("light");

  useEffect(() => {
    setTheme(currentTheme());
  }, []);

  const toggle = () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next;
    localStorage.setItem(STORAGE_KEY, next);
    setTheme(next);
    window.dispatchEvent(new CustomEvent("kairos-theme", { detail: next }));
  };

  const dark = theme === "dark";
  return (
    <button
      type="button"
      className={`theme-toggle${compact ? " compact" : ""}`}
      onClick={toggle}
      aria-label={`Switch to ${dark ? "light" : "dark"} theme`}
      title={`Switch to ${dark ? "light" : "dark"} theme`}
    >
      <span className="theme-icon" aria-hidden="true">{dark ? "☀" : "☾"}</span>
      {!compact ? <span>{dark ? "Light" : "Dark"}</span> : null}
    </button>
  );
}
