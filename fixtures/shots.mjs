import { chromium, webkit } from "/Users/ak/Projects/quran-shield-pwa/node_modules/playwright/index.mjs";
const out = process.env.HOME + "/Projects/backrooms-status/fixtures/shots/";
const runs = [["up", 1280, 900, "dark"], ["up", 390, 844, "dark"], ["up", 1440, 900, "light"], ["degraded", 390, 844, "light"], ["down", 1366, 768, "dark"], ["appdown", 390, 844, "dark"], ["stale", 390, 844, "light"], ["up", 390, 844, "dark", "offline"]];
for (const [engine, name] of [[webkit, "webkit"]]) {
  const b = await engine.launch();
  for (const [fx, w, hgt, scheme, block] of runs) {
    const p = await b.newPage({ viewport: { width: w, height: hgt }, colorScheme: scheme });
    if (block) await p.route("https://backrooms.up.railway.app/**", (r) => r.abort());
    const errs = []; p.on("pageerror", (e) => errs.push(e.message)); p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
    await p.goto(`http://127.0.0.1:8765/index.html?data=fixtures/${fx}.json`);
    await p.waitForTimeout(2600);
    await p.screenshot({ path: `${out}${fx}-${w}-${scheme}${block ? "-" + block : ""}.png`, fullPage: true });
    console.log(name, fx, w, scheme, "errors:", JSON.stringify(errs));
    await p.close();
  }
  await b.close();
}
