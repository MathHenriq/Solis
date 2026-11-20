import { useEffect, useRef, useState } from 'react';
import { lerUso, type Cota } from '../servidor';

/** A partir daqui a conversa avisa (layout.thread.quotaNotice no
 *  solis-tokens.json; aprovado pelo Matheus em 19/11/2026). Abaixo disso a cota só aparece em Configurações → Uso. */
export const AVISO_COTA_A_PARTIR = 90;

const NOMES: Record<string, string> = { sessao: 'Sessão do Claude', semana: 'Semana do Claude' };

/** "Sessão do Claude", "Semana do Claude", "Semana do Fable" (semana-fable). */
function nomeDaCota(c: Cota): string {
  if (NOMES[c.tipo]) return NOMES[c.tipo];
  const qual = c.tipo.replace(/^semana-/, '');
  return `Semana do ${qual.charAt(0).toUpperCase()}${qual.slice(1)}`;
}

const DIAS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'];

/** "volta às 18:00" (hoje) ou "volta sex, 12:00". */
export function quandoVolta(volta: string | null, agora = new Date()): string {
  if (!volta) return '';
  const d = new Date(volta);
  if (Number.isNaN(d.getTime())) return '';
  const hora = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  return d.toDateString() === agora.toDateString() ? `volta às ${hora}` : `volta ${DIAS[d.getDay()]}, ${hora}`;
}

/** A cota que merece o aviso: a mais gasta das que passaram do limite (no
 *  empate, a sessão, que acaba antes). null: nenhuma. */
export function cotaDoAviso(cotas: Cota[]): Cota | null {
  const altas = cotas.filter((c) => c.usado >= AVISO_COTA_A_PARTIR);
  if (!altas.length) return null;
  return altas.sort((a, b) => b.usado - a.usado || (a.tipo === 'sessao' ? -1 : b.tipo === 'sessao' ? 1 : 0))[0];
}

/** O aviso de cota na conversa (PARIDADE: o Claude Desktop avisa antes de a
 *  sessão acabar). Uma linha na fileira acima do campo, à direita, no jeito do
 *  "1 comando em segundo plano" (ComandosFundo): o ponto, o texto secundário.
 *  Aprovado pelo Matheus em 19/11/2026 nos 3 temas e 2 navs
 *  (design/aviso-cota-validacao.png) — desenho próprio, base no Claude.
 *  Confere a cota ao abrir e depois de cada resposta do próprio Claude (o
 *  /usage abre o CLI dele: nas respostas dos outros cérebros não se gasta isso). */
export function AvisoCota({ respondendo, ultimoCerebro }: { respondendo: boolean; ultimoCerebro?: string | null }) {
  const [cota, definirCota] = useState<Cota | null>(null);
  const antes = useRef(respondendo);
  const conferir = () => void lerUso().then((u) => definirCota(u ? cotaDoAviso(u.cotas) : null));

  useEffect(conferir, []);
  useEffect(() => {
    if (antes.current && !respondendo && ultimoCerebro === 'claude') conferir();
    antes.current = respondendo;
  }, [respondendo, ultimoCerebro]);

  if (!cota) return null;
  const acabou = cota.usado >= 100;
  const nome = nomeDaCota(cota);
  const volta = quandoVolta(cota.volta);
  const texto = acabou
    ? `${nome.replace(/^(\S+)/, (p) => `A ${p.toLowerCase()}`)} acabou`
    : `${nome} em ${cota.usado}%`;
  return (
    <span
      role="status"
      title="Quando acabar, o Solis responde pelo próximo cérebro da ordem (Configurações → Cérebros). Os números estão em Configurações → Uso."
      className="flex items-center text-text-secondary"
      style={{ gap: 8, fontSize: 'var(--et-dobra-texto)', height: 28 }}
    >
      <span
        className="shrink-0"
        style={{
          width: 'var(--et-ponto)',
          height: 'var(--et-ponto)',
          borderRadius: 'var(--radius-pill)',
          background: acabou ? 'var(--erro)' : 'var(--accent)',
        }}
      />
      {volta ? `${texto} · ${volta}` : texto}
    </span>
  );
}
