import { useState } from "react";
import {
  ArrowUp,
  CheckCheck,
  Bell,
  CalendarDays,
  Globe,
  History,
  List,
  Mic,
  MoreVertical,
  Paperclip,
} from "lucide-react";
import { SolisSymbol, type SolisState } from "../components/SolisSymbol/SolisSymbol";
import { useAudioLevel } from "../hooks/useAudioLevel";
import { useHorizonVariant } from "../hooks/useHorizonVariant";
import "./Conversa.css";

/* Tela de Conversa.
 *
 * Dois estados, cada um com a sua referência:
 *   - vazio  → 01-conversa-inicio.png (marca, saudação, composer, chips)
 *   - thread → 02-conversa-thread.png (header, mensagens, composer)
 *
 * A navegação (sidebar ou barra de ícones) é do shell, não desta tela.
 */

interface Mensagem {
  id: string;
  autor: "solis" | "usuario";
  texto: string;
  itens?: { ordenado: boolean; valores: string[] };
  hora: string;
}

/* Conteúdo da referência, usado só pra conferir a tela contra a imagem.
 * Não é estado inicial do produto: sem backend, a conversa começa vazia. */
const MENSAGENS_DA_REFERENCIA: Mensagem[] = [
  { id: "1", autor: "usuario", texto: "Quais são minhas tarefas para hoje?", hora: "10:32" },
  {
    id: "2",
    autor: "solis",
    texto: "Você tem 4 tarefas para hoje:",
    itens: {
      ordenado: false,
      valores: [
        "Finalizar o relatório do projeto",
        "Revisar o plano de aula",
        "Responder e-mails importantes",
        "Estudar sobre RAG e embeddings",
      ],
    },
    hora: "10:33",
  },
  { id: "3", autor: "usuario", texto: "Me resuma meu dia de ontem em 3 pontos.", hora: "10:35" },
  {
    id: "4",
    autor: "solis",
    texto: "Claro, Matheus. Aqui está um resumo do seu dia de ontem:",
    itens: {
      ordenado: true,
      valores: [
        "Você concluiu o relatório do projeto e enviou para a equipe.",
        "Ministrou a aula sobre visão computacional para os alunos.",
        "Pesquisou e testou aplicações de RAG com documentos locais.",
      ],
    },
    hora: "10:35",
  },
];

const SUGESTOES = [
  { id: "resumir", label: "Resumir meu dia", Icon: List },
  { id: "lembrete", label: "Criar lembrete", Icon: Bell },
  { id: "web", label: "Pesquisar na web", Icon: Globe },
  { id: "agenda", label: "Abrir agenda", Icon: CalendarDays },
];

/* A referência 01 abre com "Olá, Matheus." — fixo, sem hora.
 *
 * O ERROR_STATES.md cita o protótipo abrindo com "Bom dia, Matheus.", o que
 * sugeriria saudação por horário. A imagem é mais nova e a Regra 1 diz que ela
 * manda, então fica "Olá". PENDENTE: se a saudação deve variar com a hora
 * (o que combinaria com o ciclo do dia), é decisão de produto — não invento. */
const SAUDACAO = "Olá, Matheus.";

