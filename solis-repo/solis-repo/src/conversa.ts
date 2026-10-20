import { useCallback, useState } from 'react';
import { conversar, type Falha, type Mensagem } from './servidor';

/** Estado da conversa aberta. Mora no shell (App), não na tela, pra sobreviver
 *  à troca de tela: ir a Modelos e voltar não pode apagar o que foi dito.
 *
 *  PROVISÓRIO: só na memória da janela. Recarregar começa do zero; guardar em
 *  disco é trabalho do SQLite, que ainda não entrou. */

export type Turno = {
  de: 'pessoa' | 'solis';
  hora: string;
  texto: string;
  /** A resposta ainda está chegando. */
  digitando?: boolean;
  /** No lugar da resposta veio um aviso de erro — não volta pro modelo como histórico. */
  falha?: boolean;
};

/** ERROR_STATES.md §2: no lugar da resposta, dizendo quem falhou e o que fazer. */
const AVISOS: Record<Falha, string> = {
  'sem-servidor': 'Não consegui falar com o servidor do Solis. Iniciar com npm run backend.',
  'sem-ollama': 'Não consegui acessar o modelo local. Verificar se o Ollama está rodando.',
  'sem-modelo': 'Nenhum modelo de conversa instalado. Baixar um em Modelos locais.',
};

const agora = () => new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

export function useConversa() {
  const [turnos, definirTurnos] = useState<Turno[]>([]);
  const [respondendo, definirRespondendo] = useState(false);

  // Só a última fala muda durante o stream; as anteriores ficam intactas.
  const mudarUltimo = (mudar: (t: Turno) => Turno) =>
    definirTurnos((ts) => [...ts.slice(0, -1), mudar(ts[ts.length - 1])]);

  const enviar = useCallback(
    async (texto: string) => {
      const limpo = texto.trim();
      if (!limpo || respondendo) return;

      const historico: Mensagem[] = [
        ...turnos.filter((t) => !t.falha).map((t) => ({ papel: t.de, texto: t.texto })),
        { papel: 'pessoa', texto: limpo },
      ];
      definirTurnos((ts) => [
        ...ts,
        { de: 'pessoa', hora: agora(), texto: limpo },
        { de: 'solis', hora: agora(), texto: '', digitando: true },
      ]);
      definirRespondendo(true);

      const falha = await conversar(historico, (pedaco) =>
        mudarUltimo((t) => ({ ...t, texto: t.texto + pedaco })),
      );

      mudarUltimo((t) =>
        falha ? { ...t, texto: AVISOS[falha], digitando: false, falha: true } : { ...t, digitando: false },
      );
      definirRespondendo(false);
    },
    [turnos, respondendo],
  );

  return { turnos, respondendo, enviar };
}
