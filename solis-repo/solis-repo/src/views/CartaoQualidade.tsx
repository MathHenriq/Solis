import { useEffect, useState } from 'react';
import { Icone } from '../components/icons';
import { NOMES_CEREBRO, lerQualidade, type FuncaoQualidade, type Qualidade, type TesteQualidade } from '../servidor';
import { quando } from './CartaoAgendadas';

/** Configurações → Taxa de acerto (IDEIAS.md, princípios 3 e 4; decisões do
 *  Matheus, 17/11/2026): por função, quantas vezes RODOU sem falhar (o que o
 *  Solis sabe sozinho, do registro de uso) e o que ele achou das respostas (o
 *  voto, 👍/👎 — só ele sabe se ACERTOU). E os testes de qualidade com meta:
 *  cada um passou, não passou, ou a função ainda não tem teste. Mostra, não
 *  desliga. Todo número aqui é real (princípio 5): sem gráfico decorativo.
 *
 *  Aprovado pelo Matheus pelos prints (17/11/2026, design/qualidade-validacao.png).
 *  Desenho próprio, com o Claude como base: o cartão
 *  e as linhas do de Uso (layout.configuracoes.cerebros e .uso), com o "Ver de
 *  novo" dele. Nenhum valor novo (layout.configuracoes.qualidade). */

const FERRAMENTAS: Record<string, string> = {
  Read: 'Ler arquivos',
  ler_arquivo: 'Ler arquivos',
  Write: 'Escrever arquivos',
  Edit: 'Editar arquivos',
  MultiEdit: 'Editar arquivos',
  NotebookEdit: 'Editar arquivos',
  Bash: 'Terminal',
  PowerShell: 'Terminal',
  Grep: 'Procurar nos arquivos',
  Glob: 'Procurar nos arquivos',
  LS: 'Procurar nos arquivos',
  buscar_arquivos: 'Procurar nos arquivos',
  listar_pasta: 'Procurar nos arquivos',
  WebSearch: 'Pesquisa na web',
  WebFetch: 'Ler páginas da web',
  Skill: 'Skills',
  Task: 'Ajudantes',
  Agent: 'Ajudantes',
};

/** O nome de uma função como o Matheus reconhece. As ferramentas de nomes
 *  diferentes que fazem a mesma coisa (Read e ler_arquivo) contam juntas. */
function rotulo(f: Pick<FuncaoQualidade, 'tipo' | 'nome'>): string {
  if (f.tipo === 'cerebro') return f.nome === 'solis' ? 'Respostas rápidas' : NOMES_CEREBRO[f.nome] ?? f.nome;
  if (f.tipo === 'mcp') {
    if (f.nome === 'solis') return 'Agenda, lembretes e tela';
    if (f.nome === 'navegador') return 'Navegador';
    if (f.nome.startsWith('claude_ai_')) return `Conector ${f.nome.slice('claude_ai_'.length).replace(/_/g, ' ')}`;
    return `Servidor MCP ${f.nome}`;
  }
  return FERRAMENTAS[f.nome] ?? f.nome;
}

/** Junta as que têm o mesmo nome na tela, e devolve na ordem de mais usadas. */
function agrupar(funcoes: FuncaoQualidade[]): (FuncaoQualidade & { rotulo: string })[] {
  const grupos = new Map<string, FuncaoQualidade & { rotulo: string }>();
  for (const f of funcoes) {
    const r = rotulo(f);
    const g = grupos.get(r);
    if (!g) {
      grupos.set(r, { ...f, falhas: [...f.falhas], rotulo: r });
      continue;
    }
    g.usos += f.usos;
    g.certos += f.certos;
    g.bons += f.bons;
    g.ruins += f.ruins;
    g.falhas = [...g.falhas, ...f.falhas].sort((a, b) => b.quando.localeCompare(a.quando));
  }
  return [...grupos.values()].sort((a, b) => b.usos - a.usos);
}

const pct = (certos: number, usos: number) => Math.round((100 * certos) / usos);

function Linha({ titulo, direita, ruim, children }: { titulo: string; direita: string; ruim?: boolean; children?: React.ReactNode }) {
  return (
    <div className="border-t border-divider" style={{ marginTop: 'var(--cer-linha-pad)', paddingTop: 'var(--cer-linha-pad)' }}>
      <div className="flex items-baseline justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
        <span className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{titulo}</span>
        <span className={`shrink-0 ${ruim ? 'text-[var(--erro)]' : 'text-text-secondary'}`} style={{ fontSize: 'var(--cfg-dica)' }}>
          {direita}
        </span>
      </div>
      {children}
    </div>
  );
}

const dica = { fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)', maxWidth: 'var(--cer-texto-max)' } as const;

function Votos({ bons, ruins }: { bons: number; ruins: number }) {
  if (!bons && !ruins) return <>sem voto ainda</>;
  const icone = 'calc(var(--cfg-dica) - 1px)';
  return (
    <>
      <span className="inline-flex items-center" style={{ gap: 3 }} title="Respostas boas, pelo seu voto">
        <Icone nome="polegar" tamanho={icone} /> {bons}
      </span>
      {' · '}
      <span className="inline-flex items-center" style={{ gap: 3 }} title="Respostas ruins, pelo seu voto">
        <Icone nome="polegar-baixo" tamanho={icone} /> {ruins}
      </span>
    </>
  );
}

