import { useEffect, useState } from 'react';
import { Icone } from '../components/icons';
import { EstadoVazio } from '../components/Tela';
import { BotaoBorda, LinhaColuna, SecaoColuna, TelaColuna } from '../components/TelaNova';
import { escolherModelo, listarModelos, modeloEmUso, type Modelo, type Resultado } from '../servidor';

/** Modelos locais — o que está instalado, o que ocupa disco, o que está em uso.
 *  Referência: referencias/telas/13-modelos-locais.png.
 *
 *  PROVISÓRIO — visual novo (27/11/2026, layout.visualNovo.tela): a moldura da
 *  Memória aprovada (a coluna da conversa, a linha com o hover arredondado), as
 *  distâncias medidas na 13 (da contagem à lista, e a seção serifada como lá),
 *  o Em uso no tamanho da referência, o Baixar no botão do "Nova conversa" e as
 *  opções (⋯) só no hover, flutuando à esquerda da ponta direita, como as ações
 *  da Memória.
 *
 *  Os instalados vêm do Ollama, pelo servidor local (backend/). O nome aparece
 *  como o Ollama o chama ("llama3.1:8b"), não embelezado como na referência
 *  ("Llama 3.1 8B"): é o nome que se digita pra usar o modelo, e embelezar
 *  exigiria adivinhar a grafia de cada família. */

// PROVISÓRIO: o Ollama não tem catálogo por API. Esta lista é curada à mão e o
// "Baixar" ainda não faz nada — vira `POST /api/pull` quando o download entrar.
type Sugestao = { nome: string; tamanho: string; quant: string; contexto: string };

const DISPONIVEIS: Sugestao[] = [
  { nome: 'Gemma 2 9B', tamanho: '5,3 GB', quant: 'Q4_K_M', contexto: '8192 de contexto' },
  { nome: 'Phi-3 Medium 4K', tamanho: '2,6 GB', quant: 'Q4_K_M', contexto: '4096 de contexto' },
  { nome: 'DeepSeek Coder 6.7B', tamanho: '3,8 GB', quant: 'Q4_K_M', contexto: '16k de contexto' },
];

const GB = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Mesmas unidades do `ollama list` (10^9 e 10^6), pra o número bater com o
 *  terminal. Abaixo de 1 GB vira MB: um modelo de embeddings de 274 MB
 *  apareceria como "0,3 GB". */
const gb = (bytes: number) => `${GB.format(bytes / 1e9)} GB`;
const tamanho = (bytes: number) => (bytes < 1e9 ? `${Math.round(bytes / 1e6)} MB` : gb(bytes));

/** "128k" a partir de 16k, número cheio abaixo disso — é como a referência
 *  escreve (8192, 4096, 32k, 128k). */
const contexto = (n: number) => `${n >= 16384 ? `${Math.round(n / 1024)}k` : n} de contexto`;

/** ":latest" é a tag padrão do Ollama — não diz nada e só alonga a linha. */
const nomeCurto = (nome: string) => nome.replace(/:latest$/, '');

function detalhesDe(m: Modelo) {
  return [tamanho(m.bytes), m.quantizacao, m.contexto && contexto(m.contexto)].filter(Boolean).join(' · ');
}

function Detalhes({ texto }: { texto: string }) {
  return (
    <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
      {texto}
    </div>
  );
}

