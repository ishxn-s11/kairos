"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LIVE } from "../lib/live-api";
import { authHeaders, clearSession, getStoredUser } from "../lib/session";

export default function AccountNav() {
  const [user, setUser] = useState(null);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      const cached = getStoredUser();
      if (active) setUser(cached);
      if (!authHeaders().Authorization) return;
      try {
        const res = await fetch(`${LIVE.apiBase()}/api/auth/me`, { headers: authHeaders() });
        if (!res.ok) throw new Error("session expired");
        const body = await res.json();
        if (active) setUser(body.user || null);
        if (body.user) localStorage.setItem("kairos-user", JSON.stringify(body.user));
      } catch {
        clearSession();
        if (active) setUser(null);
      }
    };
    refresh();
    const onChange = () => refresh();
    addEventListener("kairos-auth", onChange);
    return () => { active = false; removeEventListener("kairos-auth", onChange); };
  }, []);

  const initials = user?.name
    ? user.name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase()
    : null;

  return (
    <Link className={`account-nav${user ? " signed-in" : ""}`} href="/account" aria-label={user ? `Open ${user.name}'s account` : "Log in or register"}>
      {initials ? <span className="account-avatar">{initials}</span> : <span className="account-avatar guest">↗</span>}
      <span className="account-label">{user ? user.name.split(" ")[0] : "Log in"}</span>
    </Link>
  );
}
