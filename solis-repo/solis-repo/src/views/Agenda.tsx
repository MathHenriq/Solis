import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react';
import { Botao } from '../components/Controles';
import { Icone } from '../components/icons';
import { EstadoVazio } from '../components/Tela';
import { BotaoBorda, TelaColuna } from '../components/TelaNova';
import { diaLocal, diaPorExtenso, duracaoCurta, somarDias } from '../datas';
import {
  apagarCompromisso,
  criarCompromisso,
  listarAgenda,
  mudarCompromisso,
  type CamposCompromisso,
  type Compromisso,
  type Resultado,
} from '../servidor';

/** Agenda — o DIA em linha do tempo vertical, não uma grade de mês.
 *  Referência: referencias/telas/16-agenda.png, medida em layout.agenda.
 *
 *  A grade mensal responde "que dia é hoje"; a linha do tempo responde "o que
 *  vem agora", que é a pergunta que alguém faz ao assistente. Os buracos entre
 *  horas são informação: mostram onde sobra tempo.
 *
 *  Os compromissos vêm do servidor: criados aqui ou tirados da conversa
 *  ("quinta às 15h tenho consulta com o dentista"). No dia de hoje, o que está
 *  acontecendo (ou o próximo) vira o cartão da referência.
 *
 *  Desenho próprio, aprovado pelo Matheus em 09/11/2026 (design/agenda-validacao.png), no padrão de Tarefas: Novo compromisso,
 *  editar e apagar no hover, a edição no próprio item, apagar com Desfazer, o dia
 *  vazio, e "dia todo" na coluna da hora.
 *
 *  PROVISÓRIO — visual novo (27/11/2026, layout.visualNovo.tela): a moldura das
 *  outras telas (a coluna da conversa), os botões do cabeçalho no botão do "Nova
 *  conversa" (no celular o Novo compromisso fica só com o +, e a fileira desce
 *  pra baixo do título), e o hover de cada linha no formato do cartão da vez
 *  (os mesmos 28 à esquerda e 12 à direita, e o raio dele), com as divisórias
 *  em volta sumindo, como nas outras listas. As ações flutuam à direita sem
 *  apertar o texto. */

const DESFAZER_MS = 6000;
const DURACOES = [15, 30, 45, 60, 90, 120, 180, 240];

const CAMPO =
  'bg-transparent outline-none text-text-primary border border-[var(--vn-caixa-borda)] focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]';

/** Hora em minutos desde a meia-noite. */
const minutos = (hora: string) => {
  const [h, m] = hora.split(':').map(Number);
  return h * 60 + m;
};

/** O compromisso da vez, no dia de hoje: o que está acontecendo ou, se nenhum,
 *  o próximo. Sem duração dita, conta uma hora. */
function daVez(itens: Compromisso[], agora: Date): number | null {
  const m = agora.getHours() * 60 + agora.getMinutes();
  const vez = itens.find((c) => c.hora && m < minutos(c.hora) + (c.duracao ?? 60));
  return vez?.id ?? null;
}

