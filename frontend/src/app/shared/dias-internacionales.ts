/**
 * Días internacionales reconocidos oficialmente por Naciones Unidas.
 * Fuente: https://www.un.org/es/observances/list-days-weeks (consultado 2026).
 * Se repiten cada año en la misma fecha, por eso se indexan por 'MM-DD'
 * (sin año), a diferencia de los feriados chilenos que sí llevan año.
 * No implican ningún cierre ni bloqueo — son solo informativos.
 */
export interface DiaInternacional {
  fechaMD: string;   // MM-DD
  nombre: string;
}

export const DIAS_INTERNACIONALES: DiaInternacional[] = [
  // ── Enero ──
  { fechaMD: '01-04', nombre: 'Día Mundial del Braille' },
  { fechaMD: '01-24', nombre: 'Día Internacional de la Educación' },
  { fechaMD: '01-26', nombre: 'Día Internacional de la Energía Limpia' },
  { fechaMD: '01-27', nombre: 'Día Internacional de Conmemoración de las Víctimas del Holocausto' },
  { fechaMD: '01-28', nombre: 'Día Internacional de la Coexistencia Pacífica' },

  // ── Febrero ──
  { fechaMD: '02-02', nombre: 'Día Mundial de los Humedales' },
  { fechaMD: '02-04', nombre: 'Día Internacional de la Fraternidad Humana' },
  { fechaMD: '02-06', nombre: 'Día Internacional de Tolerancia Cero con la Mutilación Genital Femenina' },
  { fechaMD: '02-10', nombre: 'Día Mundial de las Legumbres' },
  { fechaMD: '02-11', nombre: 'Día Internacional de la Mujer y la Niña en la Ciencia' },
  { fechaMD: '02-13', nombre: 'Día Mundial de la Radio' },
  { fechaMD: '02-20', nombre: 'Día Mundial de la Justicia Social' },
  { fechaMD: '02-21', nombre: 'Día Internacional de la Lengua Materna' },

  // ── Marzo ──
  { fechaMD: '03-01', nombre: 'Día Mundial de la Vida Silvestre' },
  { fechaMD: '03-08', nombre: 'Día Internacional de la Mujer' },
  { fechaMD: '03-15', nombre: 'Día Internacional para Combatir la Islamofobia' },
  { fechaMD: '03-20', nombre: 'Día Internacional de la Felicidad' },
  { fechaMD: '03-21', nombre: 'Día Internacional de la Eliminación de la Discriminación Racial' },
  { fechaMD: '03-21', nombre: 'Día Mundial del Síndrome de Down' },
  { fechaMD: '03-21', nombre: 'Día Internacional de los Bosques' },
  { fechaMD: '03-22', nombre: 'Día Mundial del Agua' },
  { fechaMD: '03-23', nombre: 'Día Meteorológico Mundial' },
  { fechaMD: '03-24', nombre: 'Día Mundial de la Tuberculosis' },
  { fechaMD: '03-30', nombre: 'Día Internacional de Cero Desechos' },

  // ── Abril ──
  { fechaMD: '04-02', nombre: 'Día Mundial de Concienciación sobre el Autismo' },
  { fechaMD: '04-06', nombre: 'Día Internacional del Deporte para el Desarrollo y la Paz' },
  { fechaMD: '04-07', nombre: 'Día Mundial de la Salud' },
  { fechaMD: '04-15', nombre: 'Día Internacional del Bienestar' },
  { fechaMD: '04-21', nombre: 'Día Mundial de la Creatividad y la Innovación' },
  { fechaMD: '04-22', nombre: 'Día Internacional de la Madre Tierra' },
  { fechaMD: '04-23', nombre: 'Día Mundial del Libro y del Derecho de Autor' },
  { fechaMD: '04-23', nombre: 'Día del Idioma Español en las Naciones Unidas' },
  { fechaMD: '04-25', nombre: 'Día Mundial del Paludismo' },
  { fechaMD: '04-26', nombre: 'Día Mundial de la Propiedad Intelectual' },
  { fechaMD: '04-28', nombre: 'Día Mundial de la Seguridad y Salud en el Trabajo' },
  { fechaMD: '04-30', nombre: 'Día Internacional del Jazz' },

  // ── Mayo ──
  { fechaMD: '05-02', nombre: 'Día Mundial del Atún' },
  { fechaMD: '05-03', nombre: 'Día Mundial de la Libertad de Prensa' },
  { fechaMD: '05-05', nombre: 'Día Mundial de la Lengua Portuguesa' },
  { fechaMD: '05-15', nombre: 'Día Internacional de las Familias' },
  { fechaMD: '05-16', nombre: 'Día Internacional de la Luz' },
  { fechaMD: '05-17', nombre: 'Día Mundial de las Telecomunicaciones y la Sociedad de la Información' },
  { fechaMD: '05-20', nombre: 'Día Mundial de las Abejas' },
  { fechaMD: '05-21', nombre: 'Día Internacional del Té' },
  { fechaMD: '05-21', nombre: 'Día Mundial de la Diversidad Cultural para el Diálogo y el Desarrollo' },
  { fechaMD: '05-22', nombre: 'Día Internacional de la Diversidad Biológica' },
  { fechaMD: '05-29', nombre: 'Día Internacional del Personal de Paz de las Naciones Unidas' },
  { fechaMD: '05-31', nombre: 'Día Mundial Sin Tabaco' },

  // ── Junio ──
  { fechaMD: '06-01', nombre: 'Día Mundial de las Madres y los Padres' },
  { fechaMD: '06-03', nombre: 'Día Mundial de la Bicicleta' },
  { fechaMD: '06-05', nombre: 'Día Mundial del Medio Ambiente' },
  { fechaMD: '06-08', nombre: 'Día Mundial de los Océanos' },
  { fechaMD: '06-12', nombre: 'Día Mundial contra el Trabajo Infantil' },
  { fechaMD: '06-14', nombre: 'Día Mundial del Donante de Sangre' },
  { fechaMD: '06-17', nombre: 'Día Mundial de Lucha contra la Desertificación' },
  { fechaMD: '06-18', nombre: 'Día Internacional para Contrarrestar el Discurso de Odio' },
  { fechaMD: '06-20', nombre: 'Día Mundial de los Refugiados' },
  { fechaMD: '06-21', nombre: 'Día Internacional del Yoga' },
  { fechaMD: '06-23', nombre: 'Día Internacional de las Viudas' },
  { fechaMD: '06-26', nombre: 'Día Internacional de la Lucha contra el Uso Indebido y el Tráfico Ilícito de Drogas' },
  { fechaMD: '06-26', nombre: 'Día Internacional en Apoyo de las Víctimas de la Tortura' },

  // ── Julio ──
  { fechaMD: '07-11', nombre: 'Día Mundial de la Población' },
  { fechaMD: '07-15', nombre: 'Día Mundial de las Habilidades de la Juventud' },
  { fechaMD: '07-18', nombre: 'Día Internacional de Nelson Mandela' },
  { fechaMD: '07-20', nombre: 'Día Mundial del Ajedrez' },
  { fechaMD: '07-28', nombre: 'Día Mundial contra la Hepatitis' },
  { fechaMD: '07-30', nombre: 'Día Internacional de la Amistad' },
  { fechaMD: '07-30', nombre: 'Día Mundial contra la Trata' },

  // ── Agosto ──
  { fechaMD: '08-09', nombre: 'Día Internacional de los Pueblos Indígenas' },
  { fechaMD: '08-12', nombre: 'Día Internacional de la Juventud' },
  { fechaMD: '08-19', nombre: 'Día Mundial de la Asistencia Humanitaria' },
  { fechaMD: '08-21', nombre: 'Día Internacional de Conmemoración y Homenaje a las Víctimas del Terrorismo' },
  { fechaMD: '08-23', nombre: 'Día Internacional del Recuerdo de la Trata de Esclavos y de su Abolición' },
  { fechaMD: '08-29', nombre: 'Día Internacional contra los Ensayos Nucleares' },
  { fechaMD: '08-31', nombre: 'Día Internacional de los Afrodescendientes' },

  // ── Septiembre ──
  { fechaMD: '09-08', nombre: 'Día Internacional de la Alfabetización' },
  { fechaMD: '09-15', nombre: 'Día Internacional de la Democracia' },
  { fechaMD: '09-16', nombre: 'Día Internacional de la Preservación de la Capa de Ozono' },
  { fechaMD: '09-17', nombre: 'Día Mundial de la Seguridad del Paciente' },
  { fechaMD: '09-21', nombre: 'Día Internacional de la Paz' },
  { fechaMD: '09-23', nombre: 'Día Internacional de las Lenguas de Señas' },
  { fechaMD: '09-27', nombre: 'Día Mundial del Turismo' },
  { fechaMD: '09-28', nombre: 'Día Mundial contra la Rabia' },
  { fechaMD: '09-29', nombre: 'Día Internacional de Concienciación sobre la Pérdida y el Desperdicio de Alimentos' },
  { fechaMD: '09-30', nombre: 'Día Internacional de la Traducción' },

  // ── Octubre ──
  { fechaMD: '10-01', nombre: 'Día Internacional del Café' },
  { fechaMD: '10-01', nombre: 'Día Internacional de las Personas de Edad' },
  { fechaMD: '10-02', nombre: 'Día Internacional de la No Violencia' },
  { fechaMD: '10-05', nombre: 'Día Mundial de los Docentes' },
  { fechaMD: '10-07', nombre: 'Día Mundial del Hábitat' },
  { fechaMD: '10-09', nombre: 'Día Mundial del Correo' },
  { fechaMD: '10-10', nombre: 'Día Mundial de la Salud Mental' },
  { fechaMD: '10-11', nombre: 'Día Internacional de la Niña' },
  { fechaMD: '10-13', nombre: 'Día Internacional para la Reducción de los Desastres' },
  { fechaMD: '10-15', nombre: 'Día Internacional de las Mujeres Rurales' },
  { fechaMD: '10-16', nombre: 'Día Mundial de la Alimentación' },
  { fechaMD: '10-17', nombre: 'Día Internacional para la Erradicación de la Pobreza' },
  { fechaMD: '10-24', nombre: 'Día de las Naciones Unidas' },
  { fechaMD: '10-31', nombre: 'Día Mundial de las Ciudades' },

  // ── Noviembre ──
  { fechaMD: '11-14', nombre: 'Día Mundial de la Diabetes' },
  { fechaMD: '11-16', nombre: 'Día Internacional de la Tolerancia' },
  { fechaMD: '11-17', nombre: 'Día Mundial en Recuerdo de las Víctimas de los Accidentes de Tráfico' },
  { fechaMD: '11-19', nombre: 'Día Mundial del Retrete' },
  { fechaMD: '11-20', nombre: 'Día Mundial de la Infancia' },
  { fechaMD: '11-21', nombre: 'Día Mundial de la Televisión' },
  { fechaMD: '11-21', nombre: 'Día Mundial de la Filosofía' },
  { fechaMD: '11-25', nombre: 'Día Internacional de la Eliminación de la Violencia contra la Mujer' },
  { fechaMD: '11-26', nombre: 'Día Mundial del Transporte Sostenible' },

  // ── Diciembre ──
  { fechaMD: '12-01', nombre: 'Día Mundial del SIDA' },
  { fechaMD: '12-02', nombre: 'Día Internacional para la Abolición de la Esclavitud' },
  { fechaMD: '12-03', nombre: 'Día Internacional de las Personas con Discapacidad' },
  { fechaMD: '12-05', nombre: 'Día Mundial del Suelo' },
  { fechaMD: '12-05', nombre: 'Día Internacional de los Voluntarios' },
  { fechaMD: '12-09', nombre: 'Día Internacional contra la Corrupción' },
  { fechaMD: '12-10', nombre: 'Día de los Derechos Humanos' },
  { fechaMD: '12-11', nombre: 'Día Internacional de las Montañas' },
  { fechaMD: '12-12', nombre: 'Día Internacional de la Cobertura Sanitaria Universal' },
  { fechaMD: '12-18', nombre: 'Día Internacional del Migrante' },
  { fechaMD: '12-20', nombre: 'Día Internacional de la Solidaridad Humana' },
  { fechaMD: '12-21', nombre: 'Día Mundial del Baloncesto' },
  { fechaMD: '12-21', nombre: 'Día Mundial de la Meditación' },
  { fechaMD: '12-27', nombre: 'Día Internacional de la Preparación ante las Epidemias' },
];

const DIAS_INTERNACIONALES_MAP: Map<string, DiaInternacional[]> = (() => {
  const mapa = new Map<string, DiaInternacional[]>();
  for (const d of DIAS_INTERNACIONALES) {
    const lista = mapa.get(d.fechaMD) ?? [];
    lista.push(d);
    mapa.set(d.fechaMD, lista);
  }
  return mapa;
})();

/** Devuelve los días internacionales de esa fecha (YYYY-MM-DD), puede ser más de uno. */
export function obtenerDiasInternacionales(fecha: string | undefined): DiaInternacional[] {
  if (!fecha) return [];
  const md = fecha.substring(5); // 'YYYY-MM-DD' → 'MM-DD'
  return DIAS_INTERNACIONALES_MAP.get(md) ?? [];
}
