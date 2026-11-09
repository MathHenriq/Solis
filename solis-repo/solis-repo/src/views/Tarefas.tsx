import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Botao } from '../components/Controles';
import { Icone } from '../components/icons';
import { BotaoContorno, EstadoVazio, Tela } from '../components/Tela';
import { diaLocal, diasEntre, rotuloPrazo } from '../datas';
import {
  apagarTarefa,
  criarTarefa,
  listarTarefas,
  mudarTarefa,
  type CamposTarefa,
  type Resultado,
  type Tarefa,
} from '../servidor';

/** Tarefas — agrupadas por prazo, não por projeto.
 *  Referência: referencias/telas/15-tarefas.png (a lista: grupos, caixa, texto,
 *  "de:" e o prazo à direita).
 *
 *  As tarefas vêm do servidor: criadas aqui ou tiradas da conversa ("me lembra de
 *  pagar a luz dia 15"). Feita hoje fica riscada no grupo dela até o dia virar.
 *
 *  Desenho próprio, aprovado pelo Matheus em 09/11/2026 (design/tarefas-validacao.png), no
 *  padrão já aprovado da Memória (layout.memoria.acoes): "Nova tarefa" no
 *  cabeçalho, como o "Adicionar fonte" do Conhecimento; editar e apagar no hover;
 *  edição no próprio item, com data e hora; apagar com Desfazer; os grupos
 *  "Atrasadas" e "Sem data", que a referência não tem. Medidas em layout.tarefas. */

const DESFAZER_MS = 6000;

type NomeGrupo = 'Atrasadas' | 'Hoje' | 'Esta semana' | 'Depois' | 'Sem data';
const GRUPOS: NomeGrupo[] = ['Atrasadas', 'Hoje', 'Esta semana', 'Depois', 'Sem data'];

/** Em que grupo a tarefa cai. A semana vai até domingo; a feita hoje com prazo
 *  vencido fica em "Hoje" (foi hoje que ela saiu da frente). */
function grupoDe(t: Tarefa, hoje: string): NomeGrupo {
  if (!t.prazo) return 'Sem data';
  const dias = diasEntre(hoje, t.prazo);
  if (dias < 0) return t.feita ? 'Hoje' : 'Atrasadas';
  if (dias === 0) return 'Hoje';
  const [y, m, d] = hoje.split('-').map(Number);
  const ateDomingo = (7 - new Date(y, m - 1, d).getDay()) % 7;
  return dias <= ateDomingo ? 'Esta semana' : 'Depois';
}

/** Caixa de seleção desenhada aqui e não com <input type=checkbox>: o nativo não
 *  aceita cor de traço nem raio consistentes entre sistemas operacionais, e esta
 *  é uma interface que precisa parecer a mesma no Windows e no Mac. O papel de
 *  checkbox fica pelo role/aria-checked. */
function Caixa({ marcada }: { marcada: boolean }) {
  return (
    <span
      aria-hidden
      className={`shrink-0 flex items-center justify-center border ${marcada ? 'border-accent' : 'border-divider'}`}
      style={{ width: 26, height: 26, borderRadius: 7 }}
    >
      {marcada && (
        <svg viewBox="0 0 24 24" style={{ width: 16, height: 16 }} fill="none"
             stroke="var(--accent)" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 12.5 10 17.5 19 7" />
        </svg>
      )}
    </span>
  );
}

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-divider focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

/** Texto, data e hora de uma tarefa — a nova e a que está sendo editada. Enter
 *  salva, Esc desiste. A hora só vale com data: sem dia, ela não diz nada. */
