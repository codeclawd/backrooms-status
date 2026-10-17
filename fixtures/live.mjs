import { webkit } from "/Users/ak/Projects/quran-shield-pwa/node_modules/playwright/index.mjs";
const b = await webkit.launch();
for (const [w, hgt, scheme] of [[390, 844, "dark"], [1280, 720, "light"]]) {
  const p = await b.newPage({ viewport: { width: w, height: hgt }, colorScheme: scheme });
  const errs = []; p.on("pageerror", (e) => errs.push(e.message)); p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
  await p.goto("https://backrooms-status.pages.dev/");
  await p.waitForTimeout(3500);
  await p.screenshot({ path: `fixtures/shots/live-${w}-${scheme}.png` });
  console.log(w, scheme, await p.textContent("#hero-title"), "|", await p.textContent("#you-text"), "errors:", JSON.stringify(errs));
  await p.close();
}
await b.close();
