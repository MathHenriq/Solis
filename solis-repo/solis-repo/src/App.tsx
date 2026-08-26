import { Horizonte } from './components/Horizonte';
import { Sidebar } from './components/Sidebar';
import { Conversa } from './views/Conversa';

/** Shell do app. O Horizonte fica AQUI, fora da árvore de views, porque a
 *  Camada 1 do SOLIS_SIGNATURE.md não pode ser remontada ao trocar de tela. */
export default function App() {
  return (
    <div className="relative flex h-full bg-canvas text-text-primary font-sans">
      <Horizonte />
      <Sidebar ativo="conversa" />
      <Conversa />
    </div>
  );
}
