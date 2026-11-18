import { useEffect, useState } from 'react';
import type { FaseChamada } from './components/Chamada';
import { aoNivel, escreverNivel } from './nivel';

/** A ponte com o app Tauri (docs/PLANO.md, bloco 1). No navegador nada disto
 *  roda: `noApp` é falso e a ilha aparece dentro da página.
 *
 *  No app, a ilha é OUTRA janela (label `chamada` no tauri.conf.json):
 *  transparente, sem moldura, por cima de tudo e fora da barra de tarefas. A
 *  janela principal — onde a escuta e a conversa moram — mostra ela, põe no
 *  alto e no centro do monitor, e manda por evento a fase, a legenda, a
 *  resposta e o nível da voz (o microfone só existe na janela principal). */

export const noApp = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

/** Esta página é a janela da ilha? (index.html?janela=chamada) */
export const ehJanelaChamada = new URLSearchParams(window.location.search).get('janela') === 'chamada';

export type EstadoIlha = { fase: FaseChamada | null; legenda?: string; resposta?: string };

const EVENTO = 'solis://chamada';
const EVENTO_NIVEL = 'solis://nivel';

/** Janela principal: a ilha segue o estado da chamada. */
export function useIlhaNoApp(estado: EstadoIlha) {
  const { fase, legenda, resposta } = estado;
  useEffect(() => {
    if (!noApp) return;
    let vivo = true;
    (async () => {
      const { WebviewWindow } = await import('@tauri-apps/api/webviewWindow');
      const { emitTo } = await import('@tauri-apps/api/event');
      const ilha = await WebviewWindow.getByLabel('chamada');
      if (!ilha || !vivo) return;
      if (fase) {
        await posicionar(ilha);
        await ilha.show();
      }
      await emitTo('chamada', EVENTO, { fase, legenda, resposta } satisfies EstadoIlha);
      // A saída é animada na própria ilha; ela some depois (fase null).
      if (!fase) await ilha.hide();
    })();
    return () => {
      vivo = false;
    };
  }, [fase, legenda, resposta]);

  // O nível da voz vai junto enquanto ouve.
  useEffect(() => {
    if (!noApp || fase !== 'ouvindo') return;
    let parar = () => {};
    (async () => {
      const { emitTo } = await import('@tauri-apps/api/event');
      parar = aoNivel((opacidade, transform) => void emitTo('chamada', EVENTO_NIVEL, { opacidade, transform }));
    })();
    return () => parar();
  }, [fase]);
}

/** No alto e no centro do monitor onde está a janela principal. */
/** No alto e no centro do monitor da janela principal. A largura é a que a
 *  ilha VAI ter lá: com monitores de escalas diferentes (o do Matheus: um a
 *  100% e o do notebook a 125%), o Windows muda o tamanho da janela quando ela
 *  troca de tela — 520 viram 650 —, e o centro calculado com a largura de
 *  antes deixava a ilha ~65 px pro lado (relato dele, 18/11/2026). Depois de
 *  mover, confere a largura de novo e acerta, se mudou. */
function xCentrado(monitor: { x: number; largura: number }, larguraLogica: number, escala: number): number {
  return monitor.x + Math.round((monitor.largura - Math.round(larguraLogica * escala)) / 2);
}

async function posicionar(ilha: {
  outerSize(): Promise<{ width: number }>;
  scaleFactor(): Promise<number>;
  setPosition(p: unknown): Promise<void>;
}) {
  const { currentMonitor, primaryMonitor, PhysicalPosition } = await import('@tauri-apps/api/window');
  const monitor = (await currentMonitor()) ?? (await primaryMonitor());
  if (!monitor) return;
  const tela = { x: monitor.position.x, largura: monitor.size.width };
  const logica = (await ilha.outerSize()).width / (await ilha.scaleFactor());
  await ilha.setPosition(new PhysicalPosition(xCentrado(tela, logica, monitor.scaleFactor), monitor.position.y));
  const { width } = await ilha.outerSize();
  const x = tela.x + Math.round((tela.largura - width) / 2);
  if (x !== xCentrado(tela, logica, monitor.scaleFactor)) await ilha.setPosition(new PhysicalPosition(x, monitor.position.y));
}

/** Janela da ilha: o estado que a principal manda. */
export function useEstadoDaIlha(): EstadoIlha {
  const [estado, definirEstado] = useState<EstadoIlha>({ fase: null });
  useEffect(() => {
    const parar: Array<() => void> = [];
    (async () => {
      const { listen } = await import('@tauri-apps/api/event');
      parar.push(await listen<EstadoIlha>(EVENTO, (e) => definirEstado(e.payload)));
      parar.push(
        await listen<{ opacidade: string; transform: string }>(EVENTO_NIVEL, (e) =>
          escreverNivel(e.payload.opacidade, e.payload.transform),
        ),
      );
    })();
    return () => parar.forEach((p) => p());
  }, []);
  return estado;
}
