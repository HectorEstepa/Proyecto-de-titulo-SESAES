import * as XLSX from 'xlsx';
import { describe, expect, it } from 'vitest';

import { normalizarTexto } from '../../shared/text-normalization';
import {
  COLUMNAS_CGR_ALUMNOS,
  COLUMNAS_CGR_ATENCIONES,
  COLUMNAS_ESPECIALIDAD,
  COLUMNAS_HISTORIAL,
  ETIQUETAS_ESTADO_CITA,
  FormatoCgrInesperadoError,
  MIME_XLSX,
  TablaCgr,
  construirLibroTabla,
  construirLibroXlsx,
  etiquetaEstadoCita,
  filasCgrAlumnosExcel,
  filasCgrAtencionesExcel,
  filasEspecialidadExcel,
  filasHistorialExcel,
  formatearFechaExcel,
  libroAXlsxBlob,
  libroCgrAlumnos,
  libroCgrAtenciones
} from './reportes-excel';

// Datos con tildes, ñ, mayúsculas y minúsculas mezcladas, como en producción.
const CITAS = [
  {
    id: 1, estudiante: 'José Pérez García', rut: '12.345.678-9', carrera: 'Kinesiología',
    especialidad: 'Nutrición y Dietética', profesional: 'Dra. María Núñez',
    fecha: '2026-09-15', hora: '10:00', estado: 'pendiente', urgente: false
  },
  {
    id: 2, estudiante: 'ÁLVARO NÚÑEZ', rut: '9.876.543-2', carrera: 'Diseño Ñuñoa',
    especialidad: 'Psicología', profesional: 'Dr. Andrés de la Fuente',
    fecha: '2026-09-14', hora: '09:30', estado: 'completada', urgente: true
  },
  {
    id: 3, estudiante: 'Constanza Muñoz', rut: '20.111.222-K', carrera: 'Ingeniería',
    especialidad: 'Nutrición y Dietética', profesional: 'Dra. María Núñez',
    fecha: '2026-09-13', hora: '15:45', estado: 'inasistencia', urgente: false
  },
  {
    id: 4, estudiante: 'Ñandú Soto', rut: '18.000.000-0', carrera: 'Derecho',
    especialidad: 'Psicología', profesional: 'Dr. Andrés de la Fuente',
    fecha: '2026-09-12', hora: '11:15', estado: 'cancelada', urgente: false
  }
];

/** Serializa a un .xlsx REAL y lo vuelve a leer, como lo haría Excel. */
function idaYVuelta(datos: readonly object[], hoja = 'Hoja') {
  const bytes = XLSX.write(construirLibroXlsx(datos, hoja), { type: 'array', bookType: 'xlsx' }) as ArrayBuffer;
  const leido = XLSX.read(bytes, { type: 'array' });
  const sheet = leido.Sheets[leido.SheetNames[0]];
  return {
    bytes: new Uint8Array(bytes),
    nombres: leido.SheetNames,
    matriz: XLSX.utils.sheet_to_json<string[]>(sheet, { header: 1, raw: true }) as unknown[][]
  };
}

describe('Excel — helpers', () => {
  it('traduce los estados a valores legibles (no códigos internos)', () => {
    expect(etiquetaEstadoCita('pendiente')).toBe('Pendiente');
    expect(etiquetaEstadoCita('completada')).toBe('Completada');
    expect(etiquetaEstadoCita('cancelada')).toBe('Cancelada');
    expect(etiquetaEstadoCita('inasistencia')).toBe('Inasistencia');
    expect(Object.keys(ETIQUETAS_ESTADO_CITA)).toHaveLength(4);
  });

  it('tolera mayúsculas/espacios en el estado y no oculta estados desconocidos', () => {
    expect(etiquetaEstadoCita(' COMPLETADA ')).toBe('Completada');
    expect(etiquetaEstadoCita('en_revision')).toBe('en_revision'); // se conserva tal cual
    expect(etiquetaEstadoCita(null)).toBe('');
    expect(etiquetaEstadoCita(undefined)).toBe('');
  });

  it('formatea la fecha ISO como DD/MM/AAAA y conserva lo que no es ISO', () => {
    expect(formatearFechaExcel('2026-09-15')).toBe('15/09/2026');
    expect(formatearFechaExcel('2026-01-05')).toBe('05/01/2026');
    expect(formatearFechaExcel('15/09/2026')).toBe('15/09/2026');
    expect(formatearFechaExcel('')).toBe('');
    expect(formatearFechaExcel(null)).toBe('');
  });
});