function Editor({
  inicial,
  dia,
  aoSalvar,
  aoCancelar,
}: {
  inicial?: Compromisso;
  dia: string;
  aoSalvar: (campos: CamposCompromisso & { titulo: string; dia: string }) => Promise<boolean>;
  aoCancelar: () => void;
}) {
  const [titulo, definirTitulo] = useState(inicial?.titulo ?? '');
  const [data, definirData] = useState(inicial?.dia ?? dia);
  const [hora, definirHora] = useState(inicial?.hora ?? '');
  const [duracao, definirDuracao] = useState(inicial?.duracao ?? 0);
  const [onde, definirOnde] = useState(inicial?.onde ?? '');
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

  const pronto = !!titulo.trim() && !!data;
  const salvar = async () => {
    if (!pronto || salvando) return;
    definirSalvando(true);
    const ok = await aoSalvar({ titulo: titulo.trim(), dia: data, hora: hora || null, duracao: duracao || null, onde: onde.trim() || null });
    definirSalvando(false);
    definirFalhou(!ok);
  };
  const teclas = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      salvar();
    } else if (e.key === 'Escape') aoCancelar();
  };
  const caixa: CSSProperties = {
    height: 'var(--mac-botao-h)',
    borderRadius: 'var(--mac-campo-raio)',
    padding: '0 var(--mac-campo-px)',
    fontSize: 'var(--mac-botao-texto)',
  };
  const opcoes = duracao && !DURACOES.includes(duracao) ? [...DURACOES, duracao].sort((a, b) => a - b) : DURACOES;

  return (
    <div>
      <input
        ref={campo}
        value={titulo}
        onChange={(e) => definirTitulo(e.target.value)}
        onKeyDown={teclas}
        placeholder="O que vai acontecer?"
        aria-label={inicial ? 'Título do compromisso' : 'Novo compromisso'}
        className={`block w-full placeholder:text-text-placeholder ${CAMPO}`}
        style={{
          // O teto de largura do texto vale pro título; a linha de campos
          // (dia, hora, duração, lugar) usa a largura da lista.
          maxWidth: 'var(--mem-texto-max)',
          fontSize: 'var(--mem-item-texto)',
          lineHeight: 'var(--mem-item-lh)',
          borderRadius: 'var(--mac-campo-raio)',
          padding: 'var(--mac-campo-py) var(--mac-campo-px)',
          marginLeft: 'calc(var(--mac-campo-px) * -1 - 1px)',
          marginTop: 'calc(var(--mac-campo-py) * -1 - 1px)',
        }}
      />
      <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
        <input type="date" value={data} onChange={(e) => definirData(e.target.value)} onKeyDown={teclas} aria-label="Dia"
               className={`solis-data text-text-secondary ${CAMPO}`} style={{ ...caixa, width: 'var(--tf-data-l)' }} />
        <input type="time" value={hora} onChange={(e) => definirHora(e.target.value)} onKeyDown={teclas} aria-label="Hora"
               className={`solis-data text-text-secondary ${CAMPO}`} style={{ ...caixa, width: 'var(--tf-hora-l)' }} />
        <select value={duracao} onChange={(e) => definirDuracao(Number(e.target.value))} aria-label="Duração"
                className={`solis-data text-text-secondary bg-canvas ${CAMPO}`} style={{ ...caixa, width: 'var(--ag-duracao-l)' }}>
          <option value={0}>Duração</option>
          {opcoes.map((d) => (
            <option key={d} value={d}>{duracaoCurta(d)}</option>
          ))}
        </select>
        <input value={onde} onChange={(e) => definirOnde(e.target.value)} onKeyDown={teclas} placeholder="Onde" aria-label="Onde"
               className={`placeholder:text-text-placeholder ${CAMPO}`} style={{ ...caixa, width: 'var(--ag-onde-l)' }} />
        <Botao tipo="destaque" onClick={salvar} disabled={salvando || !pronto}>
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

/** Uma linha da linha do tempo. A hora, o ponto e o texto ficam em x medidos
 *  (layout.agenda) a partir do começo da lista; o cartão da vez sai pra fora dela
 *  (28px à esquerda, 12 à direita), então tudo dentro dele anda o mesmo tanto. */
function Linha({
  c,
  vez,
  divisoria,
  editando,
  dia,
  aoEditar,
  aoApagar,
  aoSalvar,
  aoCancelar,
}: {
  c: Compromisso | null;
  vez: boolean;
  divisoria: boolean;
  editando: boolean;
  dia: string;
  aoEditar?: () => void;
  aoApagar?: () => void;
  aoSalvar: (campos: CamposCompromisso & { titulo: string; dia: string }) => Promise<boolean>;
  aoCancelar: () => void;
}) {
  // Dentro do cartão tudo anda o quanto ele sai pra fora, menos a borda de 1px.
  const desloc = vez ? 'calc(var(--ag-cartao-esq) - 1px)' : '0px';
  const sub = c ? [c.duracao ? duracaoCurta(c.duracao) : null, c.onde].filter(Boolean).join(' · ') : '';
  const estilo: CSSProperties = vez
    ? {
        margin: 'var(--ag-cartao-my) calc(var(--ag-cartao-dir) * -1) var(--ag-cartao-my) calc(var(--ag-cartao-esq) * -1)',
        paddingTop: 'calc(var(--ag-cartao-py))',
        paddingBottom: 'calc(var(--ag-cartao-py))',
        paddingRight: 'var(--ag-cartao-dir)',
        border: '1px solid var(--ag-cartao-borda)',
        borderRadius: 'var(--ag-cartao-raio)',
        background: 'var(--mem-hover)',
      }
    : { paddingTop: 'var(--ag-pad-cima)', paddingBottom: 'var(--ag-pad-baixo)' };
  return (
    <li
      className={`ag-linha group relative ${divisoria ? 'border-b border-divider' : ''} ${vez ? 'ag-vez' : ''}`}
      style={{ ...estilo, paddingLeft: `calc(var(--ag-titulo-x) + ${desloc})` }}
    >
      {/* O véu do hover no formato do cartão da vez (sai 28 à esquerda e 12 à
          direita, com o raio dele), por baixo do texto e da linha do tempo. */}
      {!vez && (
        <span
          aria-hidden
          className="absolute opacity-0 group-hover:opacity-100 group-has-[:focus-visible]:opacity-100 pointer-events-none"
          style={{
            inset: '0 calc(var(--ag-cartao-dir) * -1) 0 calc(var(--ag-cartao-esq) * -1)',
            borderRadius: 'var(--ag-cartao-raio)',
            background: 'var(--mem-hover)',
            zIndex: -1,
          }}
        />
      )}
      {/* A hora na linha do título: mesma entrelinha, o topo das letras alinha. */}
      <span
        className="absolute text-text-secondary whitespace-nowrap"
        style={{
          left: desloc,
          top: vez ? 'var(--ag-cartao-py)' : 'var(--ag-pad-cima)',
          fontSize: 'var(--mem-data)',
          lineHeight: 'calc(var(--mem-item-texto) * var(--mem-item-lh))',
        }}
      >
        {c?.hora ?? (c ? 'dia todo' : '')}
      </span>
      <span
        aria-hidden
        className="absolute rounded-pill"
        style={{
          width: vez ? 'var(--ag-ponto-vez)' : 'var(--ag-ponto)',
          height: vez ? 'var(--ag-ponto-vez)' : 'var(--ag-ponto)',
          left: `calc(${desloc} + var(--ag-linha-x) - ${vez ? 'var(--ag-ponto-vez)' : 'var(--ag-ponto)'} / 2)`,
          top: `calc(${vez ? 'var(--ag-cartao-py)' : 'var(--ag-pad-cima)'} + (var(--mem-item-texto) * var(--mem-item-lh) - ${vez ? 'var(--ag-ponto-vez)' : 'var(--ag-ponto)'}) / 2 + 1px)`,
          background: vez ? 'var(--accent)' : 'var(--ag-ponto-cor)',
          zIndex: 2,
        }}
      />
      {editando || !c ? (
        <Editor inicial={c ?? undefined} dia={dia} aoSalvar={aoSalvar} aoCancelar={aoCancelar} />
      ) : (
        <div className="flex items-start">
          <div className="flex-1" style={{ maxWidth: 'var(--mem-texto-max)' }}>
            <p className="text-text-primary" style={{ fontSize: 'var(--mem-item-texto)', lineHeight: 'var(--mem-item-lh)' }}>
              {c.titulo}
            </p>
            {(sub || c.privado) && (
              <p
                className="text-text-secondary flex items-center"
                style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--ag-sub-gap)', gap: 6 }}
              >
                {c.privado && <Icone nome="cadeado" tamanho="var(--mac-cadeado)" aria-label="Privado" />}
                {sub || 'privado'}
              </p>
            )}
          </div>
          {/* As ações só no hover ou no foco, como em Tarefas. Flutuam na ponta
              direita, na altura do título, sem tomar lugar do texto. */}
          <span
            className="absolute flex opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity"
            style={{
              right: vez ? 'var(--ag-cartao-dir)' : 0,
              top: `calc(${vez ? 'var(--ag-cartao-py)' : 'var(--ag-pad-cima)'} + (var(--mem-item-texto) * var(--mem-item-lh) - var(--mac-alvo)) / 2)`,
              borderRadius: 'var(--mac-botao-raio)',
              background: 'linear-gradient(var(--mem-hover), var(--mem-hover)), var(--canvas)',
            }}
          >
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
                aria-label={`${rotulo}: ${c.titulo}`}
                className="flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-[var(--mem-hover-forte)]"
                style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
              >
                <Icone nome={icone} tamanho="var(--mac-icone)" />
              </button>
            ))}
          </span>
        </div>
      )}
    </li>
  );
}

