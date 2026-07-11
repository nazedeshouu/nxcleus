import { useState } from "react";
import { NavLink, Outlet, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  ShieldCheck, Broadcast, Cube, Stack, Flask, Terminal, Gear, Plus, SidebarSimple, CaretRight,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";
import { Logo } from "../../brand/Logo";
import { api } from "../../api/client";
import { useDemoToken } from "../../api/useDemoToken";
import { usePublicConfig } from "./usePublicConfig";
import { DemoUnlock } from "./DemoUnlock";
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
  const crumbs = useCrumbs();
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

export function PlatformLayout() {
  const { config, isLive } = usePublicConfig();
  const sovereign = config.sovereign;
  const unlocked = useDemoToken();
  const qc = useQueryClient();
  const [toggling, setToggling] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("nxcleus.rail") === "1"; } catch { return false; }
  });

  const toggleRail = () => {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem("nxcleus.rail", next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  };

  const toggleSovereign = async () => {
    if (!unlocked || toggling) return;
    setToggling(true);
    try {
      await api.setSovereign(!sovereign);
      await qc.invalidateQueries({ queryKey: ["config", "public"] });
    } catch {
      /* leave state as-is; the indicator reflects the server on next poll */
    } finally {
      setToggling(false);
    }
  };

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
            <div className={styles.right}>
              {config.fallback_serving && (
                <span className={styles.fallback} title="Serving via AMD-hosted Fireworks between fleet sessions">
                  <Broadcast weight="fill" />
                  <span className={styles.hideSm}>Fallback serving</span>
                </span>
              )}
              <button
                className={`${styles.sov} ${sovereign ? styles.sovOn : ""} ${unlocked ? styles.sovBtn : ""}`}
                onClick={toggleSovereign}
                disabled={!unlocked || toggling}
                title={unlocked ? "Toggle Sovereign Mode — zero external calls" : "Sovereign Mode (presenter-only toggle)"}
                aria-pressed={sovereign}
              >
                <ShieldCheck weight={sovereign ? "fill" : "regular"} />
                <span className={styles.hideSm}>{sovereign ? "Sovereign Mode" : "Standard"}</span>
              </button>
              <span className={`${styles.conn} ${isLive ? styles.connLive : styles.connMock}`}>
                <i className={styles.pulse} />
                <span className={styles.hideSm}>{isLive ? "Live" : "Demo stream"}</span>
              </span>
              <DemoUnlock />
            </div>
          </header>

          {sovereign && (
            <div className={styles.sovStrip} role="status">
              <ShieldCheck weight="fill" />
              <b>Sovereign Mode</b>
              <span>Zero external calls. Every seat routes to the local fleet — the boundary is sealed.</span>
            </div>
          )}

          <main className={styles.main}>
            <Outlet />
          </main>
        </div>
      </div>
    </BreadcrumbProvider>
  );
}
