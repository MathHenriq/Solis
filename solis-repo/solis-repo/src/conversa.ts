import { useCallback, useEffect, useState } from 'react';
import { carregarConversa, conversar, type Falha } from './servidor';

/** Estado da conversa aberta. Mora no shell (App), não na tela, pra sobreviver
 *  à troca de tela: ir a Modelos e voltar não pode apagar o que foi dito.
 *
 *  O que está guardado de verdade é o banco do servidor; isto aqui é a cópia
 *  que a tela desenha. Ao abrir, o app reabre a conversa mais recente. */

export type Turno = {
  de: 'pessoa' | 'solis';
  hora: string;
  texto: string;
  /** A resposta ainda está chegando. */
  digitando?: boolean;
  /** No lugar da resposta veio um aviso de erro. Não é guardado no banco. */
  falha?: boolean;
};

/** ERROR_STATES.md §2: no lugar da resposta, dizendo quem falhou e o que fazer. */
const AVISOS: Record<Falha, string> = {
  'sem-servidor': 'Não consegui falar com o servidor do Solis. Iniciar com npm run backend.',
  'sem-ollama': 'Não consegui acessar o modelo local. Verificar se o Ollama está rodando.',
  'sem-modelo': 'Nenhum modelo de conversa instalado. Baixar um em Modelos locais.',
};

/** Começa uma conversa nova. Comando digitado e não botão porque a tela não
 *  tem referência visual pra um botão — e sem ele, guardar a conversa tiraria
 *  o único jeito que existia de recomeçar (recarregar a página). */
const COMANDO_NOVA = '/nova';

const hora = (d: Date) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

export function useConversa() {
  const [turnos, definirTurnos] = useState<Turno[]>([]);
  // null = a próxima mensagem cria uma conversa nova.
  const [conversa, definirConversa] = useState<number | null>(null);
  const [respondendo, definirRespondendo] = useState(false);

  useEffect(() => {
    let vivo = true;
    carregarConversa().then((c) => {
      if (!vivo || !c) return;
      definirConversa(c.id);
      definirTurnos(c.mensagens.map((m) => ({ de: m.papel, texto: m.texto, hora: hora(new Date(m.criada)) })));
    });
    return () => {
      vivo = false;
    };
  }, []);

  // Só a última fala muda durante o stream; as anteriores ficam intactas.
  const mudarUltimo = (mudar: (t: Turno) => Turno) =>
    definirTurnos((ts) => [...ts.slice(0, -1), mudar(ts[ts.length - 1])]);

  const enviar = useCallback(
    async (texto: string) => {
      const limpo = texto.trim();
      if (!limpo || respondendo) return;

      if (limpo === COMANDO_NOVA) {
        // A anterior continua no banco; só deixa de ser a aberta.
        definirConversa(null);
        definirTurnos([]);
        return;
      }

      const agora = hora(new Date());
      definirTurnos((ts) => [
        ...ts,
        { de: 'pessoa', hora: agora, texto: limpo },
        { de: 'solis', hora: agora, texto: '', digitando: true },
      ]);
      definirRespondendo(true);

      const falha = await conversar(
        conversa,
        limpo,
        (pedaco) => mudarUltimo((t) => ({ ...t, texto: t.texto + pedaco })),
        definirConversa,
      );

      mudarUltimo((t) =>
        falha ? { ...t, texto: AVISOS[falha], digitando: false, falha: true } : { ...t, digitando: false },
      );
      definirRespondendo(false);
    },
    [conversa, respondendo],
  );

  return { turnos, respondendo, enviar };
}
