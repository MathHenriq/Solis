/* Ícone exclusivo do Solis — desenhado à mão, sem dependência de biblioteca.
 *
 * Motivo: a referência (05-memoria.png, item "Ferramentas") mostra uma chave
 * inglesa e uma chave de fenda CRUZADAS. O Lucide não tem esse ícone — só
 * `Wrench` (ferramenta única). Usar `Wrench` seria "parecido", não idêntico,
 * e a Regra 2 rejeita isso. Então ele é desenhado aqui.
 *
 * Segue o grid de ícone dos tokens: 24×24, área segura 20×20, stroke 2px,
 * cap e join redondos, currentColor.
 */
interface Props {
  size?: number;
  className?: string;
  strokeWidth?: number;
}

export function ToolsCrossed({ size = 24, className, strokeWidth = 2 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* Chave inglesa: cabeça em cima à direita, cabo descendo pra esquerda. */}
      <path d="M20.4 4.6a4.2 4.2 0 0 1-5.6 5.6L5.9 19.1a2 2 0 0 1-2.8-2.8l8.9-8.9a4.2 4.2 0 0 1 5.6-5.6l-3 3 2.4 2.4 3-3.2z" />
      {/* Chave de fenda: cabo em cima à esquerda, ponta embaixo à direita. */}
      <path d="M3.6 6.4 6.4 3.6l3 3-2.8 2.8z" />
      <path d="m8.6 8.6 8.1 8.1" />
      <path d="m16 17.4 1.4-1.4 3 3-1.4 1.4z" />
    </svg>
  );
}
