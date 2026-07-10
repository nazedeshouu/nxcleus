/** Full-page screenshots that scroll first so IntersectionObserver reveals fire. */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const [base, outDir, ...shots] = process.argv.slice(2);
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
  await page.goto(`${base}${path}`, { waitUntil: "networkidle2", timeout: 20000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, Number(waitMs)));
  // scroll through the page in viewport steps so every reveal fires
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.85;
    for (let y = 0; y <= document.body.scrollHeight; y += step) {
      window.scrollTo({ top: y, behavior: "instant" });
      await new Promise((r) => setTimeout(r, 160));
    }
    window.scrollTo({ top: 0, behavior: "instant" });
    await new Promise((r) => setTimeout(r, 900));
  });
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: full === "full" });
  console.log(`shot ${name}`);
  await page.close();
}
await browser.close();
console.log("done");
