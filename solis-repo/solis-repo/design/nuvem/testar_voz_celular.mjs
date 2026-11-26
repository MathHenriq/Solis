// A voz pelo celular de ponta a ponta (26/11/2026), num Chrome do tamanho de um
// celular com um microfone falso (a fala de design/nuvem/gerar_fala_teste.py):
// tocar no microfone → o navegador grava → o servidor transcreve → enviar → a
// resposta chega e volta FALADA (o áudio da voz baixado pela tela).
//
// Com SOLIS_COM_CADEADO=1, o cadeado vai ligado (26/11/2026): a fala vai com
// privado=1, a mensagem com privada, o cadeado desliga depois de enviar, e uma
// pergunta privada que precisa de cérebro diz que só o PC responde.
//
// Rodar da raiz do app, com o servidor de teste (SOLIS_SERVIDOR=1) na 8766:
//   $env:SOLIS_TOKEN_TESTE = '...'; node design/nuvem/testar_voz_celular.mjs <fala.wav>
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { chromium } from 'playwright';

const ENDERECO = process.env.SOLIS_ENDERECO ?? 'http://localhost:8766';
const TOKEN = process.env.SOLIS_TOKEN_TESTE;
const FALA = resolve(process.argv[2] ?? '');
if (!TOKEN || !process.argv[2]) throw new Error('uso: SOLIS_TOKEN_TESTE=... node testar_voz_celular.mjs <fala.wav>');

const contexto = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'solis-voz-')), {
  channel: 'chrome',
  headless: false,
  viewport: { width: 390, height: 844 },
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${FALA}`,
    '--autoplay-policy=user-gesture-required'],
});
await contexto.grantPermissions(['microphone'], { origin: ENDERECO });
const pagina = contexto.pages()[0] ?? (await contexto.newPage());
pagina.on('pageerror', (e) => console.log('  [erro na página]', e.message));
const CADEADO = process.env.SOLIS_COM_CADEADO === '1';
const falas = [];
const pedidos = { voz: [], mensagens: [] };
pagina.on('response', (r) => {
  if (r.url().includes('/fala/fluxo/')) falas.push({ status: r.status(), tipo: r.headers()['content-type'] });
});
pagina.on('request', (r) => {
  if (r.method() === 'POST' && new URL(r.url()).pathname === '/voz') pedidos.voz.push(r.url());
  if (r.method() === 'POST' && /\/conversas\/\d+\/mensagens$/.test(new URL(r.url()).pathname)) pedidos.mensagens.push(r.postDataJSON());
});

try {
  await pagina.goto(`${ENDERECO}/`);
  await pagina.getByLabel('Senha do servidor').fill(TOKEN);
  await pagina.getByRole('button', { name: 'Entrar' }).click();
  await pagina.waitForURL(`${ENDERECO}/`);
  // Uma conversa com mensagem (a caixa da thread é a que tem o microfone completo).
  await pagina.getByRole('button', { name: 'Falar' }).first().waitFor();

  const cadeado = pagina.getByRole('button', { name: 'Privado' }).first();
  if (CADEADO) await cadeado.click();
  const t0 = Date.now();
  await pagina.getByRole('button', { name: 'Falar' }).first().click();
  await pagina.getByRole('button', { name: 'Parar de ouvir' }).first().waitFor({ timeout: 10_000 });
  await pagina.waitForTimeout(3500); // a fala do microfone falso
  await pagina.getByRole('button', { name: 'Parar de ouvir' }).first().click();
  const caixa = pagina.getByLabel('Fale com o Solis').first();
  await pagina.waitForFunction(() => {
    const c = document.querySelector('input[aria-label="Fale com o Solis"]');
    return c && c.value.trim().length > 0;
  }, null, { timeout: 30_000 });
  const ouvido = await caixa.inputValue();
  console.log(`transcrito em ${Date.now() - t0 - 3500} ms depois de parar: "${ouvido}"`);

  const antes = await pagina.evaluate(() => document.body.innerText.split('São ').length);
  const t1 = Date.now();
  await caixa.press('Enter');
  // Uma resposta NOVA (a conversa pode já ter "São ..." de rodadas anteriores).
  await pagina.waitForFunction((n) => document.body.innerText.split('São ').length > n, antes, { timeout: 30_000 });
  console.log(`resposta escrita em ${Date.now() - t1} ms`);
  const fimFala = Date.now() + 20_000;
  while (!falas.length && Date.now() < fimFala) await pagina.waitForTimeout(200);
  if (!falas.length) throw new Error('a resposta não foi falada (nenhum áudio da voz baixado)');
  console.log(`resposta falada: ${falas.length} pedaço(s) de áudio, ${falas[0].status} ${falas[0].tipo}, em ${Date.now() - t1} ms`);
  const comPrivado = pedidos.voz.at(-1)?.includes('privado=1') ?? false;
  const msgPrivada = pedidos.mensagens.at(-1)?.privada === true;
  console.log(`fala com privado=1: ${comPrivado} · mensagem privada: ${msgPrivada} · cadeado depois: ${await cadeado.getAttribute('aria-pressed')}`);
  if (comPrivado !== CADEADO || msgPrivada !== CADEADO) throw new Error('o cadeado não foi junto (ou foi sem estar ligado)');

  if (CADEADO) {
    // Uma pergunta privada que precisa de cérebro: no servidor não há o local.
    await cadeado.click();
    await caixa.fill('me lembra o que a médica falou na consulta');
    await caixa.press('Enter');
    await pagina.getByText('O privado é respondido só pelo modelo do seu PC').waitFor({ timeout: 30_000 });
    console.log('pergunta privada no servidor: avisou que só o PC responde');
  }
} finally {
  await contexto.close();
}
