// O botão do modo Conversa nas duas caixas (a da abertura e a da conversa aberta), 3 temas × 2
// navegações, e as medidas dele contra o microfone ao lado. A conversa aberta sai do próprio modo
// Conversa com o servidor de teste (um Gemini de mentira) e o microfone falso do navegador.
import { chromium } from 'playwright-core';
const [, , saida] = process.argv;
const b = await chromium.launch({ channel: 'msedge', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 930 }, deviceScaleFactor: 1, permissions: ['microphone'] });
const p = await ctx.newPage();
const medir = () => p.evaluate(() => {
  const r = (el) => el && (({ x, y, width, height }) => ({ x: Math.round(x), y: Math.round(y), w: Math.round(width), h: Math.round(height) }))(el.getBoundingClientRect());
  const conv = [...document.querySelectorAll('button[aria-label="Conversar por voz"], button[aria-label="Sair da conversa por voz"]')].map(r);
  const mic = [...document.querySelectorAll('button[aria-label="Falar"], button[aria-label="Parar de ouvir"]')].map(r);
  return { conversa: conv, microfone: mic };
});
for (const nav of ['sidebar', 'icones']) for (const tema of ['espacial', 'claro', 'dark']) {
  await p.goto('http://localhost:1421/');
  await p.evaluate(([t, n]) => { localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n); localStorage.setItem('solis.escuta', '0'); }, [tema, nav]);
  await p.goto('http://localhost:1421/', { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: '.animate-solis-horizon{animation:none!important}' });
  // O app abre a última conversa: a abertura é uma conversa nova.
  await p.getByRole('button', { name: 'Nova conversa' }).first().click();
  await p.waitForSelector('[placeholder^="Fale com o Solis"]');
  await p.mouse.move(5, 5);
  await p.waitForTimeout(500);
  await p.screenshot({ path: `${saida}/bc-${nav}-${tema}-abertura.png` });
  if (tema === 'dark') console.log('ABERTURA', nav, JSON.stringify(await medir()));
  // A conversa aberta: uma troca pelo modo Conversa, e Esc.
  await p.evaluate(() => window.__conversa());
  await p.waitForTimeout(3600);
  await p.screenshot({ path: `${saida}/bc-${nav}-${tema}-ativo.png` });
  await p.keyboard.press('Escape');
  await p.waitForTimeout(700);
  await p.mouse.move(5, 5);
  await p.screenshot({ path: `${saida}/bc-${nav}-${tema}-thread.png` });
  if (tema === 'dark') console.log('THREAD', nav, JSON.stringify(await medir()));
}
await b.close();
console.log('ok');
