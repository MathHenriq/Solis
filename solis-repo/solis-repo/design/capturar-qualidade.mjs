// Configurações → Taxa de acerto, 3 temas × 2 navegações, com as medidas do cartão contra o de Uso
// logo acima (mesma grade). Servidor de teste na 8766 com uma cópia do banco (só os números do
// registro aparecem) e a tela na 1421. Uso: node design/capturar-qualidade.mjs <pasta-de-saída>
import { chromium } from 'playwright-core';
const [, , saida] = process.argv;
const b = await chromium.launch({ channel: 'msedge' });
const ctx = await b.newContext({ viewport: { width: 1440, height: 1700 }, deviceScaleFactor: 1 });
const p = await ctx.newPage();
const medir = () => p.evaluate(() => {
  const r = (el) => el && (({ x, y, width, height }) => ({ x: Math.round(x), y: Math.round(y), w: Math.round(width), h: Math.round(height) }))(el.getBoundingClientRect());
  const secao = (t) => [...document.querySelectorAll('section')].find((s) => s.querySelector('h2')?.textContent === t);
  const q = secao('Taxa de acerto');
  const u = secao('Uso');
  const cs = (el) => { const s = getComputedStyle(el); return { pad: s.padding, raio: s.borderRadius, borda: s.borderTopColor, mt: s.marginTop }; };
  const linhas = [...q.querySelectorAll('.border-t')].map((l) => ({ ...r(l), pt: getComputedStyle(l).paddingTop, mt: getComputedStyle(l).marginTop,
    titulo: l.querySelector('span')?.textContent, fonte: getComputedStyle(l.querySelector('span')).fontSize }));
  const linhasUso = [...u.querySelectorAll('.border-t')].map((l) => ({ pt: getComputedStyle(l).paddingTop, mt: getComputedStyle(l).marginTop,
    fonte: getComputedStyle(l.querySelector('span')).fontSize }));
  return { cartao: { ...r(q), ...cs(q) }, uso: { ...r(u), ...cs(u) }, linhas, linhasUso,
    subtitulos: [...q.querySelectorAll('h3')].map((h) => ({ texto: h.textContent, fonte: getComputedStyle(h).fontSize, mt: getComputedStyle(h).marginTop })) };
});
for (const nav of ['sidebar', 'icones']) for (const tema of ['espacial', 'claro', 'dark']) {
  await p.goto('http://localhost:1421/');
  await p.evaluate(([t, n]) => { localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n); localStorage.setItem('solis.escuta', '0'); }, [tema, nav]);
  await p.goto('http://localhost:1421/', { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: '.animate-solis-horizon{animation:none!important}' });
  await p.locator('a[aria-label="Configurações"], a:has-text("Configurações")').first().click();
  const titulo = p.getByRole('heading', { name: 'Taxa de acerto' });
  await titulo.waitFor();
  await p.getByText('Testes de qualidade').waitFor();
  const cartao = p.locator('section').filter({ has: titulo });
  await cartao.scrollIntoViewIfNeeded();
  await p.evaluate(() => {
    const s = [...document.querySelectorAll('section')].find((x) => x.querySelector('h2')?.textContent === 'Uso');
    s.scrollIntoView({ block: 'start' });
  });
  await p.mouse.move(5, 5);
  await p.waitForTimeout(500);
  await cartao.screenshot({ path: `${saida}/qual-${nav}-${tema}.png` });
  if (tema === 'dark') console.log('MEDIDAS', nav, JSON.stringify(await medir()));
}
await b.close();
console.log('ok');