function Editor({
  inicial,
  aoSalvar,
  aoCancelar,
}: {
  inicial?: Tarefa;
  aoSalvar: (campos: CamposTarefa & { texto: string }) => Promise<boolean>;
  aoCancelar: () => void;
}) {
  const [texto, definirTexto] = useState(inicial?.texto ?? '');
  const [prazo, definirPrazo] = useState(inicial?.prazo ?? '');
  const [hora, definirHora] = useState(inicial?.hora ?? '');
  const [salvando, definirSalvando] = useState(false);
  const [falhou, definirFalhou] = useState(false);
  const campo = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const el = campo.current;
    if (el) {
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, []);

  const salvar = async () => {
    if (!texto.trim() || salvando) return;
    definirSalvando(true);
    const ok = await aoSalvar({ texto: texto.trim(), prazo: prazo || null, hora: prazo && hora ? hora : null });
    definirSalvando(false);
    definirFalhou(!ok);
  };
  const teclas = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      salvar();
    } else if (e.key === 'Escape') aoCancelar();
  };
  const caixa = {
    height: 'var(--mac-botao-h)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: '0 var(--mac-campo-px)',
    fontSize: 'var(--mac-botao-texto)',
  };

  return (
    <div className="flex-1" style={{ maxWidth: 'var(--mem-texto-max)' }}>
      <input
        ref={campo}
        value={texto}
        onChange={(e) => definirTexto(e.target.value)}
        onKeyDown={teclas}
        placeholder="O que precisa ser feito?"
        aria-label={inicial ? 'Texto da tarefa' : 'Nova tarefa'}
        className={`block w-full placeholder:text-text-placeholder ${CAMPO}`}
        style={{
          fontSize: 'var(--mem-item-texto)',
          lineHeight: 'var(--mem-item-lh)',
          borderRadius: 'var(--mac-campo-raio)',
          padding: 'var(--mac-campo-py) var(--mac-campo-px)',
          // O texto do campo cai na mesma coluna do texto das tarefas.
          marginLeft: 'calc(var(--mac-campo-px) * -1 - 1px)',
          marginTop: 'calc(var(--mac-campo-py) * -1 - 1px)',
        }}
      />
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <input
          type="date"
          value={prazo}
          onChange={(e) => definirPrazo(e.target.value)}
          onKeyDown={teclas}
          aria-label="Prazo"
          className={`solis-data text-text-secondary ${CAMPO}`}
          style={{ ...caixa, width: 'var(--tf-data-l)' }}
        />
        <input
          type="time"
          value={hora}
          onChange={(e) => definirHora(e.target.value)}
          onKeyDown={teclas}
          disabled={!prazo}
          aria-label="Hora"
          className={`solis-data text-text-secondary disabled:opacity-40 ${CAMPO}`}
          style={{ ...caixa, width: 'var(--tf-hora-l)' }}
        />
        <Botao tipo="destaque" onClick={salvar} disabled={salvando || !texto.trim()}>
          {salvando ? 'Salvando…' : 'Salvar'}
        </Botao>
        <Botao onClick={aoCancelar}>Cancelar</Botao>
        {falhou && (
          <span className="text-[var(--erro)]" style={{ fontSize: 'var(--mem-origem)' }}>
            Não consegui salvar. O servidor do Solis está ligado?
          </span>
        )}
      </div>
    </div>
  );
}

