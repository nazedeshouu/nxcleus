import { useState } from "react";
import { NavLink, Outlet, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Broadcast } from "@phosphor-icons/react";
import { Logo } from "../../brand/Logo";
import { api } from "../../api/client";
import { useDemoToken } from "../../api/useDemoToken";
import { usePublicConfig } from "./usePublicConfig";
import { DemoUnlock } from "./DemoUnlock";
import styles from "./PlatformLayout.module.css";

const NAV = [
  { to: "/build", label: "Build" },
  { to: "/operations", label: "Operations" },
  { to: "/gallery", label: "Gallery" },
  { to: "/sandbox", label: "Sandbox" },
  { to: "/config", label: "Config" },
];

export function PlatformLayout() {
  const { config, isLive } = usePublicConfig();
  const sovereign = config.sovereign;
  const unlocked = useDemoToken();
  const qc = useQueryClient();
  const [toggling, setToggling] = useState(false);

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
    <div className={styles.app} data-temp="inside" data-sovereign={sovereign ? "true" : "false"}>
      <header className={styles.bar}>
        <div className={styles.left}>
          <Link to="/" className={styles.brand} aria-label="Nxcleus home">
            <Logo size={19} tone="invert" />
          </Link>
          <nav className={styles.nav}>
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ""}`}
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className={styles.right}>
          {config.fallback_serving && (
            <span className={styles.fallback} title="Serving via AMD-hosted Fireworks between fleet sessions">
              <Broadcast weight="fill" />
              Fallback serving
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
            {sovereign ? "Sovereign Mode" : "Standard"}
          </button>
          <span className={`${styles.conn} ${isLive ? styles.connLive : styles.connMock}`}>
            <i className={styles.pulse} />
            {isLive ? "Live" : "Demo stream"}
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
  );
}
