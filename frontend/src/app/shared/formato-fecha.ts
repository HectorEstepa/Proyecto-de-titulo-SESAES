const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

/** Separa "YYYY-MM-DD" sin pasar por Date(string), que lo corre un día según la zona horaria. */
function partesIso(iso: string | null | undefined): { anio: number; mes: number; dia: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!m) return null;
  const mes = Number(m[2]);
  const dia = Number(m[3]);
  if (mes < 1 || mes > 12 || dia < 1 || dia > 31) return null;
  return { anio: Number(m[1]), mes, dia };
}

/** "2026-07-20" → "20 jul 2026". Si no es una fecha ISO, devuelve el texto tal cual. */
export function fechaCorta(iso: string | null | undefined): string {
  const p = partesIso(iso);
  if (!p) return iso ?? '';
  return `${p.dia} ${MESES[p.mes - 1].substring(0, 3)} ${p.anio}`;
}

/** "2026-07-20" → "Lunes, 20 de julio de 2026". Si no es una fecha ISO, devuelve el texto tal cual. */
export function fechaLarga(iso: string | null | undefined): string {
  const p = partesIso(iso);
  if (!p) return iso ?? '';
  const diaSemana = DIAS[new Date(p.anio, p.mes - 1, p.dia).getDay()];
  return `${diaSemana.charAt(0).toUpperCase()}${diaSemana.slice(1)}, ${p.dia} de ${MESES[p.mes - 1]} de ${p.anio}`;
}
