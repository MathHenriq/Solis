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
 * Roda em DUAS janelas. 1440x930 é a de referência, onde tudo foi medido. A de
 * 1532x693 é a que um navegador entrega de verdade num notebook de 1920x1080 a
 * 125% de escala, depois de descontar aba e barra de endereço — foi ela que
 * revelou que a sidebar precisava de 769px de altura e fazia a página rolar. */
import { chromium } from 'playwright-core';

const base = process.argv[2];
const TELAS = ['conversa', 'memoria', 'modelos', 'ferramentas', 'tarefas', 'agenda', 'conhecimento', 'configuracoes'];
const TEMAS = ['dark', 'claro', 'espacial'];

const JANELAS = [
  { w: 1440, h: 930, nome: 'referencia' },
  { w: 1532, h: 693, nome: 'navegador' },
];

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const problemas = [];

for (const janela of JANELAS) {
const p = await b.newPage({ viewport: { width: janela.w, height: janela.h } });
p.on('pageerror', (e) => problemas.push(`runtime: ${e.message}`));

for (const tema of TEMAS) {
  for (const tela of TELAS) {
    await p.goto(base, { waitUntil: 'networkidle' });
    await p.evaluate((t) => { localStorage.clear(); localStorage.setItem('solis.appearance.theme', t); }, tema);
    await p.goto(base, { waitUntil: 'networkidle' });
    await p.addStyleTag({ content: '.animate-solis-horizon{animation-play-state:paused!important}' });
    await p.evaluate((id) => {
      [...document.querySelectorAll('nav a')]
        .find((a) => a.getAttribute('href') === (id === 'conversa' ? '/' : `/${id}`))?.click();
    }, tela);
    await p.waitForTimeout(300);

    const achados = await p.evaluate(() => {
      const saida = [];
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
    });
    achados.forEach((a) => problemas.push(`${janela.nome} ${tema}/${tela}: ${a}`));
  }
}
await p.close();
}

if (problemas.length === 0) {
  console.log('varredura limpa — 8 telas x 3 temas x 2 janelas: sem erro, sem estouro,');
  console.log('sem rolagem de pagina, nada abaixo de 4,5:1');
}
else { console.log(`${problemas.length} achados:`); problemas.forEach((x) => console.log('  ' + x)); }
await b.close();
