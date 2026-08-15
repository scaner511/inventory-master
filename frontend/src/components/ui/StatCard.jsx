import { Link } from 'react-router-dom'

export default function StatCard({ title, value, subtitle, icon, accent = 'text-blue-400', bg = 'from-blue-500/10 to-blue-500/0', to, onClick }) {
  const inner = (
    <>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-400">{title}</p>
          <p className={`mt-2 text-3xl font-extrabold ${accent}`}>{value}</p>
          {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
        </div>
        <div className={`rounded-xl bg-gradient-to-br ${bg} p-3 text-2xl`}>{icon}</div>
      </div>
    </>
  )

  const cls =
    'group block rounded-2xl border border-slate-800 bg-gradient-to-br to-transparent p-5 transition hover:-translate-y-0.5 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-900/50'

  if (to) {
    return (
      <Link to={to} onClick={onClick} className={cls}>
        {inner}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} className={`${cls} w-full text-left`}>
      {inner}
    </button>
  )
}
