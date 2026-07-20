/**
 * Headless screenshot helper for Wave-2 DoD evidence.
 * Drives system Chrome via puppeteer-core against the running dev server so
 * live SSE views render before capture. Not shipped — dev tooling only.
 *
 *   node scripts/shoot.mjs <base> <out-dir> <name:path[:waitMs[:fullPage]]> ...
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [base, outDir, ...shots] = process.argv.slice(2);
if (!base || !outDir || shots.length === 0) {
  console.error("usage: shoot.mjs <base> <outDir> <name:path[:waitMs[:full]]> ...");
  process.exit(1);
}
mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb"],
});

for (const spec of shots) {
  const [name, path, waitMs = "2600", full = ""] = spec.split("::");
  const page = await browser.newPage();
  await page.setViewport({ width: 1512, height: 950, deviceScaleFactor: 2 });
  const url = `${base}${path}`;
  try {
    await page.goto(url, { waitUntil: "networkidle2", timeout: 20000 }).catch(() => {});
  } catch {
    /* SSE keeps the network busy; networkidle may never fire — that's fine */
  }
  await new Promise((r) => setTimeout(r, Number(waitMs)));
  const file = `${outDir}/${name}.png`;
  await page.screenshot({ path: file, fullPage: full === "full" });
  console.log(`shot ${name} <- ${url}  (${full === "full" ? "full" : "viewport"})`);
  await page.close();
}

await browser.close();
console.log("done");