function ItemTarefa({
  t,
  hoje,
  editando,
  aoMarcar,
  aoEditar,
  aoSalvar,
  aoApagar,
  aoCancelar,
}: {
  t: Tarefa;
  hoje: string;
  editando: boolean;
  aoMarcar: () => void;
  aoEditar: () => void;
  aoSalvar: (campos: CamposTarefa & { texto: string }) => Promise<boolean>;
  aoApagar: () => void;
  aoCancelar: () => void;
}) {
  const feita = !!t.feita;
  const atrasada = !feita && !!t.prazo && diasEntre(hoje, t.prazo) < 0;
  // Divisória EM CIMA de cada tarefa, como na referência: medida em y=218 (logo
  // abaixo do "HOJE"), 307 e 395, e nenhuma depois da última do grupo.
  return (
    <li
      className="group border-t border-divider [&:hover]:bg-[var(--mem-hover)]"
      style={{ paddingTop: 'var(--mem-item-pad-y)', paddingBottom: 'var(--mem-item-pad-y)' }}
    >
      <div className="flex items-start gap-lg">
        <button
          type="button"
          role="checkbox"
          aria-checked={feita}
          aria-label={`${feita ? 'Desmarcar' : 'Marcar como feita'}: ${t.texto}`}
          onClick={aoMarcar}
          disabled={editando}
          className="shrink-0"
        >
          <Caixa marcada={feita} />
        </button>
        {editando ? (
          <Editor inicial={t} aoSalvar={aoSalvar} aoCancelar={aoCancelar} />
        ) : (
          <div className="flex-1" style={{ maxWidth: 'var(--mem-texto-max)' }}>
            <p
              className={feita ? 'text-text-secondary line-through' : 'text-text-primary'}
              style={{ fontSize: 'var(--mem-item-texto)', lineHeight: 'var(--mem-item-lh)' }}
            >
              {t.texto}
            </p>
            {(t.origem || t.conversa || t.privada) && (
              <p
                className="text-text-secondary flex items-center"
                style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)', gap: 6 }}
              >
                {/* Privada: selada no banco e fora do que vai pra nuvem. */}
                {t.privada && (
                  <>
                    <Icone nome="cadeado" tamanho="var(--mac-cadeado)" />
                    <span>privada{t.conversa ? ' ·' : ''}</span>
                  </>
                )}
                {t.conversa && <span>de: {t.origem ?? 'uma conversa'}</span>}
              </p>
            )}
          </div>
        )}
        <div className="ml-auto shrink-0 flex items-center" style={{ gap: 'var(--mac-data-gap)' }}>
          {/* As ações só no hover ou no foco, como na Memória: a lista é pra ler. */}
          {!editando && (
            <span className="flex opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity">
              {(
                [
                  ['lapis', 'Editar', aoEditar],
                  ['lixeira', 'Apagar', aoApagar],
                ] as const
              ).map(([icone, rotulo, acao]) => (
                <button
                  key={rotulo}
                  type="button"
                  onClick={acao}
                  title={rotulo}
                  aria-label={`${rotulo}: ${t.texto}`}
                  className="flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-[var(--mem-hover-forte)]"
                  style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
                >
                  <Icone nome={icone} tamanho="var(--mac-icone)" />
                </button>
              ))}
            </span>
          )}
          {t.prazo && (
            <span
              className={`whitespace-nowrap ${atrasada ? 'text-[var(--erro)]' : 'text-text-secondary'}`}
              style={{ fontSize: 'var(--mem-data)' }}
            >
              {rotuloPrazo(t.prazo, t.hora, hoje)}
            </span>
          )}
        </div>
      </div>
    </li>
  );
}

