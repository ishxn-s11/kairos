"use client";

import { usePathname } from "next/navigation";
import { wipeNavigate } from "../lib/client";
import ThemeToggle from "./ThemeToggle";
import AccountNav from "./AccountNav";

export default function Chrome() {
  const pathname = usePathname() || "/";
  const page = pathname.startsWith("/about") ? "about"
    : pathname.startsWith("/results") ? "results"
    : pathname.startsWith("/workflow") ? "workflow"
    : pathname.startsWith("/test") ? "test"
    : pathname.startsWith("/account") ? "account"
    : pathname.startsWith("/work") ? "work" : "home";

  const go = (e, href) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    if (href.startsWith("#")) return;
    e.preventDefault();
    wipeNavigate(href.replace(/\/$/, "") + "/", page);
  };

  if (page === "home") return null;

  return (
    <header className="chrome">
      <a className="brand" href="/" onClick={(e) => go(e, "/")}>Kairos<span className="dot">.</span></a>
      <nav>
        <a className={"uline" + (page === "workflow" ? " active" : "")} href="/workflow" onClick={(e) => go(e, "/workflow")}>Workflow</a>
        <a className={"uline" + (page === "results" ? " active" : "")} href="/results" onClick={(e) => go(e, "/results")}>Results</a>
        <a className={"uline" + (page === "test" ? " active" : "")} href="/test" onClick={(e) => go(e, "/test")}>Test bench</a>
        <a className={"uline" + (page === "about" ? " active" : "")} href="/about" onClick={(e) => go(e, "/about")}>About</a>
      </nav>
      <div className="right">
        <AccountNav />
        <ThemeToggle compact />
        <a className="chrome-cta" href="/test" onClick={(e) => go(e, "/test")}>Try the agent</a>
        <button id="soundToggle">SOUND — <span id="soundWord">OFF</span><span className="eq"><i></i><i></i><i></i></span></button>
      </div>
    </header>
  );
}
