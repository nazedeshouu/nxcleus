import { useRef, type ReactNode, type PointerEvent } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  StackSimple,
  ListChecks,
  UsersThree,
} from "@phosphor-icons/react";

import { Logo } from "../brand/Logo";
import { BRAND } from "../brand/brand";
import { BoundaryDiagram } from "../components/landing/BoundaryDiagram";
import { Reveal } from "../components/ui/Reveal";
import heroImg from "../assets/hero-archive-crossing.jpg";
import wedgeImg from "../assets/img/wedge-dark.webp";
import fieldImg from "../assets/img/field-light.webp";
import styles from "./Landing.module.css";

// The platform app deploys separately at amdplatform.nxcleus.tech, but ONLY the
// dedicated landing host hands off cross-origin — on every other host (nxcleus.tech,
// sslip, localhost) this same SPA serves the platform routes, so stay in-app.
// Runtime host check, not a build-time flag: one bundle serves all hosts.
const CROSS_HOST = typeof window !== "undefined" && window.location.hostname === "amd.nxcleus.tech";
const PLATFORM_ORIGIN = CROSS_HOST ? "https://amdplatform.nxcleus.tech" : "";

function PlatformLink({ to, className, children }: { to: string; className?: string; children: ReactNode }) {
  return PLATFORM_ORIGIN ? (
    <a className={className} href={PLATFORM_ORIGIN + to}>{children}</a>
  ) : (
    <Link className={className} to={to}>{children}</Link>
  );
}

