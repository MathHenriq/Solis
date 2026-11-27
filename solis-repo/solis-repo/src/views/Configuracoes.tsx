import { useState, type ReactNode } from 'react';
import { Interruptor, Segmentado } from '../components/Controles';
import { TelaColuna } from '../components/TelaNova';
import { TEMAS, type EstiloNav, type Tema } from '../theme/theme';
import { CartaoAgendadas } from './CartaoAgendadas';
import { CartaoCerebros } from './CartaoCerebros';
import { CartaoConectores } from './CartaoConectores';
import { CartaoEstilos } from './CartaoEstilos';
import { CartaoNavegador } from './CartaoNavegador';
import { CartaoServidoresMcp } from './CartaoServidoresMcp';
import { CartaoHooks } from './CartaoHooks';
import { CartaoSkills } from './CartaoSkills';
import { CartaoTela } from './CartaoTela';
import { CartaoAvisosCelular } from './CartaoAvisosCelular';
import { CartaoServidor } from './CartaoServidor';
import { CartaoUso } from './CartaoUso';
import { CartaoQualidade } from './CartaoQualidade';
import { CartaoDocumentos } from './CartaoDocumentos';
import { CartaoVoz } from './CartaoVoz';

/** Configurações.
 *
 *  Aparência: medidas de referencias/telas/11-configuracoes-aparencia.png, em
 *  solis-tokens.json → layout.configuracoes. Tipografia derivada pelas razões
 *  contra o corpo de 16px, não por px bruto da imagem — ver
 *  layout.memoria._escala para o porquê.
 *
 *  São TRÊS controles e só três. "Cor de destaque" foi removido do produto: o
 *  accent é fixo por tema, e desde que ele passou a ser derivado até 4,5:1 ele
 *  também não é mais uma escolha livre — deixar o usuário trocar reintroduziria
 *  o problema de contraste que a derivação resolveu.
 *
 *  PROVISÓRIO — visual novo (27/11/2026, layout.visualNovo.config): a moldura
 *  das outras telas (a coluna da conversa) e, como nas configurações do Claude,
 *  abas no topo em vez de 16 cartões numa coluna só. Cada cartão vira uma seção
 *  sem caixa, separada da próxima por uma divisória (.cfg-cartao no index.css). */

const NOME_TEMA: Record<Tema, string> = {
  espacial: 'Espacial',
  claro: 'Claro',
  dark: 'Dark',
};

/** As abas, na ordem do uso: o que se mexe mais vem antes. */
const ABAS = [
  { id: 'geral', nome: 'Geral' },
  { id: 'cerebros', nome: 'Cérebros' },
  { id: 'voz', nome: 'Voz' },
  { id: 'ferramentas', nome: 'Ferramentas' },
  { id: 'agendadas', nome: 'Agendadas' },
  { id: 'celular', nome: 'Celular e servidor' },
] as const;
type Aba = (typeof ABAS)[number]['id'];

const CHAVE_ABA = 'solis.configuracoes.aba';

/** A aba que Configurações abre (quem leva pra cá, como o "criar estilo" da
 *  Conversa, escolhe antes). Guardada no navegador: é só conveniência. */
export function abrirAbaConfiguracoes(aba: Aba) {
  try {
    localStorage.setItem(CHAVE_ABA, aba);
  } catch {
    /* sem armazenamento: abre na Geral */
  }
}

function abaGuardada(): Aba {
  try {
    const a = localStorage.getItem(CHAVE_ABA);
    if (ABAS.some((x) => x.id === a)) return a as Aba;
  } catch {
    /* sem armazenamento */
  }
  return 'geral';
}

function Linha({ rotulo, dica, children }: { rotulo: string; dica?: string; children?: ReactNode }) {
  return (
    <div
      className="flex flex-wrap items-center justify-between border-t border-divider first:border-t-0"
      style={{ paddingTop: 'var(--cfg-linha-pad)', paddingBottom: 'var(--cfg-linha-pad)', columnGap: 16, rowGap: 12 }}
    >
      <div>
        <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>{rotulo}</div>
        {dica && (
          <div
            className="text-text-secondary"
            style={{ fontSize: 'var(--cfg-dica)', marginTop: 'var(--cfg-dica-top)' }}
          >
            {dica}
          </div>
        )}
      </div>
      {children}
    </div>
  );
}

