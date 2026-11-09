const MES = new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short' });

/** "hoje", "ontem", "há 3 dias", e a data a partir de uma semana — como a
 *  referência escreve. Conta dias de calendário, não blocos de 24h: uma memória
 *  das 23h é "ontem" à 1h da manhã seguinte. */
export function quando(iso: string): string {
  const d = new Date(iso);
  const hoje = new Date();
  const dias = Math.round(
    (new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate()).getTime() -
      new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) /
      86_400_000,
  );
  if (dias <= 0) return 'hoje';
  if (dias === 1) return 'ontem';
  if (dias < 7) return `há ${dias} dias`;
  return MES.format(d).replace('.', '');
}

// — Prazos das tarefas ———————————————————————————————————————————————————————————

const DIAS_SEMANA = ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'];
const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

/** A data local de hoje (ou de `d`) como AAAA-MM-DD — o formato do prazo. */
export function diaLocal(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Dias de `de` até `ate` (AAAA-MM-DD), contando dias de calendário. */
export function diasEntre(de: string, ate: string): number {
  const [a, b] = [de, ate].map((s) => {
    const [y, m, d] = s.split('-').map(Number);
    return Date.UTC(y, m - 1, d);
  });
  return Math.round((b - a) / 86_400_000);
}

/** "10h", "14h30". */
export function horaCurta(hora: string): string {
  const [h, m] = hora.split(':');
  return `${Number(h)}h${m === '00' ? '' : m}`;
}

/** O prazo como a referência (15-tarefas) escreve: "hoje, 10h", "amanhã",
 *  "quinta" nos próximos dias, "12 mar" depois; "ontem" e "3 nov" no atrasado. */
export function rotuloPrazo(prazo: string, hora: string | null, hoje = diaLocal()): string {
  const dias = diasEntre(hoje, prazo);
  const [y, m, d] = prazo.split('-').map(Number);
  const data = new Date(y, m - 1, d);
  const dia =
    dias === 0
      ? 'hoje'
      : dias === 1
        ? 'amanhã'
        : dias === -1
          ? 'ontem'
          : dias > 1 && dias < 7
            ? DIAS_SEMANA[data.getDay()]
            : `${d} ${MESES[m - 1]}`;
  return hora ? `${dia}, ${horaCurta(hora)}` : dia;
}
