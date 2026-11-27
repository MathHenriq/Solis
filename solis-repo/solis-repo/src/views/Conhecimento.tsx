import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Botao } from '../components/Controles';
import { Icone, type NomeIcone } from '../components/icons';
import { EstadoVazio } from '../components/Tela';
import { BotaoBorda, BuscaColuna, TelaColuna } from '../components/TelaNova';
import { quando } from '../datas';
import {
  adicionarDocumento,
  adicionarPagina,
  apagarDocumento,
  listarDocumentos,
  marcarDocumentoPrivado,
  type Documento,
  type Resultado,
} from '../servidor';

/** Conhecimento — os arquivos que o Matheus deu pro Solis ler.
 *  Referência: referencias/telas/17-conhecimento.png (a grade e os cartões).
 *
 *  Não confundir com Memória: lá são fatos curtos que ele aprendeu sozinho; aqui
 *  são fontes que a pessoa entregou. Por isso grade de cartões e não lista —
 *  cada fonte é um objeto com identidade, não uma linha de texto.
 *
 *  O servidor lê o arquivo (PDF, .md, .txt), guarda o texto em trechos e faz um
 *  vetor de cada um; o "Indexando… 64%" é a conta real de trechos com vetor. A
 *  página escaneada passa antes pelo OCR: "Lendo as páginas escaneadas… 40%" é
 *  a conta de páginas lidas — a mesma barra, sem desenho novo (aprovado em
 *  09/11/2026, design/conhecimento-ocr-validacao.png).
 *
 *  Desenho próprio, aprovado pelo Matheus em 08/11/2026 (design/conhecimento-validacao.png,
 *  layout.conhecimento): o menu dos três pontos e
 *  o aviso de baixo. "Adicionar fonte" abre um menu: arquivo ou página da web (o
 *  campo de endereço é desenho próprio, PROVISÓRIO até o Matheus aprovar).
 *
 *  PROVISÓRIO — visual novo (27/11/2026, layout.visualNovo.tela): a moldura das
 *  outras telas (a coluna da conversa, a busca da Memória), a grade em 2 colunas
 *  (na coluna de 720 o cartão fica do tamanho do da referência, que tinha 3 numa
 *  tela inteira), os cartões e os menus com a borda e o fundo da caixa de
 *  escrever, o ⋯ só no hover, e o "Adicionar fonte" no botão do "Nova conversa". */

const DESFAZER_MS = 6000;
const ACOMPANHAR_MS = 1500;
/** Tantas voltas sem nenhum trecho novo indexado = parou (Ollama fora, quase
 *  sempre). Dizer isso é melhor que um "Indexando… 12%" pra sempre. */
const VOLTAS_PARADO = 4;

const ACEITA = '.pdf,.md,.markdown,.txt';

const numero = new Intl.NumberFormat('pt-BR');

function detalhe(d: Documento) {
  // Página web como a referência escreve: "Página web · há 1 semana".
  if (d.tipo === 'web') return `Página web · ${quando(d.criado)}`;
  const rotulo = d.tipo === 'nota' ? 'Nota' : d.escaneadas && d.escaneadas === d.paginas ? 'PDF escaneado' : 'PDF';
  // O OCR leu tudo e não achou texto: dizer, em vez de um cartão que parece normal.
  if (!d.trechos) return `${rotulo} · nenhum texto encontrado`;
  const tamanho =
    d.tipo === 'pdf'
      ? `${numero.format(d.paginas ?? 0)} ${d.paginas === 1 ? 'página' : 'páginas'}`
      : `${numero.format(d.trechos)} ${d.trechos === 1 ? 'trecho' : 'trechos'}`;
  return `${rotulo} · ${tamanho} · ${quando(d.criado)}`;
}

const ICONE = { pdf: 'documento', nota: 'nota', web: 'web' } as const;

type Aviso = { texto: string; desfazer?: () => void };

