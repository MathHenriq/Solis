import { useState, type ReactElement } from 'react';
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
  // Só em desenvolvimento: abrir o modo Conversa pela página (pra ver sem microfone de verdade).
  if (import.meta.env.DEV) (window as unknown as { __conversa?: () => void }).__conversa = () => voz.iniciar(conversa.conversa);
  const escuta = useEscuta(
    (texto) => {
      definirTela('conversa');
      if (pedeConversa(texto)) {
        voz.iniciar(conversa.conversa);
        return;
      }
      marcarRespostaFalada(falaAutomatica());
      conversa.enviar(texto);
      chamada.enviado(texto);
    },
    // Na conversa, o microfone é dela: a escuta do "Solis" desliga.
    voz.fase !== null,
  );
  const ouvindo = escuta.estado === 'ouvindo';
  // O Solis aparecendo quando é chamado (components/Chamada.tsx).
  const ultimo = conversa.turnos[conversa.turnos.length - 1];
  const chamada = useChamada(escuta.estado, conversa.respondendo, !!(ultimo?.de === 'solis' && ultimo.texto));
  const resposta = chamada.resposta ?? (ultimo?.de === 'solis' ? ultimo.texto : undefined);
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
  const comSidebar = nav === 'sidebar';
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
        <Conversa aoEnviar={conversa.enviar} ouvindo={ouvindo} />
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