describe('Excel — historial de citas', () => {
  it('tiene exactamente las columnas esperadas, en orden fijo', () => {
    expect([...COLUMNAS_HISTORIAL]).toEqual([
      'Estudiante', 'RUT', 'Carrera', 'Especialidad', 'Profesional', 'Fecha', 'Hora', 'Estado'
    ]);

    const filas = filasHistorialExcel(CITAS);
    for (const fila of filas) {
      expect(Object.keys(fila)).toEqual([...COLUMNAS_HISTORIAL]);
    }
  });

  it('el archivo es un .xlsx real (ZIP), no texto tabulado', () => {
    const { bytes } = idaYVuelta(filasHistorialExcel(CITAS));
    // Firma de un contenedor ZIP/OOXML: "PK".
    expect([bytes[0], bytes[1]]).toEqual([0x50, 0x4b]);
    expect(new TextDecoder().decode(bytes.slice(0, 200))).not.toContain('\t');
  });

  it('una fila por cita y encabezados en la primera fila del archivo', () => {
    const { matriz, nombres } = idaYVuelta(filasHistorialExcel(CITAS), 'Historial de citas');

    expect(nombres).toEqual(['Historial de citas']);
    expect(matriz).toHaveLength(1 + CITAS.length);
    expect(matriz[0]).toEqual([...COLUMNAS_HISTORIAL]);
  });

  it('cada dato queda en su propia celda (separación correcta de campos)', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel(CITAS));
    const primera = matriz[1];

    expect(primera).toEqual([
      'José Pérez García',        // Estudiante
      '12.345.678-9',             // RUT
      'Kinesiología',             // Carrera
      'Nutrición y Dietética',    // Especialidad
      'Dra. María Núñez',         // Profesional
      '15/09/2026',               // Fecha
      '10:00',                    // Hora
      'Pendiente'                 // Estado
    ]);
    expect(primera).toHaveLength(COLUMNAS_HISTORIAL.length);
  });

  it('no hay datos concatenados por accidente: ninguna celda contiene el valor de otra columna', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel(CITAS));

    for (const fila of matriz.slice(1)) {
      const celdas = fila.map(String);
      celdas.forEach((celda, i) => {
        // Sin separadores típicos de valores pegados.
        expect(celda).not.toMatch(/\t|\n|\r| - | \| |;/);
        celdas.forEach((otra, j) => {
          if (i !== j && otra.length > 2 && otra !== celda) {
            expect(celda.includes(otra), `«${celda}» contiene «${otra}»`).toBe(false);
          }
        });
      });
    }
  });

  it('el ejemplo del enunciado NO se exporta mezclado en una sola celda', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel([CITAS[0]]));
    const todo = matriz[1].map(String);

    expect(todo).not.toContain('José Pérez García - Nutrición y Dietética - Pendiente - 15/09/2026 10:00');
    // Fecha y hora son columnas distintas.
    expect(todo[COLUMNAS_HISTORIAL.indexOf('Fecha')]).toBe('15/09/2026');
    expect(todo[COLUMNAS_HISTORIAL.indexOf('Hora')]).toBe('10:00');
  });

  it('conserva tildes, ñ y caracteres especiales tras serializar el .xlsx', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel(CITAS));
    const plano = matriz.flat().map(String);

    for (const esperado of [
      'José Pérez García', 'Nutrición y Dietética', 'Dra. María Núñez',
      'Kinesiología', 'Diseño Ñuñoa', 'Constanza Muñoz', 'Ñandú Soto',
      'Psicología', 'Ingeniería'
    ]) {
      expect(plano, esperado).toContain(esperado);
    }
    // Ningún carácter dañado (reemplazo Unicode o mojibake).
    expect(plano.join('')).not.toMatch(/\uFFFD|Ã.|Â./);
  });

  it('conserva mayúsculas y minúsculas originales (no normaliza lo exportado)', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel(CITAS));
    const col = (n: string) => matriz.slice(1).map(f => String(f[COLUMNAS_HISTORIAL.indexOf(n as any)]));

    expect(col('Estudiante')).toContain('ÁLVARO NÚÑEZ');          // mayúsculas intactas
    expect(col('Profesional')).toContain('Dr. Andrés de la Fuente'); // "de la" en minúscula
    expect(col('RUT')).toContain('20.111.222-K');                  // K mayúscula

    // La normalización de BÚSQUEDA es una función aparte y no altera el dato.
    expect(normalizarTexto('José Pérez García')).toBe('jose perez garcia');
    expect(col('Estudiante')).toContain('José Pérez García');
    expect(filasHistorialExcel(CITAS)[0].Estudiante).toBe('José Pérez García');
  });

  it('los estados salen legibles en el archivo', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel(CITAS));
    const estados = matriz.slice(1).map(f => f[COLUMNAS_HISTORIAL.indexOf('Estado')]);

    expect(estados).toEqual(['Pendiente', 'Completada', 'Inasistencia', 'Cancelada']);
  });

  it('respeta los filtros: exporta solo el resultado recibido, sin agregar ni quitar registros', () => {
    // El backend ya filtró (p. ej. estado = completada + especialidad = Psicología).
    const filtradas = CITAS.filter(c => c.estado === 'completada' && c.especialidad === 'Psicología');

    const filas = filasHistorialExcel(filtradas);

    expect(filas).toHaveLength(1);
    expect(filas[0].Estudiante).toBe('ÁLVARO NÚÑEZ');
    expect(filas.map(f => f.Estudiante)).not.toContain('José Pérez García');

    // Más filtros → menos filas; mismo orden que la pantalla.
    expect(filasHistorialExcel(CITAS.filter(c => c.especialidad === 'Nutrición y Dietética')).map(f => f.RUT))
      .toEqual(['12.345.678-9', '20.111.222-K']);
    expect(filasHistorialExcel([])).toEqual([]);
  });

  it('no muta los datos de origen', () => {
    const copia = JSON.parse(JSON.stringify(CITAS));
    filasHistorialExcel(CITAS);
    expect(CITAS).toEqual(copia);
  });

  it('valores ausentes quedan como celda vacía, no como "null" ni "undefined"', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel([
      { estudiante: 'Ana', rut: null, carrera: undefined, especialidad: 'Psicología', profesional: 'Dr. X',
        fecha: '2026-09-15', hora: '10:00', estado: 'pendiente' }
    ]));

    const plano = matriz.flat().map(v => String(v ?? ''));
    expect(plano).not.toContain('null');
    expect(plano).not.toContain('undefined');
  });

  it('un campo con separadores internos sigue siendo UNA sola celda', () => {
    const { matriz } = idaYVuelta(filasHistorialExcel([
      { ...CITAS[0], carrera: 'Diseño; Comunicación / Arte' }
    ]));

    expect(matriz[1]).toHaveLength(COLUMNAS_HISTORIAL.length);
    expect(matriz[1][COLUMNAS_HISTORIAL.indexOf('Carrera')]).toBe('Diseño; Comunicación / Arte');
  });
});

