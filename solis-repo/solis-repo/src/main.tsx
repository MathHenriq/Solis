import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/index.css';

const raiz = document.getElementById('root');
if (!raiz) throw new Error('#root não encontrado no index.html');

createRoot(raiz).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
