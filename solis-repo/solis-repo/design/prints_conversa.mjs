// Os prints da Conversa nos 3 temas × 2 navegações × 2 estados (vazia e com a
// thread), pra conferência e aprovação do Matheus (CLAUDE.md, passo 3 do fluxo).
//
// Roda contra o servidor de teste (o modo servidor serve o dist/ já construído):
//   npm run build
//   node design/prints_conversa.mjs http://localhost:8766 <token> <pasta> ["título da conversa"]
//
// Na thread, abre a conversa pelo título na lista (na barra lateral, ou na gaveta
// do modo ícones). Também mede as caixas principais e grava em medidas.json.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from 'playwright';

const [base = 'http://localhost:8766', token = '', pasta = 'prints', titulo = 'Visual novo · exemplo'] = process.argv.slice(2);
mkdirSync(pasta, { recursive: true });

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
    // O app reabre a última conversa: a vazia é a de uma conversa nova.
    await pagina.getByRole('button', { name: 'Nova conversa' }).first().click();
    await pagina.waitForTimeout(1200);
    await pagina.screenshot({ path: join(pasta, `${tema}-${nav}-vazia.png`) });

    if (nav === 'icones') await pagina.getByRole('button', { name: 'Conversas' }).click();
    await pagina.getByRole('button', { name: titulo }).first().click();
    await pagina.waitForTimeout(1500);
    await pagina.mouse.move(1, 450); // o hover fora das falas: as ações somem
    await pagina.waitForTimeout(300);
    await pagina.screenshot({ path: join(pasta, `${tema}-${nav}-thread.png`) });
    medidas[`${tema}-${nav}`] = await pagina.evaluate(() => {
      const caixa = (s) => {
        const e = document.querySelector(s);
        if (!e) return null;
        const b = e.getBoundingClientRect();
        return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)];
      };
      return {
        caixa: caixa('.composer-solis'),
        voz: caixa('.caixa-voz'),
        coluna: caixa('main .flex-1.overflow-y-auto > div'),
        horizonte: caixa('.cena-camada'),
      };
    });
    await contexto.close();
  }
}
await navegador.close();
writeFileSync(join(pasta, 'medidas.json'), JSON.stringify(medidas, null, 2));
console.log(JSON.stringify(medidas));
