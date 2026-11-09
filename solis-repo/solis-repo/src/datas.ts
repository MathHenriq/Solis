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
