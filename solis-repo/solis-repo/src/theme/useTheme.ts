import { useCallback, useEffect, useState } from 'react';
import { ler, escrever } from './config';
import {
  CHAVE_CENA, CHAVE_TEMA, TEMA_PADRAO, aplicarCena, aplicarTema, ehTema, type Tema,
} from './theme';

/** O bootstrap inline do index.html já aplicou o tema antes do primeiro paint.
 *  Este hook não reaplica no mount — só assume o que já está no DOM, pra não
 *  causar um segundo paint à toa. */
export function useTheme() {
  const [tema, setTemaState] = useState<Tema>(() => {
    const salvo = ler(CHAVE_TEMA);
    return ehTema(salvo) ? salvo : TEMA_PADRAO;
  });
  const [cena, setCenaState] = useState<boolean>(() => ler(CHAVE_CENA) !== 'off');

  const setTema = useCallback((t: Tema) => {
    aplicarTema(t);
    escrever(CHAVE_TEMA, t);
    setTemaState(t);
  }, []);

  const setCena = useCallback((ligada: boolean) => {
    aplicarCena(ligada);
    escrever(CHAVE_CENA, ligada ? 'on' : 'off');
    setCenaState(ligada);
  }, []);

  useEffect(() => {
    // Reconcilia se o DOM e o estado divergirem (ex.: storage bloqueado).
    if (document.documentElement.dataset.theme !== tema) aplicarTema(tema);
  }, [tema]);

  return { tema, setTema, cena, setCena };
}
