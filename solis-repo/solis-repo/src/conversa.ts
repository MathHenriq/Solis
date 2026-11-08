import { useCallback, useEffect, useState } from 'react';
import type { EtapaRecebida } from './etapas';
import { abrirConversa, carregarConversa, conversar, type Falha, type Mensagem } from './servidor';

/** Estado da conversa aberta. Mora no shell (App), não na tela, pra sobreviver
 *  à troca de tela: ir a Modelos e voltar não pode apagar o que foi dito.
 *
 *  O que está guardado de verdade é o banco do servidor; isto aqui é a cópia
 *  que a tela desenha. Ao abrir, o app reabre a conversa mais recente. */

export type Turno = {
  /** Identidade local do turno: as etapas de fundo de uma resposta chegam
   *  depois que a próxima mensagem já pode ter saído, e têm que cair na
   *  resposta certa, não na última. */
  id: number;
  de: 'pessoa' | 'solis';
  hora: string;
  texto: string;
  /** A resposta ainda está chegando. */
  digitando?: boolean;
  /** No lugar da resposta veio um aviso de erro. Não é guardado no banco. */
  falha?: boolean;
  /** Quem respondeu: 'local', 'claude', 'codex'. */
  cerebro?: string | null;
  /** O que o servidor fez pra responder, em ordem, com os tempos. */
  etapas?: EtapaRecebida[];
};

/** ERROR_STATES.md §2: no lugar da resposta, dizendo quem falhou e o que fazer. */
function aviso(falha: Falha): string {
  switch (falha.tipo) {
    case 'sem-servidor':
      return 'Não consegui falar com o servidor do Solis. Iniciar com npm run backend.';
    case 'sem-ollama':
      return 'Não consegui acessar o modelo local. Verificar se o Ollama está rodando.';
    case 'sem-modelo':
      return 'Nenhum modelo de conversa instalado. Baixar um em Modelos locais.';
    case 'sem-cerebro':
      return `O ${falha.cerebro} não respondeu. Verificar o login e a cota dele, ou mandar de novo sem o comando.`;
  }
}

/** "/claude explica X" chega na tela como "explica X" — igual ao que o servidor
 *  guarda. O comando escolhe quem responde; não faz parte do que foi dito. */
const semComando = (texto: string) => texto.replace(/^\/(claude|codex|local)\s+(?=\S)/i, '');

/** Começa uma conversa nova, como o botão do painel. Ficou de quando não
 *  havia o botão — e continua valendo pra quem prefere o teclado. */
const COMANDO_NOVA = '/nova';

const hora = (d: Date) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

let proximoId = 0;
const novoId = () => ++proximoId;

const turnosDe = (mensagens: Mensagem[]): Turno[] =>
  mensagens.map((m) => ({
    id: novoId(),
    de: m.papel,
    texto: m.texto,
    hora: hora(new Date(m.criada)),
    cerebro: m.cerebro,
    etapas: m.etapas ?? undefined,
  }));

export function useConversa() {
  const [turnos, definirTurnos] = useState<Turno[]>([]);
  // null = a próxima mensagem cria uma conversa nova.
  const [conversa, definirConversa] = useState<number | null>(null);
  const [respondendo, definirRespondendo] = useState(false);
  // Muda quando a lista de conversas do painel ficou velha: uma conversa nova
  // nasceu, ou uma antiga ganhou mensagem e sobe pro topo.
  const [versao, definirVersao] = useState(0);

  useEffect(() => {
    let vivo = true;
    carregarConversa().then((c) => {
      if (!vivo || !c) return;
      definirConversa(c.id);
      definirTurnos(turnosDe(c.mensagens));
    });
    return () => {
      vivo = false;
    };
  }, []);

  const mudar = (id: number, mudar: (t: Turno) => Turno) =>
    definirTurnos((ts) => ts.map((t) => (t.id === id ? mudar(t) : t)));

  /** A anterior continua no banco; só deixa de ser a aberta. */
  const nova = useCallback(() => {
    definirConversa(null);
    definirTurnos([]);
  }, []);

  /** Volta a uma conversa antiga. Uma resposta ainda chegando na que estava
   *  aberta não se perde: o servidor a termina e guarda, e ela aparece ao
   *  voltar pra lá. */
  const abrir = useCallback(async (id: number) => {
    const c = await abrirConversa(id);
    if (!c) return;
    definirConversa(c.id);
    definirTurnos(turnosDe(c.mensagens));
  }, []);

  const enviar = useCallback(
    async (texto: string) => {
      const limpo = texto.trim();
      if (!limpo || respondendo) return;

      if (limpo === COMANDO_NOVA) {
        nova();
        return;
      }

      const agora = hora(new Date());
      const id = novoId();
      definirTurnos((ts) => [
        ...ts,
        { id: novoId(), de: 'pessoa', hora: agora, texto: semComando(limpo) },
        { id, de: 'solis', hora: agora, texto: '', digitando: true, etapas: [] },
      ]);
      definirRespondendo(true);
      let terminou = false;

      const falha = await conversar(conversa, limpo, {
        aoReceber: (pedaco) => mudar(id, (t) => ({ ...t, texto: t.texto + pedaco })),
        aoCriar: definirConversa,
        aoEtapa: (etapa) => {
          mudar(id, (t) => ({
            ...t,
            etapas: [...(t.etapas ?? []), { ...etapa, recebida: Date.now() }],
            cerebro: etapa.etapa === 'primeira_palavra' ? etapa.cerebro : t.cerebro,
            digitando: etapa.etapa === 'fim' ? false : t.digitando,
          }));
          // A mensagem já está no banco quando a busca na memória termina: a
          // conversa entra (ou sobe) na lista do painel. E o título, quando o
          // modelo local o dá depois da resposta, troca a primeira fala nela.
          if (etapa.etapa === 'memoria' || etapa.etapa === 'titulo') definirVersao((v) => v + 1);
          // A conversa libera no fim da resposta; o aprendizado e o resumo
          // seguem chegando no mesmo stream sem prender o campo.
          if (etapa.etapa === 'fim') {
            terminou = true;
            definirRespondendo(false);
          }
        },
      });

      // Depois do `fim` a próxima mensagem já pode estar respondendo: liberar o
      // campo de novo aqui o soltaria no meio dela.
      if (terminou) return;
      mudar(id, (t) =>
        falha ? { ...t, texto: aviso(falha), digitando: false, falha: true } : { ...t, digitando: false },
      );
      definirRespondendo(false);
    },
    [conversa, respondendo, nova],
  );

  return { turnos, respondendo, enviar, conversa, abrir, nova, versao };
}
