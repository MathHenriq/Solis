import { Icone } from '../components/icons';
import { BotaoContorno, LinhaLista, Tela } from '../components/Tela';

/** Modelos locais — o que está instalado, o que ocupa disco, o que está em uso.
 *  Referência: referencias/telas/13-modelos-locais.png.
 *
 *  PROVISÓRIO: a lista é estática. Quando o Ollama entrar, ela vem de
 *  `ollama list` e o tamanho em disco do próprio manifesto. */

type Modelo = { nome: string; tamanho: string; quant: string; contexto: string; papel?: 'uso' | 'embeddings' };

const INSTALADOS: Modelo[] = [
  { nome: 'Llama 3.1 8B', tamanho: '4,7 GB', quant: 'Q4_K_M', contexto: '128k de contexto', papel: 'uso' },
  { nome: 'Qwen 2.5 14B', tamanho: '8,1 GB', quant: 'Q4_K_M', contexto: '128k de contexto' },
  { nome: 'Mistral 7B', tamanho: '3,8 GB', quant: 'Q4_K_M', contexto: '32k de contexto' },
  { nome: 'Nomic Embed', tamanho: '1,6 GB', quant: 'Q4_K_M', contexto: '8192 de contexto', papel: 'embeddings' },
];

const DISPONIVEIS: Modelo[] = [
  { nome: 'Gemma 2 9B', tamanho: '5,3 GB', quant: 'Q4_K_M', contexto: '8192 de contexto' },
  { nome: 'Phi-3 Medium 4K', tamanho: '2,6 GB', quant: 'Q4_K_M', contexto: '4096 de contexto' },
  { nome: 'DeepSeek Coder 6.7B', tamanho: '3,8 GB', quant: 'Q4_K_M', contexto: '16k de contexto' },
];

function Detalhes({ m }: { m: Modelo }) {
  return (
    <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
      {m.tamanho} · {m.quant} · {m.contexto}
    </div>
  );
}

export function ModelosLocais() {
  return (
    <Tela titulo="Modelos locais" subtitulo="4 modelos · 18,2 GB em disco">
      {INSTALADOS.map((m) => (
        <LinhaLista key={m.nome}>
          <div className="flex items-center gap-lg">
            <div className="flex-1">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{m.nome}</div>
              <Detalhes m={m} />
            </div>
            {/* "Em uso" é etiqueta preenchida e "Embeddings" é só texto: um é
                estado do sistema agora, o outro é uma função permanente. Dar o
                mesmo peso visual aos dois esconderia qual modelo está rodando. */}
            {m.papel === 'uso' && (
              <span
                className="bg-accent text-canvas shrink-0"
                style={{ fontSize: 'var(--mem-data)', padding: '7px 16px', borderRadius: 8 }}
              >
                Em uso
              </span>
            )}
            {m.papel === 'embeddings' && (
              <span className="text-text-secondary shrink-0" style={{ fontSize: 'var(--mem-data)' }}>
                Embeddings
              </span>
            )}
            <button type="button" className="text-text-secondary shrink-0" aria-label={`Opções de ${m.nome}`}>
              <Icone nome="mais" tamanho={20} />
            </button>
          </div>
        </LinhaLista>
      ))}

      <h2
        className="text-text-primary"
        style={{ fontSize: 'var(--cfg-secao)', marginTop: 'calc(var(--mem-item-pad-y) * 2)' }}
      >
        Disponíveis para baixar
      </h2>
      {DISPONIVEIS.map((m) => (
        <LinhaLista key={m.nome}>
          <div className="flex items-center gap-lg">
            <div className="flex-1">
              <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{m.nome}</div>
              <Detalhes m={m} />
            </div>
            <BotaoContorno>Baixar</BotaoContorno>
          </div>
        </LinhaLista>
      ))}
    </Tela>
  );
}
