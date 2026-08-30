/* Exporta a caixa e a cor de cada texto da tela, direto do DOM.
 *
 *   node design/medir-caixas.mjs http://localhost:4173/ <arquivo.json> [larg] [alt]
 *
 * Serve pra medir contraste sem chutar onde o texto está: a caixa vem do
 * getBoundingClientRect e a cor do getComputedStyle, então o número medido é o
 * do texto que o app realmente pinta — não o do token que eu acho que ele usa.
 * O par disso é design/medir-contraste.py, que lê este JSON contra a captura
 * feita em modo `fundo`. */
import { chromium } from 'playwright-core';
import fs from 'fs';

const [, , base, saida, larg = '1440', alt = '930'] = process.argv;
const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const p = await b.newPage({ viewport: { width: Number(larg), height: Number(alt) }, deviceScaleFactor: 1 });
const fora = {};
for (const tema of ['espacial', 'claro', 'dark']) {
  await p.goto(base, { waitUntil: 'networkidle' });
  await p.evaluate((t) => document.documentElement.setAttribute('data-theme', t), tema);
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(300);
  fora[tema] = await p.evaluate(() => {
    const caixa = (nome, el, cor) => {
      const r = el.getBoundingClientRect();
      return { nome, x: r.x, y: r.y, w: r.width, h: r.height, cor: cor || getComputedStyle(el).color };
    };
    const raiz = getComputedStyle(document.documentElement);
    const out = [];
    const um = (nome, sel, cor) => { const e = document.querySelector(sel); if (e) out.push(caixa(nome, e, cor)); };
    const varios = (pre, sel) => [...document.querySelectorAll(sel)].forEach((e, i) => out.push(caixa(pre + i, e)));
    um('saudacao', 'h1');
    um('subtitulo', 'main p');
    um('placeholder', 'main input', raiz.getPropertyValue('--text-placeholder').trim());
    um('composer-microfone', 'main form button[aria-label="Falar"]');
    um('composer-enviar', 'main form button[type="submit"]');
    varios('chip', 'main form ~ div > button');
    um('nav-ativo', 'nav a[aria-current]');
    varios('nav', 'nav ul a:not([aria-current])');
    um('perfil-nome', 'nav .mt-auto div div:nth-child(1)');
    um('perfil-online', 'nav .mt-auto div div:nth-child(2)');
    return out;
  });
  console.log(tema, fora[tema].length, 'caixas');
}
fs.writeFileSync(saida, JSON.stringify(fora, null, 1));
await b.close();
