export default function Table({ columns, children }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-slate-800 bg-slate-800/50">
            {columns.map((col) => (
              <th key={col.key} className={`px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-400 ${col.align === 'center' ? 'text-center' : ''}`}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">{children}</tbody>
      </table>
    </div>
  )
}

export function EmptyState({ message = 'Sin datos para mostrar' }) {
  return (
    <div className="py-14 text-center">
      <p className="text-4xl">🗂️</p>
      <p className="mt-3 text-sm text-slate-400">{message}</p>
    </div>
  )
}
