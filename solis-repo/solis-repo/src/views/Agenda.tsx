import { Icone } from '../components/icons';
import { Tela } from '../components/Tela';

/** Agenda — o DIA em linha do tempo vertical, não uma grade de mês.
 *  Referência: referencias/telas/16-agenda.png.
 *
 *  A grade mensal responde "que dia é hoje"; a linha do tempo responde "o que
 *  vem agora", que é a pergunta que alguém faz ao assistente. Os buracos entre
 *  horas são informação: mostram onde sobra tempo.
 *
 *  PROVISÓRIO: lista estática, e a data não vem do relógio. */

type Compromisso = { hora: string; titulo: string; duracao: string; onde: string; proximo?: boolean };

const DIA: Compromisso[] = [
  { hora: '09:00', titulo: 'Reunião de alinhamento do projeto', duracao: '1h', onde: 'Google Meet' },
  { hora: '11:30', titulo: 'Aula: Engenharia de Prompt', duracao: '1h30', onde: 'online' },
  { hora: '14:00', titulo: 'Foco: desenvolvimento do Solis', duracao: '2h', onde: 'trabalho profundo', proximo: true },
  { hora: '16:00', titulo: 'Revisar arquitetura da API', duracao: '45 min', onde: 'remoto' },
  { hora: '19:30', titulo: 'Treino de musculação', duracao: '1h15', onde: 'academia' },
];

export function Agenda() {
  return (
    <Tela
      titulo="Agenda"
      subtitulo="Sexta, 14 de março"
      acao={
        <div className="flex items-center gap-md shrink-0">
          <button type="button" className="border border-divider rounded-md text-text-primary flex items-center justify-center"
                  style={{ width: 'var(--cfg-sw-l)', height: 'var(--cfg-sw-l)' }} aria-label="Dia anterior">
            <Icone nome="anterior" tamanho={20} />
          </button>
          <button type="button" className="border border-divider rounded-md text-text-primary flex items-center justify-center"
                  style={{ width: 'var(--cfg-sw-l)', height: 'var(--cfg-sw-l)' }} aria-label="Próximo dia">
            <Icone nome="proximo" tamanho={20} />
          </button>
          <button type="button" className="border border-divider rounded-md text-text-primary"
                  style={{ height: 'var(--cfg-sw-l)', paddingLeft: 22, paddingRight: 22, fontSize: 'var(--cfg-rotulo)' }}>
            Hoje
          </button>
        </div>
      }
    >
      <ol className="relative">
        {DIA.map((c) => (
          <li key={c.hora} className="flex items-start" style={{ paddingTop: 22, paddingBottom: 22 }}>
            <span
              className="text-text-secondary shrink-0 text-right"
              style={{ width: 92, fontSize: 'var(--mem-data)', paddingTop: 2 }}
            >
              {c.hora}
            </span>

            {/* A linha corre por trás dos pontos e é desenhada por item, não uma
                única barra absoluta: assim ela acompanha a altura real de cada
                bloco, que varia com o texto. */}
            <span className="relative shrink-0" style={{ width: 56 }} aria-hidden>
              <span className="absolute bg-divider" style={{ left: 27, top: -22, bottom: -22, width: 2 }} />
              <span
                className="absolute rounded-pill"
                style={{
                  left: 22, top: 4, width: 12, height: 12,
                  background: c.proximo ? 'var(--accent)' : 'var(--divider)',
                }}
              />
            </span>

            <span
              className="flex-1"
              style={{
                background: c.proximo ? 'var(--mem-hover)' : undefined,
                borderRadius: c.proximo ? 12 : undefined,
                padding: c.proximo ? '14px 20px' : undefined,
                marginTop: c.proximo ? -14 : undefined,
                marginLeft: c.proximo ? -20 : undefined,
              }}
            >
              <span className="block text-text-primary" style={{ fontSize: 'var(--cfg-secao)' }}>{c.titulo}</span>
              <span
                className="block text-text-secondary"
                style={{ fontSize: 'var(--mem-origem)', marginTop: 'var(--mem-origem-top)' }}
              >
                {c.duracao} · {c.onde}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </Tela>
  );
}
