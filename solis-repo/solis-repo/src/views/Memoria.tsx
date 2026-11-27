import { useEffect, useRef, useState } from 'react';
import { Botao } from '../components/Controles';
import { quando } from '../datas';
import { Icone } from '../components/icons';
import { EstadoVazio } from '../components/Tela';
import { TelaColuna } from '../components/TelaNova';
import {
  CORES_PERSONALIDADE,
  corrigirMemoria,
  esquecerMemoria,
  listarMemorias,
  NOMES_PERSONALIDADE,
  type Memoria as MemoriaGuardada,
  type Resultado,
} from '../servidor';

/** Tela de Memória — lista e busca.
 *
 *  Medidas de texto em docs/solis-tokens.json → layout.memoria, tiradas de
 *  referencias/telas/09-memoria.png.
 *
 *  PROVISÓRIO — visual novo (27/11/2026, layout.visualNovo.tela): a tela fica na
 *  coluna da conversa (--vn-coluna), no centro, como a lista de conversas do
 *  Claude; antes ia da divisória da barra até a borda da janela. O hover da linha
 *  é um bloco arredondado que passa 16 da coluna, a busca tem o fundo e a borda
 *  da caixa de escrever, e a memória que uma personalidade aprendeu leva o nome
 *  dela, na cor dela (a mesma da resposta na thread).
 *
 *  Da referência foi adotado o LAYOUT. A paleta dela (canvas #0D1216, divisória
 *  #232629, sidebar com superfície própria) NÃO foi: canvas e divisória estavam
 *  fechados desde as 3 telas de tema, o gerador recebeu os hexes exatos no
 *  prompt e não os respeitou. Ver layout.memoria._divergencias.
 *
 *  Corrigir, esquecer e o cadeado da privada são desenho próprio, sem
 *  referência (layout.memoria.acoes): as ações só aparecem no hover ou no foco,
 *  e tudo acontece no próprio item, sem janela no meio da tela. */

/** Quanto o Desfazer fica na tela; o esquecer só vai pro servidor depois. */
const DESFAZER_MS = 6000;

