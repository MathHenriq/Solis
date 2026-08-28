/** Ponto único de leitura/escrita da config local do usuário.
 *
 *  PROVISÓRIO — hoje isto é localStorage. Ele persiste entre sessões, que é o
 *  requisito ("config local, não estado de sessão"), mas num app Tauri o lugar
 *  certo é um arquivo de config ou o SQLite que já existe pro resto. Está tudo
 *  atrás desta interface justamente pra que essa troca seja um arquivo só.
 *  Ver docs/HANDOFF.md → persistência. */

export function ler(chave: string): string | null {
  try {
    return localStorage.getItem(chave);
  } catch {
    return null; // storage bloqueado — cai no padrão, não quebra o boot
  }
}

export function escrever(chave: string, valor: string): void {
  try {
    localStorage.setItem(chave, valor);
  } catch {
    /* sem persistência disponível; a sessão atual continua funcionando */
  }
}
