import { useState } from 'react';
import { Horizonte } from './components/Horizonte';
import { Sidebar } from './components/Sidebar';
import { Conversa } from './views/Conversa';
import { Memoria } from './views/Memoria';

/** Shell do app. O Horizonte fica AQUI, fora da árvore de views, porque a
 *  Camada 1 do SOLIS_SIGNATURE.md não pode ser remontada ao trocar de tela.
 *
 *  A troca de tela é um estado local, não um router: o Solis é uma janela só,
 *  local-first, sem URL pra compartilhar e sem histórico de navegador pra
 *  respeitar. Trazer react-router aqui seria peso de bundle sem contrapartida —
 *  e o PERFORMANCE.md manda o contrário. Se um dia houver deep link do sistema
 *  operacional, isto vira um router de verdade. */
export default function App() {
  const [tela, definirTela] = useState('conversa');

  return (
    <div className="relative flex h-full bg-canvas text-text-primary font-sans">
      <Horizonte />
      <Sidebar ativo={tela} aoTrocar={definirTela} />
      {tela === 'memoria' ? <Memoria /> : <Conversa />}
    </div>
  );
}
