import { useEffect, useState } from 'react'
import { getCommercialDashboard } from '../api/index.js'
import { formatMoney } from '../api/client.js'

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
  const max = Math.max(1, ...rows.map((r) => r.count))
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
                <span className="capitalize">{String(r[keyField]).replace(/_/g, ' ')}</span>
                <span className="font-semibold">{r.count}</span>
              </div>
              <div className="h-2 rounded-full bg-slate-800">
                <div className="h-2 rounded-full bg-blue-500" style={{ width: `${(r.count / max) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function CommercialDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCommercialDashboard()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="py-10 text-center text-sm text-slate-400">Cargando…</p>
  if (!data) return <p className="py-10 text-center text-sm text-red-400">No se pudo cargar el dashboard</p>

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-slate-100">Dashboard comercial</h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Prospectos" value={data.total_prospects} hint={`${data.converted} convertidos`} />
        <Card label="Tasa de conversión" value={`${data.conversion_rate}%`} accent="text-emerald-400" />
        <Card label="Valor del pipeline" value={formatMoney(data.active_pipeline_value)} hint={`Ponderado ${formatMoney(data.weighted_value)}`} accent="text-blue-400" />
        <Card label="Seguimientos pendientes" value={data.pending_followups} accent="text-amber-400" />
        <Card label="Citas hoy" value={data.appointments_today} />
        <Card label="Citas esta semana" value={data.appointments_week} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BarList title="Prospectos por etapa" rows={data.by_stage.map((r) => ({ stage: r.stage, count: r.count }))} keyField="stage" />
        <BarList title="Prospectos por estado" rows={data.by_status.map((r) => ({ status: r.status, count: r.count }))} keyField="status" />
        <BarList title="Productos de interés (top)" rows={data.top_products.map((r) => ({ product: r.product, count: r.count }))} keyField="product" />
        <BarList title="Motivos de no compra" rows={data.lost_reasons.map((r) => ({ reason: r.reason, count: r.count }))} keyField="reason" />
      </div>

      <BarList title="Prospectos por mes" rows={data.by_month.map((r) => ({ month: r.month, count: r.count }))} keyField="month" />
    </div>
  )
}
