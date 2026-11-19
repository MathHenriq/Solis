import { useEffect, useState, type CSSProperties } from 'react';
import { Botao, Interruptor } from '../components/Controles';
import {
  apagarAgendada,
  listarAgendadas,
  rodarAgendada,
  salvarAgendada,
  type Agendada,
  type Frequencia,
  type NovaAgendada,
} from '../servidor';

/** Configurações → Tarefas agendadas: um pedido que o Solis faz sozinho num
 *  horário, como as tarefas agendadas do Claude Desktop (backend/solis/agendadas.py).
 *  Na hora, o Solis abre uma conversa com o nome da tarefa e avisa no Windows.
 *  Vai primeiro pro Claude e, sem ele, pros outros cérebros (19/11/2026); o
 *  texto dizia "o Claude" e virou "o Solis" a pedido do Matheus, aprovado
 *  pelos prints nos 3 temas e 2 navs (19/11/2026).
 *
 *  Aprovado pelo Matheus em 15/11/2026 nos 3 temas e 2 navs — desenho próprio:
 *  o cartão e as linhas do de Cérebros (layout.configuracoes.cerebros), as ações
 *  em texto como o "Ver de novo" dos Conectores, o interruptor da Aparência e
 *  os campos da edição de Tarefas/Agenda (--mac-*, --tf-*). Medidas novas em
 *  layout.configuracoes.agendadas. */

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

const FREQUENCIAS: [Frequencia, string][] = [
  ['diaria', 'Todo dia'],
  ['dias_uteis', 'Dias úteis'],
  ['semanal', 'Toda semana'],
  ['hora_em_hora', 'De hora em hora'],
  ['uma_vez', 'Uma vez'],
];
const DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
const MINUTOS = Array.from({ length: 12 }, (_, i) => String(i * 5).padStart(2, '0'));

