import { useCallback, useEffect, useState } from 'react'
import { getAudit } from '../api/index.js'
import { openAuthenticatedUrl } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import { Button, Input } from '../components/ui/Form.jsx'

const ACTION_STYLE = {
  PRESTAMO: 'bg-blue-500/10 text-blue-400',
  DEVOLUCION: 'bg-emerald-500/10 text-emerald-400',
  PRORROGA: 'bg-amber-500/10 text-amber-400',
}

export default function History() {
  const { user } = useAuth()
  const [entries, setEntries] = useState([])
  const [q, setQ] = useState('')
  const [day, setDay] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setEntries(await getAudit({ q, day }))
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [q, day])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  if (user?.role !== 'admin') {
    return (
      <div className="mx-auto mt-20 max-w-md rounded-2xl border border-red-500/30 bg-red-500/5 p-8 text-center">
        <p className="text-4xl">🚫</p>
        <h2 className="mt-3 text-xl font-bold text-red-400">Acceso denegado</h2>
        <p className="mt-2 text-sm text-slate-400">Solo los administradores pueden ver el historial de movimientos.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white md:text-3xl">Historial de movimientos</h2>
          <p className="text-sm text-slate-400">Auditoría de préstamos, devoluciones y prórrogas</p>
        </div>
        <Button variant="ghost" onClick={() => openAuthenticatedUrl('/audit/export')}>
          📥 Exportar a Excel
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar acción, producto o detalle..." className="max-w-xs" />
        <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="w-44" />
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      ) : entries.length === 0 ? (
        <EmptyState message="Sin movimientos registrados" />
      ) : (
        <Table
          columns={[
            { key: 'when', label: 'Fecha' },
            { key: 'who', label: 'Usuario' },
            { key: 'action', label: 'Acción', align: 'center' },
            { key: 'product', label: 'Producto' },
            { key: 'qty', label: 'Cantidad', align: 'center' },
            { key: 'detail', label: 'Detalle' },
          ]}
        >
          {entries.map((e) => (
            <tr key={e.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(e.timestamp).toLocaleString('es-US')}</td>
              <td className="px-4 py-3 text-slate-300">{e.username || 'Sistema'}</td>
              <td className="px-4 py-3 text-center">
                <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-bold ${ACTION_STYLE[e.action] || 'bg-slate-500/10 text-slate-400'}`}>
                  {e.action}
                </span>
              </td>
              <td className="px-4 py-3 text-slate-200">{e.product_name || '—'}</td>
              <td className="px-4 py-3 text-center text-slate-300">{e.quantity ?? '—'}</td>
              <td className="px-4 py-3 text-xs text-slate-500">{e.detail || '—'}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  )
}
