// A esfera (o visual da voz dentro do app): as tres fases paradas e a voz no pico, nos 3 temas
// e 2 navegacoes, a janela inteira. Sem microfone nem modelo: ?chamada=<fase> (so em dev).
import { chromium } from 'playwright-core';
const [, , saida] = process.argv;
const b = await chromium.launch({ channel: 'msedge' });
const p = await (await b.newContext({ viewport: { width: 1440, height: 930 }, deviceScaleFactor: 1 })).newPage();
const LEG = encodeURIComponent('Me lembra de pagar a luz amanhã.');
const RESP = encodeURIComponent('Anotei: pagar a luz amanhã. Te aviso às nove da manhã, antes de você sair.');

async function abrir(tema, nav, q) {
  await p.goto('http://localhost:1421/');
  await p.evaluate(([t, n]) => { localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n); }, [tema, nav]);
  await p.goto(`http://localhost:1421/?${q}`, { waitUntil: 'load' });
  await p.waitForSelector('.solis-esfera-fundo', { timeout: 8000 });
  await p.addStyleTag({ content: '.animate-solis-horizon{animation:none!important}' });
  await p.waitForTimeout(700);
}
// Congela as animações da esfera no tempo t (ms): o meio do ciclo é o pico.
const congelar = (t) => p.evaluate((t) => document.getAnimations().forEach((a) => {
  if (!a.effect?.target?.closest?.('.solis-esfera-fundo')) return;
  a.pause(); a.currentTime = t;
}), t);

for (const nav of ['sidebar', 'icones']) for (const tema of ['espacial', 'claro', 'dark']) {
  await abrir(tema, nav, 'chamada=ouvindo');
  await p.screenshot({ path: `${saida}/es-${nav}-${tema}-ouvindo-silencio.png` });
  // A voz no pico: o que o nivel.ts escreve no halo com a voz alta (opacity 1, scale 1,022).
  await p.evaluate(() => { const h = document.querySelector('.solis-esfera-halo'); h.style.opacity = '1'; h.style.transform = 'scale(1.022)'; });
  await p.waitForTimeout(150);
  await p.screenshot({ path: `${saida}/es-${nav}-${tema}-ouvindo-pico.png` });
  await abrir(tema, nav, `chamada=pensando&legenda=${LEG}`);
  await congelar(1200); // metade dos 2,4 s: o halo no pico do pensando
  await p.screenshot({ path: `${saida}/es-${nav}-${tema}-pensando.png` });
  await abrir(tema, nav, `chamada=respondendo&resposta=${RESP}`);
  await congelar(550); // metade dos 1,1 s
  await p.screenshot({ path: `${saida}/es-${nav}-${tema}-respondendo.png` });
}
const foco = await p.evaluate(() => document.hasFocus());
await b.close();
console.log('ok, foco da pagina:', foco);