// The "Nx." landing wordmark: N + x in ink (flips on dark via tokens), the dot
// in accent. Landing header only; the platform keeps the <Logo> mark.
function Wordmark() {
  return (
    <span className={styles.wordmark} aria-label={BRAND.name}>
      Nx<span className={styles.wordmarkDot}>.</span>
    </span>
  );
}

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
  const heroRef = useRef<HTMLDivElement>(null);

  // Pointer-reactive hero: write cursor position (0..1) as CSS vars; the media
  // and light layers read them. No re-render, no deps. Motion is user-driven, so
  // it is exempt from the reduced-motion autoplay concern; the CSS still eases.
  function onHeroMove(e: PointerEvent<HTMLDivElement>) {
    const el = heroRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--px", String((e.clientX - r.left) / r.width));
    el.style.setProperty("--py", String((e.clientY - r.top) / r.height));
  }

  return (
    <div className={styles.page}>
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <Link to="/" aria-label={`${BRAND.name} home`}>
            <Wordmark />
          </Link>
          <nav className={styles.navLinks}>
            <a className={styles.navLink} href="#boundary">The boundary</a>
            <a className={styles.navLink} href="#lifecycle">Lifecycle</a>
            <a className={styles.navLink} href="#economics">Economics</a>
            <PlatformLink className={styles.navLink} to="/sandbox">Sandbox</PlatformLink>
          </nav>
          <PlatformLink to="/build" className={styles.navCta}>
            Enter the platform
            <span className={styles.btnCoin}><ArrowRight weight="bold" /></span>
          </PlatformLink>
        </div>
      </header>

      {/* ---------- hero: full-bleed cinematic, copy bottom-left ---------- */}
      <div className={styles.hero} ref={heroRef} onPointerMove={onHeroMove}>
        <div className={styles.heroMedia} aria-hidden="true">
          {/* HERO BACKGROUND — single swap point: replace the heroImg import (top of file) */}
          <img src={heroImg} alt="" width={1600} height={1200} fetchPriority="high" />
          <div className={styles.heroDrift} />
          <div className={styles.heroSoften} />
          <div className={styles.heroScrim} />
        </div>
        <div className={styles.heroHud} aria-hidden="true">
          <span className={styles.heroMeterLbl}>egress monitor</span>
          <span className={styles.heroMeterVal}><b>0</b> external calls</span>
        </div>
        <div className={styles.container}>
          <div className={styles.heroCopy}>
            <div className={styles.heroText}>
              <h1 className={styles.heroTitle}>
                Run frontier intelligence <em>inside your walls</em>.
              </h1>
              <p className={styles.heroSub}>
                Describe an internal process. Nxcleus builds and verifies it into a sovereign automation, yours to run
                forever.
              </p>
              <p className={styles.heroProof}>
                <b>AMD MI300X</b> · ROCm + vLLM · raw data crossings: <b>0</b>
              </p>
            </div>
            <div className={styles.heroCtas}>
              <PlatformLink to="/build" className={styles.btnPrimary}>
                Enter the platform
                <span className={styles.btnCoin}><ArrowRight weight="bold" /></span>
              </PlatformLink>
              <PlatformLink to="/sandbox" className={styles.btnSecondary}>
                Judge sandbox
              </PlatformLink>
            </div>
          </div>
        </div>
      </div>

      {/* ---------- boundary moment ---------- */}
      <section className={`${styles.container} ${styles.section} ${styles.boundary}`} id="boundary">
        <Reveal className={styles.boundaryHead}>
          <div className={styles.eyebrow}>The boundary</div>
          <h2 className={styles.sectionTitle}>
            One brief crosses. <em>Nothing else does.</em>
          </h2>
          <p className={styles.sectionLede}>
            Every raw record, document, and identifier stays sealed on your AMD hardware. A frontier planner
            sees only a sanitized brief, governed by your own confidentiality policy. Flip Sovereign Mode and
            even that crossing disappears.
          </p>
        </Reveal>
        <Reveal className={styles.boundaryStage}>
          <BoundaryDiagram />
        </Reveal>
      </section>

      {/* ---------- adaptive modes (bento) ---------- */}
      <section className={`${styles.container} ${styles.section} ${styles.planner}`}>
        <Reveal>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>
              The planner designs the right <span className={styles.shapeHi}>shape</span> for the work.
            </h2>
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
              <ul className={styles.leadFeats}>
                <li className={styles.leadFeat}><i /> Typed modules with declared interfaces</li>
                <li className={styles.leadFeat}><i /> Objective tests gate every ship</li>
                <li className={styles.leadFeat}><i /> Adversarial QA before it lands</li>
                <li className={styles.leadFeat}><i /> Versioned, re-runnable registry asset</li>
              </ul>
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
            <h2 className={`${styles.sectionTitle} ${styles.lifeTitle}`}>
              Build once. <em>Operate <span className={styles.forever}>forever</span>.</em> Refine on demand.
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
        <Reveal className={styles.money}>
          <div className={styles.moneyCopy}>
            <div className={styles.eyebrow}>The economics</div>
            <h2 className={styles.moneyStat}>
              Frontier intelligence is a <em>capital expense,</em> not a marginal cost.
            </h2>
            <p className={styles.moneyLede}>
              Paid once, at plan time, on sanitized specs. Every run after that is local and cheap. Competitors
              pay frontier tokens and surrender data on every single run.
            </p>
            <div className={styles.moneyPair}>
              <div className={styles.moneyItem}>
                <span className={styles.moneyItemK}>Nxcleus</span>
                <span className={styles.moneyItemV}>Build cost paid once, then flat local per-run.</span>
              </div>
              <div className={styles.moneyItem}>
                <span className={`${styles.moneyItemK} ${styles.moneyItemExt}`}>Chat / cloud agent</span>
                <span className={styles.moneyItemV}>Frontier tokens and data surrendered every run.</span>
              </div>
            </div>
          </div>
          <div className={styles.chartShell}>
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
          <div className={styles.wedgeArt} aria-hidden="true">
            <img src={wedgeImg} alt="" loading="lazy" width={1920} height={823} />
          </div>
          <p className={styles.wedgeKicker}>Inside the walls</p>
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
          <div className={styles.ctaArt} aria-hidden="true">
            <img src={fieldImg} alt="" loading="lazy" width={1920} height={823} />
          </div>
          <h2 className={styles.ctaTitle}>See a real process built, live.</h2>
          <p className={styles.ctaSub}>
            Watch a KYC pipeline get planned, certified, and verified in mission control. Or run your own prompt in
            the judge sandbox against synthetic bank, clinic, and law-firm data.
          </p>
          <div className={styles.ctaRow}>
            <PlatformLink to="/build" className={styles.btnPrimary}>
              Enter the platform
              <span className={styles.btnCoin}><ArrowRight weight="bold" /></span>
            </PlatformLink>
            <PlatformLink to="/sandbox" className={styles.btnSecondary}>
              Judge sandbox
            </PlatformLink>
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
            <PlatformLink className={styles.footerLink} to="/build">Platform</PlatformLink>
            <PlatformLink className={styles.footerLink} to="/operations">Operations</PlatformLink>
            <PlatformLink className={styles.footerLink} to="/sandbox">Sandbox</PlatformLink>
          </div>
        </div>
      </footer>
    </div>
  );
}
