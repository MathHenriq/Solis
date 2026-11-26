/** Os avisos no celular, do lado do navegador (backend/solis/push.py, 26/11/2026).
 *
 *  O service worker (public/sw.js) recebe o push e mostra a notificação; aqui o
 *  navegador pede a permissão, se inscreve no serviço de push dele com a chave
 *  pública do servidor e manda a inscrição pro Solis guardar.
 *
 *  Onde funciona: navegador com service worker e Push (Chrome, Edge, Firefox,
 *  Android; no iPhone, só com o Solis na Tela de Início), em https (ou
 *  localhost). No app do PC (Tauri) não: lá o aviso é a notificação do Windows. */

import { noApp } from './tauri';
import { inscreverPush, lerPush, removerPush } from './servidor';

export type SuportePush =
  | { pode: true }
  | { pode: false; motivo: 'app' | 'inseguro' | 'navegador' | 'iphone-fora-da-tela' };

const ehIphone = () => /iPhone|iPad|iPod/.test(navigator.userAgent);
const naTelaDeInicio = () =>
  window.matchMedia('(display-mode: standalone)').matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true;

export function suportePush(): SuportePush {
  if (noApp) return { pode: false, motivo: 'app' };
  if (!window.isSecureContext) return { pode: false, motivo: 'inseguro' };
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return { pode: false, motivo: ehIphone() && !naTelaDeInicio() ? 'iphone-fora-da-tela' : 'navegador' };
  }
  return { pode: true };
}

async function registro(): Promise<ServiceWorkerRegistration> {
  await navigator.serviceWorker.register('/sw.js');
  return navigator.serviceWorker.ready;
}

/** A inscrição deste navegador, se já estiver ligado. */
export async function inscricaoAtual(): Promise<PushSubscription | null> {
  if (!suportePush().pode) return null;
  const r = await navigator.serviceWorker.getRegistration('/');
  return r ? r.pushManager.getSubscription() : null;
}

function chaveEmBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (base64url.length % 4)) % 4);
  const texto = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(texto.length));
  for (let i = 0; i < texto.length; i++) bytes[i] = texto.charCodeAt(i);
  return bytes;
}

/** Liga os avisos neste aparelho. Devolve o que deu errado, em palavras, ou null. */
export async function ligarPush(): Promise<string | null> {
  const suporte = suportePush();
  if (!suporte.pode) return 'Este navegador não recebe avisos.';
  const permissao = await Notification.requestPermission();
  if (permissao !== 'granted') {
    return permissao === 'denied'
      ? 'As notificações estão bloqueadas pra este site. Libere nas configurações do navegador e tente de novo.'
      : 'Sem a permissão de notificação, os avisos não chegam.';
  }
  const estado = await lerPush();
  if (!estado) return 'O servidor do Solis não respondeu.';
  const reg = await registro();
  let inscricao = await reg.pushManager.getSubscription();
  // Inscrito com outra chave (o servidor trocou a dele): refaz.
  const chave = chaveEmBytes(estado.chave);
  const atual = inscricao?.options.applicationServerKey;
  if (inscricao && atual && !iguais(new Uint8Array(atual), chave)) {
    await inscricao.unsubscribe();
    inscricao = null;
  }
  try {
    inscricao ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: chave });
  } catch (e) {
    return `O navegador não conseguiu se inscrever: ${e instanceof Error ? e.message : String(e)}`;
  }
  const r = await inscreverPush(inscricao.toJSON());
  return r.ok ? null : `O servidor recusou: ${r.motivo}`;
}

/** Desliga neste aparelho (no navegador e no servidor). */
export async function desligarPush(): Promise<void> {
  const inscricao = await inscricaoAtual();
  if (!inscricao) return;
  await removerPush(inscricao.endpoint);
  await inscricao.unsubscribe();
}

function iguais(a: Uint8Array, b: Uint8Array): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}
