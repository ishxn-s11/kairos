"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { initChrome, initCursor, initGrain, initEnter } from "../lib/client";

/* Runs the shared chrome behaviors once per page, client-side only. */
export default function Boot() {
  const pathname = usePathname() || "/";

  useEffect(() => {
    initChrome();
    initCursor();
    initGrain();
    initEnter();
  }, [pathname]);

  return null;
}
