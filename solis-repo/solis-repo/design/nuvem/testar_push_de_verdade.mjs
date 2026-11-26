// O aviso no celular de ponta a ponta, com um navegador de verdade (26/11/2026):
// o Solis de teste (SOLIS_SERVIDOR=1, porta 8766) → o serviço de push do navegador
// (o da Microsoft, no Edge) → o service worker → a notificação na tela.
//
// Um Edge com perfil temporário (nada do Matheus), a permissão de notificação
// liberada só pro localhost:8766. Liga os avisos pelo cartão de Configurações,
// como a pessoa faria, pede um aviso de teste e espera ele aparecer.
//
// Rodar da raiz do app, com o servidor de teste no ar:
//   $env:SOLIS_TOKEN_TESTE = '<o token do servidor de teste>'; node design/nuvem/testar_push_de_verdade.mjs
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { chromium } from 'playwright';

const ENDERECO = process.env.SOLIS_ENDERECO ?? 'http://localhost:8766';
const TOKEN = process.env.SOLIS_TOKEN_TESTE;
if (!TOKEN) throw new Error('falta SOLIS_TOKEN_TESTE');

const contexto = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'solis-push-')), {
  channel: process.env.SOLIS_NAVEGADOR ?? 'msedge',
  headless: false, // o push não chega em navegador sem janela
  viewport: { width: 420, height: 860 },
  // O Playwright desliga a rede de fundo do navegador, e é por ela que o Chrome
  // fala com o serviço de push do Google (o Edge usa o do Windows).
  ignoreDefaultArgs: ['--disable-background-networking'],
});
await contexto.grantPermissions(['notifications'], { origin: ENDERECO });
const pagina = contexto.pages()[0] ?? (await contexto.newPage());
pagina.on('console', (m) => m.type() === 'error' && console.log('  [erro na página]', m.text()));
pagina.on('pageerror', (e) => console.log('  [erro na página]', e.message));
// O primeiro registro no serviço de push num perfil novo pode demorar.
const ESPERA = Number(process.env.SOLIS_ESPERA_MS ?? 60_000);

try {
  // Entrar, como no celular.
  await pagina.goto(`${ENDERECO}/`);
  await pagina.getByLabel('Senha do servidor').fill(TOKEN);
  await pagina.getByRole('button', { name: 'Entrar' }).click();
  await pagina.waitForURL(`${ENDERECO}/`);

  // O servidor de teste começa sem aparelho (de rodadas anteriores).
  const tirados = await pagina.evaluate(async () => {
    const { aparelhos } = await (await fetch('/avisos/push')).json();
    for (const a of aparelhos)
      await fetch('/avisos/push/remover', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quem: a.id }) });
    return aparelhos.length;
  });
  if (tirados) console.log(`(tirados ${tirados} aparelhos de rodadas anteriores)`);

  // Configurações → Avisos no celular → Receber neste aparelho.
  await pagina.getByRole('link', { name: 'Configurações' }).first().click();
  const chave = pagina.getByRole('switch', { name: 'Receber os avisos neste aparelho' });
  await chave.scrollIntoViewIfNeeded();
  const t0 = Date.now();
  await chave.click();
  // Espera a inscrição DESTE navegador (ou o erro que o cartão mostrar).
  const endpoint = await pagina.evaluate(async (espera) => {
    const fim = Date.now() + espera;
    while (Date.now() < fim) {
      const r = await navigator.serviceWorker.getRegistration('/');
      const s = await r?.pushManager.getSubscription();
      if (s) return s.endpoint;
      await new Promise((ok) => setTimeout(ok, 200));
    }
    return null;
  }, ESPERA);
  if (!endpoint) {
    const erro = await pagina.getByRole('alert').textContent().catch(() => '(o cartão não disse)');
    throw new Error(`o navegador não se inscreveu em ${ESPERA / 1000} s: ${erro}`);
  }
  await pagina.getByText('Aparelhos ligados').waitFor({ timeout: 10_000 });
  console.log(`inscrito em ${Date.now() - t0} ms, no serviço: ${new URL(endpoint).host}`);

  // O aviso de teste, pelo botão do cartão; e esperar a notificação de verdade.
  const t1 = Date.now();
  await pagina.getByRole('button', { name: 'Mandar um aviso de teste' }).click();
  const chegou = await pagina.evaluate(async () => {
    const r = await navigator.serviceWorker.getRegistration('/');
    const fim = Date.now() + 30_000;
    while (Date.now() < fim) {
      const avisos = await r.getNotifications();
      if (avisos.length) return { titulo: avisos[0].title, texto: avisos[0].body };
      await new Promise((ok) => setTimeout(ok, 200));
    }
    return null;
  });
  if (!chegou) throw new Error('o aviso não apareceu em 30 s');
  console.log(`aviso na tela em ${Date.now() - t1} ms: "${chegou.titulo}" — ${chegou.texto}`);
  console.log('recado do cartão:', await pagina.getByRole('status').textContent().catch(() => '(nenhum)'));
} finally {
  await contexto.close();
}