describe('Excel — citas por especialidad (compatibilidad)', () => {
  const DATOS = [
    { especialidad: 'Nutrición y Dietética', cantidad: 30, porcentaje: 60 },
    { especialidad: 'Psicología', cantidad: 20, porcentaje: 40 }
  ];

  it('conserva las columnas y valores originales de la exportación', () => {
    expect([...COLUMNAS_ESPECIALIDAD]).toEqual(['Especialidad', 'Cantidad', 'Porcentaje']);
    expect(filasEspecialidadExcel(DATOS)).toEqual([
      { Especialidad: 'Nutrición y Dietética', Cantidad: 30, Porcentaje: '60%' },
      { Especialidad: 'Psicología', Cantidad: 20, Porcentaje: '40%' }
    ]);
  });

  it('se serializa a .xlsx con cada dato en su celda y las tildes intactas', () => {
    const { matriz, nombres } = idaYVuelta(filasEspecialidadExcel(DATOS), 'Citas por especialidad');

    expect(nombres).toEqual(['Citas por especialidad']);
    expect(matriz).toEqual([
      ['Especialidad', 'Cantidad', 'Porcentaje'],
      ['Nutrición y Dietética', 30, '60%'],
      ['Psicología', 20, '40%']
    ]);
  });
});

// ══════════════════════════════════════════════════════════════════
// CGR — atenciones y listado de alumnos (B2)
// ══════════════════════════════════════════════════════════════════
const ATENCIONES: TablaCgr = {
  columnas: [...COLUMNAS_CGR_ATENCIONES],
  filas: [
    ['José Pérez García', '12.345.678-9', 'Nutrición y Dietética', '2026-09-14', '16:00', 'No aplica', 'Dra. María Núñez'],
    ['ÁLVARO NÚÑEZ', '9.876.543-2', 'Psicología', '2026-09-15', '08:30', 'Paracetamol 500 mg', 'Dr. Andrés de la Fuente'],
    ['Ñandú Soto', '18.000.000-0', 'Kinesiología', '2026-09-15', '10:00', 'Ácido fólico', 'Dra. María Núñez'],
    ['—', '—', '—', '2026-01-05', '09:05', 'No aplica', '—']
  ],
  total: 4
};

