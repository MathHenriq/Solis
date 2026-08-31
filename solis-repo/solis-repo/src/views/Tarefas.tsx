import { LinhaLista, Tela } from '../components/Tela';

/** Tarefas — agrupadas por prazo, não por projeto.
 *  Referência: referencias/telas/15-tarefas.png.
 *
 *  PROVISÓRIO: lista estática e o check não persiste. */

type Tarefa = { id: number; texto: string; quando: string; origem?: string; feita?: boolean };
type Grupo = { titulo: string; itens: Tarefa[] };

const GRUPOS: Grupo[] = [
  {
    titulo: 'Hoje',
    itens: [
      { id: 1, texto: 'Revisar integração do Ollama com o Solis', quando: 'hoje, 10h', origem: 'Conversa sobre o TCC' },
      { id: 2, texto: 'Finalizar lógica de memória recente', quando: 'hoje, 14h', origem: 'Conversa sobre o Solis' },
      { id: 3, texto: 'Corrigir bug na busca semântica', quando: 'hoje, 18h', origem: 'Conversa sobre o Solis' },
    ],
  },
  {
    titulo: 'Esta semana',
    itens: [
      { id: 4, texto: 'Escrever seção de arquitetura do TCC', quando: 'quinta' },
      { id: 5, texto: 'Estudar FastAPI: middlewares e dependências', quando: 'sexta' },
      { id: 6, texto: 'Definir schema das tabelas do banco', quando: 'quarta', origem: 'Conversa sobre o Solis', feita: true },
    ],
  },
  {
    titulo: 'Depois',
    itens: [
      { id: 7, texto: 'Refatorar componente de chat em React', quando: '12 mar' },
      { id: 8, texto: 'Criação de testes para o módulo de tarefas', quando: '15 mar' },
      { id: 9, texto: 'Implementar exportação de conversas', quando: '18 mar' },
    ],
  },
];

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

export function Tarefas() {
  const paraHoje = GRUPOS[0].itens.filter((t) => !t.feita).length;
  const abertas = GRUPOS.flatMap((g) => g.itens).filter((t) => !t.feita).length;
  return (
    <Tela titulo="Tarefas" subtitulo={`${paraHoje} para hoje · ${abertas} abertas`}>
      {GRUPOS.map((g) => (
        <section key={g.titulo}>
          <h2
            className="text-text-secondary uppercase"
            style={{
              fontSize: 'var(--mem-origem)',
              letterSpacing: '0.08em',
              marginTop: 'var(--mem-item-pad-y)',
              marginBottom: 'var(--mem-origem-top)',
            }}
          >
            {g.titulo}
          </h2>
          {g.itens.map((t) => (
            <LinhaLista key={t.id}>
              <button type="button" role="checkbox" aria-checked={!!t.feita} className="flex items-start gap-lg w-full text-left">
                <Caixa marcada={!!t.feita} />
                <span className="flex-1">
                  <span
                    className={t.feita ? 'text-text-secondary line-through' : 'text-text-primary'}
                    style={{ fontSize: 'var(--mem-item-texto)' }}
                  >
                    {t.texto}
                  </span>
                  {t.origem && (
                    <span
                      className="block text-text-secondary"
                      style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}
                    >
                      de: {t.origem}
                    </span>
                  )}
                </span>
                <span className="text-text-secondary shrink-0 whitespace-nowrap" style={{ fontSize: 'var(--mem-data)' }}>
                  {t.quando}
                </span>
              </button>
            </LinhaLista>
          ))}
        </section>
      ))}
    </Tela>
  );
}
