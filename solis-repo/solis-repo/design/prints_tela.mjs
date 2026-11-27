// Os prints de uma tela da navegação (Memória, Modelos locais...) nos 3 temas × 2
// navegações, pra conferência e aprovação do Matheus (CLAUDE.md, passo 3 do
// fluxo). A Conversa tem o script próprio (prints_conversa.mjs), por causa dos
// estados vazia e thread.
//
// Roda contra o servidor de teste (o modo servidor serve o dist/ já construído):
//   npm run build
//   node design/prints_tela.mjs http://localhost:8766 <token> <pasta> Memória [n]
//
// Com [n], tira também, no dark com a barra lateral, o print com o mouse sobre a
// n-ésima linha da lista (.vn-linha, .ag-linha na Agenda, o cartão no
// Conhecimento; o hover). Mede as caixas principais e grava em
// medidas.json.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright';

const [base = 'http://localhost:8766', token = '', pasta = 'prints', tela = 'Memória', linha] = process.argv.slice(2);
mkdirSync(pasta, { recursive: true });
const nome = tela
  .normalize('NFD')
  .replace(/[̀-ͯ]/g, '')
  .toLowerCase()
  .replace(/\s+/g, '-');

// O Edge do Windows, sem janela: não precisa baixar o navegador do Playwright.
const navegador = await chromium.launch({ channel: 'msedge', headless: true });
const medidas = {};
for (const tema of ['dark', 'claro', 'espacial']) {
  for (const nav of ['sidebar', 'icones']) {
    const contexto = await navegador.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    const url = new URL(base);
    if (token) await contexto.addCookies([{ name: 'solis_token', value: token, domain: url.hostname, path: '/' }]);
    await contexto.addInitScript(
      ([t, n]) => {
        localStorage.setItem('solis.appearance.theme', t);
        localStorage.setItem('solis.appearance.nav', n);
      },
      [tema, nav],
    );
    const pagina = await contexto.newPage();
    await pagina.goto(base, { waitUntil: 'networkidle' });
    // O item é um link (<a>) nos dois modos: na barra lateral pelo texto, na de
    // ícones pelo aria-label.
    await pagina.getByRole('link', { name: tela, exact: true }).first().click();
    await pagina.waitForTimeout(1200);
    await pagina.mouse.move(1, 450); // o mouse fora da lista: sem hover
    await pagina.waitForTimeout(300);
    await pagina.screenshot({ path: join(pasta, `${tema}-${nav}-${nome}.png`) });

    if (linha && tema === 'dark' && nav === 'sidebar') {
      await pagina.locator('main .vn-linha, main .ag-linha, main article').nth(Number(linha) - 1).hover();
      await pagina.waitForTimeout(400);
      await pagina.screenshot({ path: join(pasta, `${tema}-${nav}-${nome}-hover.png`) });
    }

    medidas[`${tema}-${nav}`] = await pagina.evaluate(() => {
      const caixa = (e) => {
        if (!e) return null;
        const b = e.getBoundingClientRect();
        return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)];
      };
      const q = (s) => caixa(document.querySelector(s));
      return {
        main: q('main'),
        titulo: q('main h1'),
        busca: caixa(document.querySelector('main input')?.parentElement),
        linha: q('main .vn-linha, main .ag-linha, main article'),
      };
    });
    await contexto.close();
  }
}
await navegador.close();
writeFileSync(join(pasta, 'medidas.json'), JSON.stringify(medidas, null, 2));
console.log(JSON.stringify(medidas));