export function ModelosLocais() {
  // null = ainda perguntando. Não há "carregando" visível: o servidor é local e
  // responde em milissegundos; um indicador só piscaria.
  const [resultado, definirResultado] = useState<Resultado<Modelo[]> | null>(null);
  // Só pra re-renderizar ao escolher: a escolha em si mora na config local.
  const [, definirEscolha] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    listarModelos().then((r) => vivo && definirResultado(r));
    return () => {
      vivo = false;
    };
  }, []);

  if (resultado?.estado === 'sem-servidor') {
    return (
      <TelaColuna
        titulo="Modelos locais"
        estado={
          <EstadoVazio
            icone="modelos"
            titulo="Servidor do Solis desligado"
            corpo={'Sem ele, o Solis não enxerga os modelos instalados.\nIniciar com npm run backend.'}
          />
        }
      />
    );
  }

  // Texto de ERROR_STATES.md §2.
  if (resultado?.estado === 'sem-ollama') {
    return (
      <TelaColuna
        titulo="Modelos locais"
        estado={
          <EstadoVazio
            icone="modelos"
            titulo="Ollama fora do ar"
            corpo={'Não consegui acessar o modelo local.\nVerificar se o Ollama está rodando.'}
          />
        }
      />
    );
  }

  // Só o título até a resposta chegar: montar "Disponíveis" antes faria a
  // seção pular pra baixo quando os instalados aparecessem em cima dela.
  if (resultado === null) return <TelaColuna titulo="Modelos locais" />;

  const instalados = resultado.dados;
  const emUso = modeloEmUso(instalados);
  const total = instalados.reduce((soma, m) => soma + m.bytes, 0);
  const subtitulo =
    instalados.length === 0
      ? 'Nenhum modelo instalado ainda'
      : `${instalados.length} ${instalados.length === 1 ? 'modelo' : 'modelos'} · ${gb(total)} em disco`;

  return (
    <TelaColuna titulo="Modelos locais" subtitulo={subtitulo}>
      {instalados.map((m) => (
        <LinhaColuna
          key={m.nome}
          // Clicar na linha escolhe o modelo da Conversa. Embeddings não
          // conversa, então a linha dele não é clicável.
          aoClicar={
            m.embeddings
              ? undefined
              : () => {
                  escolherModelo(m.nome);
                  definirEscolha(m.nome);
                }
          }
          rotulo={m.embeddings ? undefined : `Usar ${nomeCurto(m.nome)} na Conversa`}
        >
          <div className="flex items-center gap-lg">
            <div className="flex-1">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{nomeCurto(m.nome)}</div>
              <Detalhes texto={detalhesDe(m)} />
            </div>
            {/* A ponta direita fica alinhada com o Baixar das linhas de baixo:
                as opções (⋯) flutuam à esquerda dela, sem tomar lugar, e só
                aparecem no hover ou no foco do teclado, como as ações da
                Memória. O fundo é o da linha com o véu. stopPropagation: o
                menu fica dentro da linha clicável, e abrir as opções não pode
                escolher o modelo de quebra. */}
            <div className="shrink-0 relative flex items-center">
              <button
                type="button"
                className="absolute flex items-center justify-center text-text-secondary opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity hover:text-text-primary"
                style={{
                  right: '100%',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  marginRight: m.nome === emUso || m.embeddings ? 'var(--mac-data-gap)' : 0,
                  width: 'var(--mac-alvo)',
                  height: 'var(--mac-alvo)',
                  borderRadius: 'var(--mac-botao-raio)',
                  background: 'linear-gradient(var(--mem-hover), var(--mem-hover)), var(--canvas)',
                }}
                aria-label={`Opções de ${nomeCurto(m.nome)}`}
                onClick={(e) => e.stopPropagation()}
              >
                <Icone nome="mais" tamanho="var(--mac-icone)" />
              </button>
              {/* "Em uso" é etiqueta preenchida e "Embeddings" é só texto: um é
                  estado do sistema agora, o outro é uma função permanente. Dar o
                  mesmo peso visual aos dois esconderia qual modelo está rodando. */}
              {m.nome === emUso && (
                <span
                  className="bg-accent text-canvas flex items-center"
                  style={{
                    fontSize: 'var(--mem-data)',
                    height: 'var(--vn-tela-etiqueta-h)',
                    padding: '0 var(--vn-tela-etiqueta-px)',
                    borderRadius: 'var(--vn-tela-etiqueta-raio)',
                  }}
                >
                  Em uso
                </span>
              )}
              {m.embeddings && (
                <span className="text-text-secondary" style={{ fontSize: 'var(--mem-data)' }}>
                  Embeddings
                </span>
              )}
            </div>
          </div>
        </LinhaColuna>
      ))}

      <SecaoColuna>Disponíveis para baixar</SecaoColuna>
      {DISPONIVEIS.map((m) => (
        <LinhaColuna key={m.nome}>
          <div className="flex items-center gap-lg">
            <div className="flex-1">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{m.nome}</div>
              <Detalhes texto={`${m.tamanho} · ${m.quant} · ${m.contexto}`} />
            </div>
            <BotaoBorda>Baixar</BotaoBorda>
          </div>
        </LinhaColuna>
      ))}
    </TelaColuna>
  );
}
