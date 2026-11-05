/**
 * Normaliza texto para búsquedas de UI: ignora espacios extremos,
 * mayúsculas/minúsculas y diacríticos (tildes).
 */
export function normalizarTexto(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ');
}


/**
 * Devuelve true cuando la consulta normalizada aparece en cualquiera de los
 * valores indicados. Una consulta vacía no filtra resultados.
 */
export function coincideBusqueda(consulta: unknown, ...valores: unknown[]): boolean {
  const q = normalizarTexto(consulta);
  if (!q) return true;

  return valores.some(valor => normalizarTexto(valor).includes(q));
}
