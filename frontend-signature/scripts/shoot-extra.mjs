/** One-off verification shots: sovereign chrome, replay, joblist, mobile landing. */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [base, outDir] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb"],
});

const shoot = async (name, path, { width = 1512, height = 950, waitMs = 3000, before } = {}) => {
  const page = await browser.newPage();
  await page.setViewport({ width, height, deviceScaleFactor: 2 });
  await page.goto(`${base}${path}`, { waitUntil: "networkidle2", timeout: 20000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, waitMs));
  if (before) await page.evaluate(before);
  await new Promise((r) => setTimeout(r, 700));
  await page.screenshot({ path: `${outDir}/${name}.png` });
  console.log(`shot ${name}`);
  await page.close();
};

await shoot("sovereign", "/build/demo", {
  waitMs: 4500,
  before: () => {
    const app = document.querySelector('[data-temp="inside"]');
    if (app) app.setAttribute("data-sovereign", "true");
  },
});
await shoot("joblist", "/build");
await shoot("landing-mobile", "/", { width: 390, height: 844, waitMs: 3200 });

await browser.close();
console.log("done");