export function Agenda() {
  const [dia, definirDia] = useState(diaLocal());
  const [resultado, definirResultado] = useState<Resultado<Compromisso[]> | null>(null);
  const [editando, definirEditando] = useState<number | 'novo' | null>(null);
  const [apagado, definirApagado] = useState<Compromisso | null>(null);
  const [agora, definirAgora] = useState(() => new Date());
  const pendente = useRef<{ id: number; espera: number } | null>(null);
  const hoje = diaLocal(agora);

  useEffect(() => {
    let vivo = true;
    definirEditando(null);
    listarAgenda(dia).then((r) => vivo && definirResultado(r));
    return () => {
      vivo = false;
    };
  }, [dia]);

  // O cartão da vez anda com o relógio: confere a cada minuto.
  useEffect(() => {
    const t = window.setInterval(() => definirAgora(new Date()), 60_000);
    return () => window.clearInterval(t);
  }, []);

  const trocar = (f: (cs: Compromisso[]) => Compromisso[]) =>
    definirResultado((r) => (r?.estado === 'ok' ? { ...r, dados: f(r.dados) } : r));

  const confirmarApagar = () => {
    if (!pendente.current) return;
    clearTimeout(pendente.current.espera);
    const id = pendente.current.id;
    pendente.current = null;
    apagarCompromisso(id);
    trocar((cs) => cs.filter((x) => x.id !== id));
  };
  useEffect(() => () => confirmarApagar(), []);

  const apagar = (c: Compromisso) => {
    confirmarApagar();
    definirEditando(null);
    definirApagado(c);
    pendente.current = {
      id: c.id,
      espera: window.setTimeout(() => {
        confirmarApagar();
        definirApagado(null);
      }, DESFAZER_MS),
    };
  };
  const desfazer = () => {
    if (pendente.current) clearTimeout(pendente.current.espera);
    pendente.current = null;
    definirApagado(null);
  };

  // Salvo pra outro dia, ele sai desta lista; a ordem é a do servidor (dia todo
  // primeiro, depois pela hora).
  const salvar = async (c: Compromisso | null, campos: CamposCompromisso & { titulo: string; dia: string }) => {
    const novo = c ? await mudarCompromisso(c.id, campos) : await criarCompromisso(campos);
    if (!novo) return false;
    const r = await listarAgenda(dia);
    definirResultado(r);
    definirEditando(null);
    return true;
  };

  const itens = (resultado?.estado === 'ok' ? resultado.dados : []).filter((c) => c.id !== apagado?.id);
  const vez = dia === hoje ? daVez(itens, agora) : null;

  return (
    <TelaColuna
      titulo="Agenda"
      subtitulo={diaPorExtenso(dia)}
      acao={
        <div className="flex items-center shrink-0" style={{ gap: 'var(--mac-botao-gap)' }}>
          {resultado?.estado === 'ok' && (
            <BotaoBorda onClick={() => definirEditando('novo')} rotulo="Novo compromisso">
              <Icone nome="adicionar" tamanho={18} className="text-accent" tracoFixo="2" />
              {/* No celular a fileira não cabe: fica só o +. */}
              <span className="hidden md:inline">Novo compromisso</span>
            </BotaoBorda>
          )}
          <BotaoBorda quadrado onClick={() => definirDia(somarDias(dia, -1))} rotulo="Dia anterior">
            <Icone nome="anterior" tamanho={18} />
          </BotaoBorda>
          <BotaoBorda quadrado onClick={() => definirDia(somarDias(dia, 1))} rotulo="Próximo dia">
            <Icone nome="proximo" tamanho={18} />
          </BotaoBorda>
          <BotaoBorda onClick={() => definirDia(hoje)}>Hoje</BotaoBorda>
        </div>
      }
      sobre={
        apagado && (
          <div
            role="status"
            className="solis-aviso absolute left-1/2 -translate-x-1/2 flex items-center text-text-primary"
            style={{
              height: 'var(--mac-aviso-h)',
              padding: '0 var(--mac-aviso-px)',
              borderRadius: 'var(--mac-aviso-raio)',
              gap: 'var(--mac-aviso-px)',
              fontSize: 'var(--mac-botao-texto)',
              // Flutua sobre a lista: o fundo, a borda e a sombra da caixa de escrever.
              background: 'var(--vn-caixa-fundo)',
              border: '1px solid var(--vn-caixa-borda)',
              boxShadow: 'var(--vn-caixa-sombra)',
              zIndex: 3,
            }}
          >
            Compromisso apagado
            <button type="button" onClick={desfazer} className="text-accent" style={{ fontSize: 'var(--mac-botao-texto)' }}>
              Desfazer
            </button>
          </div>
        )
      }
      estado={
        resultado?.estado === 'sem-servidor' ? (
          <EstadoVazio icone="agenda" titulo="Servidor do Solis desligado"
                       corpo={'Sem ele, a agenda não aparece.\nIniciar com npm run backend.'} />
        ) : resultado?.estado === 'ok' && itens.length === 0 && editando !== 'novo' ? (
          <EstadoVazio icone="agenda" titulo="Dia livre"
                       corpo={'Nada marcado pra este dia. Diga ao Solis —\n"reunião com o orientador quinta às 15h" — ou use Novo compromisso.'} />
        ) : undefined
      }
    >
      {(itens.length > 0 || editando === 'novo') && (
        <ol className="relative" style={{ marginLeft: 'var(--ag-recuo)' }}>
          {/* Uma linha só, por trás dos pontos e por cima do fundo do cartão — na
              referência ela atravessa o cartão da vez. */}
          <span
            aria-hidden
            className="absolute"
            style={{
              left: 'calc(var(--ag-linha-x) - var(--ag-linha-l) / 2)',
              top: 0,
              bottom: 0,
              width: 'var(--ag-linha-l)',
              background: 'var(--ag-linha-cor)',
              zIndex: 1,
            }}
          />
          {editando === 'novo' && (
            <Linha c={null} vez={false} divisoria editando dia={dia}
                   aoSalvar={(campos) => salvar(null, campos)} aoCancelar={() => definirEditando(null)} />
          )}
          {itens.map((c, i) => (
            <Linha
              key={c.id}
              c={c}
              vez={c.id === vez}
              // A divisória fica embaixo de cada um, menos do cartão e do que vem
              // logo antes dele: o cartão tem borda própria (referência 16).
              divisoria={c.id !== vez && itens[i + 1]?.id !== vez}
              editando={editando === c.id}
              dia={dia}
              aoEditar={() => definirEditando(c.id)}
              aoApagar={() => apagar(c)}
              aoSalvar={(campos) => salvar(c, campos)}
              aoCancelar={() => definirEditando(null)}
            />
          ))}
        </ol>
      )}
    </TelaColuna>
  );
}
