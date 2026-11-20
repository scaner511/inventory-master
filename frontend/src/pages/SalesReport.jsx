import { useCallback, useEffect, useMemo, useState } from 'react'
import { getSalesReport } from '../api/index.js'
import { Button, Field, Input, Select } from '../components/ui/Form.jsx'

const PERIODS = [
  { value: 'day', label: 'Diaria' },
  { value: 'week', label: 'Semanal' },
  { value: 'month', label: 'Mensual' },
  { value: 'year', label: 'Anual' },
]

const SOURCES = { calculadora: 'Calculadora', cita: 'Cita' }
const RESULTS = { compra: 'Compra', reagendado: 'Reagendada', venta_realizada: 'Venta' }

function fmtMoney(n) {
  return 'RD$ ' + Number(n || 0).toLocaleString('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtDate(d) {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  return `${day}/${m}/${y}`
}

export default function SalesReport() {
  const today = new Date().toISOString().slice(0, 10)
  const [period, setPeriod] = useState('month')
  const [onDate, setOnDate] = useState(today)
  const [commissionPct, setCommissionPct] = useState('10')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [openSeller, setOpenSeller] = useState(null)
  const [openSections, setOpenSections] = useState({})

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(
        await getSalesReport({
          period,
          on_date: onDate || undefined,
          commission_pct: Number(commissionPct) || 0,
        })
      )
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [period, onDate, commissionPct])

  useEffect(() => {
    load()
  }, [load])

  // Agrupar vendedores por sección.
  const sections = useMemo(() => {
    const map = {}
    for (const s of data?.sellers || []) {
      ;(map[s.section] ||= []).push(s)
    }
    return Object.entries(map).sort(([a], [b]) => a.localeCompare(b))
  }, [data])

  function toggleSection(name) {
    setOpenSections((prev) => ({ ...prev, [name]: !prev[name] }))
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Reporte Mensual de Ventas</h1>
        <p className="text-sm text-slate-400">
          {data ? `${fmtDate(data.from)} — ${fmtDate(data.to)}` : 'Cargando…'}
        </p>
      </div>

      {/* Controles */}
      <div className="grid gap-4 rounded-xl border border-slate-700 bg-slate-800/60 p-4 sm:grid-cols-4">
        <Field label="Período">
          <Select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </Select>
        </Field>
        <Field label="Fecha de referencia">
          <Input type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} />
        </Field>
        <Field label="Comisión (%)" hint="Se aplica sobre ventas sin ITBIS">
          <Input
            type="number"
            min="0"
            max="100"
            step="0.5"
            value={commissionPct}
            onChange={(e) => setCommissionPct(e.target.value)}
          />
        </Field>
        <div className="flex items-end">
          <Button type="button" variant="ghost" onClick={load} disabled={loading}>
            {loading ? 'Cargando…' : 'Actualizar'}
          </Button>
        </div>
      </div>

      {/* Totales */}
      {data && (
        <div className="grid gap-3 rounded-xl border border-slate-700 bg-slate-800/60 p-4 sm:grid-cols-4">
          <div>
            <div className="text-xs text-slate-400">Total ventas aprobadas</div>
            <div className="text-xl font-bold text-white">{fmtMoney(data.totals.sales_total)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Base sin ITBIS ({data.itbis_rate}%)</div>
            <div className="text-xl font-bold text-blue-400">{fmtMoney(data.totals.sales_base)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Comisión ({data.commission_pct}%)</div>
            <div className="text-xl font-bold text-green-400">{fmtMoney(data.totals.commission)}</div>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-sm">
            <div className="rounded bg-white/5 p-2">
              <div className="text-lg font-bold text-white">{data.totals.clients_closed}</div>
              <div className="text-[10px] text-slate-400">Clientes</div>
            </div>
            <div className="rounded bg-white/5 p-2">
              <div className="text-lg font-bold text-white">{data.totals.presentations}</div>
              <div className="text-[10px] text-slate-400">Presentaciones</div>
            </div>
            <div className="rounded bg-white/5 p-2">
              <div className="text-lg font-bold text-white">{data.totals.prospects_captured}</div>
              <div className="text-[10px] text-slate-400">Prospectos</div>
            </div>
          </div>
        </div>
      )}

      {/* Vendedores por sección */}
      {sections.length === 0 && !loading && (
        <div className="rounded-xl border border-slate-700 bg-slate-800/60 p-8 text-center text-slate-400">
          No hay actividad registrada en este período.
        </div>
      )}

      {sections.map(([section, sellers]) => {
        const open = openSections[section] !== false
        const secSales = sellers.reduce((a, s) => a + s.sales_total, 0)
        return (
          <div key={section} className="overflow-hidden rounded-xl border border-slate-700">
            <button
              type="button"
              onClick={() => toggleSection(section)}
              className="flex w-full items-center justify-between bg-slate-800 px-4 py-3 text-left hover:bg-slate-700/60"
            >
              <span className="font-bold text-white">
                {open ? '▾' : '▸'} {section}
              </span>
              <span className="text-sm text-slate-400">
                {sellers.length} vendedor(es) · {fmtMoney(secSales)}
              </span>
            </button>
            {open && (
              <div className="divide-y divide-slate-700/60 bg-slate-900/40">
                {sellers.map((s) => {
                  const isOpen = openSeller === s.seller
                  return (
                    <div key={s.seller}>
                      <button
                        type="button"
                        onClick={() => setOpenSeller(isOpen ? null : s.seller)}
                        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-slate-800/60"
                      >
                        <span className="font-semibold text-blue-300">
                          {isOpen ? '▾' : '▸'} {s.seller}
                        </span>
                        <span className="flex gap-4 text-xs text-slate-400">
                          <span>{s.clients_closed} clientes</span>
                          <span>{s.prospects_captured} prospectos</span>
                          <span>{s.presentations} presentaciones</span>
                          <span className="font-bold text-green-400">{fmtMoney(s.sales_total)}</span>
                        </span>
                      </button>
                      {isOpen && (
                        <div className="grid gap-3 px-4 pb-4 sm:grid-cols-2">
                          <DetailList
                            title="Clientes que cerró ventas"
                            items={s.closed_list.map((i) => ({
                              main: i.name,
                              sub: `${fmtDate(i.date)} · ${fmtMoney(i.total)}`,
                            }))}
                            empty="Sin ventas cerradas"
                          />
                          <DetailList
                            title="Prospectos captados"
                            items={s.captured_list.map((i) => ({
                              main: i.name,
                              sub: fmtDate(i.date),
                            }))}
                            empty="Sin prospectos captados"
                          />
                          <DetailList
                            title="Presentaciones realizadas"
                            items={s.presentation_list.map((i, idx) => ({
                              main: i.name || `${SOURCES[i.source] || i.source} · ${RESULTS[i.detail] || i.detail}`,
                              sub: `${fmtDate(i.date)} · ${SOURCES[i.source] || i.source}`,
                              key: idx,
                            }))}
                            empty="Sin presentaciones"
                          />
                          <DetailList
                            title="Ventas aprobadas"
                            items={s.sales_list.map((i, idx) => ({
                              main: i.name,
                              sub: `${fmtDate(i.date)} · ${fmtMoney(i.total)}`,
                              key: idx,
                            }))}
                            empty="Sin ventas aprobadas"
                          />
                          <div className="sm:col-span-2 rounded-lg bg-slate-800/70 p-3 text-sm">
                            <span className="text-slate-400">Total ventas: </span>
                            <span className="font-bold text-white">{fmtMoney(s.sales_total)}</span>
                            <span className="text-slate-400"> · sin ITBIS: </span>
                            <span className="font-bold text-blue-400">
                              {fmtMoney(s.sales_total / (1 + (data.itbis_rate || 18) / 100))}
                            </span>
                            <span className="text-slate-400"> · comisión ({data.commission_pct}%): </span>
                            <span className="font-bold text-green-400">
                              {fmtMoney(
                                (s.sales_total / (1 + (data.itbis_rate || 18) / 100)) *
                                  (data.commission_pct / 100)
                              )}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function DetailList({ title, items, empty }) {
  return (
    <div className="rounded-lg border border-slate-700/70 bg-slate-800/50 p-3">
      <div className="mb-2 text-xs font-bold uppercase text-slate-400">{title} ({items.length})</div>
      {items.length === 0 ? (
        <div className="text-xs text-slate-500">{empty}</div>
      ) : (
        <ul className="max-h-40 space-y-1 overflow-y-auto text-sm">
          {items.map((i, idx) => (
            <li key={i.key ?? idx} className="flex items-center justify-between gap-2">
              <span className="truncate text-slate-200">{i.main}</span>
              <span className="shrink-0 text-xs text-slate-400">{i.sub}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