/** A caixa flutuante dos menus (o ⋮ do cartão e o "Adicionar fonte"): fecha
 *  com clique fora ou Esc, como qualquer menu, e põe o foco no primeiro
 *  controle de dentro. Desenho em layout.conhecimento. */
function Caixa({ largura, aoFechar, children }: { largura?: string; aoFechar: () => void; children: ReactNode }) {
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fora = (e: MouseEvent) => !caixa.current?.contains(e.target as Node) && aoFechar();
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && aoFechar();
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', esc);
    caixa.current?.querySelector<HTMLElement>('input, button')?.focus();
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', esc);
    };
  }, [aoFechar]);
  return (
    <div
      ref={caixa}
      role="menu"
      className="absolute right-0 z-10"
      style={{
        top: `calc(100% + var(--kn-menu-top))`,
        width: largura ?? 'var(--kn-menu-l)',
        padding: 'var(--kn-menu-pad)',
        borderRadius: 'var(--kn-menu-raio)',
        // Flutua: o fundo, a borda e a sombra da caixa de escrever.
        background: 'var(--vn-caixa-fundo)',
        border: '1px solid var(--vn-caixa-borda)',
        boxShadow: 'var(--vn-caixa-sombra)',
      }}
    >
      {children}
    </div>
  );
}

function ItemMenu({ icone, onClick, children }: { icone: NomeIcone; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="flex items-center w-full text-left text-text-primary hover:bg-[var(--mem-hover)]"
      style={{
        height: 'var(--kn-menu-item-h)',
        padding: '0 var(--kn-menu-item-px)',
        gap: 'var(--kn-menu-icone-gap)',
        borderRadius: 'calc(var(--kn-menu-raio) - var(--kn-menu-pad))',
        fontSize: 'var(--mac-botao-texto)',
      }}
    >
      <Icone nome={icone} tamanho="var(--mac-icone)" className="text-text-secondary" />
      {children}
    </button>
  );
}

function Menu({
  d,
  aoFechar,
  aoPrivado,
  aoRemover,
}: {
  d: Documento;
  aoFechar: () => void;
  aoPrivado: () => void;
  aoRemover: () => void;
}) {
  return (
    <Caixa aoFechar={aoFechar}>
      {d.url && (
        <ItemMenu
          icone="web"
          onClick={() => {
            window.open(d.url!, '_blank', 'noopener');
            aoFechar();
          }}
        >
          Abrir a página
        </ItemMenu>
      )}
      <ItemMenu icone="cadeado" onClick={aoPrivado}>
        {d.privado ? 'Deixar de ser privado' : 'Marcar como privado'}
      </ItemMenu>
      <ItemMenu icone="lixeira" onClick={aoRemover}>
        Remover do Conhecimento
      </ItemMenu>
    </Caixa>
  );
}

/** "Adicionar fonte": arquivo do computador ou página da web. A página vira um
 *  campo de endereço na própria caixa, sem janela no meio da tela. */
