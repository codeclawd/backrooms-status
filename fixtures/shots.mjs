import { chromium, webkit } from "playwright";
const out = process.env.HOME + "/Projects/backrooms-status/fixtures/shots/";
const runs = [["up", 1280, 900, "light"], ["up", 390, 844, "light"], ["degraded", 390, 844, "dark"], ["down", 1280, 720, "dark"], ["cap", 390, 844, "light"], ["stale", 390, 844, "light"], ["up", 390, 844, "light", "offline"]];
for (const [engine, name] of [[webkit, "webkit"]]) {
  const b = await engine.launch();
  for (const [fx, w, hgt, scheme, block] of runs) {
    const p = await b.newPage({ viewport: { width: w, height: hgt }, colorScheme: scheme });
    if (block) await p.route("https://backrooms-1k7.pages.dev/**", (r) => r.abort());
    const errs = []; p.on("pageerror", (e) => errs.push(e.message)); p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
    await p.goto(`http://127.0.0.1:8765/index.html?data=fixtures/${fx}.json`);
    await p.waitForTimeout(1500);
    await p.screenshot({ path: `${out}${fx}-${w}-${scheme}${block ? "-" + block : ""}.png`, fullPage: true });
    console.log(name, fx, w, scheme, "errors:", JSON.stringify(errs));
    await p.close();
  }
  await b.close();
}
