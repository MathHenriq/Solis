import { useEffect, useRef, useState, type ReactElement } from 'react';
import { BarraIcones } from './components/BarraIcones';
import { Chamada, type FaseChamada } from './components/Chamada';
import { pedeConversa, useConversaVoz } from './conversaVoz';
import { EsferaVoz } from './components/EsferaVoz';
import { useJanelaEmFrente } from './janelaEmFrente';
import { Horizonte } from './components/Horizonte';
import { GavetaConversas, type PropsLista } from './components/ListaConversas';
import { Sidebar } from './components/Sidebar';
import { TopoIcones } from './components/TopoIcones';
import { useChamada } from './chamada';
import { noApp, useIlhaNoApp } from './tauri';
import { useConversa } from './conversa';
import { useEscuta } from './escuta';
import { falaAutomatica, marcarRespostaFalada } from './fala';
import { aplicarNav } from './theme/theme';
import { useTheme } from './theme/useTheme';
import { Agenda } from './views/Agenda';
import { Conhecimento } from './views/Conhecimento';
import { Configuracoes } from './views/Configuracoes';
import { Conversa } from './views/Conversa';
import { Ferramentas } from './views/Ferramentas';
import { Memoria } from './views/Memoria';
import { ModelosLocais } from './views/ModelosLocais';
import { Tarefas } from './views/Tarefas';
import { Thread } from './views/Thread';

/** Shell do app. O Horizonte fica AQUI, fora da árvore de views, porque a
 *  Camada 1 do SOLIS_SIGNATURE.md não pode ser remontada ao trocar de tela.
 *
 *  A troca de tela é um estado local, não um router: o Solis é uma janela só,
 *  local-first, sem URL pra compartilhar e sem histórico de navegador pra
 *  respeitar. Se um dia houver deep link do sistema operacional, isto vira um
 *  router de verdade. */
