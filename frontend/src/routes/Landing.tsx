import { Link } from "react-router-dom";
import {
  ArrowRight,
  ShieldCheck,
  GraphicsCard,
  Cpu,
  Broadcast,
  StackSimple,
  ListChecks,
  UsersThree,
} from "@phosphor-icons/react";

import { Logo } from "../brand/Logo";
import { BRAND } from "../brand/brand";
import { BoundaryDiagram } from "../components/landing/BoundaryDiagram";
import { Reveal } from "../components/ui/Reveal";
import heroImg from "../assets/img/hero.webp";
import styles from "./Landing.module.css";

function MoneyChart() {
  // Illustrative cost-vs-runs: a competitor pays every run (rising); Nxcleus pays
  // frontier once at build, then flat local per-run. Shape is the argument, not exact figures.
  const w = 420;
  const h = 240;
  const pad = 28;
  const runs = 10;
  const x = (i: number) => pad + (i / runs) * (w - pad * 2);
  const y = (v: number) => h - pad - v * (h - pad * 2);
  const competitor = Array.from({ length: runs + 1 }, (_, i) => [x(i), y(0.08 + i * 0.085)] as const);
  const nx = Array.from({ length: runs + 1 }, (_, i) => [x(i), y(i === 0 ? 0.62 : 0.62 + i * 0.006)] as const);
  const toPath = (pts: readonly (readonly [number, number])[]) => pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label="Illustrative cost per run: competitors rise every run; Nxcleus stays flat after the one-time build.">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="var(--hairline)" strokeWidth="1" />
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} stroke="var(--hairline)" strokeWidth="1" />
      <path d={toPath(competitor)} fill="none" stroke="var(--zone-external)" strokeWidth="2.4" strokeDasharray="5 5" />
      <path d={toPath(nx)} fill="none" stroke="var(--accent)" strokeWidth="2.8" strokeLinecap="round" />
      <circle cx={x(0)} cy={y(0.62)} r="4" fill="var(--accent)" />
      <text x={x(0) + 8} y={y(0.62) - 8} fontFamily="var(--font-mono)" fontSize="10" fill="var(--accent-strong)">build once</text>
      <text x={w - pad} y={h - pad + 16} textAnchor="end" fontFamily="var(--font-mono)" fontSize="9" fill="var(--text-faint)">runs over time →</text>
    </svg>
  );
}

