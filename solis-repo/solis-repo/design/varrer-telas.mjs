/* Varredura de fechamento: toda tela, todo tema, procurando o que só aparece
 * quando se olha tudo junto.
 *
 *   npm run build && npx vite preview --port 4173
 *   node design/varrer-telas.mjs http://localhost:4173/
 *
 * Checa quatro coisas que passam despercebidas numa tela só:
 *   - erro de runtime em qualquer combinação de tela e tema;
 *   - estouro horizontal (conteúdo mais largo que a janela);
 *   - ROLAGEM DA PÁGINA (conteúdo mais alto que a janela) — o Solis é um app: o
 *     que rola é a área de conteúdo, nunca o documento. Uma barra de rolagem no
 *     documento significa que algum bloco de altura fixa não coube;
 *   - contraste de CADA texto contra o fundo que ele realmente tem, medido no
 *     DOM e não no token — é o que pega o texto que herdou a cor errada.
 *
 * O critério é 4,5:1, o mesmo do resto do projeto. Texto grande não ganha
 * desconto: todos os outros tokens de texto do sistema cumprem 4,5:1.
 *
 * Roda em DUAS janelas e nos DOIS modos de navegação. 1440x930 é a janela de
 * referência, onde tudo foi medido; 1532x693 é a que um navegador entrega de
 * verdade num notebook de 1920x1080 a 125% de escala, depois de descontar aba e
 * barra de endereço — foi ela que revelou que a sidebar precisava de 769px de
 * altura e fazia a página rolar.
 *
 * Os dois modos de nav porque a varredura só cobria a sidebar, e o modo 'icones'
 * tem geometria própria: cabeçalho fixo no topo, cápsula flutuante embaixo e o
 * respiro que os dois exigem. Foi exatamente ali que o bug seguinte se escondeu —
 * o respiro da cápsula contado duas vezes, no main e de novo na coluna. Uma
 * varredura que não cobre um modo inteiro é uma varredura que mente. */
import { chromium } from 'playwright-core';

const base = process.argv[2];
const TELAS = ['conversa', 'memoria', 'modelos', 'ferramentas', 'tarefas', 'agenda', 'conhecimento', 'configuracoes'];
const TEMAS = ['dark', 'claro', 'espacial'];
const NAVS = ['sidebar', 'icones'];

const JANELAS = [
  { w: 1440, h: 930, nome: 'referencia' },
  { w: 1532, h: 693, nome: 'navegador' },
];

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const problemas = [];

