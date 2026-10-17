import { webkit } from "/Users/ak/Projects/quran-shield-pwa/node_modules/playwright/index.mjs";
const b = await webkit.launch();
for (const rm of ["no-preference", "reduce"]) {
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: rm });
  await p.goto("http://127.0.0.1:8765/index.html?data=fixtures/up.json");
  await p.waitForTimeout(300);
  const early = await p.evaluate(() => ({ dash: getComputedStyle(document.querySelector(".spark .line")).strokeDashoffset, anims: document.getAnimations().length }));
  await p.waitForTimeout(2500);
  const late = await p.evaluate(() => getComputedStyle(document.querySelector(".spark .line")).strokeDashoffset);
  await p.click("#stamp");
  const drops = await p.evaluate(() => document.querySelectorAll(".drop").length);
  console.log(rm, JSON.stringify({ early, late, drops }));
  await p.close();
}
await b.close();