/** Botão de texto das ações (Salvar, Cancelar, Esquecer). */
function ItemMemoria({
  m,
  editando,
  confirmando,
  aoEditar,
  aoConfirmar,
  aoSalvar,
  aoEsquecer,
  aoCancelar,
}: {
  m: MemoriaGuardada;
  editando: boolean;
  confirmando: boolean;
  aoEditar: () => void;
  aoConfirmar: () => void;
  aoSalvar: (texto: string) => Promise<boolean>;
  aoEsquecer: () => void;
  aoCancelar: () => void;
}) {
  const [rascunho, definirRascunho] = useState(m.texto);
  const [salvando, definirSalvando] = useState(false);
  const [falhou, definirFalhou] = useState(false);
  const campo = useRef<HTMLTextAreaElement>(null);

  // O campo nasce com o texto, o cursor no fim e a altura do texto.
  useEffect(() => {
    if (!editando) return;
    definirRascunho(m.texto);
    definirFalhou(false);
    const el = campo.current;
    if (el) {
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, [editando, m.texto]);
  useEffect(() => {
    const el = campo.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [rascunho, editando]);

  const salvar = async () => {
    if (!rascunho.trim() || salvando) return;
    if (rascunho.trim() === m.texto) return aoCancelar();
    definirSalvando(true);
    const ok = await aoSalvar(rascunho);
    definirSalvando(false);
    definirFalhou(!ok);
  };

  // Quem aprendeu, se foi uma personalidade: o nome na cor dela, misturada ao
  // texto como na thread (--vn-persona-mix).
  const nome = m.area ? NOMES_PERSONALIDADE[m.area] : undefined;
  const cor = m.area ? CORES_PERSONALIDADE[m.area] : undefined;

  return (
    // A linha das telas de lista (.vn-linha no index.css, a mesma da LinhaColuna):
    // a divisória fica no corpo, na largura da coluna; o hover passa dela.
    <li className="vn-linha group">
      <div className="vn-linha-corpo">
      {/* A data é ancorada na borda direita do bloco, não colada no fim do
          texto: na referência ela forma uma coluna própria, alinhada entre
          todos os itens, independente do tamanho de cada texto. */}
      {/* Fora da edição a data se alinha pela base da primeira linha do texto,
          como na referência; o campo de corrigir não tem uma base confiável. */}
      <div className={`flex gap-lg ${editando ? 'items-start' : 'items-baseline'}`}>
        {editando ? (
          <div className="flex-1" style={{ maxWidth: 'var(--mem-texto-max)' }}>
            <textarea
              ref={campo}
              value={rascunho}
              rows={1}
              onChange={(e) => definirRascunho(e.target.value)}
              onKeyDown={(e) => {
                // Enter salva; Shift+Enter quebra a linha; Esc desiste.
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  salvar();
                } else if (e.key === 'Escape') aoCancelar();
              }}
              aria-label="Corrigir a memória"
              className="block w-full resize-none overflow-hidden bg-transparent outline-none text-text-primary border border-[var(--vn-caixa-borda)] focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
              style={{
                fontSize: 'var(--mem-item-texto)',
                lineHeight: 'var(--mem-item-lh)',
                borderRadius: 'var(--mac-campo-raio)',
                padding: 'var(--mac-campo-py) var(--mac-campo-px)',
                // O texto do campo cai na mesma coluna do texto dos outros itens.
                marginLeft: 'calc(var(--mac-campo-px) * -1 - 1px)',
                marginTop: 'calc(var(--mac-campo-py) * -1 - 1px)',
              }}
            />
            <div className="flex items-center" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
              <Botao tipo="destaque" onClick={salvar} disabled={salvando || !rascunho.trim()}>
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
        ) : (
          /* O teto de largura é medido: sem ele o texto se espalha até a coluna
             da data e o item que na referência ocupa 2 linhas passa a caber em
             1, mudando a altura de toda a lista. */
          <p
            className="flex-1 text-text-primary"
            style={{ fontSize: 'var(--mem-item-texto)', lineHeight: 'var(--mem-item-lh)', maxWidth: 'var(--mem-texto-max)' }}
          >
            {m.texto}
          </p>
        )}
        <div className="ml-auto shrink-0 relative">
          {/* As ações só aparecem no hover ou no foco do teclado: a lista é pra
              ler, e dois ícones em todo item fariam ruído em cada linha. Elas
              flutuam à esquerda da data, sem tomar lugar: escondidas, não
              apertam o texto (no celular ele quebrava cedo). O fundo é o da
              linha com o véu, pra cobrir o fim do texto onde a coluna é estreita. */}
          {!editando && !confirmando && (
            <span
              className="absolute flex opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity"
              style={{
                right: '100%',
                top: '50%',
                transform: 'translateY(-50%)',
                marginRight: 'var(--mac-data-gap)',
                borderRadius: 'var(--mac-botao-raio)',
                background: 'linear-gradient(var(--mem-hover), var(--mem-hover)), var(--canvas)',
              }}
            >
              {(
                [
                  ['lapis', 'Corrigir', aoEditar],
                  ['lixeira', 'Esquecer', aoConfirmar],
                ] as const
              ).map(([icone, rotulo, acao]) => (
                <button
                  key={rotulo}
                  type="button"
                  onClick={acao}
                  title={rotulo}
                  aria-label={`${rotulo}: ${m.texto}`}
                  className="flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-[var(--mem-hover-forte)]"
                  style={{ width: 'var(--mac-alvo)', height: 'var(--mac-alvo)', borderRadius: 'var(--mac-botao-raio)' }}
                >
                  <Icone nome={icone} tamanho="var(--mac-icone)" />
                </button>
              ))}
            </span>
          )}
          <span className="text-text-secondary whitespace-nowrap" style={{ fontSize: 'var(--mem-data)' }}>
            {quando(m.criada)}
          </span>
        </div>
      </div>

      {confirmando ? (
        // A confirmação mora no próprio item: a pessoa vê o que vai esquecer.
        <div className="flex items-center flex-wrap" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
          <span className="text-text-primary" style={{ fontSize: 'var(--mem-origem)', marginRight: 'var(--mac-botao-gap)' }}>
            Esquecer esta memória? O Solis deixa de usar isso.
          </span>
          <Botao tipo="perigo" onClick={aoEsquecer} autoFocus>
            Esquecer
          </Botao>
          <Botao onClick={aoCancelar}>Cancelar</Botao>
        </div>
      ) : (
        !editando && (
          <p
            className="text-text-secondary flex items-center"
            style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)', gap: 6 }}
          >
            {/* Privada: criptografada no banco e nunca vai pra nuvem. */}
            {m.privada && (
              <>
                <Icone nome="cadeado" tamanho="var(--mac-cadeado)" />
                <span>privada ·</span>
              </>
            )}
            de: {m.tema}
            {nome && (
              <>
                <span aria-hidden>·</span>
                <span
                  title={`Quem aprendeu: ${nome}`}
                  style={{
                    fontWeight: 500,
                    color: cor ? `color-mix(in srgb, ${cor} var(--vn-persona-mix), var(--text-primary))` : undefined,
                  }}
                >
                  {nome}
                </span>
              </>
            )}
          </p>
        )
      )}
      </div>
    </li>
  );
}

export function Memoria() {
  const [busca, definirBusca] = useState('');
  const [resultado, definirResultado] = useState<Resultado<MemoriaGuardada[]> | null>(null);
  const [achadas, definirAchadas] = useState<MemoriaGuardada[] | null>(null);
  const [editando, definirEditando] = useState<number | null>(null);
  const [confirmando, definirConfirmando] = useState<number | null>(null);
  // Esquecida há pouco: some da lista na hora, mas só vai pro servidor quando
  // o Desfazer sai da tela (ou outra é esquecida, ou a tela fecha).
  const [esquecida, definirEsquecida] = useState<MemoriaGuardada | null>(null);
  const pendente = useRef<{ id: number; espera: number } | null>(null);

  const confirmarEsquecer = () => {
    if (!pendente.current) return;
    clearTimeout(pendente.current.espera);
    const id = pendente.current.id;
    pendente.current = null;
    esquecerMemoria(id);
    const sem = (ms: MemoriaGuardada[]) => ms.filter((x) => x.id !== id);
    definirResultado((r) => (r?.estado === 'ok' ? { ...r, dados: sem(r.dados) } : r));
    definirAchadas((a) => a && sem(a));
  };
  // Saiu da tela com um esquecer na espera: ele vai agora, não se perde.
  useEffect(() => () => confirmarEsquecer(), []);

  const esquecer = (m: MemoriaGuardada) => {
    confirmarEsquecer();
    definirConfirmando(null);
    definirEsquecida(m);
    pendente.current = {
      id: m.id,
      espera: window.setTimeout(() => {
        confirmarEsquecer();
        definirEsquecida(null);
      }, DESFAZER_MS),
    };
  };

  const desfazer = () => {
    if (pendente.current) clearTimeout(pendente.current.espera);
    pendente.current = null;
    definirEsquecida(null);
  };

  const salvar = async (m: MemoriaGuardada, texto: string) => {
    const nova = await corrigirMemoria(m.id, texto);
    if (!nova) return false;
    const troca = (ms: MemoriaGuardada[]) => ms.map((x) => (x.id === m.id ? nova : x));
    definirResultado((r) => (r?.estado === 'ok' ? { ...r, dados: troca(r.dados) } : r));
    definirAchadas((a) => a && troca(a));
    definirEditando(null);
    return true;
  };

  useEffect(() => {
    let vivo = true;
    listarMemorias().then((r) => vivo && definirResultado(r));
    return () => {
      vivo = false;
    };
  }, []);

  // A busca vai pro servidor (índice FTS5): por palavra, por prefixo e sem
  // diferença de acento — "memoria synge" acha "memória" e "Syngenta", o que
  // o filtro por trecho exato que havia aqui não achava. Espera a pessoa parar
  // de digitar, pra não ir ao banco a cada letra.
  useEffect(() => {
    if (!busca.trim()) {
      definirAchadas(null);
      return;
    }
    let vivo = true;
    const espera = setTimeout(
      () => listarMemorias(busca).then((r) => vivo && definirAchadas(r.estado === 'ok' ? r.dados : [])),
      200,
    );
    return () => {
      vivo = false;
      clearTimeout(espera);
    };
  }, [busca]);

  // A esquecida há pouco já sai da conta e da lista, mesmo antes de ir pro servidor.
  const visivel = (m: MemoriaGuardada) => m.id !== esquecida?.id;
  const todas = (resultado?.estado === 'ok' ? resultado.dados : []).filter(visivel);
  const filtradas = (achadas ?? todas).filter(visivel);

  // Antes da resposta, nem contagem nem vazio: piscaria "Nenhuma memória"
  // por um instante numa lista que tem memórias.
  const subtitulo =
    resultado?.estado !== 'ok'
      ? ''
      : todas.length === 0
        ? 'Nenhuma memória ainda'
        : `${todas.length} ${todas.length === 1 ? 'memória' : 'memórias'}`;

  return (
    <TelaColuna
      titulo="Memória"
      subtitulo={subtitulo}
      topo={
        /* O fundo e a borda da caixa de escrever, sem a sombra (não flutua). */
        <div
          className="flex items-center"
          style={{
            marginTop: 'var(--vn-tela-busca-top)',
            height: 'var(--mem-busca-h)',
            borderRadius: 'var(--mem-busca-raio)',
            background: 'var(--vn-caixa-fundo)',
            border: '1px solid var(--vn-caixa-borda)',
          }}
        >
          <span
            className="text-text-secondary shrink-0 flex"
            style={{ paddingLeft: 'var(--vn-tela-busca-pl)', paddingRight: 'var(--vn-tela-busca-gap)' }}
          >
            <Icone nome="buscar" tamanho="var(--vn-tela-busca-icone)" />
          </span>
          <input
            className="flex-1 min-w-0 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
            style={{ fontSize: 'var(--mem-item-texto)', paddingRight: 'var(--vn-tela-busca-pl)' }}
            placeholder="Buscar nas memórias…"
            aria-label="Buscar nas memórias"
            value={busca}
            onChange={(e) => definirBusca(e.target.value)}
          />
        </div>
      }
      estado={
        <>
          {/* Texto de referencias/telas/10-memoria-vazio.png. */}
          {resultado?.estado === 'ok' && todas.length === 0 && (
            <EstadoVazio
              icone="memoria"
              titulo="Ainda não há nada guardado"
              corpo={'O Solis guarda o que importa das suas conversas.\nO que ele lembrar vai aparecer aqui.'}
            />
          )}
          {resultado?.estado === 'sem-servidor' && (
            <EstadoVazio
              icone="memoria"
              titulo="Servidor do Solis desligado"
              corpo={'Sem ele, o Solis não alcança as memórias guardadas.\nIniciar com npm run backend.'}
            />
          )}
        </>
      }
      sobre={
        /* O aviso do esquecer, com Desfazer: esquecer é rápido de propósito (um
           clique de confirmação), e o Desfazer é a rede de segurança. */
        esquecida && (
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
            }}
          >
            Memória esquecida
            <button type="button" onClick={desfazer} className="text-accent" style={{ fontSize: 'var(--mac-botao-texto)' }}>
              Desfazer
            </button>
          </div>
        )
      }
    >
      <ul>
        {filtradas.map((m) => (
          <ItemMemoria
            key={m.id}
            m={m}
            editando={editando === m.id}
            confirmando={confirmando === m.id}
            aoEditar={() => {
              definirConfirmando(null);
              definirEditando(m.id);
            }}
            aoConfirmar={() => {
              definirEditando(null);
              definirConfirmando(m.id);
            }}
            aoSalvar={(texto) => salvar(m, texto)}
            aoEsquecer={() => esquecer(m)}
            aoCancelar={() => {
              definirEditando(null);
              definirConfirmando(null);
            }}
          />
        ))}
      </ul>
    </TelaColuna>
  );
}