const ALUMNOS: TablaCgr = {
  columnas: [...COLUMNAS_CGR_ALUMNOS],
  filas: [
    ['ÁLVARO NÚÑEZ', '9.876.543-2', 'Diseño', 'alvaro@utem.cl'],
    ['José Pérez García', '12.345.678-9', 'Kinesiología', 'jose@utem.cl'],
    ['—', '—', '—', 'sin.datos@utem.cl']
  ],
  total: 3
};

async function leerLibro(blob: Blob) {
  const bytes = await new Promise<ArrayBuffer>((ok, error) => {
    const lector = new FileReader();
    lector.onload = () => ok(lector.result as ArrayBuffer);
    lector.onerror = () => error(lector.error);
    lector.readAsArrayBuffer(blob);
  });
  // cellStyles: SheetJS solo interpreta anchos de columna al leer si se le pide.
  const libro = XLSX.read(bytes, { type: 'array', cellStyles: true });
  const hoja = libro.Sheets[libro.SheetNames[0]];
  return {
    bytes: new Uint8Array(bytes),
    nombres: libro.SheetNames,
    hoja,
    matriz: XLSX.utils.sheet_to_json<unknown[]>(hoja, { header: 1, raw: true }) as unknown[][]
  };
}

describe('CGR — contrato de columnas', () => {
  it('atenciones: 7 columnas en el orden ya definido por el endpoint', () => {
    expect([...COLUMNAS_CGR_ATENCIONES]).toEqual([
      'Nombre Completo', 'RUT', 'Tipo de Atención', 'Fecha', 'Hora',
      'Medicamento Suministrado', 'Profesional que Atendió'
    ]);
  });

  it('alumnos: 4 columnas en el orden ya definido por el endpoint', () => {
    expect([...COLUMNAS_CGR_ALUMNOS]).toEqual(['Nombre Completo', 'RUT', 'Carrera', 'Correo']);
  });

  it('rechaza una respuesta con columnas distintas o en otro orden (no entrega datos corridos)', () => {
    const otroOrden = { ...ATENCIONES, columnas: [...ATENCIONES.columnas].reverse() };
    expect(() => filasCgrAtencionesExcel(otroOrden)).toThrow(FormatoCgrInesperadoError);
    expect(() => filasCgrAtencionesExcel({ ...ATENCIONES, columnas: ATENCIONES.columnas.slice(0, 6) }))
      .toThrow(FormatoCgrInesperadoError);
    expect(() => filasCgrAlumnosExcel(ATENCIONES)).toThrow(FormatoCgrInesperadoError);
    expect(() => filasCgrAtencionesExcel(undefined as unknown as TablaCgr)).toThrow(FormatoCgrInesperadoError);
  });

  it('rechaza filas con una cantidad de valores distinta a la de las columnas', () => {
    const corrida = { ...ATENCIONES, filas: [['solo', 'tres', 'valores']] };
    expect(() => filasCgrAtencionesExcel(corrida)).toThrow(FormatoCgrInesperadoError);
  });
});