function LinhaFuncao({ f, cerebro }: { f: FuncaoQualidade & { rotulo: string }; cerebro: boolean }) {
  const falhou = f.usos - f.certos;
  const ultima = f.falhas[0];
  return (
    <Linha titulo={f.rotulo} direita={`${f.certos} de ${f.usos} sem falhar (${pct(f.certos, f.usos)}%)`} ruim={f.certos / f.usos < 0.9}>
      {cerebro && (
        <div className="text-text-secondary flex flex-wrap items-center" style={{ ...dica, columnGap: 6 }}>
          <Votos bons={f.bons} ruins={f.ruins} />
        </div>
      )}
      {falhou > 0 && ultima && (
        <div className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
          Última falha {quando(ultima.quando)}
          {ultima.detalhe ? `: ${ultima.detalhe}` : ''}
        </div>
      )}
    </Linha>
  );
}

const NOMES_TESTE: Record<string, string> = { escuta: 'Escuta da voz', aprendizado: 'Aprendizado da memória' };

function LinhaTeste({ t, meta }: { t: TesteQualidade; meta: number }) {
  return (
    <Linha titulo={NOMES_TESTE[t.id] ?? t.id} direita={`${t.certos} de ${t.total} · ${t.passou ? 'passou' : 'não passou'}`} ruim={!t.passou}>
      <div className="text-text-secondary" style={dica}>
        Meta: {Math.round(meta * 10)} em 10
        {t.falsos !== null ? `, sem chamada falsa · ${t.falsos === 0 ? 'nenhuma falsa' : `${t.falsos} ${t.falsos === 1 ? 'falsa' : 'falsas'}`}` : ''}
        {t.quando ? ` · ${quando(t.quando)}` : ''}
      </div>
    </Linha>
  );
}

function Subtitulo({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-text-secondary" style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-linha-pad)' }}>
      {children}
    </h3>
  );
}

export function CartaoQualidade() {
  // undefined = lendo; null = não deu.
  const [q, definir] = useState<Qualidade | null | undefined>(undefined);
  const ler = () => {
    definir(undefined);
    void lerQualidade().then(definir);
  };
  useEffect(() => ler(), []);

  const cerebros = q ? agrupar(q.funcoes.filter((f) => f.tipo === 'cerebro')) : [];
  const ferramentas = q ? agrupar(q.funcoes.filter((f) => f.tipo !== 'cerebro')) : [];

  return (
    <section className="cfg-cartao">
      <div className="flex items-start justify-between" style={{ gap: 'var(--cer-controles-gap)' }}>
        <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Taxa de acerto</h2>
        <button
          type="button"
          onClick={ler}
          disabled={q === undefined}
          className="text-text-secondary hover:text-text-primary hover:underline disabled:opacity-50 shrink-0"
          style={{ fontSize: 'var(--cfg-dica)' }}
        >
          Ver de novo
        </button>
      </div>
      <p className="text-text-secondary" style={{ ...dica, textWrap: 'pretty' }}>
        Nos últimos {q?.dias ?? 30} dias: quantas vezes cada função rodou sem falhar e o que você achou das respostas.
        Rodar não é acertar — só o seu voto, embaixo da resposta, diz se ela estava certa. Teste de qualidade com
        meta ({Math.round((q?.meta ?? 0.9) * 10)} em 10), por enquanto, só a escuta e o aprendizado têm.
      </p>

      {q === undefined && (
        <p className="text-text-secondary" style={{ ...dica, marginTop: 'var(--cer-linha-pad)' }}>Lendo o registro…</p>
      )}
      {q === null && (
        <p className="text-text-secondary" style={{ ...dica, marginTop: 'var(--cer-linha-pad)' }}>
          Não consegui ler o registro agora: o servidor do Solis não respondeu.
        </p>
      )}
      {q && !q.funcoes.length && !q.testes.length && (
        <p className="text-text-secondary" style={{ ...dica, marginTop: 'var(--cer-linha-pad)' }}>
          Nada usado nos últimos {q.dias} dias ainda.
        </p>
      )}

      {cerebros.length > 0 && (
        <>
          <Subtitulo>Cérebros</Subtitulo>
          {cerebros.map((f) => <LinhaFuncao key={f.rotulo} f={f} cerebro />)}
        </>
      )}
      {ferramentas.length > 0 && (
        <>
          <Subtitulo>Ferramentas</Subtitulo>
          {ferramentas.map((f) => <LinhaFuncao key={f.rotulo} f={f} cerebro={false} />)}
        </>
      )}
      {q && q.testes.length > 0 && (
        <>
          <Subtitulo>Testes de qualidade</Subtitulo>
          {q.testes.map((t) => <LinhaTeste key={t.id} t={t} meta={q.meta} />)}
        </>
      )}
    </section>
  );
}