export default function App() {
  const [tela, definirTela] = useState('conversa');
  // A Conversa tem dois estados: vazia e com thread. Quem decide é ter ou não
  // mensagens — e a conversa mora aqui, então trocar de tela não a apaga.
  const conversa = useConversa();
  const { tema, setTema, cena, setCena, nav, setNav } = useTheme();
  // "Solis, ..." de qualquer tela: o que veio depois da palavra vira mensagem na
  // conversa aberta, e a resposta é falada (se "Responder falando" estiver ligado).
  // O modo Conversa (conversaVoz.ts): bate-papo por voz em tempo real. Cada troca
  // fica salva na conversa, que recarrega pra mostrar.
  const voz = useConversaVoz((id) => void conversa.abrir(id));
  // O botão das caixas de conversa (BotaoConversa): entra, ou sai se já estiver.
  useEffect(() => {
    const alternar = () => (voz.fase ? voz.encerrar() : voz.iniciar(conversa.conversa));
    window.addEventListener('solis-conversa', alternar);
    return () => window.removeEventListener('solis-conversa', alternar);
  }, [voz, conversa.conversa]);
  // Só em desenvolvimento: abrir o modo Conversa pela página (pra ver sem microfone de verdade).
  if (import.meta.env.DEV) (window as unknown as { __conversa?: () => void }).__conversa = () => voz.iniciar(conversa.conversa);
  // Chamado de novo com uma resposta ainda chegando (o Claude trabalhando, por
  // exemplo): a resposta de antes para e o pedido novo vai assim que ela parar.
  // Antes o pedido novo era ignorado calado (o campo estava ocupado), e a ilha
  // mostrava a frase nova com a resposta da anterior (relato do Matheus, 18/11/2026).
  const pedidoNaFila = useRef<string | null>(null);
  // O pedido ao vivo: o que o Solis está dizendo (a resposta na ilha enquanto fala);
  // null fora dele, e a ilha mostra a última resposta da conversa, como sempre.
  const [respostaAoVivo, definirRespostaAoVivo] = useState<string | null>(null);
  const escuta = useEscuta(
    (texto) => {
      definirRespostaAoVivo(null);
      definirTela('conversa');
      if (pedeConversa(texto)) {
        voz.iniciar(conversa.conversa);
        return;
      }
      chamada.enviado(texto);
      if (conversa.respondendo) {
        pedidoNaFila.current = texto;
        conversa.parar();
        return;
      }
      marcarRespostaFalada(falaAutomatica());
      conversa.enviar(texto);
    },
    // Na conversa, o microfone é dela: a escuta do "Solis" desliga.
    voz.fase !== null,
    // O pedido ao vivo (backend/solis/pedido_ao_vivo.py): com "Responder falando",
    // o servidor responde pela voz do Gemini e salva a troca na conversa aberta.
    {
      conversa: conversa.conversa,
      falar: falaAutomatica(),
      aoVivo: (pedido) => {
        definirTela('conversa');
        definirRespostaAoVivo('');
        chamada.enviado(pedido);
      },
      aoVivoTexto: (disse) => definirRespostaAoVivo(disse),
      aoVivoFim: (id, disse) => {
        definirRespostaAoVivo(disse);
        void conversa.abrir(id);
      },
    },
  );
  const ouvindo = escuta.estado === 'ouvindo';
  // O Solis aparecendo quando é chamado (components/Chamada.tsx).
  const ultimo = conversa.turnos[conversa.turnos.length - 1];
  const chamada = useChamada(
    escuta.estado,
    conversa.respondendo,
    respostaAoVivo !== null ? !!respostaAoVivo : !!(ultimo?.de === 'solis' && ultimo.texto),
  );
  // O pedido na fila sai quando a resposta parada acaba. Depois da chamada (os
  // efeitos rodam em ordem): o dela manda a ilha embora com a resposta parada,
  // e este a põe de volta pensando no pedido novo.
  useEffect(() => {
    const texto = pedidoNaFila.current;
    if (conversa.respondendo || texto === null) return;
    pedidoNaFila.current = null;
    marcarRespostaFalada(falaAutomatica());
    void conversa.enviar(texto);
    chamada.enviado(texto);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversa.respondendo]);
  const resposta =
    chamada.resposta ?? (respostaAoVivo !== null ? respostaAoVivo || undefined : ultimo?.de === 'solis' ? ultimo.texto : undefined);
  // Com a janela do Solis na frente, a voz aparece na esfera, dentro do app;
  // atrás ou minimizada, na ilha — no app Tauri, uma janela própria por cima
  // de tudo (tauri.ts). Decisão do Matheus, 16/11/2026.
  const emFrente = useJanelaEmFrente();
  // Na conversa, o mesmo visual: ouvindo (com o que ele está dizendo) ou falando.
  const emConversa = voz.fase !== null;
  const faseVoz: FaseChamada | null = emConversa ? (voz.fase === 'falando' ? 'respondendo' : 'ouvindo') : chamada.fase;
  const legendaVoz = emConversa ? voz.ouviu : chamada.legenda;
  const respostaVoz = emConversa ? voz.disse : resposta;
  useIlhaNoApp({ fase: emFrente ? null : faseVoz, legenda: legendaVoz, resposta: respostaVoz });

  // 'icones' SUBSTITUI a sidebar — não convive com ela. Neste modo o conteúdo
  // ocupa a janela inteira e a cápsula flutua por cima, no rodapé.
  // No celular (o Solis aberto pelo servidor, 26/11/2026) a sidebar comia mais da
  // metade dos 375 px e espremia a conversa: em tela estreita vale o modo ícones,
  // qualquer que seja a escolha das Configurações (que continua valendo no PC).
  // PROVISÓRIO: o visual do celular é desenhado na refação do visual.
  const estreita = useEstreita();
  const comSidebar = nav === 'sidebar' && !estreita;
  // O modo valendo vai pro DOM (o CSS reserva o espaço da barra por ele). Depois
  // do useTheme, que põe o escolhido: em tela estreita, este ganha.
  useEffect(() => aplicarNav(comSidebar ? 'sidebar' : 'icones'), [comSidebar, nav]);
  const [gaveta, definirGaveta] = useState(false);

  // A lista de conversas aparece em qualquer tela (na sidebar, ou na gaveta do
  // modo ícones), como no Claude: abrir uma conversa ou começar outra leva pra
  // tela de Conversa.
  const lista: PropsLista = {
    aberta: conversa.conversa,
    versao: conversa.versao,
    aoAbrir: (id) => {
      definirTela('conversa');
      conversa.abrir(id);
    },
    aoNova: () => {
      definirTela('conversa');
      conversa.nova();
    },
    // Apagou a que estava aberta: vai pra uma conversa nova.
    aoApagada: (id) => {
      if (id === conversa.conversa) conversa.nova();
    },
  };

  const TELAS: Record<string, () => ReactElement> = {
    conversa: () =>
      conversa.turnos.length ? (
        <Thread
          turnos={conversa.turnos}
          respondendo={conversa.respondendo}
          aoEnviar={conversa.enviar}
          aoParar={conversa.parar}
          aoRefazer={conversa.refazer}
          aoCortar={conversa.cortarDesde}
          aoRecarregar={() => {
            if (conversa.conversa !== null) void conversa.abrir(conversa.conversa);
          }}
          aoCriarEstilo={() => definirTela('configuracoes')}
          conversa={conversa.conversa}
          ouvindo={ouvindo}
        />
      ) : (
        <Conversa aoEnviar={(texto, privada) => conversa.enviar(texto, undefined, undefined, false, privada)} ouvindo={ouvindo} />
      ),
    memoria: () => <Memoria />,
    modelos: () => <ModelosLocais />,
    ferramentas: () => <Ferramentas />,
    tarefas: () => <Tarefas />,
    agenda: () => <Agenda />,
    conhecimento: () => <Conhecimento />,
    configuracoes: () => (
      <Configuracoes
        tema={tema}
        aoTrocarTema={setTema}
        cena={cena}
        aoTrocarCena={setCena}
        nav={nav}
        aoTrocarNav={setNav}
        aoAbrirConversa={lista.aoAbrir}
      />
    ),
  };


  return (
    <div className="relative flex h-full bg-canvas text-text-primary font-sans">
      <Horizonte />
      {comSidebar && <Sidebar ativo={tela} aoTrocar={definirTela} conversas={lista} />}
      {!comSidebar && <TopoIcones aoNova={lista.aoNova} aoAlternarLista={() => definirGaveta((g) => !g)} />}
      {!comSidebar && <GavetaConversas {...lista} visivel={gaveta} aoFechar={() => definirGaveta(false)} />}
      {(TELAS[tela] ?? TELAS.conversa)()}
      {!comSidebar && <BarraIcones ativo={tela} aoTrocar={definirTela} />}
      {faseVoz && emFrente && (
        <EsferaVoz fase={faseVoz} legenda={legendaVoz} resposta={respostaVoz} comSidebar={comSidebar} />
      )}
      {faseVoz && !emFrente && !noApp && (
        <Chamada fase={faseVoz} legenda={legendaVoz} resposta={respostaVoz} comSidebar={comSidebar} />
      )}
    </div>
  );
}

/** Tela estreita (celular): abaixo de 768 px, o ponto em que o tablet em pé começa. */
const ESTREITA = '(max-width: 767px)';

function useEstreita() {
  const [estreita, definir] = useState(() => typeof window !== 'undefined' && window.matchMedia(ESTREITA).matches);
  useEffect(() => {
    const m = window.matchMedia(ESTREITA);
    const mudou = () => definir(m.matches);
    m.addEventListener('change', mudou);
    return () => m.removeEventListener('change', mudou);
  }, []);
  return estreita;
}