/** Miniatura do tema: uma prévia da PRÓPRIA tela, não um ícone de lua ou sol.
 *  É desenhada com as custom properties do tema que ela representa, dentro de um
 *  `data-theme` local — então ela não pode divergir do tema de verdade, porque
 *  lê exatamente os mesmos tokens. Na coluna nova as três dividem a largura. */
function Miniatura({ tema, ativo, aoEscolher }: { tema: Tema; ativo: boolean; aoEscolher: () => void }) {
  return (
    <button type="button" onClick={aoEscolher} aria-pressed={ativo} className="text-left min-w-0">
      <div
        data-theme={tema}
        className="relative overflow-hidden bg-canvas"
        style={{
          aspectRatio: 'var(--cfg-mini-razao)',
          borderRadius: 'var(--cfg-mini-raio)',
          border: ativo ? '2px solid var(--accent)' : '1px solid var(--vn-caixa-borda)',
        }}
      >
        <div className="absolute inset-y-0 left-0 border-r border-divider" style={{ width: '14%' }} />
        <div className="absolute" style={{ left: '22%', right: '10%', top: '16%' }}>
          {[100, 74, 88].map((l, i) => (
            <div
              key={i}
              className="bg-text-primary"
              style={{ height: 3, width: `${l}%`, marginTop: i ? 9 : 0, opacity: i ? 0.35 : 0.8 }}
            />
          ))}
        </div>
        {/* A cena aparece na miniatura pelo mesmo mecanismo da tela real: é a
            imagem do tema, ancorada embaixo. */}
        <div
          className="absolute inset-x-0 bottom-0"
          style={{
            height: '46%',
            backgroundImage: 'var(--solis-horizon-image, none)',
            backgroundSize: 'cover',
            backgroundPosition: '50% 66%',
            maskImage: 'linear-gradient(to bottom, transparent, #000 55%)',
            WebkitMaskImage: 'linear-gradient(to bottom, transparent, #000 55%)',
          }}
        />
      </div>
      <div
        className={ativo ? 'text-text-primary' : 'text-text-secondary'}
        style={{ fontSize: 'var(--cfg-rotulo)', marginTop: 'var(--cfg-mini-nome-top)', textAlign: 'center' }}
      >
        {NOME_TEMA[tema]}
      </div>
    </button>
  );
}

/** As abas: linhas como as da barra lateral (36, raio 9, o véu na ativa). No
 *  celular rolam pro lado, sem quebrar. */
function Abas({ ativa, aoTrocar }: { ativa: Aba; aoTrocar: (a: Aba) => void }) {
  return (
    <div
      role="tablist"
      aria-label="Seções de Configurações"
      className="vn-abas flex overflow-x-auto"
      style={{ marginTop: 'var(--vn-cfg-abas-top)', gap: 'var(--vn-cfg-aba-gap)' }}
    >
      {ABAS.map((a) => {
        const esta = a.id === ativa;
        return (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={esta}
            onClick={() => aoTrocar(a.id)}
            className={`shrink-0 whitespace-nowrap ${esta ? 'text-text-primary' : 'text-[var(--vn-inativo)] hover:text-text-primary hover:bg-[var(--mem-hover)]'}`}
            style={{
              height: 'var(--vn-sb-item-h)',
              padding: '0 var(--vn-cfg-aba-px)',
              borderRadius: 'var(--vn-sb-item-raio)',
              fontSize: 'var(--vn-sb-rotulo)',
              fontWeight: esta ? 500 : undefined,
              background: esta ? 'var(--vn-ativo)' : undefined,
            }}
          >
            {a.nome}
          </button>
        );
      })}
    </div>
  );
}