describe('CGR — filas de atenciones', () => {
  it('fecha en DD/MM/AAAA y hora en HH:MM, en columnas separadas', () => {
    const filas = filasCgrAtencionesExcel(ATENCIONES);
    const iFecha = COLUMNAS_CGR_ATENCIONES.indexOf('Fecha');
    const iHora = COLUMNAS_CGR_ATENCIONES.indexOf('Hora');

    expect(filas.map(f => f[iFecha])).toEqual(['14/09/2026', '15/09/2026', '15/09/2026', '05/01/2026']);
    expect(filas.map(f => f[iHora])).toEqual(['16:00', '08:30', '10:00', '09:05']);
    expect(iFecha).not.toBe(iHora);
  });

  it('una fila por registro, un valor por campo y en el orden recibido', () => {
    const filas = filasCgrAtencionesExcel(ATENCIONES);
    expect(filas).toHaveLength(ATENCIONES.filas.length);
    expect(filas.every(f => f.length === COLUMNAS_CGR_ATENCIONES.length)).toBe(true);
    expect(filas.map(f => f[0])).toEqual(['José Pérez García', 'ÁLVARO NÚÑEZ', 'Ñandú Soto', '—']);
  });

  it('conserva "No aplica" y "—" tal cual y nunca los reemplaza por vacío', () => {
    const filas = filasCgrAtencionesExcel(ATENCIONES);
    const iMed = COLUMNAS_CGR_ATENCIONES.indexOf('Medicamento Suministrado');

    expect(filas[0][iMed]).toBe('No aplica');
    expect(filas[3].filter(v => v === '—')).toHaveLength(4);      // nombre, RUT, especialidad y profesional
    expect(filas.flat().every(v => v !== '')).toBe(true);
  });

  it('un valor nulo que llegara por error se muestra como "—", no como celda vacía', () => {
    const conNulo: TablaCgr = { ...ATENCIONES, filas: [[null, '1-9', 'X', '2026-09-14', '10:00', null, 'Dr. Y']] };
    const fila = filasCgrAtencionesExcel(conNulo)[0];
    expect(fila[0]).toBe('—');
    expect(fila[5]).toBe('—');
  });

  it('no altera nombres ni capitalización y no aplica la normalización de búsqueda', () => {
    const filas = filasCgrAtencionesExcel(ATENCIONES);
    expect(filas[1][0]).toBe('ÁLVARO NÚÑEZ');
    expect(filas[0][6]).toBe('Dra. María Núñez');
    expect(filas[1][6]).toBe('Dr. Andrés de la Fuente');
    for (const fila of filas.slice(0, 3)) {
      expect(fila[0]).not.toBe(normalizarTexto(fila[0]));          // el exportado NO es el normalizado
    }
  });

  it('no muta la respuesta recibida', () => {
    const copia = JSON.parse(JSON.stringify(ATENCIONES));
    filasCgrAtencionesExcel(ATENCIONES);
    expect(ATENCIONES).toEqual(copia);
  });
});

describe('CGR — filas de alumnos', () => {
  it('un valor por campo, en orden, con los ausentes como "—"', () => {
    const filas = filasCgrAlumnosExcel(ALUMNOS);
    expect(filas).toHaveLength(3);
    expect(filas[0]).toEqual(['ÁLVARO NÚÑEZ', '9.876.543-2', 'Diseño', 'alvaro@utem.cl']);
    expect(filas[2]).toEqual(['—', '—', '—', 'sin.datos@utem.cl']);
  });
});