function MenuAdicionar({
  aoArquivo,
  aoPagina,
  aoFechar,
}: {
  aoArquivo: () => void;
  aoPagina: (url: string) => void;
  aoFechar: () => void;
}) {
  const [pagina, definirPagina] = useState(false);
  const [url, definirUrl] = useState('');
  const enviar = () => url.trim() && aoPagina(url.trim());
  if (!pagina) {
    return (
      <Caixa aoFechar={aoFechar}>
        <ItemMenu icone="documento" onClick={aoArquivo}>
          Arquivo do computador
        </ItemMenu>
        <ItemMenu icone="web" onClick={() => definirPagina(true)}>
          Página da web
        </ItemMenu>
      </Caixa>
    );
  }
  return (
    <Caixa largura="var(--kn-endereco-l)" aoFechar={aoFechar}>
      <div style={{ padding: 'var(--kn-menu-pad)' }}>
        <input
          type="url"
          value={url}
          spellCheck={false}
          onChange={(e) => definirUrl(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && enviar()}
          placeholder="Cole o endereço da página"
          aria-label="Endereço da página"
          className="block w-full bg-transparent outline-none text-text-primary placeholder:text-text-placeholder border border-[var(--vn-caixa-borda)] focus:border-[color-mix(in_srgb,var(--accent)_55%,transparent)]"
          style={{
            fontSize: 'var(--mac-botao-texto)',
            borderRadius: 'var(--mac-campo-raio)',
            padding: 'var(--mac-campo-py) var(--mac-campo-px)',
          }}
        />
        <div className="flex items-center" style={{ gap: 'var(--mac-botao-gap)', marginTop: 'var(--mac-botao-top)' }}>
          <Botao tipo="destaque" onClick={enviar} disabled={!url.trim()}>
            Adicionar
          </Botao>
          <Botao onClick={aoFechar}>Cancelar</Botao>
        </div>
      </div>
    </Caixa>
  );
}

function Cartao({
  d,
  parado,
  menuAberto,
  aoMenu,
  aoPrivado,
  aoRemover,
}: {
  d: Documento | { id: string; nome: string; lendo: true; web?: boolean };
  parado?: boolean;
  menuAberto?: boolean;
  aoMenu?: (aberto: boolean) => void;
  aoPrivado?: () => void;
  aoRemover?: () => void;
}) {
  const lendo = 'lendo' in d;
  const doc = lendo ? null : d;
  // Primeiro o OCR lê as páginas escaneadas; a indexação vem depois (ver ocr.py).
  const lendoPaginas = !!doc && doc.lidas < doc.escaneadas;
  const indexando = doc && doc.indexados < doc.trechos;
  const pct = !doc
    ? 0
    : lendoPaginas
      ? Math.floor((doc.lidas / doc.escaneadas) * 100)
      : doc.trechos
        ? Math.floor((doc.indexados / doc.trechos) * 100)
        : 0;
  const estado = lendo
    ? d.web
      ? 'Baixando a página…'
      : 'Lendo o arquivo…'
    : lendoPaginas
      ? doc!.leitura_parada === 'ollama'
        ? `Parado em ${pct}%. O Ollama está ligado?`
        : doc!.leitura_parada === 'ocr'
          ? `Parado em ${pct}%. Não consegui ler as páginas.`
          : `Lendo as páginas escaneadas… ${pct}%`
      : parado
        ? `Parado em ${pct}%. O Ollama está ligado?`
        : `Indexando… ${pct}%`;

  return (
    <article
      className="group relative hover:bg-[var(--mem-hover)] min-w-0"
      style={{ borderRadius: 'var(--cfg-card-raio)', padding: 24, border: '1px solid var(--vn-caixa-borda)' }}
    >
      <div className="flex items-start justify-between">
        <span className="text-text-secondary">
          <Icone nome={lendo ? (d.web ? 'web' : 'documento') : ICONE[doc!.tipo]} tamanho={28} />
        </span>
        {doc && (
          <div className="relative">
            {/* As opções só no hover, no foco do teclado ou com o menu aberto,
                como as ações das outras listas. */}
            <button
              type="button"
              className={`flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-[var(--mem-hover-forte)] transition-opacity ${menuAberto ? '' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'}`}
              style={{
                width: 'var(--mac-alvo)',
                height: 'var(--mac-alvo)',
                borderRadius: 'var(--mac-botao-raio)',
                margin: 'calc((var(--mac-alvo) - 18px) / -2)',
              }}
              aria-label={`Opções de ${doc.nome}`}
              aria-haspopup="menu"
              aria-expanded={menuAberto}
              onClick={() => aoMenu?.(!menuAberto)}
            >
              <Icone nome="mais" tamanho={18} />
            </button>
            {menuAberto && (
              <Menu d={doc} aoFechar={() => aoMenu?.(false)} aoPrivado={aoPrivado!} aoRemover={aoRemover!} />
            )}
          </div>
        )}
      </div>
      {/* O nome numa linha só: nome de arquivo pode ser enorme, e o cartão não
          pode crescer por isso. O inteiro fica no title. */}
      <div className="text-text-primary truncate" title={'url' in d && d.url ? d.url : d.nome} style={{ fontSize: 'var(--cfg-secao)', marginTop: 30 }}>
        {d.nome}
      </div>
      {lendo || lendoPaginas || indexando ? (
        <div style={{ marginTop: 12 }}>
          {/* Barra de progresso desenhada, não <progress>: o nativo não
              aceita altura nem cor consistentes entre navegadores. */}
          <div className="bg-divider" style={{ height: 4, borderRadius: 999 }}>
            <div className="bg-accent" style={{ width: `${pct}%`, height: 4, borderRadius: 999 }} />
          </div>
          <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 10 }}>
            {estado}
          </div>
        </div>
      ) : (
        <div
          className="flex items-center text-text-secondary"
          style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)', gap: 6 }}
        >
          {doc!.privado && <Icone nome="cadeado" tamanho="var(--mac-cadeado)" aria-label="Privado" />}
          <span className="truncate">{detalhe(doc!)}</span>
        </div>
      )}
    </article>
  );
}