export function Tarefas() {
  const [resultado, definirResultado] = useState<Resultado<Tarefa[]> | null>(null);
  const [editando, definirEditando] = useState<number | 'nova' | null>(null);
  const [apagada, definirApagada] = useState<Tarefa | null>(null);
  const pendente = useRef<{ id: number; espera: number } | null>(null);
  const hoje = diaLocal();

  useEffect(() => {
    let vivo = true;
    listarTarefas().then((r) => vivo && definirResultado(r));
    return () => {
      vivo = false;
    };
  }, []);

  const trocar = (f: (ts: Tarefa[]) => Tarefa[]) =>
    definirResultado((r) => (r?.estado === 'ok' ? { ...r, dados: f(r.dados) } : r));

  // Apagar some da lista na hora, mas só vai pro servidor quando o Desfazer sai
  // da tela (ou outra é apagada, ou a tela fecha) — como o esquecer da Memória.
  const confirmarApagar = () => {
    if (!pendente.current) return;
    clearTimeout(pendente.current.espera);
    const id = pendente.current.id;
    pendente.current = null;
    apagarTarefa(id);
    trocar((ts) => ts.filter((x) => x.id !== id));
  };
  useEffect(() => () => confirmarApagar(), []);

  const apagar = (t: Tarefa) => {
    confirmarApagar();
    definirEditando(null);
    definirApagada(t);
    pendente.current = {
      id: t.id,
      espera: window.setTimeout(() => {
        confirmarApagar();
        definirApagada(null);
      }, DESFAZER_MS),
    };
  };
  const desfazer = () => {
    if (pendente.current) clearTimeout(pendente.current.espera);
    pendente.current = null;
    definirApagada(null);
  };

  // Marcar é otimista: a caixa responde no clique, e volta se o servidor falhar.
  const marcar = async (t: Tarefa) => {
    const marcada = { ...t, feita: t.feita ? null : new Date().toISOString() };
    trocar((ts) => ts.map((x) => (x.id === t.id ? marcada : x)));
    const nova = await mudarTarefa(t.id, { feita: !t.feita });
    trocar((ts) => ts.map((x) => (x.id === t.id ? (nova ?? t) : x)));
  };

  const salvar = async (t: Tarefa | null, campos: CamposTarefa & { texto: string }) => {
    const nova = t ? await mudarTarefa(t.id, campos) : await criarTarefa(campos);
    if (!nova) return false;
    trocar((ts) => (t ? ts.map((x) => (x.id === t.id ? nova : x)) : [...ts, nova]));
    definirEditando(null);
    return true;
  };

  const todas = (resultado?.estado === 'ok' ? resultado.dados : []).filter((t) => t.id !== apagada?.id);
  const abertas = todas.filter((t) => !t.feita);
  const atrasadas = abertas.filter((t) => grupoDe(t, hoje) === 'Atrasadas').length;
  const paraHoje = abertas.filter((t) => grupoDe(t, hoje) === 'Hoje').length;
  // Antes da resposta, nem contagem nem vazio: piscaria "Nenhuma tarefa".
  const subtitulo =
    resultado?.estado !== 'ok'
      ? ''
      : abertas.length === 0
        ? 'Nenhuma tarefa aberta'
        : [
            atrasadas ? `${atrasadas} ${atrasadas === 1 ? 'atrasada' : 'atrasadas'}` : null,
            `${paraHoje} para hoje`,
            `${abertas.length} ${abertas.length === 1 ? 'aberta' : 'abertas'}`,
          ]
            .filter(Boolean)
            .join(' · ');

  // Na ordem do servidor (prazo, hora, sem prazo por último) dentro de cada grupo.
  const grupos = GRUPOS.map((nome) => ({ nome, itens: todas.filter((t) => grupoDe(t, hoje) === nome) })).filter(
    (g) => g.itens.length,
  );

  return (
    <Tela
      titulo="Tarefas"
      subtitulo={subtitulo}
      acao={
        resultado?.estado === 'ok' && (
          <BotaoContorno onClick={() => definirEditando('nova')}>
            <Icone nome="adicionar" tamanho={16} />
            Nova tarefa
          </BotaoContorno>
        )
      }
      estado={
        resultado?.estado === 'sem-servidor' ? (
          <EstadoVazio
            icone="tarefas"
            titulo="Servidor do Solis desligado"
            corpo={'Sem ele, as tarefas não aparecem.\nIniciar com npm run backend.'}
          />
        ) : resultado?.estado === 'ok' && todas.length === 0 && editando !== 'nova' ? (
          <EstadoVazio
            icone="tarefas"
            titulo="Nenhuma tarefa por aqui"
            corpo={'Diga ao Solis o que precisa fazer — "me lembra de pagar a luz dia 15" —\nou use Nova tarefa.'}
          />
        ) : undefined
      }
    >
      {editando === 'nova' && (
        <div
          className="flex items-start gap-lg border-b border-divider"
          style={{ paddingTop: 'var(--mem-item-pad-y)', paddingBottom: 'var(--mem-item-pad-y)' }}
        >
          <Caixa marcada={false} />
          <Editor aoSalvar={(c) => salvar(null, c)} aoCancelar={() => definirEditando(null)} />
        </div>
      )}
      {grupos.map((g) => (
        <section key={g.nome}>
          <h2
            className="text-text-secondary uppercase"
            style={{
              fontSize: 'var(--mem-origem)',
              letterSpacing: '0.08em',
              marginTop: 'var(--mem-item-pad-y)',
              marginBottom: 'var(--mem-origem-top)',
            }}
          >
            {g.nome}
          </h2>
          <ul>
            {g.itens.map((t) => (
              <ItemTarefa
                key={t.id}
                t={t}
                hoje={hoje}
                editando={editando === t.id}
                aoMarcar={() => marcar(t)}
                aoEditar={() => definirEditando(t.id)}
                aoSalvar={(c) => salvar(t, c)}
                aoApagar={() => apagar(t)}
                aoCancelar={() => definirEditando(null)}
              />
            ))}
          </ul>
        </section>
      ))}

      {apagada && (
        <div
          role="status"
          className="solis-aviso absolute left-1/2 -translate-x-1/2 flex items-center text-text-primary border border-divider bg-canvas"
          style={{
            height: 'var(--mac-aviso-h)',
            padding: '0 var(--mac-aviso-px)',
            borderRadius: 'var(--mac-aviso-raio)',
            gap: 'var(--mac-aviso-px)',
            fontSize: 'var(--mac-botao-texto)',
            boxShadow: '0 8px 24px rgb(0 0 0 / 0.25)',
          }}
        >
          Tarefa apagada
          <button type="button" onClick={desfazer} className="text-accent" style={{ fontSize: 'var(--mac-botao-texto)' }}>
            Desfazer
          </button>
        </div>
      )}
    </Tela>
  );
}
