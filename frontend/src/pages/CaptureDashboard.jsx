import { useEffect, useState } from 'react'
import { getCaptureDashboard, captureExportUrl } from '../api/index.js'
import { openAuthenticatedUrl } from '../api/client.js'

function Card({ label, value, hint, accent = 'text-slate-100' }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${accent}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
    </div>
  )
}

function BarList({ title, rows, keyField }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <p className="mb-3 text-sm font-semibold text-slate-200">{title}</p>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">Sin datos</p>
      ) : (
        <div className="space-y-2">
          {rows.map((r) => (
            <div key={r[keyField]}>
              <div className="mb-1 flex justify-between text-xs text-slate-300">
                <span>{String(r[keyField])}</span>
                <span className="font-semibold">{r.value}</span>
              </div>
              <div className="h-2 rounded-full bg-slate-800">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-blue-500 to-indigo-500"
                  style={{ width: `${(r.value / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function CaptureDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCaptureDashboard()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="py-10 text-center text-sm text-slate-400">Cargando…</p>
  if (!data) return <p className="py-10 text-center text-sm text-red-400">No se pudo cargar el dashboard</p>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-bold text-slate-100">Dashboard de captación</h2>
        <div className="flex gap-2">
          <button
            onClick={() => openAuthenticatedUrl(captureExportUrl('pdf'))}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm font-semibold text-slate-200 hover:bg-slate-800"
          >
            PDF
          </button>
          <button
            onClick={() => openAuthenticatedUrl(captureExportUrl('excel'))}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm font-semibold text-slate-200 hover:bg-slate-800"
          >
            Excel
          </button>
          <button
            onClick={() => openAuthenticatedUrl(captureExportUrl('csv'))}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm font-semibold text-slate-200 hover:bg-slate-800"
          >
            CSV
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Captados hoy" value={data.captured_today} accent="text-blue-400" />
        <Card label="Captados este mes" value={data.captured_month} />
        <Card label="Total participaciones" value={data.total_entries} hint={`${data.sessions_count} jornadas`} />
        <Card label="Premios entregados" value={data.prizes_given} accent="text-amber-400" />
        <Card label="Convertidos" value={data.converted} accent="text-emerald-400" />
        <Card label="% Conversión" value={`${data.conversion_rate}%`} accent="text-emerald-400" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BarList title="Captaciones por campaña" rows={data.by_campaign} keyField="name" />
        <BarList title="Captaciones por vendedor" rows={data.by_vendor} keyField="name" />
        <BarList title="Premios entregados" rows={data.by_prize} keyField="name" />
        <BarList title="Top campañas" rows={data.top_campaigns} keyField="name" />
      </div>

      <BarList
        title="Captaciones por día"
        rows={data.by_day.map((d) => ({ date: d.date, value: d.value }))}
        keyField="date"
      />
    </div>
  )
}
