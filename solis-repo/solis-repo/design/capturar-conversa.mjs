// O modo Conversa na tela, com um microfone falso do navegador e o servidor de teste (um Gemini de
// mentira): a linha do tempo do visual, prints de ouvindo e falando, a troca salva na conversa e o Esc.
import { chromium } from 'playwright-core';
const [, , saida, tema = 'dark', nav = 'sidebar'] = process.argv;
const b = await chromium.launch({ channel: 'msedge', args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'] });
const ctx = await b.newContext({ viewport: { width: 1440, height: 930 }, deviceScaleFactor: 1, permissions: ['microphone'] });
const p = await ctx.newPage();
await p.goto('http://localhost:1421/');
await p.evaluate(([t, n]) => { localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n); localStorage.setItem('solis.escuta', '0'); }, [tema, nav]);
await p.goto('http://localhost:1421/', { waitUntil: 'networkidle' });
await p.addStyleTag({ content: '.animate-solis-horizon{animation:none!important}' });
const t0 = Date.now();
await p.evaluate(() => window.__conversa());
const linha = [];
let ultimo = '';
let viuOuvindo = false, viuFalando = false;
while (Date.now() - t0 < 6000) {
  const s = await p.evaluate(() => {
    const f = document.querySelector('.solis-esfera-fundo');
    return f ? `${f.getAttribute('data-fase')}|${f.querySelector('.solis-esfera-estado')?.textContent}|${f.querySelector('.solis-esfera-legenda')?.textContent}` : 'sem visual';
  });
  if (s !== ultimo) { linha.push(`${((Date.now() - t0) / 1000).toFixed(1)} s  ${s}`); ultimo = s; }
  if (!viuOuvindo && s.startsWith('ouvindo')) { viuOuvindo = true; await p.screenshot({ path: `${saida}/conversa-${nav}-${tema}-ouvindo.png` }); }
  if (!viuFalando && s.startsWith('respondendo')) { viuFalando = true; await p.screenshot({ path: `${saida}/conversa-${nav}-${tema}-falando.png` }); }
  await p.waitForTimeout(80);
}
console.log('LINHA DO TEMPO\n' + linha.join('\n'));
const naConversa = await p.evaluate(() => document.body.innerText.includes('Tudo ótimo! E com você?') && document.body.innerText.includes('Oi Solis, tudo bem?'));
console.log('troca salva e mostrada na conversa:', naConversa);
await p.keyboard.press('Escape');
await p.waitForTimeout(600);
console.log('depois do Esc, visual:', await p.evaluate(() => !!document.querySelector('.solis-esfera-fundo')));
await p.screenshot({ path: `${saida}/conversa-${nav}-${tema}-depois.png` });
await b.close();
