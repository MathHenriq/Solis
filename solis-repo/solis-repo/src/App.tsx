import { useState, type ReactElement } from 'react';
import { BarraIcones } from './components/BarraIcones';
import { Horizonte } from './components/Horizonte';
import { Sidebar } from './components/Sidebar';
import { TopoIcones } from './components/TopoIcones';
import { useConversa } from './lib/useConversa';
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
  // A Conversa tem dois estados: vazia e com thread.
  const [comThread, definirComThread] = useState(false);
  const { tema, setTema, cena, setCena, nav, setNav } = useTheme();
  // A conversa mora AQUI e não dentro da Conversa ou da Thread: as duas são a
  // mesma tela em dois estados, e o App troca uma pela outra ao enviar. Estado
  // dentro delas morreria nessa troca — junto com a mensagem recém-enviada.
  const conversa = useConversa();

  // 'icones' SUBSTITUI a sidebar — não convive com ela. Neste modo o conteúdo
  // ocupa a janela inteira e a cápsula flutua por cima, no rodapé.
  const comSidebar = nav === 'sidebar';

  const TELAS: Record<string, () => ReactElement> = {
    conversa: () =>
      comThread ? (
        <Thread turnos={conversa.turnos} gerando={conversa.gerando} aoEnviar={conversa.enviar} />
      ) : (
        <Conversa aoAbrirThread={() => definirComThread(true)} aoEnviar={conversa.enviar} />
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
      />
    ),
  };

  const trocar = (id: string) => {
    if (id !== 'conversa') definirComThread(false);
    definirTela(id);
  };

  return (
    <div className="relative flex h-full bg-canvas text-text-primary font-sans">
      <Horizonte />
      {comSidebar && <Sidebar ativo={tela} aoTrocar={trocar} />}
      {!comSidebar && <TopoIcones />}
      {(TELAS[tela] ?? TELAS.conversa)()}
      {!comSidebar && <BarraIcones ativo={tela} aoTrocar={trocar} />}
    </div>
  );
}