export function Conhecimento() {
  const [resultado, definirResultado] = useState<Resultado<Documento[]> | null>(null);
  const [busca, definirBusca] = useState('');
  const [achados, definirAchados] = useState<Documento[] | null>(null);
  const [lendo, definirLendo] = useState<{ id: string; nome: string; lendo: true; web?: boolean }[]>([]);
  const [adicionando, definirAdicionando] = useState(false);
  const [menu, definirMenu] = useState<number | null>(null);
  const [aviso, definirAviso] = useState<Aviso | null>(null);
  const [removido, definirRemovido] = useState<number | null>(null);
  const [parado, definirParado] = useState(false);
  const arquivo = useRef<HTMLInputElement>(null);
  const prazo = useRef<number | undefined>(undefined);

  const recarregar = () => listarDocumentos().then(definirResultado);

  useEffect(() => {
    recarregar();
  }, []);

  // Busca no servidor (nome e texto), com uma pausa curta pra não perguntar a
  // cada letra.
  useEffect(() => {
    if (!busca.trim()) {
      definirAchados(null);
      return;
    }
    const t = window.setTimeout(() => {
      listarDocumentos(busca).then((r) => r.estado === 'ok' && definirAchados(r.dados));
    }, 250);
    return () => window.clearTimeout(t);
  }, [busca, resultado]);

  // Acompanha a indexação enquanto houver trecho sem vetor.
  // Acompanha também a leitura das páginas escaneadas. Enquanto o OCR lê, a
  // indexação espera de propósito (ver ocr.py): isso não é "parado".
  const docs = resultado?.estado === 'ok' ? resultado.dados : [];
  const faltaIndexar = (ds: Documento[]) => ds.reduce((s, d) => s + d.trechos - d.indexados, 0);
  const lendoAgora = (ds: Documento[]) => ds.some((d) => d.lidas < d.escaneadas && !d.leitura_parada);
  const faltam = faltaIndexar(docs) + docs.reduce((s, d) => s + d.escaneadas - d.lidas, 0);
  useEffect(() => {
    if (!faltam) {
      definirParado(false);
      return;
    }
    let voltas = 0;
    let antes = faltaIndexar(docs);
    const t = window.setInterval(async () => {
      const r = await listarDocumentos();
      if (r.estado !== 'ok') return;
      const agora = faltaIndexar(r.dados);
      voltas = agora < antes || lendoAgora(r.dados) ? 0 : voltas + 1;
      antes = agora;
      definirParado(voltas >= VOLTAS_PARADO);
      definirResultado(r);
    }, ACOMPANHAR_MS);
    return () => window.clearInterval(t);
    // Só reinicia quando passa de "falta" pra "não falta": o próprio intervalo
    // atualiza `resultado`, e reiniciar a cada volta zeraria a conta do parado.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [faltam > 0]);

  function avisar(a: Aviso) {
    window.clearTimeout(prazo.current);
    definirAviso(a);
    prazo.current = window.setTimeout(() => definirAviso(null), DESFAZER_MS);
  }

  async function adicionar(arquivos: FileList | null) {
    if (!arquivos?.length) return;
    const lista = [...arquivos];
    const marcas = lista.map((f, i) => ({ id: `lendo-${Date.now()}-${i}`, nome: f.name, lendo: true as const }));
    definirLendo((l) => [...marcas, ...l]);
    const problemas: string[] = [];
    await Promise.all(
      lista.map(async (f, i) => {
        const r = await adicionarDocumento(f);
        definirLendo((l) => l.filter((x) => x.id !== marcas[i].id));
        if (r.estado === 'nao-leu') problemas.push(`${f.name}: ${r.motivo}`);
        else if (r.estado === 'ja-existe') problemas.push(`${f.name} já está no Conhecimento`);
        else if (r.estado === 'sem-servidor') problemas.push(`${f.name}: o servidor do Solis está desligado`);
      }),
    );
    await recarregar();
    if (problemas.length) avisar({ texto: problemas.join(' · ') });
  }

  async function adicionarEndereco(url: string) {
    definirAdicionando(false);
    // Enquanto baixa, o cartão mostra o site — o título só vem com a página.
    const site = url.replace(/^https?:\/\//i, '').split('/')[0];
    const marca = { id: `lendo-${Date.now()}`, nome: site, lendo: true as const, web: true };
    definirLendo((l) => [marca, ...l]);
    const r = await adicionarPagina(url);
    definirLendo((l) => l.filter((x) => x.id !== marca.id));
    await recarregar();
    if (r.estado === 'nao-leu') avisar({ texto: `${site}: ${r.motivo}` });
    else if (r.estado === 'ja-existe') avisar({ texto: 'Essa página já está no Conhecimento' });
    else if (r.estado === 'sem-servidor') avisar({ texto: 'O servidor do Solis está desligado' });
  }

  // Remover some na hora e só vai pro servidor depois do Desfazer: o texto
  // guardado não volta (o arquivo original não é copiado), então o atraso é a
  // única rede de segurança.
  function remover(d: Documento) {
    definirMenu(null);
    definirRemovido(d.id);
    const t = window.setTimeout(async () => {
      await apagarDocumento(d.id);
      definirRemovido(null);
      recarregar();
    }, DESFAZER_MS);
    avisar({
      texto: `${d.nome} removido`,
      desfazer: () => {
        window.clearTimeout(t);
        definirRemovido(null);
        definirAviso(null);
      },
    });
  }

  async function privado(d: Documento) {
    definirMenu(null);
    const novo = await marcarDocumentoPrivado(d.id, !d.privado);
    if (novo) {
      recarregar();
      avisar({
        texto: novo.privado
          ? 'Privado: só o modelo local lê, e o texto fica criptografado'
          : 'Deixou de ser privado: os cérebros de nuvem podem ler',
      });
    }
  }

  const botao = (
    <div className="relative shrink-0">
      <BotaoBorda onClick={() => definirAdicionando((a) => !a)}>
        <Icone nome="adicionar" tamanho={18} className="text-accent" tracoFixo="2" />
        Adicionar fonte
      </BotaoBorda>
      {adicionando && (
        <MenuAdicionar
          aoArquivo={() => {
            definirAdicionando(false);
            arquivo.current?.click();
          }}
          aoPagina={adicionarEndereco}
          aoFechar={() => definirAdicionando(false)}
        />
      )}
    </div>
  );
  const entrada = (
    <input
      ref={arquivo}
      type="file"
      accept={ACEITA}
      multiple
      hidden
      onChange={(e) => {
        adicionar(e.target.files);
        e.target.value = ''; // o mesmo arquivo de novo tem que disparar
      }}
    />
  );

  if (resultado?.estado === 'sem-servidor') {
    return (
      <TelaColuna
        titulo="Conhecimento"
        estado={
          <EstadoVazio
            icone="conhecimento"
            titulo="Servidor do Solis desligado"
            corpo={'Sem ele, o Solis não alcança os seus arquivos.\nIniciar com npm run backend.'}
          />
        }
      />
    );
  }
  if (resultado === null) return <TelaColuna titulo="Conhecimento" />;

  const visiveis = (achados ?? docs).filter((d) => d.id !== removido);
  const contados = docs.filter((d) => d.id !== removido);
  const indexados = contados.reduce((s, d) => s + d.indexados, 0);
  const subtitulo =
    contados.length === 0
      ? undefined
      : `${numero.format(contados.length)} ${contados.length === 1 ? 'fonte' : 'fontes'} · ` +
        `${numero.format(indexados)} ${indexados === 1 ? 'trecho indexado' : 'trechos indexados'}`;
  const vazio = contados.length === 0 && lendo.length === 0;

  return (
    <TelaColuna
      titulo="Conhecimento"
      subtitulo={subtitulo}
      acao={botao}
      topo={
        !vazio && (
          <BuscaColuna
            valor={busca}
            aoMudar={definirBusca}
            placeholder="Buscar no conhecimento…"
            rotulo="Buscar no conhecimento"
          />
        )
      }
      sobre={
        aviso && (
          <div
            role="status"
            className="solis-aviso absolute left-1/2 -translate-x-1/2 flex items-center text-text-primary"
            style={{
              minHeight: 'var(--mac-aviso-h)',
              maxWidth: 'calc(100% - var(--vn-tela-px) * 2)',
              padding: '10px var(--mac-aviso-px)',
              borderRadius: 'var(--mac-aviso-raio)',
              gap: 'var(--mac-aviso-px)',
              fontSize: 'var(--mac-botao-texto)',
              // Flutua sobre a lista: o fundo, a borda e a sombra da caixa de escrever.
              background: 'var(--vn-caixa-fundo)',
              border: '1px solid var(--vn-caixa-borda)',
              boxShadow: 'var(--vn-caixa-sombra)',
              zIndex: 20,
            }}
          >
            {aviso.texto}
            {aviso.desfazer && (
              <button type="button" onClick={aviso.desfazer} className="text-accent shrink-0" style={{ fontSize: 'var(--mac-botao-texto)' }}>
                Desfazer
              </button>
            )}
          </div>
        )
      }
      estado={
        vazio ? (
          <EstadoVazio
            icone="conhecimento"
            titulo="Nenhuma fonte ainda"
            corpo={'Adicione PDFs, notas, textos e páginas da web. O Solis lê, guarda\no texto e usa nas respostas, dizendo de onde tirou.'}
          />
        ) : undefined
      }
    >
      {entrada}
      {!vazio && achados && visiveis.length === 0 && (
        <p
          className="text-text-secondary"
          style={{ fontSize: 'var(--mem-item-texto)', paddingTop: 'calc(var(--vn-tela-grade-top) - var(--vn-tela-lista-gap))' }}
        >
          Nenhuma fonte com “{busca.trim()}” no nome ou no texto.
        </p>
      )}

      {/* 2 colunas na coluna da conversa (1 no celular); a grade começa à
          distância medida da busca (--vn-tela-grade-top). */}
      <div
        className="grid grid-cols-1 md:grid-cols-2"
        style={{
          gap: 'var(--vn-tela-grade-gap)',
          paddingTop: 'calc(var(--vn-tela-grade-top) - var(--vn-tela-lista-gap))',
          paddingBottom: 'var(--vn-tela-grade-gap)',
        }}
      >
        {!achados && lendo.map((l) => <Cartao key={l.id} d={l} />)}
        {visiveis.map((d) => (
          <Cartao
            key={d.id}
            d={d}
            parado={parado}
            menuAberto={menu === d.id}
            aoMenu={(aberto) => definirMenu(aberto ? d.id : null)}
            aoPrivado={() => privado(d)}
            aoRemover={() => remover(d)}
          />
        ))}
      </div>
    </TelaColuna>
  );
}
