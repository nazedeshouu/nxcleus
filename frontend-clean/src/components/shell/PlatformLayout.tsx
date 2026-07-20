import { useEffect, useState } from "react";
import { NavLink, Outlet, Link, useLocation, Navigate, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Cube, Stack, Flask, Terminal, Gear, Plus, SidebarSimple, CaretRight, SignOut,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { Logo } from "../../brand/Logo";
import { setDemoToken } from "../../api/config";
import { authApi, type AuthSession } from "../../api/client";
import { MaturityBadge } from "../ui/MaturityBadge";
import { usePublicConfig } from "./usePublicConfig";
import { useAuth } from "./useAuth";
import { BreadcrumbProvider, useCrumbs } from "./breadcrumbs";
import styles from "./PlatformLayout.module.css";

const NAV: { to: string; label: string; icon: Icon }[] = [
  { to: "/build", label: "Build", icon: Cube },
  { to: "/operations", label: "Operations", icon: Stack },
  { to: "/sandbox", label: "Sandbox", icon: Flask },
  { to: "/traces", label: "Traces", icon: Terminal },
  { to: "/config", label: "Settings", icon: Gear },
];

function TopBar() {
  const published = useCrumbs();
  const { pathname } = useLocation();
  // top-level list routes publish no trail — fall back to the nav label so the bar is never empty
  const navLabel = NAV.find((n) => pathname === n.to || pathname.startsWith(`${n.to}/`))?.label;
  const crumbs = published.length ? published : navLabel ? [{ label: navLabel } as { label: string; to?: string }] : [];
  return (
    <div className={styles.crumbs} aria-label="Breadcrumb">
      {crumbs.map((c, i) => (
        <span key={i} className={styles.crumb}>
          {i > 0 && <CaretRight weight="bold" className={styles.crumbSep} />}
          {c.to && i < crumbs.length - 1 ? (
            <Link to={c.to} className={styles.crumbLink}>{c.label}</Link>
          ) : (
            <span className={i === crumbs.length - 1 ? styles.crumbHere : styles.crumbLink}>{c.label}</span>
          )}
        </span>
      ))}
    </div>
  );
}

function SessionChip({ session }: { session: AuthSession }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const signOut = async () => {
    try { await authApi.logout(); } catch { /* already gone */ }
    await qc.invalidateQueries({ queryKey: ["auth", "me"] });
    nav("/login", { replace: true });
  };
  return (
    <div className={styles.session}>
      <span className={styles.sessionName}>{session.username}</span>
      <span className={styles.sessionRole}>{session.role}</span>
      <button className={styles.signout} onClick={signOut} title="Sign out" aria-label="Sign out">
        <SignOut weight="regular" />
      </button>
    </div>
  );
}

export function PlatformLayout() {
  const { config } = usePublicConfig();
  const { session, needsLogin } = useAuth();
  const location = useLocation();
  const sovereign = config.sovereign; // backend-driven; default standard, no manual toggle
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("nxcleus.rail") === "1"; } catch { return false; }
  });

  // ponytail: hidden presenter unlock until real auth lands — ?presenter=<token> stores it, then strips the param
  useEffect(() => {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("presenter") ?? new URLSearchParams(url.hash.replace(/^#/, "")).get("presenter");
    if (!token) return;
    setDemoToken(token);
    url.searchParams.delete("presenter");
    url.hash = url.hash.replace(/[#&]?presenter=[^&]*/, "");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }, []);

  const toggleRail = () => {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem("nxcleus.rail", next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  };

  // real login wall: only trips when auth is enabled backend-side (dev/mock get a synthetic session)
  if (needsLogin) return <Navigate to="/login" state={{ from: location.pathname }} replace />;

  return (
    <BreadcrumbProvider>
      <div className={styles.app} data-temp="inside" data-sovereign={sovereign ? "true" : "false"} data-collapsed={collapsed ? "true" : "false"}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarTop}>
            <Link to="/" className={styles.brand} aria-label="Nxcleus home">
              <Logo size={19} tone="invert" markOnly={collapsed} />
            </Link>
            <button className={styles.railToggle} onClick={toggleRail} title={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-label="Toggle sidebar">
              <SidebarSimple weight="regular" />
            </button>
          </div>

          <NavLink to="/build" className={styles.cta}>
            <Plus weight="bold" />
            <span className={styles.ctaLabel}>New process</span>
          </NavLink>

          <nav className={styles.nav}>
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
                title={n.label}
              >
                <n.icon weight="regular" className={styles.linkIcon} />
                <span className={styles.linkLabel}>{n.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        <div className={styles.content}>
          <header className={styles.bar}>
            <TopBar />
            <div className={styles.headRight}>
              <MaturityBadge label="Preview build" tip="Demo build — not production-ready" />
              {session?.auth_enabled && <SessionChip session={session} />}
            </div>
          </header>

          <main className={styles.main}>
            <Outlet />
          </main>
        </div>
      </div>
    </BreadcrumbProvider>
  );
}
