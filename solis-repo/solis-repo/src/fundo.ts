import { useEffect, useRef, useState } from 'react';
import { lerFundo, type Fundo } from './servidor';

/** O que o Claude deixou rodando em segundo plano na conversa, e a resposta
 *  que ele começa sozinho quando um comando acaba (backend: agente._Viva).
 *
 *  Não há stream aberto pra isso: a tela pergunta ao servidor a cada 1,5 s,
 *  mas só enquanto houver algo — e confere uma vez ao abrir a conversa e no
 *  fim de cada resposta (é quando um comando pode ter ficado rodando). Quando
 *  a resposta que o Claude começou sozinho termina, ela já está no banco:
 *  `aoMudar` recarrega a conversa. */

const INTERVALO_MS = 1500;
const VAZIO: Fundo = { comandos: [], resposta: null };

export function useFundo(conversa: number | null, respondendo: boolean, aoMudar: () => void): Fundo {
  const [fundo, definirFundo] = useState<Fundo>(VAZIO);
  const tinhaResposta = useRef(false);
  const mudou = useRef(aoMudar);
  mudou.current = aoMudar;

  useEffect(() => {
    if (conversa === null || respondendo) {
      if (conversa === null) definirFundo(VAZIO);
      return;
    }
    let vivo = true;
    let espera: ReturnType<typeof setTimeout> | undefined;
    const olhar = async () => {
      const f = (await lerFundo(conversa)) ?? VAZIO;
      if (!vivo) return;
      definirFundo(f);
      // A resposta que veio sozinha acabou: ela está no banco agora.
      if (tinhaResposta.current && !f.resposta) mudou.current();
      tinhaResposta.current = !!f.resposta;
      if (f.comandos.length || f.resposta) espera = setTimeout(olhar, INTERVALO_MS);
    };
    // Logo depois do fim de uma resposta, o comando pode estar começando.
    espera = setTimeout(olhar, 300);
    return () => {
      vivo = false;
      clearTimeout(espera);
    };
  }, [conversa, respondendo]);

  return fundo;
}
