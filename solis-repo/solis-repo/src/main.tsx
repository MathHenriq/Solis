import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { JanelaChamada } from './JanelaChamada';
import { abrirLink } from './servidor';
import { ehJanelaChamada, noApp } from './tauri';
import './styles/index.css';

const raiz = document.getElementById('root');
if (!raiz) throw new Error('#root não encontrado no index.html');

// No app, a janela do Tauri não abre link em nova janela (o clique não fazia
// nada): todo link de página com target="_blank" vai pro navegador padrão do
// Windows, pelo servidor (POST /link/abrir). No navegador, segue o normal.
if (noApp) {
  document.addEventListener(
    'click',
    (e) => {
      const a = (e.target as Element | null)?.closest?.('a[target="_blank"]') as HTMLAnchorElement | null;
      if (!a || !/^https?:\/\//i.test(a.href)) return;
      e.preventDefault();
      void abrirLink(a.href);
    },
    true,
  );
}

createRoot(raiz).render(
  <React.StrictMode>
    {ehJanelaChamada ? <JanelaChamada /> : <App />}
  </React.StrictMode>,
);
