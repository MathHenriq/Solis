/* Fotografa a tela construída nos 3 temas — é o que sustenta qualquer
 * afirmação visual feita sobre o app. A Regra 2 do CLAUDE.md não aceita
 * "parecido": ou existe o pixel pra comparar com a referência, ou não existe
 * a afirmação.
 *
 *   npm run build && npx vite preview --port 4173
 *   node design/capturar-telas.mjs http://localhost:4173/ <pasta> [larg] [alt] [modo]
 *
 * modo:
 *   (vazio)  a tela como ela é
 *   fundo    esconde main e nav — sobra só a camada do horizonte, que é o que
 *            se mede pra contraste e pra altura do horizonte
 *   antes    reproduz a geometria ANTERIOR da cena (foto esticada na tela
 *            inteira, sem máscara) pra montar o antes/depois
 *
 * A animação de 90s é congelada no frame 0% (`animation-play-state: paused`
 * com delay zero) — sem isso duas capturas do mesmo tema saem com escala e
 * opacidade diferentes e nenhuma medição fecha com a outra.
 *
 * Precisa do playwright disponível no node_modules (não é dependência
 * declarada do app: isto aqui é ferramenta de validação, não roda no produto)
 * e do Chromium em /opt/pw-browsers. */
import { chromium } from 'playwright';

const [, , base, saida, larg = '1440', alt = '930', modo = ''] = process.argv;
const W = Number(larg), H = Number(alt);

const CONGELA = '.animate-solis-horizon{animation-delay:0s!important;animation-play-state:paused!important}';
const EXTRA = {
  fundo: 'main,nav{visibility:hidden!important}',
  antes: `:root{--solis-bg-position-y:50%}
          .cena-camada{left:0!important;top:0;height:100vh!important;
                       -webkit-mask-image:none!important;mask-image:none!important}`,
}[modo] || '';

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await b.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
for (const tema of ['espacial', 'claro', 'dark']) {
  await p.goto(base, { waitUntil: 'networkidle' });
  await p.addStyleTag({ content: CONGELA + EXTRA });
  await p.evaluate((t) => document.documentElement.setAttribute('data-theme', t), tema);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(400);
  const sufixo = modo ? `-${modo}` : '';
  await p.screenshot({ path: `${saida}/${tema}${sufixo}-${W}x${H}.png` });
  console.log(tema, modo || 'tela', 'ok');
}
await b.close();
