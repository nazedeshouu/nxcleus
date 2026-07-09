import { NavLink, Outlet, Link } from "react-router-dom";
import { ShieldCheck, Broadcast } from "@phosphor-icons/react";
import { Logo } from "../../brand/Logo";
import { usePublicConfig } from "./usePublicConfig";
import { DemoUnlock } from "./DemoUnlock";
import styles from "./PlatformLayout.module.css";

const NAV = [
  { to: "/build", label: "Build" },
  { to: "/operations", label: "Operations" },
  { to: "/gallery", label: "Gallery" },
  { to: "/sandbox", label: "Sandbox" },
];

export function PlatformLayout() {
  const { config, isLive } = usePublicConfig();
  const sovereign = config.sovereign;

  return (
    <div className={styles.app} data-sovereign={sovereign ? "true" : "false"}>
      <header className={styles.bar}>
        <div className={styles.left}>
          <Link to="/" className={styles.brand} aria-label="Nxcleus home">
            <Logo size={19} tone={sovereign ? "invert" : "default"} />
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
          <span className={`${styles.sov} ${sovereign ? styles.sovOn : ""}`}>
            <ShieldCheck weight={sovereign ? "fill" : "regular"} />
            {sovereign ? "Sovereign Mode" : "Standard"}
          </span>
          <span className={`${styles.conn} ${isLive ? styles.connLive : styles.connMock}`}>
            <i className={styles.pulse} />
            {isLive ? "Live" : "Demo stream"}
          </span>
          <DemoUnlock />
        </div>
      </header>

      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