export function Landing() {
  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <Link to="/" aria-label={`${BRAND.name} home`}>
            <Logo size={20} />
          </Link>
          <nav className={styles.navLinks}>
            <a className={styles.navLink} href="#boundary">The boundary</a>
            <a className={styles.navLink} href="#lifecycle">Lifecycle</a>
            <a className={styles.navLink} href="#economics">Economics</a>
            <Link className={styles.navLink} to="/sandbox">Sandbox</Link>
          </nav>
          <Link to="/build" className={styles.navCta}>
            Enter the platform <ArrowRight weight="bold" />
          </Link>
        </div>
      </header>

      {/* ---------- hero ---------- */}
      <section className={styles.container}>
        <div className={styles.hero}>
          <div className={styles.heroCopy}>
            <h1 className={styles.heroTitle}>
              Run frontier intelligence <em>inside your walls</em>.
            </h1>
            <p className={styles.heroSub}>
              Describe an internal process. Nxcleus builds and verifies it into a sovereign automation, yours to run
              forever.
            </p>
            <div className={styles.heroCtas}>
              <Link to="/build" className={styles.btnPrimary}>
                Enter the platform <ArrowRight weight="bold" />
              </Link>
              <Link to="/sandbox" className={styles.btnSecondary}>
                Judge sandbox
              </Link>
            </div>
          </div>
          <div className={styles.heroArt}>
            <img src={heroImg} alt="An abstract luminous interior separated from a darker exterior by a single precise threshold." width={1800} height={1350} fetchPriority="high" />
            <span className={styles.heroArtChip}>
              <ShieldCheck weight="fill" /> sovereign by design
            </span>
          </div>
        </div>
      </section>

      {/* ---------- AMD strip ---------- */}
      <section className={styles.container}>
        <div className={styles.amdStrip}>
          <span className={styles.amdLabel}>Runs entirely on AMD</span>
          <div className={styles.amdItems}>
            <span className={styles.amdItem}><GraphicsCard weight="fill" /> 8× MI300X fleet</span>
            <span className={styles.amdItem}><Cpu weight="fill" /> ROCm + vLLM</span>
            <span className={styles.amdItem}><Broadcast weight="fill" /> Fireworks <span className="muted">fallback only</span></span>
            <span className={styles.amdItem}>Live GPU telemetry in every build</span>
          </div>
        </div>
      </section>

      {/* ---------- boundary moment ---------- */}
      <section className={`${styles.container} ${styles.section}`} id="boundary">
        <Reveal>
          <div className={styles.sectionHead}>
            <div className={styles.eyebrow}>The boundary</div>
            <h2 className={styles.sectionTitle}>
              One brief crosses. <em>Nothing else does.</em>
            </h2>
            <p className={styles.sectionLede}>
              Every raw record, document, and identifier stays sealed on your AMD hardware. A frontier planner
              sees only a sanitized brief, governed by your own confidentiality policy. Flip Sovereign Mode and
              even that crossing disappears.
            </p>
          </div>
        </Reveal>
        <Reveal className={styles.boundaryWrap}>
          <BoundaryDiagram />
        </Reveal>
      </section>

      {/* ---------- adaptive modes (bento) ---------- */}
      <section className={`${styles.container} ${styles.section}`}>
        <Reveal>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>The planner designs the right shape for the work.</h2>
            <p className={styles.sectionLede}>One platform, three topologies, chosen per task and provisioned from the plan's own model bill of materials.</p>
          </div>
        </Reveal>
        <Reveal>
          <div className={styles.modes}>
            <div className={`${styles.mode} ${styles.modeLead}`}>
              <StackSimple weight="regular" className={styles.modeIcon} />
              <div className={styles.modeName}>Build mode</div>
              <p className={styles.modeDesc}>
                Construct a real process automation: typed modules, declared interfaces, objective tests. The
                fleet builds it in waves, a conductor reviews between each, and it lands in the registry ready to run.
              </p>
              <div className={styles.modeTag}>software plan → running process</div>
            </div>
            <div className={styles.mode}>
              <ListChecks weight="regular" className={styles.modeIcon} />
              <div className={styles.modeName}>Process mode</div>
              <p className={styles.modeDesc}>
                Fan local models across a corpus, one unit per worker, and aggregate into a dataset or dashboard.
              </p>
              <div className={styles.modeTag}>ten thousand contracts by morning</div>
            </div>
            <div className={styles.mode}>
              <UsersThree weight="regular" className={styles.modeIcon} />
              <div className={styles.modeName}>Semi-automated</div>
              <p className={styles.modeDesc}>
                Human-review steps designed in. The models do the pass; your people adjudicate the flags.
              </p>
              <div className={styles.modeTag}>queues and approvals</div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ---------- lifecycle ---------- */}
      <section className={`${styles.container} ${styles.section}`} id="lifecycle">
        <Reveal>
          <div className={styles.sectionHead}>
            <div className={styles.eyebrow}>The lifecycle</div>
            <h2 className={styles.sectionTitle}>
              Build once. <em>Operate forever.</em> Refine on demand.
            </h2>
          </div>
        </Reveal>
        <Reveal>
          <div className={styles.lifecycle}>
            <div className={styles.phase}>
              <div className={styles.phaseNode}><i /> Build</div>
              <div className={styles.phaseName}>Planned, certified, verified</div>
              <p className={styles.phaseDesc}>
                Frontier-planned on a sanitized brief, completed and certified locally against the raw context the
                frontier never saw, then built by the fleet and cleared by adversarial QA.
              </p>
            </div>
            <div className={`${styles.phase} ${styles.phaseHero}`}>
              <div className={styles.phaseNode}><i /> Operate</div>
              <div className={styles.phaseName}>Runs on new data, <em>fully local</em></div>
              <p className={styles.phaseDesc}>
                The certified process runs forever on customer hardware. Zero frontier calls, metered per run, with
                oracle spot-checks as a live warranty. This is where the economics compound.
              </p>
            </div>
            <div className={styles.phase}>
              <div className={styles.phaseNode}><i /> Refine</div>
              <div className={styles.phaseName}>Re-certified, versioned, diffed</div>
              <p className={styles.phaseDesc}>
                A change request re-opens planning under the same triage model. Every refinement ships a versioned,
                re-certified successor. Old versions stay runnable.
              </p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ---------- money slide ---------- */}
      <section className={`${styles.container} ${styles.section}`} id="economics">
        <Reveal>
          <div className={styles.money}>
            <div>
              <h2 className={styles.moneyStat}>
                Frontier intelligence is a <em>capital expense,</em> not a marginal cost.
              </h2>
              <p className={styles.moneyLede}>
                Paid once, at plan time, on sanitized specs. Every run after that is local and cheap. Competitors
                pay frontier tokens and surrender data on every single run.
              </p>
            </div>
            <div className={styles.chartCard}>
              <div className={styles.chartLegend}>
                <span className={styles.legendItem}>
                  <span className={styles.legendSwatch} style={{ background: "var(--accent)" }} /> Nxcleus, per run
                </span>
                <span className={styles.legendItem}>
                  <span className={styles.legendSwatch} style={{ background: "var(--zone-external)" }} /> Chat / cloud agent, per run
                </span>
              </div>
              <MoneyChart />
              <p className={styles.chartNote}>Illustrative. Build cost is paid once; local per-run cost stays flat.</p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ---------- wedge ---------- */}
      <section className={styles.container}>
        <Reveal className={styles.wedge} as="div">
          <p className={styles.wedgeQuote}>
            We operate <em>where external AI is banned.</em>
          </p>
          <p className={styles.wedgeSub}>
            Banks, insurers, healthcare, legal. The internal processes that cannot move to the cloud, running on
            hardware you control.
          </p>
        </Reveal>
      </section>

      {/* ---------- final CTA ---------- */}
      <section className={styles.container}>
        <div className={styles.cta}>
          <h2 className={styles.ctaTitle}>See a real process built, live.</h2>
          <p className={styles.ctaSub}>
            Watch a KYC pipeline get planned, certified, and verified in mission control. Or run your own prompt in
            the judge sandbox against synthetic bank, clinic, and law-firm data.
          </p>
          <div className={styles.ctaRow}>
            <Link to="/build" className={styles.btnPrimary}>
              Enter the platform <ArrowRight weight="bold" />
            </Link>
            <Link to="/sandbox" className={styles.btnSecondary}>
              Judge sandbox
            </Link>
          </div>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={`${styles.container} ${styles.footerInner}`}>
          <div>
            <Logo size={18} />
            <p className={styles.footerMeta} style={{ marginTop: 10 }}>
              {BRAND.tagline}. Built on AMD MI300X with ROCm and vLLM.
            </p>
          </div>
          <div className={styles.footerLinks}>
            <Link className={styles.footerLink} to="/build">Platform</Link>
            <Link className={styles.footerLink} to="/operations">Operations</Link>
            <Link className={styles.footerLink} to="/sandbox">Sandbox</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