describe('CGR — archivo .xlsx', () => {
  it('atenciones: .xlsx real, hoja "Atenciones", encabezados y una fila por atención', async () => {
    const blob = libroAXlsxBlob(libroCgrAtenciones(ATENCIONES));
    const { bytes, nombres, matriz } = await leerLibro(blob);

    expect(blob.type).toBe(MIME_XLSX);
    expect([bytes[0], bytes[1]]).toEqual([0x50, 0x4b]);           // ZIP/OOXML, no texto tabulado
    expect(nombres).toEqual(['Atenciones']);                       // una sola hoja
    expect(matriz).toHaveLength(1 + ATENCIONES.filas.length);
    expect(matriz[0]).toEqual([...COLUMNAS_CGR_ATENCIONES]);
  });

  it('atenciones: cada dato en su celda, fecha y hora separadas', async () => {
    const { matriz } = await leerLibro(libroAXlsxBlob(libroCgrAtenciones(ATENCIONES)));

    expect(matriz[1]).toEqual([
      'José Pérez García', '12.345.678-9', 'Nutrición y Dietética',
      '14/09/2026', '16:00', 'No aplica', 'Dra. María Núñez'
    ]);
    expect(matriz[4]).toEqual(['—', '—', '—', '05/01/2026', '09:05', 'No aplica', '—']);
    for (const fila of matriz.slice(1)) expect(fila).toHaveLength(COLUMNAS_CGR_ATENCIONES.length);
  });

  it('atenciones: ninguna celda concatena campos', async () => {
    const { matriz } = await leerLibro(libroAXlsxBlob(libroCgrAtenciones(ATENCIONES)));

    for (const fila of matriz.slice(1)) {
      const celdas = fila.map(String);
      celdas.forEach((celda, i) => {
        expect(celda).not.toMatch(/\t|\n|\r| - | \| |;/);
        celdas.forEach((otra, j) => {
          if (i !== j && otra.length > 3 && otra !== celda) {
            expect(celda.includes(otra), `«${celda}» contiene «${otra}»`).toBe(false);
          }
        });
      });
    }
  });

  it('conserva tildes, ñ, mayúsculas y Unicode tras serializar', async () => {
    const { matriz } = await leerLibro(libroAXlsxBlob(libroCgrAtenciones(ATENCIONES)));
    const plano = matriz.flat().map(String);

    for (const esperado of ['José Pérez García', 'ÁLVARO NÚÑEZ', 'Ñandú Soto', 'Nutrición y Dietética',
                            'Dra. María Núñez', 'Ácido fólico', 'Dr. Andrés de la Fuente', 'Tipo de Atención',
                            'Profesional que Atendió']) {
      expect(plano, esperado).toContain(esperado);
    }
    expect(plano.join('')).not.toMatch(/\uFFFD|Ã.|Â./);
  });

  it('tiene autofiltro sobre los encabezados y todas las filas', async () => {
    const { hoja } = await leerLibro(libroAXlsxBlob(libroCgrAtenciones(ATENCIONES)));
    expect(hoja['!autofilter']?.ref).toBe('A1:G5');               // 7 columnas, 1 encabezado + 4 filas
  });

  it('cada columna tiene un ancho razonable según su contenido', async () => {
    const { hoja } = await leerLibro(libroAXlsxBlob(libroCgrAtenciones(ATENCIONES)));
    const anchos = (hoja['!cols'] ?? []).map((c: any) => c.wch ?? (c.wpx ? c.wpx / 7 : 0));

    expect(anchos).toHaveLength(COLUMNAS_CGR_ATENCIONES.length);
    expect(anchos.every((a: number) => a >= 10 && a <= 60)).toBe(true);
    // "Tipo de Atención" (contenido largo) es más ancha que "Hora".
    expect(anchos[COLUMNAS_CGR_ATENCIONES.indexOf('Tipo de Atención')])
      .toBeGreaterThan(anchos[COLUMNAS_CGR_ATENCIONES.indexOf('Hora')]);
  });

  it('sin registros: el archivo igual trae los encabezados (y el autofiltro)', async () => {
    const { matriz, hoja } = await leerLibro(libroAXlsxBlob(libroCgrAtenciones({ columnas: [...COLUMNAS_CGR_ATENCIONES], filas: [], total: 0 })));

    expect(matriz).toEqual([[...COLUMNAS_CGR_ATENCIONES]]);
    expect(hoja['!autofilter']?.ref).toBe('A1:G1');
  });

  it('alumnos: .xlsx real, hoja "Alumnos", columnas y filas en orden', async () => {
    const blob = libroAXlsxBlob(libroCgrAlumnos(ALUMNOS));
    const { bytes, nombres, matriz, hoja } = await leerLibro(blob);

    expect([bytes[0], bytes[1]]).toEqual([0x50, 0x4b]);
    expect(nombres).toEqual(['Alumnos']);
    expect(matriz[0]).toEqual([...COLUMNAS_CGR_ALUMNOS]);
    expect(matriz.slice(1)).toEqual(ALUMNOS.filas);
    expect(hoja['!autofilter']?.ref).toBe('A1:D4');
  });

  it('el libro genérico no altera las exportaciones existentes (Historial/Especialidad)', () => {
    const libro = construirLibroXlsx([{ A: 1, B: 'x' }], 'Hoja');
    expect(libro.SheetNames).toEqual(['Hoja']);
    expect(libro.Sheets['Hoja']['!autofilter']).toBeUndefined();  // sin autofiltro ni anchos añadidos
    expect(libro.Sheets['Hoja']['!cols']).toBeUndefined();
  });

  it('construirLibroTabla limita el ancho máximo de columna', () => {
    const libro = construirLibroTabla(['Columna'], [['x'.repeat(500)]], 'Hoja');
    expect((libro.Sheets['Hoja']['!cols'] as any[])[0].wch).toBe(60);
  });
});
