// Contenido legal de Inventory Master OS Web v2026.
// Se muestra en el modal obligatorio de aceptación (components/TermsModal.jsx).

export const LEGAL_VERSION = 'Agosto 2026'

export const PRIVACY_POLICY = {
  id: 'privacy',
  title: 'POLÍTICA DE PRIVACIDAD',
  system: 'Inventory Master OS Web v2026',
  updated: LEGAL_VERSION,
  sections: [
    {
      heading: '1. Introducción',
      paragraphs: [
        'Inventory Master OS Web es una plataforma diseñada para la gestión de inventario, préstamos de equipos, control de licencias y administración de usuarios dentro de una organización. El uso del sistema implica la aceptación de la presente Política de Privacidad.',
      ],
    },
    {
      heading: '2. Información recopilada',
      paragraphs: ['El sistema puede almacenar:'],
      bullets: [
        'Nombre de usuario.',
        'Contraseñas cifradas mediante algoritmos seguros.',
        'Preguntas y respuestas de recuperación de cuenta.',
        'Historial de movimientos y actividades realizadas dentro del sistema.',
        'Información de inventario registrada por la empresa.',
        'Datos de préstamos y devoluciones.',
        'Datos de configuración de la empresa.',
        'Archivos cargados por los usuarios, incluyendo importaciones de Excel, CSV y logotipos.',
      ],
    },
    {
      heading: '3. Uso de la información',
      paragraphs: ['La información recopilada será utilizada exclusivamente para:'],
      bullets: [
        'Gestionar inventarios.',
        'Controlar préstamos y devoluciones.',
        'Generar reportes e indicadores.',
        'Mantener la seguridad del sistema.',
        'Realizar copias de seguridad.',
        'Cumplir con funciones administrativas y operativas.',
      ],
    },
    {
      heading: '4. Seguridad',
      paragraphs: [
        'El sistema implementa medidas de seguridad tales como:',
      ],
      bullets: [
        'Cifrado de contraseñas mediante bcrypt.',
        'Autenticación mediante JWT.',
        'Control de acceso basado en roles.',
        'Historial de auditoría de acciones administrativas.',
        'Restricción de acceso a funciones sensibles.',
      ],
      footer:
        'Sin embargo, ningún sistema informático puede garantizar una protección absoluta frente a amenazas externas.',
    },
    {
      heading: '5. Respaldo de información',
      paragraphs: [
        'Inventory Master OS Web puede generar copias de seguridad automáticas o manuales para proteger los datos almacenados.',
        'La responsabilidad de conservar dichas copias corresponde al administrador del sistema y a la organización propietaria de los datos.',
      ],
    },
    {
      heading: '6. Compartición de datos',
      paragraphs: [
        'El sistema no comparte información con terceros de manera automática.',
        'Cualquier exportación, respaldo o transmisión de datos será realizada únicamente por usuarios autorizados por la organización.',
      ],
    },
    {
      heading: '7. Responsabilidad del usuario',
      paragraphs: ['Cada usuario es responsable de:'],
      bullets: [
        'Mantener la confidencialidad de sus credenciales.',
        'No compartir contraseñas.',
        'Utilizar el sistema conforme a las políticas internas de la empresa.',
        'Reportar accesos no autorizados.',
      ],
    },
    {
      heading: '8. Modificaciones',
      paragraphs: [
        'La organización administradora podrá modificar esta política en cualquier momento. Los cambios serán notificados dentro del sistema.',
      ],
    },
  ],
}

export const TERMS_OF_USE = {
  id: 'terms',
  title: 'TÉRMINOS Y CONDICIONES DE USO',
  system: 'Inventory Master OS Web v2026',
  updated: LEGAL_VERSION,
  sections: [
    {
      heading: '1. Aceptación',
      paragraphs: [
        'Al acceder o utilizar Inventory Master OS Web, usted acepta cumplir estos Términos y Condiciones.',
      ],
    },
    {
      heading: '2. Uso autorizado',
      paragraphs: ['El sistema está destinado exclusivamente para actividades relacionadas con:'],
      bullets: [
        'Gestión de inventario.',
        'Control de activos.',
        'Registro de préstamos.',
        'Administración de usuarios.',
        'Generación de reportes.',
      ],
    },
    {
      heading: '3. Cuentas de usuario',
      paragraphs: ['Cada usuario deberá utilizar únicamente su propia cuenta.', 'Está prohibido:'],
      bullets: [
        'Compartir credenciales.',
        'Intentar acceder a información sin autorización.',
        'Alterar registros sin autorización.',
        'Manipular datos con fines fraudulentos.',
      ],
    },
    {
      heading: '4. Licenciamiento',
      paragraphs: [
        'El uso del sistema está sujeto a una licencia válida.',
        'Cuando una licencia expire, determinadas funciones podrán quedar restringidas o bloqueadas según la configuración del sistema.',
      ],
    },
    {
      heading: '5. Disponibilidad',
      paragraphs: [
        'Aunque se realizarán esfuerzos razonables para garantizar la disponibilidad, no se garantiza que el sistema esté libre de interrupciones, errores o fallos.',
      ],
    },
    {
      heading: '6. Copias de seguridad',
      paragraphs: [
        'El administrador del sistema es responsable de verificar y conservar los respaldos generados.',
      ],
    },
    {
      heading: '7. Limitación de responsabilidad',
      paragraphs: ['Los desarrolladores y propietarios del sistema no serán responsables por:'],
      bullets: [
        'Pérdida de datos causada por errores de usuario.',
        'Fallos de hardware.',
        'Problemas de red.',
        'Ataques informáticos externos.',
        'Modificaciones realizadas por terceros.',
      ],
    },
    {
      heading: '8. Terminación de acceso',
      paragraphs: [
        'La organización podrá suspender o revocar el acceso de cualquier usuario que incumpla estos términos.',
      ],
    },
    {
      heading: '9. Aceptación electrónica',
      paragraphs: [
        'La aceptación electrónica de estos términos tendrá la misma validez que una aceptación escrita para fines de uso interno del sistema.',
      ],
    },
  ],
}
