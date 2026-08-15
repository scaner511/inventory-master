import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getDashboard } from '../api/index.js'
import { formatMoney } from '../api/client.js'
import StatCard from '../components/ui/StatCard.jsx'
import Badge from '../components/ui/Badge.jsx'

const tooltipStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8 }

export default function Dashboard() {
  const [data, setData] = useState(null)

  useEffect(() => {
    getDashboard().then(setData).catch(() => {})
  }, [])

  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    )
  }

  const chartData = data.top_products.map((p) => ({
    name: p.name.length > 14 ? p.name.slice(0, 14) + '…' : p.name,
    valor: p.value,
  }))

  const activityData = data.loans_last_7_days || []

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white md:text-3xl">Dashboard</h2>
          <p className="text-sm text-slate-400">Resumen en tiempo real de tu negocio</p>
        </div>
        <div className="flex gap-2">
          <Link
            to="/products"
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-700 hover:text-white"
          >
            📦 Inventario
          </Link>
          <Link
            to="/loans"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
          >
            ➕ Nuevo préstamo
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard
          to="/products"
          title="Total Productos"
          value={data.total_products}
          subtitle={`${data.total_units} unidades en stock`}
          icon="📦"
        />
        <StatCard
          to="/loans"
          title="Préstamos Activos"
          value={data.active_loans}
          subtitle="pendientes de devolución"
          icon="🤝"
          accent="text-amber-400"
          bg="from-amber-500/10 to-amber-500/0"
        />
        <StatCard
          to="/loans"
          title="Vencidos"
          value={data.overdue_loans}
          subtitle="deben devolverse ya"
          icon="🔴"
          accent="text-red-400"
          bg="from-red-500/10 to-red-500/0"
        />
        <StatCard
          to="/products"
          title="Stock Crítico"
          value={data.low_stock_products}
          subtitle="productos por debajo del umbral"
          icon="⚠️"
          accent="text-orange-400"
          bg="from-orange-500/10 to-orange-500/0"
        />
        <StatCard
          title="Capital Invertido"
          value={formatMoney(data.capital_invested)}
          subtitle="valor de compra del stock actual"
          icon="💰"
          accent="text-emerald-400"
          bg="from-emerald-500/10 to-emerald-500/0"
        />
        <StatCard
          title="Ingreso Potencial"
          value={formatMoney(data.potential_income)}
          subtitle="valor de venta del stock actual"
          icon="💵"
          accent="text-violet-400"
          bg="from-violet-500/10 to-violet-500/0"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Gráfico de productos más valiosos */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <h3 className="mb-4 text-sm font-bold text-slate-200">Top 5 productos por valor en inventario</h3>
          {chartData.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500">Aún no hay productos</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip
                  cursor={{ fill: '#1e293b' }}
                  contentStyle={tooltipStyle}
                  formatter={(value) => [formatMoney(value), 'Valor']}
                />
                <Bar dataKey="valor" fill="#3b82f6" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Actividad de préstamos últimos 7 días */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <h3 className="mb-4 text-sm font-bold text-slate-200">Préstamos registrados · últimos 7 días</h3>
          {activityData.every((d) => d.prestamos === 0) ? (
            <p className="py-10 text-center text-sm text-slate-500">Sin movimiento esta semana</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={activityData}>
                <defs>
                  <linearGradient id="gradLoans" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.5} />
                    <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="day" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                <Tooltip contentStyle={tooltipStyle} formatter={(value) => [value, 'Préstamos']} />
                <Area type="monotone" dataKey="prestamos" stroke="#a78bfa" strokeWidth={2} fill="url(#gradLoans)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Préstamos vencidos */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200">Préstamos vencidos</h3>
            <Link to="/loans" className="text-xs font-semibold text-blue-400 transition hover:text-blue-300">
              Ver todos →
            </Link>
          </div>
          {data.overdue_loans_list.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500">No hay préstamos vencidos 🎉</p>
          ) : (
            <ul className="space-y-2">
              {data.overdue_loans_list.map((loan) => (
                <li key={loan.id} className="flex items-center justify-between rounded-lg bg-red-500/5 px-3 py-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-200">{loan.seller}</p>
                    <p className="text-xs text-slate-400">
                      {loan.product_name} · {loan.pending} pendiente(s)
                    </p>
                  </div>
                  <span className="text-xs font-bold text-red-400">Venció {loan.due_date}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Actividad reciente */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200">Actividad reciente</h3>
            <Link to="/loans" className="text-xs font-semibold text-blue-400 transition hover:text-blue-300">
              Ver todos →
            </Link>
          </div>
          {data.recent_loans.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-500">Sin préstamos registrados todavía</p>
          ) : (
            <ul className="space-y-2">
              {data.recent_loans.map((loan) => (
                <li key={loan.id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-800/50 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-200">{loan.seller}</p>
                    <p className="truncate text-xs text-slate-400">
                      {loan.product_name} · {loan.pending}/{loan.quantity}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge status={loan.status} />
                    <span className="text-xs text-slate-500">{new Date(loan.loan_date).toLocaleDateString('es-US')}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Lista stock bajo */}
      {data.low_stock_list.length > 0 && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-bold text-amber-300">⚠️ Productos con stock bajo</h3>
            <Link to="/products" className="text-xs font-semibold text-amber-400 transition hover:text-amber-300">
              Ir al inventario →
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.low_stock_list.map((p) => (
              <Link
                to="/products"
                key={p.id}
                className="flex items-center justify-between rounded-lg bg-slate-900 px-3 py-2 transition hover:bg-slate-800"
              >
                <span className="text-sm text-slate-200">{p.name}</span>
                <Badge status={p.status} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