function Aparencia({
  tema,
  aoTrocarTema,
  cena,
  aoTrocarCena,
  nav,
  aoTrocarNav,
}: {
  tema: Tema;
  aoTrocarTema: (t: Tema) => void;
  cena: boolean;
  aoTrocarCena: (v: boolean) => void;
  nav: EstiloNav;
  aoTrocarNav: (e: EstiloNav) => void;
}) {
  return (
    <section className="cfg-cartao">
      <h2 className="text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>Aparência</h2>

      <div style={{ marginTop: 'var(--cfg-linha-pad)' }}>
        <div className="text-text-primary" style={{ fontSize: 'var(--cfg-rotulo)' }}>Tema</div>
        <div className="grid grid-cols-3" style={{ gap: 'var(--vn-tela-grade-gap)', marginTop: 'var(--cfg-linha-pad)' }}>
          {TEMAS.map((t) => (
            <Miniatura key={t} tema={t} ativo={t === tema} aoEscolher={() => aoTrocarTema(t)} />
          ))}
        </div>
      </div>

      <div style={{ marginTop: 'var(--cfg-linha-pad)' }}>
        <Linha rotulo="Navegação" dica="Onde os atalhos das telas ficam">
          {/* Segmentado, não dois botões soltos: são opções mutuamente
              exclusivas do mesmo eixo, e a forma tem que dizer isso. */}
          <Segmentado
            opcoes={[['sidebar', 'Barra lateral'], ['icones', 'Barra de ícones']] as const}
            valor={nav}
            aoTrocar={aoTrocarNav}
            rotulo="Estilo de navegação"
          />
        </Linha>

        <Linha rotulo="Exibir imagem de fundo" dica="Desligado, o tema usa cor sólida">
          <Interruptor ligado={cena} rotulo="Exibir imagem de fundo" aoTrocar={aoTrocarCena} />
        </Linha>
      </div>
    </section>
  );
}

export function Configuracoes({
  tema,
  aoTrocarTema,
  cena,
  aoTrocarCena,
  nav,
  aoTrocarNav,
  aoAbrirConversa,
}: {
  tema: Tema;
  aoTrocarTema: (t: Tema) => void;
  cena: boolean;
  aoTrocarCena: (v: boolean) => void;
  nav: EstiloNav;
  aoTrocarNav: (e: EstiloNav) => void;
  /** As tarefas agendadas abrem a conversa onde o Claude respondeu. */
  aoAbrirConversa?: (id: number) => void;
}) {
  const [aba, definirAba] = useState<Aba>(abaGuardada);
  const trocar = (a: Aba) => {
    definirAba(a);
    abrirAbaConfiguracoes(a);
  };

  return (
    <TelaColuna titulo="Configurações" topo={<Abas ativa={aba} aoTrocar={trocar} />}>
      <div role="tabpanel" aria-label={ABAS.find((a) => a.id === aba)?.nome} className="cfg-painel">
        {aba === 'geral' && (
          <Aparencia
            tema={tema}
            aoTrocarTema={aoTrocarTema}
            cena={cena}
            aoTrocarCena={aoTrocarCena}
            nav={nav}
            aoTrocarNav={aoTrocarNav}
          />
        )}
        {aba === 'cerebros' && (
          <>
            <CartaoCerebros />
            <CartaoEstilos />
            <CartaoUso />
            <CartaoQualidade />
          </>
        )}
        {aba === 'voz' && <CartaoVoz />}
        {aba === 'ferramentas' && (
          <>
            <CartaoConectores />
            <CartaoServidoresMcp />
            <CartaoSkills />
            <CartaoHooks />
            <CartaoNavegador />
            <CartaoTela />
            <CartaoDocumentos />
          </>
        )}
        {aba === 'agendadas' && <CartaoAgendadas aoAbrirConversa={aoAbrirConversa} />}
        {aba === 'celular' && (
          <>
            <CartaoAvisosCelular />
            <CartaoServidor />
          </>
        )}
      </div>
    </TelaColuna>
  );
}
