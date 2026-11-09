import { rotuloPrazo } from './datas';
import { NOMES_CEREBRO, type Etapa } from './servidor';

/** Das etapas cruas do servidor (backend/solis/etapas.py) pras frases da tela.
 *
 *  O servidor conta tudo — o processo do CLI subindo, a primeira linha, a
 *  primeira palavra. A tela agrupa em poucas frases que dizem o que importa:
 *  o que foi buscado, quem foi escolhido, quanto ele levou pra pensar, e se
 *  alguém falhou no caminho. Referência: referencias/telas/20-conversa-etapas.png. */

export type Passo = {
  /** `falhou`: o cérebro não respondeu e o Solis passou pro próximo. */
  estado: 'feita' | 'atual' | 'futura' | 'falhou';
  texto: string;
};

const quem = (c?: string) =>
  c === 'local' ? 'o modelo local' : NOMES_CEREBRO[c ?? ''] ? `o ${NOMES_CEREBRO[c ?? '']}` : 'o modelo';
const maiuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const plural = (n: number, um: string, varios: string, nenhum: string) =>
  n === 0 ? nenhum : `${n} ${n === 1 ? um : varios}`;

/** "4,2 s": com uma casa, vírgula decimal. */
export const segundos = (s: number) => `${s.toFixed(1).replace('.', ',')} s`;

/** Etapa com a hora em que chegou no front. Só existe nas respostas ao vivo:
 *  é o que deixa o relógio da etapa atual andar entre um evento e outro. */
export type EtapaRecebida = Etapa & { recebida?: number };

export function passos(etapas: EtapaRecebida[], vivo: boolean, agora = Date.now()): Passo[] {
  const saida: Passo[] = [];
  const memoria = etapas.find((e) => e.etapa === 'memoria');
  if (!memoria) {
    if (vivo) {
      saida.push({ estado: 'atual', texto: 'Buscando na memória…' });
      saida.push({ estado: 'futura', texto: 'Escolher quem responde' });
      saida.push({ estado: 'futura', texto: 'Escrever a resposta' });
    }
    return saida;
  }
  saida.push({
    estado: 'feita',
    // Os arquivos só aparecem quando algum entrou: "nenhum trecho dos seus
    // arquivos" em toda resposta seria ruído pra quem nem tem arquivo.
    texto:
      'Busquei na memória: ' +
      plural(memoria.memorias ?? 0, 'memória', 'memórias', 'nenhuma memória') +
      (memoria.arquivos ? ', ' : ' e ') +
      plural(memoria.trechos ?? 0, 'trecho de conversa antiga', 'trechos de conversas antigas', 'nenhum trecho de conversa antiga') +
      (memoria.arquivos
        ? ' e ' + plural(memoria.arquivos, 'trecho dos seus arquivos', 'trechos dos seus arquivos', '')
        : ''),
  });

  // Cada tentativa começa num `cerebro` e acaba na primeira palavra ou numa queda.
  etapas.forEach((e, i) => {
    if (e.etapa !== 'cerebro') return;
    const fim = etapas.findIndex((x, j) => j > i && x.etapa === 'cerebro');
    const tentativa = etapas.slice(i + 1, fim === -1 ? undefined : fim);
    const nome = quem(e.cerebro);
    saida.push({ estado: 'feita', texto: `Escolhi ${nome}` });

    const queda = tentativa.find((x) => x.etapa === 'queda');
    const palavra = tentativa.find((x) => x.etapa === 'primeira_palavra');
    if (queda) {
      saida.push({ estado: 'falhou', texto: `${maiuscula(nome)} não respondeu: ${queda.motivo ?? 'sem motivo'}` });
    } else if (palavra) {
      saida.push({ estado: 'feita', texto: `${maiuscula(nome)} pensou por ${segundos(palavra.t - e.t)}` });
    } else if (vivo) {
      const passou = e.recebida ? Math.max(0, Math.floor((agora - e.recebida) / 1000)) : 0;
      // Claude e Codex sobem um processo antes de pensar; até a primeira linha
      // dele, o que demora é o CLI, não o modelo — e a tela diz isso.
      const abrindo = tentativa.some((x) => x.etapa === 'processo') && !tentativa.some((x) => x.etapa === 'primeira_linha');
      saida.push({
        estado: 'atual',
        texto: abrindo ? `Abrindo ${nome}… ${passou} s` : `${maiuscula(nome)} está pensando… ${passou} s`,
      });
    }
  });

  const fim = etapas.find((e) => e.etapa === 'fim');
  if (fim) saida.push({ estado: 'feita', texto: fim.cortada ? 'Escrevi a resposta, cortada no meio' : 'Escrevi a resposta' });
  else if (vivo && etapas.some((e) => e.etapa === 'primeira_palavra'))
    saida.push({ estado: 'atual', texto: 'Escrevendo a resposta…' });
  else if (vivo) saida.push({ estado: 'futura', texto: 'Escrever a resposta' });
  return saida;
}

/** Tempo da resposta inteira, do pedido ao fim do texto. */
export function duracao(etapas: Etapa[]): number {
  const fim = etapas.find((e) => e.etapa === 'fim');
  return fim ? fim.t : Math.max(0, ...etapas.map((e) => e.t));
}

/** O que aconteceu depois da resposta e merece aparecer embaixo dela. */
export function depois(etapas: Etapa[]): string[] {
  const avisos: string[] = [];
  for (const texto of etapas.find((e) => e.etapa === 'aprendizado')?.textos ?? []) {
    // "Quer uma GPU com 16 GB ou mais." vira "quer uma GPU com 16 GB ou mais",
    // como na referência — sem quebrar sigla ("GPU nova" fica em caixa alta).
    const corpo = texto.trim().replace(/\.$/, '');
    const minuscula = /^[A-ZÀ-Ú][a-zà-ú]/.test(corpo) ? corpo.charAt(0).toLowerCase() + corpo.slice(1) : corpo;
    avisos.push(`Memória guardada: ${minuscula}`);
  }
  // O chip da tarefa segue o desenho do de memória (referência 18); aprovado
  // pelo Matheus em 09/11/2026. "Tarefa anotada: pagar a conta de luz · dia 15".
  for (const t of etapas.find((e) => e.etapa === 'aprendizado')?.tarefas ?? []) {
    const corpo = t.texto.trim().replace(/\.$/, '');
    const minuscula = /^[A-ZÀ-Ú][a-zà-ú]/.test(corpo) ? corpo.charAt(0).toLowerCase() + corpo.slice(1) : corpo;
    avisos.push(`Tarefa anotada: ${minuscula}${t.prazo ? ` · ${rotuloPrazo(t.prazo, t.hora)}` : ''}`);
  }
  // PROVISÓRIO: o do compromisso, no mesmo desenho. "Na agenda: consulta com o
  // dentista · quinta, 15h".
  for (const c of etapas.find((e) => e.etapa === 'aprendizado')?.compromissos ?? []) {
    const corpo = c.titulo.trim().replace(/\.$/, '');
    const minuscula = /^[A-ZÀ-Ú][a-zà-ú]/.test(corpo) ? corpo.charAt(0).toLowerCase() + corpo.slice(1) : corpo;
    avisos.push(`Na agenda: ${minuscula} · ${rotuloPrazo(c.dia, c.hora)}`);
  }
  // PROVISÓRIO: a referência só mostra o chip de memória. O de resumo segue o
  // mesmo desenho e precisa do aval do Matheus.
  if (etapas.find((e) => e.etapa === 'resumo')?.resumiu) avisos.push('Conversa resumida: o começo virou resumo');
  return avisos;
}