export default function Conversa() {
  /* Sem backend ainda, a conversa começa vazia — que é o estado de referência
     01. `?mock=1` em desenvolvimento carrega o conteúdo da referência 02 pra
     conferir a tela contra a imagem. */
  const mock =
    import.meta.env.DEV && new URLSearchParams(window.location.search).has("mock");
  const [mensagens, setMensagens] = useState<Mensagem[]>(
    mock ? MENSAGENS_DA_REFERENCIA : [],
  );
  const [rascunho, setRascunho] = useState("");
  const [escutando, setEscutando] = useState(false);

  const audio = useAudioLevel(escutando);

  /* O horizonte grande é da TELA de Conversa, não do estado vazio: as duas
     referências dela (01 e 02) mostram o arco subindo 129 e 162px, enquanto
     03, 05 e 06 sobem 6 a 10. Por isso vale nos dois estados. */
  useHorizonVariant("hero");

  /* Estado do símbolo. Ainda não há LLM ligado, então `thinking`/`responding`
     não têm origem real — entram quando o Ollama for conectado. */
  const estado: SolisState = escutando ? "listening" : "idle";


  const enviar = () => {
    const texto = rascunho.trim();
    if (!texto) return;
    setMensagens((m) => [
      ...m,
      {
        id: crypto.randomUUID(),
        autor: "usuario",
        texto,
        hora: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
    setRascunho("");
  };

  const composer = (
    <div
      className={`conversa__composer${mensagens.length === 0 ? " conversa__composer--empty" : ""}`}
    >
      {/* Microfone negado: o texto e o caminho de saída vêm de ERROR_STATES.md.
          O Solis não se desculpa, diz o que aconteceu e o que fazer a seguir. */}
      {audio.status === "denied" && (
        <div className="conversa__mic-aviso" role="status">
          <strong>Microfone desativado</strong>
          <p>
            Sem acesso ao microfone, o Solis só responde por texto. Ativar em
            Configurações do sistema.
          </p>
        </div>
      )}

      <div className="conversa__composer-inner">
        {mensagens.length > 0 && (
          <button type="button" className="conversa__icon-btn" aria-label="Anexar arquivo">
            <Paperclip size={20} strokeWidth={2} aria-hidden />
          </button>
        )}

        <input
          className="conversa__input"
          placeholder="Fale com o Solis..."
          value={rascunho}
          onChange={(e) => setRascunho(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
        />

        {mensagens.length === 0 && (
          <button
            type="button"
            className="conversa__icon-btn"
            data-listening={escutando}
            aria-label={escutando ? "Parar de escutar" : "Falar com o Solis"}
            aria-pressed={escutando}
            onClick={() => setEscutando((v) => !v)}
          >
            <Mic size={20} strokeWidth={2} aria-hidden />
          </button>
        )}

        <button
          type="button"
          className="conversa__send"
          onClick={enviar}
          disabled={!rascunho.trim()}
          aria-label="Enviar"
        >
          <ArrowUp size={20} strokeWidth={2.5} aria-hidden />
        </button>
      </div>
    </div>
  );

  return (
    <div className="conversa">
      {mensagens.length > 0 && (
        <header className="conversa__header">
          <SolisSymbol state={estado} size="md" />
          <span className="conversa__header-name">Solis</span>
          <span className="conversa__status" data-state={estado}>
            <span className="conversa__status-dot" />
            {estado === "listening" ? "Escutando" : "Repouso"}
          </span>
          <div className="conversa__header-actions">
            <button type="button" className="conversa__icon-btn" aria-label="Histórico">
              <History size={24} strokeWidth={2} aria-hidden />
            </button>
            <button type="button" className="conversa__icon-btn" aria-label="Mais opções">
              <MoreVertical size={24} strokeWidth={2} aria-hidden />
            </button>
          </div>
        </header>
      )}

      <div className="conversa__scroll">
        {mensagens.length === 0 ? (
          /* Conversa vazia nunca é tela em branco sem direção
             (ERROR_STATES.md item 4): o próprio Solis abre o diálogo. */
          <div className="conversa__empty">
            <div className="conversa__brand">
              <SolisSymbol state={estado} size="md" />
              <span className="conversa__brand-wordmark">SOLIS</span>
            </div>

            <h1 className="conversa__greeting">{SAUDACAO}</h1>
            <p className="conversa__sub">Como posso te ajudar hoje?</p>

            {composer}

            <div className="conversa__chips">
              {SUGESTOES.map(({ id, label, Icon }) => (
                <button
                  key={id}
                  type="button"
                  className="conversa__chip"
                  onClick={() => setRascunho(label)}
                >
                  <Icon size={20} strokeWidth={2} aria-hidden />
                  {label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="conversa__list">
            {mensagens.map((m) => (
              <div
                key={m.id}
                className={`conversa__row${m.autor === "usuario" ? " conversa__row--user" : ""}`}
              >
                {m.autor === "solis" && (
                  <SolisSymbol size="md" className="conversa__avatar" />
                )}
                <div
                  className={`conversa__bubble conversa__bubble--${
                    m.autor === "usuario" ? "user" : "solis"
                  }`}
                >
                  <p>{m.texto}</p>
                  {m.itens &&
                    (m.itens.ordenado ? (
                      <ol>
                        {m.itens.valores.map((v) => (
                          <li key={v}>{v}</li>
                        ))}
                      </ol>
                    ) : (
                      <ul>
                        {m.itens.valores.map((v) => (
                          <li key={v}>{v}</li>
                        ))}
                      </ul>
                    ))}
                  <span className="conversa__time">
                    {m.hora}
                    {/* A referência mostra marcas de entrega no balão do
                        usuário. Fica igual à imagem, mas vale confirmar o
                        sentido disso num assistente local: não há entrega em
                        rede pra confirmar. */}
                    {m.autor === "usuario" && (
                      <CheckCheck size={14} strokeWidth={2} aria-hidden />
                    )}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {mensagens.length > 0 && composer}
    </div>
  );
}
