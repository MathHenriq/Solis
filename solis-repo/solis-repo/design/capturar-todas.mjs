/* Fotografa todas as telas construídas, nos temas pedidos.
 *
 *   npm run build && npx vite preview --port 4173
 *   node design/capturar-todas.mjs http://localhost:4173/ <pasta> [tema]
 *
 * Congela a animação do horizonte: sem isso duas capturas do mesmo estado saem
 * com escala e opacidade diferentes e nenhuma comparação fecha. */
import { chromium } from 'playwright-core';

const [, , base, saida, tema = 'dark'] = process.argv;
const TELAS = ['conversa', 'memoria', 'modelos', 'ferramentas', 'tarefas', 'agenda', 'conhecimento', 'configuracoes'];
const CONGELA = '.animate-solis-horizon{animation-play-state:paused!important}';

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await b.newPage({ viewport: { width: 1440, height: 930 } });
const erros = [];
p.on('pageerror', (e) => erros.push(e.message));

await p.goto(base, { waitUntil: 'networkidle' });
await p.evaluate((t) => {
  localStorage.clear();
  localStorage.setItem('solis.appearance.theme', t);
}, tema);

for (const tela of TELAS) {
  await p.goto(base, { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: CONGELA });
  await p.evaluate((id) => {
    const alvo = [...document.querySelectorAll('nav a')].find((a) => a.getAttribute('href') === (id === 'conversa' ? '/' : `/${id}`));
    alvo?.click();
  }, tela);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(400);
  await p.screenshot({ path: `${saida}/${tela}-${tema}.png` });
}

// a Conversa tem dois estados: o segundo abre ao enviar
await p.goto(base, { waitUntil: 'networkidle' });
await p.addStyleTag({ content: CONGELA });
await p.evaluate(() => document.querySelector('main form')?.requestSubmit());
await p.waitForTimeout(400);
await p.screenshot({ path: `${saida}/thread-${tema}.png` });

console.log(tema, '—', erros.length ? erros : 'sem erro de runtime');
await b.close();
