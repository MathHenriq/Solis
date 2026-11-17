// Configurações → Voz → Escuta rápida: a linha nova, ligada e desligada, nos 3 temas × 2 navegações,
// e as medidas dela contra a linha de cima (a "Palavra de ativação", aprovada).
import { chromium } from 'playwright-core';
const [, , saida] = process.argv;
const b = await chromium.launch({ channel: 'msedge' });
const p = await b.newPage({ viewport: { width: 1440, height: 930 }, deviceScaleFactor: 1 });
async function abrir(tema, nav, rapida) {
  await p.goto('http://localhost:1421/');
  await p.evaluate(([t, n, r]) => {
    localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n);
    localStorage.setItem('solis.escuta.rapida', r ? '1' : '0');
  }, [tema, nav, rapida]);
  await p.goto('http://localhost:1421/', { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: '.animate-solis-horizon,.solis-ouvindo{animation:none!important}' });
  await p.getByRole('button', { name: 'Configurações' }).or(p.getByRole('link', { name: 'Configurações' })).first().click();
  await p.getByRole('heading', { name: 'Voz' }).waitFor();
  await p.waitForTimeout(600);
  await p.getByText('Escuta rápida', { exact: true }).first().evaluate((el) => el.scrollIntoView({ block: 'center' }));
  await p.mouse.move(5, 700);
  await p.waitForTimeout(300);
}
const medida = () => p.evaluate(() => {
  const r = (el) => (({ x, y, width, height }) => ({ x: Math.round(x), y: Math.round(y), w: Math.round(width), h: Math.round(height) }))(el.getBoundingClientRect());
  const linhaDe = (t) => [...document.querySelectorAll('main section div')].find((d) => d.firstElementChild?.textContent?.startsWith(t) && d.querySelector('[role=switch]'));
  const a = linhaDe('Palavra de ativação'), e = linhaDe('Escuta rápida');
  return { palavra: r(a), rapida: r(e), interruptorPalavra: r(a.querySelector('[role=switch]')), interruptorRapida: r(e.querySelector('[role=switch]')) };
});
for (const nav of ['sidebar', 'icones']) for (const tema of ['espacial', 'claro', 'dark']) for (const rapida of [true, false]) {
  await abrir(tema, nav, rapida);
  await p.screenshot({ path: `${saida}/er-${nav}-${tema}-${rapida ? 'ligada' : 'desligada'}.png` });
  if (tema === 'dark' && rapida) console.log('MEDIDAS', nav, JSON.stringify(await medida()));
}
await b.close();
console.log('ok');
