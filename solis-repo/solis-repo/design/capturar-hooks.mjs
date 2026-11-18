// Configurações → Hooks: a lista e o formulário aberto, 3 temas × 2 navegações, e as medidas contra o
// cartão de Servidores MCP logo acima (mesma grade). Na primeira volta, o caminho inteiro pela tela:
// adicionar, ver na lista, remover. Servidor de teste na 8766 com uma casa de teste (o settings.json
// do Matheus não é tocado) e a tela na 1421. Uso: node design/capturar-hooks.mjs <pasta-de-saída>
import { chromium } from 'playwright-core';
const [, , saida] = process.argv;
const b = await chromium.launch({ channel: 'msedge' });
const ctx = await b.newContext({ viewport: { width: 1440, height: 1500 }, deviceScaleFactor: 1 });
const p = await ctx.newPage();
const medir = () => p.evaluate(() => {
  const r = (el) => el && (({ x, y, width, height }) => ({ x: Math.round(x), y: Math.round(y), w: Math.round(width), h: Math.round(height) }))(el.getBoundingClientRect());
  const secao = (t) => [...document.querySelectorAll('section')].find((s) => s.querySelector('h2')?.textContent === t);
  const h = secao('Hooks');
  const m = secao('Servidores MCP');
  const cs = (el) => { const s = getComputedStyle(el); return { pad: s.padding, raio: s.borderRadius, mt: s.marginTop }; };
  const linhas = (s) => [...s.querySelectorAll('.border-t')].map((l) => ({ pt: getComputedStyle(l).paddingTop, mt: getComputedStyle(l).marginTop }));
  const campos = [...h.querySelectorAll('select, input')].map((c) => ({ rotulo: c.getAttribute('aria-label'), ...r(c), fonte: getComputedStyle(c).fontSize }));
  const botoes = [...h.querySelectorAll('button')].map((c) => ({ texto: c.textContent, ...r(c) }));
  return { hooks: { ...r(h), ...cs(h) }, mcp: { ...r(m), ...cs(m) }, linhasHooks: linhas(h), linhasMcp: linhas(m).slice(0, 2), campos, botoes };
});
let primeira = true;
for (const nav of ['sidebar', 'icones']) for (const tema of ['espacial', 'claro', 'dark']) {
  await p.goto('http://localhost:1421/');
  await p.evaluate(([t, n]) => { localStorage.setItem('solis.appearance.theme', t); localStorage.setItem('solis.appearance.nav', n); localStorage.setItem('solis.escuta', '0'); }, [tema, nav]);
  await p.goto('http://localhost:1421/', { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: '.animate-solis-horizon{animation:none!important}' });
  await p.locator('a[aria-label="Configurações"], a:has-text("Configurações")').first().click();
  const titulo = p.getByRole('heading', { name: 'Hooks', exact: true });
  await titulo.waitFor();
  const cartao = p.locator('section').filter({ has: titulo });
  await cartao.getByText('Antes de usar uma ferramenta').first().waitFor();
  await cartao.scrollIntoViewIfNeeded();
  if (primeira) {
    // O caminho inteiro: adicionar pela tela, ver na lista, remover.
    await cartao.getByRole('button', { name: 'Novo hook' }).click();
    await cartao.getByLabel('Quando roda').selectOption('PostToolUse');
    await cartao.getByLabel('Ferramenta').fill('Write|Edit');
    await cartao.getByLabel('Comando').fill('npx prettier --write');
    await cartao.getByRole('button', { name: 'Adicionar' }).click();
    await cartao.getByText('npx prettier --write').waitFor();
    console.log('ADICIONOU', JSON.stringify(await (await fetch('http://127.0.0.1:8766/hooks')).json().then((d) => d.hooks.map((h) => [h.evento, h.ferramenta, h.comando]))));
    const linhaNova = cartao.locator('.border-t').filter({ hasText: 'npx prettier --write' });
    await linhaNova.getByRole('button', { name: 'Remover' }).click();
    await linhaNova.getByRole('button', { name: 'Remover' }).click();
    await cartao.getByText('npx prettier --write').waitFor({ state: 'detached' });
    console.log('REMOVEU', JSON.stringify(await (await fetch('http://127.0.0.1:8766/hooks')).json().then((d) => d.hooks.length)));
    primeira = false;
  }
  await p.mouse.move(5, 5);
  await p.waitForTimeout(400);
  await cartao.screenshot({ path: `${saida}/hooks-${nav}-${tema}-lista.png` });
  await cartao.getByRole('button', { name: 'Novo hook' }).click();
  await p.mouse.move(5, 5);
  await p.waitForTimeout(400);
  await cartao.screenshot({ path: `${saida}/hooks-${nav}-${tema}-novo.png` });
  if (tema === 'dark') console.log('MEDIDAS', nav, JSON.stringify(await medir()));
}
await b.close();
console.log('ok');