const hoje = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/** "hoje às 8:00", "amanhã às 8:00", "seg, 16/11 às 9:00". */
export function quando(iso: string): string {
  const d = new Date(iso);
  const h = `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
  const dia = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const agora = new Date();
  const hj = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate()).getTime();
  const dias = Math.round((dia - hj) / 86_400_000);
  if (dias === 0) return `hoje às ${h}`;
  if (dias === 1) return `amanhã às ${h}`;
  if (dias === -1) return `ontem às ${h}`;
  const semana = d.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '');
  return `${semana}, ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} às ${h}`;
}

function Formulario({
  inicial,
  aoSalvar,
  aoCancelar,
}: {
  inicial?: Agendada;
  aoSalvar: (a: Agendada) => void;
  aoCancelar: () => void;
}) {
  const [nome, definirNome] = useState(inicial?.nome ?? '');
  const [pedido, definirPedido] = useState(inicial?.pedido ?? '');
  const [frequencia, definirFrequencia] = useState<Frequencia>(inicial?.frequencia ?? 'diaria');
  const [hora, definirHora] = useState(inicial?.hora ?? '08:00');
  const [dia, definirDia] = useState(inicial?.dia_semana ?? 0);
  const [data, definirData] = useState(inicial?.data ?? hoje());
  const [salvando, definirSalvando] = useState(false);
  const [erro, definirErro] = useState<string | null>(null);

  const salvar = async () => {
    definirSalvando(true);
    definirErro(null);
    const dados: NovaAgendada = {
      nome,
      pedido,
      frequencia,
      hora,
      dia_semana: frequencia === 'semanal' ? dia : null,
      data: frequencia === 'uma_vez' ? data : null,
      ativa: inicial ? inicial.ativa || frequencia === 'uma_vez' : true,
    };
    const r = await salvarAgendada(dados, inicial?.id);
    definirSalvando(false);
    if ('erro' in r) definirErro(r.erro);
    else aoSalvar(r);
  };

  const caixa: CSSProperties = {
    height: 'var(--mac-botao-h)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: '0 var(--mac-campo-px)',
    fontSize: 'var(--mac-botao-texto)',
  };
  const texto: CSSProperties = {
    fontSize: 'var(--cfg-rotulo)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: 'var(--mac-campo-py) var(--mac-campo-px)',
    maxWidth: 'var(--cer-texto-max)',
  };

  return (
    <div
      className="border-t border-divider"
      style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}
    >
      <input
        value={nome}
        onChange={(e) => definirNome(e.target.value)}
        placeholder="Nome da tarefa"
        aria-label="Nome da tarefa"
        autoFocus
        className={`block w-full placeholder:text-text-placeholder ${CAMPO}`}
        style={texto}
      />
      <textarea
        value={pedido}
        onChange={(e) => definirPedido(e.target.value)}
        placeholder="O que o Solis deve fazer — ex.: resuma as notícias de tecnologia de hoje"
        aria-label="O que o Solis deve fazer"
        rows={3}
        className={`block w-full resize-y placeholder:text-text-placeholder ${CAMPO}`}
        style={{ ...texto, marginTop: 'var(--agd-campo-gap)', lineHeight: 1.5 }}
      />
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <select
          value={frequencia}
          onChange={(e) => definirFrequencia(e.target.value as Frequencia)}
          aria-label="Quando"
          className={`solis-data text-text-secondary bg-canvas ${CAMPO}`}
          style={{ ...caixa, width: 'var(--agd-freq-l)' }}
        >
          {FREQUENCIAS.map(([id, rot]) => (
            <option key={id} value={id}>{rot}</option>
          ))}
        </select>
        {frequencia === 'semanal' && (
          <select
            value={dia}
            onChange={(e) => definirDia(Number(e.target.value))}
            aria-label="Dia da semana"
            className={`solis-data text-text-secondary bg-canvas ${CAMPO}`}
            style={{ ...caixa, width: 'var(--tf-data-l)' }}
          >
            {DIAS.map((d, i) => (
              <option key={d} value={i}>{d}</option>
            ))}
          </select>
        )}
        {frequencia === 'uma_vez' && (
          <input
            type="date"
            value={data}
            min={hoje()}
            onChange={(e) => definirData(e.target.value)}
            aria-label="Dia"
            className={`solis-data text-text-secondary ${CAMPO}`}
            style={{ ...caixa, width: 'var(--tf-data-l)' }}
          />
        )}
        {frequencia === 'hora_em_hora' ? (
          <select
            value={hora.slice(3, 5)}
            onChange={(e) => definirHora(`00:${e.target.value}`)}
            aria-label="Minuto de cada hora"
            className={`solis-data text-text-secondary bg-canvas ${CAMPO}`}
            style={{ ...caixa, width: 'var(--agd-min-l)' }}
          >
            {(MINUTOS.includes(hora.slice(3, 5)) ? MINUTOS : [...MINUTOS, hora.slice(3, 5)].sort()).map((m) => (
              <option key={m} value={m}>aos {m} min</option>
            ))}
          </select>
        ) : (
          <input
            type="time"
            value={hora}
            onChange={(e) => definirHora(e.target.value)}
            aria-label="Hora"
            className={`solis-data text-text-secondary ${CAMPO}`}
            style={{ ...caixa, width: 'var(--tf-hora-l)' }}
          />
        )}
        <Botao tipo="destaque" onClick={salvar} disabled={salvando || !nome.trim() || !pedido.trim() || !hora}>
          {salvando ? 'Salvando…' : inicial ? 'Salvar' : 'Agendar'}
        </Botao>
        <Botao onClick={aoCancelar}>Cancelar</Botao>
      </div>
      {erro && (
        <div className="text-[var(--erro)]" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}>
          {erro}
        </div>
      )}
    </div>
  );
}

function Acao({ children, onClick, perigo }: { children: string; onClick: () => void; perigo?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${perigo ? 'text-[var(--erro)]' : 'text-text-secondary hover:text-text-primary'} hover:underline`}
      style={{ fontSize: 'var(--cfg-dica)' }}
    >
      {children}
    </button>
  );
}

