// Load every tab of site/ at desktop and phone width; report console errors and horizontal overflow; save screenshots.
// Usage: node scripts/check_dashboard.js <outdir>   (serves site/ on :8765 itself)
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");
const out = process.argv[2] || "/tmp";
const tabs = ["overview", "central-banks", "liquidity", "consumer", "cycle", "inflation", "markets", "outlook", "research", "reports", "data"];
(async () => {
  const srv = spawn("python3", ["-m", "http.server", "8765", "-d", path.join(__dirname, "..", "site")], { stdio: "ignore" });
  await new Promise(r => setTimeout(r, 1200));
  const browser = await chromium.launch();
  let problems = 0;
  for (const [name, vp, scheme] of [["desktop", { width: 1440, height: 1000 }, "light"], ["phone", { width: 390, height: 844 }, "dark"]]) {
    const page = await browser.newPage({ viewport: vp, colorScheme: scheme });
    const errs = [];
    page.on("console", m => { if (m.type() === "error") errs.push(m.text()); });
    page.on("pageerror", e => errs.push(String(e)));
    for (const t of tabs) {
      await page.goto(`http://localhost:8765/#${t}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(400);
      const o = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth,
        empty: document.querySelectorAll(".chart .empty").length, charts: document.querySelectorAll(".chart svg").length,
        failed: [...document.querySelectorAll("section.view > p.empty")].map(e => e.textContent) }));
      const flag = o.sw > o.cw + 1 || o.failed.length;
      if (flag) problems++;
      console.log(`${name} ${t.padEnd(14)} charts ${o.charts} emptyCharts ${o.empty} overflow ${o.sw - o.cw}px ${o.failed.join(" ")}`);
      if (["overview", "liquidity", "markets", "outlook"].includes(t) || name === "phone" && t === "overview")
        await page.screenshot({ path: `${out}/${name}-${t}.png`, fullPage: t !== "research" });
    }
    if (errs.length) { problems++; console.log(`${name} console errors:`, errs.slice(0, 5)); }
    await page.close();
  }
  await browser.close(); srv.kill();
  console.log(problems ? `PROBLEMS: ${problems}` : "OK: no console errors, no horizontal overflow");
})();
