import { useCallback, useRef, useState } from 'react';
import { chat, SolisApiError, type Fonte, type TurnoHistorico } from './solisApi';

/** O estado de uma conversa: os turnos, se há resposta em curso, e como mandar
 *  a próxima. Mora fora das views porque a Conversa (tela vazia) e a Thread
 *  (tela com histórico) são dois componentes distintos que o App alterna — se o
 *  estado morasse numa delas, ele se perderia na troca.
 *
 *  O que trocou em relação ao protótipo foi só a ORIGEM: a Thread desenha os
 *  mesmos `Turno`s de antes, agora vindos do modelo local em vez de uma
 *  constante no arquivo. */

/** Um bloco de resposta: parágrafo (string) ou lista (array). É exatamente o
 *  que a Thread já sabia desenhar. */
export type Bloco = string | string[];

export type Turno =
  | { de: 'pessoa'; hora: string; texto: string }
  | {
      de: 'solis';
      hora: string;
      blocos: Bloco[];
      digitando?: boolean;
      erro?: boolean;
      /** Trechos da base de conhecimento que embasaram esta resposta. Vazio ou
       *  ausente quando ela não veio de documento nenhum. */
      fontes?: Fonte[];
    };

/** Quantos turnos anteriores acompanham a mensagem nova. Seis é o suficiente
 *  pra "o que eu disse antes" continuar valendo sem empurrar a conversa inteira
 *  a cada envio — cada token de histórico é reprocessado pelo modelo local. */
const HISTORICO = 6;

const hora = () =>
  new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

/** Quebra o texto cru do modelo nos blocos da Thread.
 *
 *  Deliberadamente NÃO é um parser de markdown: a Thread tem um estilo de
 *  parágrafo e um de lista, e nada mais. Título, negrito e tabela não teriam
 *  onde ser desenhados, então o system prompt pede pro modelo não usá-los e
 *  aqui só se distingue linha de lista de linha comum. */
export function emBlocos(texto: string): Bloco[] {
  const blocos: Bloco[] = [];
  let paragrafo: string[] = [];
  let lista: string[] = [];

  const fecharParagrafo = () => {
    if (paragrafo.length) blocos.push(paragrafo.join(' '));
    paragrafo = [];
  };
  const fecharLista = () => {
    if (lista.length) blocos.push(lista);
    lista = [];
  };

  for (const linha of texto.split('\n')) {
    const limpa = linha.trim();
    const item = /^[-*•]\s+(.+)$/.exec(limpa);
    if (item) {
      fecharParagrafo();
      lista.push(item[1]);
    } else if (!limpa) {
      fecharParagrafo();
      fecharLista();
    } else {
      fecharLista();
      paragrafo.push(limpa);
    }
  }
  fecharParagrafo();
  fecharLista();

  return blocos.length ? blocos : [texto.trim()];
}

function textoCru(turno: Turno): string {
  if (turno.de === 'pessoa') return turno.texto;
  return turno.blocos
    .map((b) => (Array.isArray(b) ? b.map((i) => `- ${i}`).join('\n') : b))
    .join('\n\n');
}

/** Falha técnica → frase do Solis.
 *
 *  Tom do ERROR_STATES.md: diz o que houve e o que fazer, sem se desculpar e
 *  sem vocabulário de stack trace. O caso `http` já chega pronto do backend. */
function frasePara(erro: unknown): string {
  if (erro instanceof SolisApiError) {
    if (erro.tipo === 'rede')
      return 'Não consegui falar com o backend do Solis. Verificar se o serviço local está rodando.';
    if (erro.tipo === 'timeout')
      return 'O modelo demorou demais para responder. Tentar de novo ou usar um modelo menor.';
    return erro.message;
  }
  return 'Algo falhou ao gerar a resposta. Tentar de novo.';
}

export function useConversa() {
  const [turnos, definirTurnos] = useState<Turno[]>([]);
  const [gerando, definirGerando] = useState(false);

  // Espelho dos turnos em ref. `enviar` é estável (useCallback sem
  // dependências) e precisa ler a conversa atual pra montar o histórico —
  // pelo state ela leria o valor congelado no render em que foi criada.
  const conversa = useRef<Turno[]>([]);
  // Trava de envio. O guarda de verdade é aqui e não num `disabled` no botão:
  // o Enter no campo dispara submit mesmo com o botão desabilitado.
  const emVoo = useRef(false);
  const horaPendente = useRef('');

  const acrescentar = useCallback((turno: Turno) => {
    conversa.current = [...conversa.current, turno];
    definirTurnos(conversa.current);
  }, []);

  const enviar = useCallback(
    async (entrada: string) => {
      const texto = entrada.trim();
      if (!texto || emVoo.current) return;

      // Histórico montado ANTES de acrescentar a pergunta nova — ela vai no
      // campo `message`, não no `history`, e duplicá-la faria o modelo ver a
      // mesma frase duas vezes. Turnos de erro ficam de fora: são recado da
      // interface, não coisa que o Solis disse.
      const historico: TurnoHistorico[] = conversa.current
        .filter((t) => !(t.de === 'solis' && t.erro))
        .slice(-HISTORICO)
        .map((t) => ({ role: t.de === 'pessoa' ? 'user' : 'assistant', content: textoCru(t) }));

      emVoo.current = true;
      horaPendente.current = hora();
      acrescentar({ de: 'pessoa', hora: horaPendente.current, texto });
      definirGerando(true);

      try {
        const resposta = await chat({ message: texto, history: historico });
        acrescentar({
          de: 'solis',
          hora: hora(),
          blocos: emBlocos(resposta.response),
          // `sources` e não `used_knowledge`: o que a interface mostra é a
          // lista de trechos, então é a lista que decide se há o que mostrar.
          fontes: resposta.sources?.length ? resposta.sources : undefined,
        });
      } catch (erro) {
        // Backend fora do ar, Ollama parado, modelo ausente: tudo vira mensagem
        // dentro da conversa. Nada de alert nem de tela de crash
        // (ERROR_STATES.md §6).
        acrescentar({ de: 'solis', hora: hora(), blocos: [frasePara(erro)], erro: true });
      } finally {
        definirGerando(false);
        emVoo.current = false;
      }
    },
    [acrescentar],
  );

  // Enquanto a resposta não chega, entra um turno do Solis vazio com o cursor
  // — o mesmo `digitando` que a Thread já desenhava. Ele é derivado e não
  // guardado no estado, pra não haver risco de sobrar na lista se a chamada
  // falhar no meio.
  const visiveis: Turno[] = gerando
    ? [...turnos, { de: 'solis', hora: horaPendente.current, blocos: [], digitando: true }]
    : turnos;

  return { turnos: visiveis, gerando, enviar };
}