export function CartaoAgendadas({ aoAbrirConversa }: { aoAbrirConversa?: (id: number) => void }) {
  // undefined = lendo; null = servidor fora.
  const [lista, definirLista] = useState<Agendada[] | null | undefined>(undefined);
  // 'nova', o id em edição, ou null.
  const [editando, definirEditando] = useState<'nova' | number | null>(null);
  const [apagando, definirApagando] = useState<number | null>(null);
  // As que o Matheus mandou rodar agora: a conversa onde o Solis está respondendo.
  const [rodando, definirRodando] = useState<Record<number, number>>({});

  const ler = () => void listarAgendadas().then(definirLista);
  useEffect(() => {
    ler();
    // A última vez muda sozinha (o relógio do servidor): relê de tempo em tempo.
    const t = window.setInterval(ler, 15_000);
    return () => window.clearInterval(t);
  }, []);

  const trocar = async (a: Agendada, ativa: boolean) => {
    definirLista((l) => l?.map((x) => (x.id === a.id ? { ...x, ativa } : x)));
    const r = await salvarAgendada({ ...a, ativa }, a.id);
    if ('erro' in r) ler();
    else definirLista((l) => l?.map((x) => (x.id === a.id ? r : x)));
  };

  const rodar = async (a: Agendada) => {
    const conversa = await rodarAgendada(a.id);
    if (conversa !== null) definirRodando((r) => ({ ...r, [a.id]: conversa }));
  };

  const apagar = async (id: number) => {
    definirApagando(null);
    if (await apagarAgendada(id)) definirLista((l) => l?.filter((x) => x.id !== id));
  };

  const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;
  const linha = { marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' } as const;

  return (
    <section
      className="border border-divider"
      style={{
        marginTop: 'var(--cer-cartao-gap)',
        marginBottom: 'var(--cer-cartao-gap)',
        borderRadius: 'var(--cfg-card-raio)',
        padding: 'var(--cfg-card-pad)',
      }}
    >
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Tarefas agendadas</h2>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        O Solis faz um pedido sozinho no horário marcado: abre uma conversa com o nome da tarefa e avisa no
        Windows quando acaba. Só roda com o Solis aberto; o que precisar da sua aprovação espera você ver.
      </p>

      {lista === undefined && <p className="text-text-secondary" style={{ ...dica, ...linha }}>Vendo…</p>}
      {lista === null && (
        <p className="text-text-secondary" style={{ ...dica, ...linha }}>
          Servidor do Solis desligado. Iniciar com npm run backend.
        </p>
      )}

      {lista?.map((a) =>
        editando === a.id ? (
          <Formulario
            key={a.id}
            inicial={a}
            aoCancelar={() => definirEditando(null)}
            aoSalvar={(r) => {
              definirEditando(null);
              definirLista((l) => l?.map((x) => (x.id === r.id ? r : x)));
            }}
          />
        ) : (
          <div
            key={a.id}
            className="flex items-center justify-between border-t border-divider"
            style={{ ...linha, gap: 'var(--cer-controles-gap)' }}
          >
            <div className="min-w-0">
              <div className="text-text-primary truncate" style={{ fontSize: 'var(--cfg-rotulo)', maxWidth: 'var(--cer-texto-max)' }}>
                {a.nome}
              </div>
              <div className="text-text-secondary" style={dica}>
                {a.descricao}
                {a.ativa && a.proxima && ` · próxima ${quando(a.proxima)}`}
                {!a.ativa && (a.frequencia === 'uma_vez' && a.ultima ? ' · já rodou' : ' · desligada')}
              </div>
              <div className="flex items-center flex-wrap" style={{ gap: 'var(--agd-acoes-gap)', marginTop: 'var(--cfg-dica-top)' }}>
                {apagando === a.id ? (
                  <>
                    <span className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)' }}>Apagar esta tarefa?</span>
                    <Acao perigo onClick={() => void apagar(a.id)}>Apagar</Acao>
                    <Acao onClick={() => definirApagando(null)}>Cancelar</Acao>
                  </>
                ) : (
                  <>
                    {rodando[a.id] !== undefined ? (
                      <Acao onClick={() => aoAbrirConversa?.(rodando[a.id])}>Rodando… ver a conversa</Acao>
                    ) : (
                      <Acao onClick={() => void rodar(a)}>Rodar agora</Acao>
                    )}
                    {a.ultima && a.ultima_conversa !== null && rodando[a.id] === undefined && (
                      <Acao onClick={() => aoAbrirConversa?.(a.ultima_conversa as number)}>
                        {`Última: ${quando(a.ultima)}`}
                      </Acao>
                    )}
                    <Acao onClick={() => definirEditando(a.id)}>Editar</Acao>
                    <Acao onClick={() => definirApagando(a.id)}>Apagar</Acao>
                  </>
                )}
              </div>
            </div>
            <Interruptor
              ligado={a.ativa}
              rotulo={`Ligar ${a.nome}`}
              aoTrocar={a.frequencia === 'uma_vez' && !a.proxima && !a.ativa ? undefined : (v) => void trocar(a, v)}
            />
          </div>
        ),
      )}

      {lista && editando === 'nova' && (
        <Formulario
          aoCancelar={() => definirEditando(null)}
          aoSalvar={(r) => {
            definirEditando(null);
            definirLista((l) => [...(l ?? []), r]);
          }}
        />
      )}
      {lista && editando !== 'nova' && (
        <div className={lista.length ? 'border-t border-divider' : ''} style={linha}>
          {lista.length === 0 && (
            <p className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginBottom: 'var(--cer-linha-pad)' }}>
              Nenhuma ainda. Você também pode pedir na conversa: "todo dia às 8, me resuma as notícias".
            </p>
          )}
          <Botao tipo="destaque" onClick={() => definirEditando('nova')}>Nova tarefa</Botao>
        </div>
      )}
    </section>
  );
}