for (const janela of JANELAS) {
const p = await b.newPage({ viewport: { width: janela.w, height: janela.h } });
p.on('pageerror', (e) => problemas.push(`runtime: ${e.message}`));

for (const nav of NAVS) {
  for (const tema of TEMAS) {
  for (const tela of TELAS) {
    await p.goto(base, { waitUntil: 'networkidle' });
    await p.evaluate(([t, n]) => {
      localStorage.clear();
      localStorage.setItem('solis.appearance.theme', t);
      localStorage.setItem('solis.appearance.nav', n);
    }, [tema, nav]);
    await p.goto(base, { waitUntil: 'networkidle' });
    /* Congela o horizonte E a animação de entrada. A entrada é um translateY de
       10px, e transform entra na área de scroll do ancestral: medir no meio dela
       acusava "pagina rola: 940px em 930px" — 10px exatos, o deslocamento. Isto
       aqui mede layout, não movimento. */
    await p.addStyleTag({ content: '.animate-solis-horizon{animation-play-state:paused!important}'
      + 'main{animation:none!important}' });
    await p.evaluate((id) => {
      [...document.querySelectorAll('nav a')]
        .find((a) => a.getAttribute('href') === (id === 'conversa' ? '/' : `/${id}`))?.click();
    }, tela);
    await p.waitForTimeout(300);

    const achados = await p.evaluate((tela) => {
      const saida = [];
      /* A Conversa em estado de abertura e uma composicao FECHADA: titulo,
         subtitulo, campo e quatro atalhos. Ela nao tem conteudo variavel, entao
         nunca ha o que rolar — se a area de conteudo rola, alguma medida nao
         coube. Foi assim que o respiro da capsula contado duas vezes apareceu:
         nao rolava a pagina e nao cortava nada, mas o main pedia 828px numa
         janela de 693 e virava uma area rolavel solta por cima do horizonte.
         Nas telas de lista rolar e o esperado, entao a regra vale so aqui. */
      if (tela === 'conversa') {
        const main = document.querySelector('main');
        if (main && main.scrollHeight > main.clientHeight + 1) {
          saida.push(`conteudo rola sem ter o que rolar: ${main.scrollHeight}px em ${main.clientHeight}px`);
        }
      }
      /* O EIXO. No modo 'icones' tudo e centrado na janela, e "tudo" inclui o
         texto dentro do campo. Ele estava caindo 30px a esquerda porque texto
         centralizado se centra na caixa do INPUT, e a caixa do input e mais
         curta que o form — o microfone e a seta ocupam a direita. Nenhuma
         medida de caixa pegava isso: a caixa do form estava certa. A regra e a
         que o olho usa, entao ela e escrita como o olho ve: todo elemento que
         devia estar no eixo, no eixo. */
      if (document.documentElement.dataset.nav === 'icones') {
        const eixo = window.innerWidth / 2;
        const meio = (el) => { const r = el.getBoundingClientRect(); return (r.left + r.right) / 2; };
        const col = document.querySelector('.conversa-coluna');
        const cap = [...document.querySelectorAll('nav, div')]
          .find((e) => getComputedStyle(e).position === 'fixed' && e.querySelectorAll('a').length >= 8);
        const nome = [...document.querySelectorAll('header span')]
          .find((e) => e.textContent.trim() === 'SOLIS');
        const alvos = [
          ['nome no cabecalho', nome],
          ['capsula', cap],
          ['campo', col && col.querySelector('form')],
          ['texto dentro do campo', col && col.querySelector('input')],
          ['fileira de atalhos', col && col.lastElementChild],
        ];
        for (const [rotulo, el] of alvos) {
          if (!el) continue;
          const d = meio(el) - eixo;
          if (Math.abs(d) > 1) saida.push(`fora do eixo: ${rotulo} a ${d.toFixed(1)}px do centro`);
        }
      }
      if (document.documentElement.scrollWidth > window.innerWidth + 1) {
        saida.push(`estouro horizontal: ${document.documentElement.scrollWidth}px`);
      }
      const d = document.documentElement;
      if (d.scrollHeight > d.clientHeight + 1) {
        saida.push(`pagina rola: ${d.scrollHeight}px de conteudo em ${d.clientHeight}px de janela`);
      }
      /* Rolagem da pagina e so metade do sintoma: um `overflow: hidden` no
         caminho troca a barra de rolagem por conteudo CORTADO, que e pior e nao
         aparece em nenhuma medida de altura. Entao se procura o corte na fonte:
         qualquer caixa que esconda o que nao coube. */
      for (const el of document.querySelectorAll('body *')) {
        const cs = getComputedStyle(el);
        if (cs.overflowY !== 'hidden' && cs.overflowX !== 'hidden') continue;
        if (cs.overflowY === 'hidden' && el.scrollHeight > el.clientHeight + 1) {
          saida.push(`corta o conteudo na vertical: <${el.tagName.toLowerCase()}` +
                     `${el.className ? '.' + String(el.className).split(' ')[0] : ''}> ` +
                     `precisa de ${el.scrollHeight}px e tem ${el.clientHeight}px`);
        }
      }
      const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
      const lum = ([r, g, b]) => 0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255);
      const rgb = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
      const alpha = (s) => { const n = (s.match(/[\d.]+/g) || []); return n.length > 3 ? Number(n[3]) : 1; };
      const fundo = (el) => {
        for (let n = el; n; n = n.parentElement) {
          const bg = getComputedStyle(n).backgroundColor;
          if (alpha(bg) === 1 && rgb(bg).length === 3) return rgb(bg);
        }
        return [0, 0, 0];
      };
      for (const el of document.querySelectorAll('main *, nav *, header *')) {
        const texto = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
        if (!texto) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.opacity === '0') continue;
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) continue;
        const c = (() => {
          const lt = lum(rgb(cs.color));
          const lf = lum(fundo(el));
          return (Math.max(lt, lf) + 0.05) / (Math.min(lt, lf) + 0.05);
        })();
        if (c < 4.5) saida.push(`contraste ${c.toFixed(2)}:1 — "${el.textContent.trim().slice(0, 42)}" (${cs.color})`);
      }
      return saida;
    }, tela);
    achados.forEach((a) => problemas.push(`${janela.nome} ${nav}/${tema}/${tela}: ${a}`));
  }
  }
}
await p.close();
}

if (problemas.length === 0) {
  console.log('varredura limpa — 8 telas x 3 temas x 2 modos de nav x 2 janelas (96 combinacoes):');
  console.log('sem erro, sem estouro, sem rolagem de pagina, sem conteudo cortado,');
  console.log('nada abaixo de 4,5:1');
}
else { console.log(`${problemas.length} achados:`); problemas.forEach((x) => console.log('  ' + x)); }
await b.close();
