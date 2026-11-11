import { useEffect } from 'react';
import { Chamada } from './components/Chamada';
import { useEstadoDaIlha } from './tauri';

/** A página da janela `chamada` do app Tauri: só a ilha, num fundo
 *  transparente — a janela fica por cima de tudo, e o que não é ilha tem que
 *  deixar ver o que está atrás. O estado vem da janela principal (tauri.ts). */
export function JanelaChamada() {
  const { fase, legenda, resposta } = useEstadoDaIlha();
  useEffect(() => {
    document.documentElement.style.background = 'transparent';
    document.body.style.background = 'transparent';
  }, []);
  // Uma ilha nova a cada chamada: o `key` faz ela nascer de novo (descer do alto).
  return fase ? <Chamada key={fase === 'ouvindo' ? 'nova' : 'mesma'} fase={fase} legenda={legenda} resposta={resposta} /> : null;
}
