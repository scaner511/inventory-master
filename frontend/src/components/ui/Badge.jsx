const STYLES = {
  DISPONIBLE: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  STOCK_BAJO: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  NO_DISPONIBLE: 'bg-red-500/10 text-red-400 border-red-500/30',
  ACTIVO: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  VENCE_HOY: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  VENCIDO: 'bg-red-500/10 text-red-400 border-red-500/30',
  COMPLETADO: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
}

const LABELS = {
  DISPONIBLE: 'Disponible',
  STOCK_BAJO: 'Stock bajo',
  NO_DISPONIBLE: 'No disponible',
  ACTIVO: 'Activo',
  VENCE_HOY: 'Vence hoy',
  VENCIDO: 'Vencido',
  COMPLETADO: 'Completado',
}

export default function Badge({ status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
        STYLES[status] || 'bg-slate-500/10 text-slate-400 border-slate-500/30'
      }`}
    >
      {LABELS[status] || status}
    </span>
  )
}
