import { useCallback, useEffect, useState } from 'react';
import { ler, escrever } from './config';
import {
  CHAVE_CENA, CHAVE_NAV, CHAVE_TEMA, NAV_PADRAO, TEMA_PADRAO, aplicarCena, aplicarTema,
  aplicarNav, ehEstiloNav, ehTema, type EstiloNav, type Tema,
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
  // O estilo de nav não precisa de bootstrap antes do paint como o tema: ele não
  // muda cor, muda que componente monta, e isso o React já resolve no primeiro
  // render sem piscar.
  const [nav, setNavState] = useState<EstiloNav>(() => {
    const salvo = ler(CHAVE_NAV);
    return ehEstiloNav(salvo) ? salvo : NAV_PADRAO;
  });

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

  const setNav = useCallback((e: EstiloNav) => {
    aplicarNav(e);
    escrever(CHAVE_NAV, e);
    setNavState(e);
  }, []);

  useEffect(() => {
    aplicarNav(nav);
  }, [nav]);

  return { tema, setTema, cena, setCena, nav, setNav };
}
