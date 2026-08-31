import { useState } from 'react';
import { BarraIcones } from './components/BarraIcones';
import { Horizonte } from './components/Horizonte';
import { Sidebar } from './components/Sidebar';
import { useTheme } from './theme/useTheme';
import { Conversa } from './views/Conversa';
import { Configuracoes } from './views/Configuracoes';
import { Memoria } from './views/Memoria';

/** Shell do app. O Horizonte fica AQUI, fora da árvore de views, porque a
 *  Camada 1 do SOLIS_SIGNATURE.md não pode ser remontada ao trocar de tela.
 *
 *  A troca de tela é um estado local, não um router: o Solis é uma janela só,
 *  local-first, sem URL pra compartilhar e sem histórico de navegador pra
 *  respeitar. Se um dia houver deep link do sistema operacional, isto vira um
 *  router de verdade. */
export default function App() {
  const [tela, definirTela] = useState('conversa');
  const { tema, setTema, cena, setCena, nav, setNav } = useTheme();

  // 'icones' SUBSTITUI a sidebar — não convive com ela. Neste modo o conteúdo
  // ocupa a janela inteira e a cápsula flutua por cima, no rodapé.
  const comSidebar = nav === 'sidebar';

  return (
    <div className="relative flex h-full bg-canvas text-text-primary font-sans">
      <Horizonte />
      {comSidebar && <Sidebar ativo={tela} aoTrocar={definirTela} />}

      {tela === 'memoria' ? (
        <Memoria />
      ) : tela === 'configuracoes' ? (
        <Configuracoes
          tema={tema}
          aoTrocarTema={setTema}
          cena={cena}
          aoTrocarCena={setCena}
          nav={nav}
          aoTrocarNav={setNav}
        />
      ) : (
        <Conversa />
      )}

      {!comSidebar && <BarraIcones ativo={tela} aoTrocar={definirTela} />}
    </div>
  );
}
