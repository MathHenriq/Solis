import { useEffect, useState } from 'react';

/** Se a janela do Solis está na frente agora: com o foco e visível. Decide quem
 *  mostra a voz (decisão do Matheus, 16/11/2026): na frente, a esfera dentro
 *  do app (EsferaVoz.tsx); atrás ou minimizada, a ilha por cima das outras
 *  janelas (Chamada.tsx). */
function agora(): boolean {
  return document.visibilityState === 'visible' && document.hasFocus();
}

export function useJanelaEmFrente(): boolean {
  const [emFrente, definir] = useState(agora);
  useEffect(() => {
    const atualizar = () => definir(agora());
    window.addEventListener('focus', atualizar);
    window.addEventListener('blur', atualizar);
    document.addEventListener('visibilitychange', atualizar);
    return () => {
      window.removeEventListener('focus', atualizar);
      window.removeEventListener('blur', atualizar);
      document.removeEventListener('visibilitychange', atualizar);
    };
  }, []);
  return emFrente;
}
