/** Hardening-wave verification shots (mock/empty data; timed to catch the clarify beat). */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [base, outDir] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });

const KYC = "job_01JKYCDEMO0000000000000001";

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb"],
});

const shoot = async (name, path, { width = 1512, height = 950, waitMs = 3000, full = false, waitText } = {}) => {
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 2 });
  await page.goto(`${base}${path}`, { waitUntil: "networkidle2", timeout: 20000 }).catch(() => {});
  if (waitText) {
    await page
      .waitForFunction((t) => document.body.innerText.includes(t), { timeout: 8000 }, waitText)
      .catch(() => {});
    await new Promise((r) => setTimeout(r, 250));
  } else {
    await new Promise((r) => setTimeout(r, waitMs));
  }
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: full });
  console.log(`shot ${name}`);
  await page.close();
};

// clarify panel parks the replay for ~2.6s — wait for its heading, not a timer
await shoot("hardening-clarify", `/build/${KYC}`, { waitText: "A few decisions before we build" });
// full cockpit after the replay settles: now strip, certify panel, probe board, sweep
await shoot("hardening-cockpit", `/build/${KYC}`, { waitMs: 16000, full: true });
await shoot("hardening-traces", "/traces", { waitMs: 2000 });
await shoot("hardening-config", "/config", { waitMs: 2200, full: true });
await shoot("hardening-sandbox", "/sandbox", { waitMs: 2600, full: true });

await browser.close();
console.log("done");
