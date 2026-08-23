/* Telas ainda não construídas.
 *
 * Cada tela do Solis é construída UMA POR VEZ, medida contra a sua imagem de
 * referência antes de passar pra próxima. Gerar todas juntas foi exatamente o
 * que produziu a inconsistência entre as telas anteriores.
 *
 * Este placeholder existe pra rota existir e a navegação ser testável na Fase 0.
 * Ele é deliberadamente sem estilo: nada aqui deve ser confundido com uma tela
 * pronta, nem servir de base pra uma.
 */
export function Placeholder({ title, reference }: { title: string; reference?: string }) {
  return (
    <section style={{ padding: "24px", position: "relative", zIndex: 1 }}>
      <h1 style={{ fontSize: "var(--solis-title1-size)", fontWeight: 600, margin: 0 }}>
        {title}
      </h1>
      <p style={{ color: "var(--solis-muted)", marginTop: "8px" }}>
        Tela ainda não construída.{" "}
        {reference
          ? `Referência: ${reference}.`
          : "Sem referência visual ainda — pedir ao Matheus antes de finalizar."}
      </p>
    </section>
  );
}
