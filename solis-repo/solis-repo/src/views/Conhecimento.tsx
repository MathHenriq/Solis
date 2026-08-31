import { useState } from 'react';
import { Icone, type NomeIcone } from '../components/icons';
import { BotaoContorno, Tela } from '../components/Tela';

/** Conhecimento — os documentos que a pessoa deu pro Solis ler.
 *  Referência: referencias/telas/17-conhecimento.png.
 *
 *  Não confundir com Memória: lá são fatos curtos que ele aprendeu sozinho; aqui
 *  são fontes que ela entregou. Por isso grade de cartões e não lista — cada
 *  fonte é um objeto com identidade, não uma linha de texto.
 *
 *  PROVISÓRIO: grade estática, e o progresso de indexação não é real. */

type Fonte = { nome: string; tipo: string; detalhe: string; icone: NomeIcone; progresso?: number };

const FONTES: Fonte[] = [
  { nome: 'Documentação do Tauri 2', tipo: 'PDF', detalhe: '240 páginas · há 2 dias', icone: 'documento' },
  { nome: 'Anotações da faculdade', tipo: 'Nota', detalhe: '156 páginas · há 3 dias', icone: 'nota' },
  { nome: 'Arquitetura de sistemas locais', tipo: 'Página web', detalhe: 'há 1 semana', icone: 'web' },
  { nome: 'SQLite FTS5 — referência', tipo: 'PDF', detalhe: '89 páginas · há 1 semana', icone: 'documento' },
  { nome: 'FastAPI — docs oficiais', tipo: 'Página web', detalhe: 'há 2 semanas', icone: 'web' },
  { nome: 'Guia de Prompt Engineering', tipo: 'PDF', detalhe: '', icone: 'documento', progresso: 64 },
  { nome: 'Ideias de funcionalidades', tipo: 'Nota', detalhe: 'há 3 semanas', icone: 'nota' },
  { nome: 'Padrões de projeto', tipo: 'PDF', detalhe: '312 páginas · há 1 mês', icone: 'documento' },
  { nome: 'Princípios SOLID', tipo: 'Página web', detalhe: 'há 1 mês', icone: 'web' },
];

export function Conhecimento() {
  const [busca, definirBusca] = useState('');
  const vistas = busca ? FONTES.filter((f) => f.nome.toLowerCase().includes(busca.toLowerCase())) : FONTES;

  return (
    <Tela
      titulo="Conhecimento"
      subtitulo="12 fontes · 1.847 trechos indexados"
      acao={<BotaoContorno><span style={{ fontSize: 20, lineHeight: 1 }}>+</span> Adicionar fonte</BotaoContorno>}
    >
      <div
        className="flex items-center border border-divider"
        style={{ height: 'var(--mem-busca-h)', borderRadius: 'var(--mem-busca-raio)', marginBottom: 'var(--mem-lista-gap)' }}
      >
        <span className="text-text-secondary shrink-0" style={{ paddingLeft: 22, paddingRight: 16 }}>
          <Icone nome="buscar" tamanho={19} />
        </span>
        <input
          className="flex-1 bg-transparent outline-none text-text-primary placeholder:text-text-placeholder"
          style={{ fontSize: 'var(--mem-item-texto)', paddingRight: 22 }}
          placeholder="Buscar no conhecimento…"
          aria-label="Buscar no conhecimento"
          value={busca}
          onChange={(e) => definirBusca(e.target.value)}
        />
      </div>

      <div className="grid grid-cols-3" style={{ gap: 'var(--cfg-mini-gap)' }}>
        {vistas.map((f) => (
          <article
            key={f.nome}
            className="border border-divider hover:bg-[var(--mem-hover)]"
            style={{ borderRadius: 'var(--cfg-card-raio)', padding: 24 }}
          >
            <div className="flex items-start justify-between">
              <span className="text-text-secondary"><Icone nome={f.icone} tamanho={28} /></span>
              <button type="button" className="text-text-secondary" aria-label={`Opções de ${f.nome}`}>
                <Icone nome="mais" tamanho={18} />
              </button>
            </div>
            <div className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)', marginTop: 30 }}>{f.nome}</div>
            {f.progresso === undefined ? (
              <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}>
                {f.tipo} · {f.detalhe}
              </div>
            ) : (
              <div style={{ marginTop: 12 }}>
                {/* Barra de progresso desenhada, não <progress>: o nativo não
                    aceita altura nem cor consistentes entre navegadores. */}
                <div className="bg-divider" style={{ height: 4, borderRadius: 999 }}>
                  <div className="bg-accent" style={{ width: `${f.progresso}%`, height: 4, borderRadius: 999 }} />
                </div>
                <div className="text-text-secondary" style={{ fontSize: 'var(--mem-origem)', marginTop: 10 }}>
                  Indexando… {f.progresso}%
                </div>
              </div>
            )}
          </article>
        ))}
      </div>
    </Tela>
  );
}
