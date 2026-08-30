/* Fotografa a folha dos 5 estados com a animacao congelada num instante fixo.
 * Sem congelar, cada captura pega uma fase diferente do ciclo e duas folhas do
 * mesmo codigo saem diferentes. */
import { chromium } from 'playwright-core';
const [, , arquivo, saida, fase = '0.5'] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await b.newPage({ viewport: { width: 1500, height: 460 }, deviceScaleFactor: 2 });
await p.goto('file://' + arquivo, { waitUntil: 'load' });
await p.waitForTimeout(300);
// congela cada camada na fracao pedida do proprio ciclo
await p.evaluate((f) => {
  document.querySelectorAll('.solis-brilho').forEach((el) => {
    const dur = parseFloat(getComputedStyle(el).animationDuration) || 1;
    el.style.animationDelay = `${-dur * f}s`;
    el.style.animationPlayState = 'paused';
  });
}, Number(fase));
await p.waitForTimeout(200);
await p.screenshot({ path: saida });
await b.close();
