/* Custo real de uma animação, em trabalho de main thread.
 *
 *   npm run build
 *   node design/medir-custo-animacao.mjs <arquivo.html> [outro.html ...]
 *
 * Existe porque a regra 1 do PERFORMANCE.md ("só transform e opacity em loop")
 * vinha sendo aplicada de fé. Agora dá pra medir.
 *
 * Contar frames com requestAnimationFrame NÃO serve: numa cena pequena as duas
 * versões batem 60fps e a diferença some. rAF mede a cadência do main thread, e
 * o que separa uma camada rasterizada uma vez de uma que refaz o filtro a cada
 * frame é o TRABALHO, não a cadência. Por isso a medida vem do CDP
 * (Performance.getMetrics) numa janela fixa de 6 segundos.
 *
 * Referência medida nos 5 estados do símbolo animando ao mesmo tempo:
 *   camada certa (opacity + transform)      4ms de tarefa,   0 recálculos
 *   filter dentro do keyframe             133ms de tarefa, 360 recálculos
 * Um recálculo de estilo por frame, 33× mais trabalho, pelo mesmo efeito. */
import { chromium } from 'playwright-core';

const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const arquivo of process.argv.slice(2)) {
  const p = await b.newPage({ viewport: { width: 1440, height: 930 } });
  const cdp = await p.context().newCDPSession(p);
  await cdp.send('Performance.enable');
  await p.goto(arquivo.startsWith('http') ? arquivo : 'file://' + arquivo, { waitUntil: 'load' });
  await p.waitForTimeout(1200);            // deixa assentar antes de medir
  const pega = async () =>
    Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map((m) => [m.name, m.value]));
  const antes = await pega();
  await p.waitForTimeout(6000);
  const depois = await pega();
  const d = (k) => depois[k] - antes[k];
  console.log(
    `${arquivo.split('/').pop().padEnd(24)} tarefa ${(d('TaskDuration') * 1000).toFixed(0).padStart(5)}ms  ` +
    `estilo ${(d('RecalcStyleDuration') * 1000).toFixed(1).padStart(6)}ms  ` +
    `recalculos ${String(d('RecalcStyleCount')).padStart(4)}  layouts ${String(d('LayoutCount')).padStart(4)}`,
  );
  await p.close();
}
await b.close();
