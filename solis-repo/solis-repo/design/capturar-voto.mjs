// O voto na resposta (👍/👎): no hover e votado, 3 temas × 2 navegações, e as medidas dos botões
// da fileira (Copiar, os dois polegares, Refazer). Servidor de teste na 8766 (cérebro de mentira,
// banco temporário) e a tela na 1421. Uso: node design/capturar-voto.mjs <pasta-de-saída>
import { chromium } from 'playwright-core';
const [, , saida] = process.argv;
const b = await chromium.launch({ channel: 'msedge' });
const ctx = await b.newContext({ viewport: { width: 1440, height: 930 }, deviceScaleFactor: 1 });
const p = await ctx.newPage();
const medir = () => p.evaluate(() => {
  const r = (el) => el && (({ x, y, width, height }) => ({ x: Math.round(x), y: Math.round(y), w: Math.round(width), h: Math.round(height) }))(el.getBoundingClientRect());
  const nomes = ['Copiar a resposta', 'Resposta boa', 'Tirar o voto', 'Resposta ruim', 'Refazer a resposta'];
  const bts = [...document.querySelectorAll('button')].filter((x) => nomes.includes(x.getAttribute('aria-label'))).slice(-4);
  return bts.map((x) => ({ rotulo: x.getAttribute('aria-label'), ...r(x), opacidade: getComputedStyle(x).opacity, cor: getComputedStyle(x).color,
    icone: r(x.querySelector('svg')) }));
});
let primeira = true;
for (const nav of ['sidebar', 'icones']) for (const tema of ['espacial', 'claro', 'dark']) {
  await p.goto('http://localhost:1421/');
  await p.evaluate(([t, n]) => { localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n); localStorage.setItem('solis.escuta', '0'); }, [tema, nav]);
  await p.goto('http://localhost:1421/', { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: '.animate-solis-horizon{animation:none!important}' });
  if (primeira) {
    // Uma troca de verdade com o servidor de teste: a resposta chega com o id no `fim`.
    await p.getByRole('button', { name: 'Nova conversa' }).first().click();
    const campo = p.locator('[placeholder^="Fale com o Solis"]').first();
    await campo.fill('Me explica o que é o registro de uso');
    await campo.press('Enter');
    primeira = false;
  }
  const boa = p.getByRole('button', { name: 'Resposta boa' }).last();
  await boa.waitFor({ state: 'attached', timeout: 30000 });
  await p.waitForTimeout(600);
  // No hover da resposta: a fileira inteira aparece.
  const resposta = p.locator('.group').filter({ has: boa }).last();
  await resposta.hover();
  await p.waitForTimeout(400);
  await p.screenshot({ path: `${saida}/voto-${nav}-${tema}-hover.png` });
  if (tema === 'dark') console.log('HOVER', nav, JSON.stringify(await medir()));
  // Votado, e o mouse fora: só o polegar escolhido fica à vista.
  await boa.click();
  await p.waitForTimeout(500);
  await p.mouse.move(5, 5);
  await p.waitForTimeout(400);
  await p.screenshot({ path: `${saida}/voto-${nav}-${tema}-votado.png` });
  if (tema === 'dark') console.log('VOTADO', nav, JSON.stringify(await medir()));
  // Tira o voto: a próxima volta começa igual.
  await p.getByRole('button', { name: 'Tirar o voto' }).last().click();
  await p.waitForTimeout(400);
}
// O voto chegou no servidor (e saiu): o registro diz.
console.log('QUALIDADE', JSON.stringify(await (await fetch('http://127.0.0.1:8766/qualidade')).json()));
await b.close();
console.log('ok');
