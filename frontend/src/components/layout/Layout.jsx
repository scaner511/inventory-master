import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { logout } from '../../api/auth.js'
import { useState } from 'react'

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'M3 13l9-9 9 9M5 10v10h14V10' },
  { to: '/loans', label: 'Préstamos', icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
  { to: '/history', label: 'Historial', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z', adminOnly: true },
  { to: '/admin', label: 'Panel Admin', icon: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z', adminOnly: true },
]

export default function Layout() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-[#0b1220]">
      {/* Sidebar escritorio */}
      <aside className="sticky top-0 hidden h-screen w-64 flex-col border-r border-slate-800 bg-[#050a18] p-4 md:flex">
        <SidebarContent user={user} />
      </aside>

      {/* Sidebar móvil */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 bg-[#050a18] p-4 shadow-xl">
            <SidebarContent user={user} onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Barra superior */}
        <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-slate-800 bg-[#0b1220]/90 px-4 py-3 backdrop-blur md:px-8">
          <button
            onClick={() => setOpen(true)}
            className="rounded-lg p-2 text-slate-300 hover:bg-slate-800 md:hidden"
            aria-label="Abrir menú"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <h1 className="text-lg font-bold text-blue-400 md:text-xl">INVENTORY MASTER OS</h1>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-200">{user?.username}</p>
              <p className="text-xs capitalize text-slate-400">{user?.role === 'admin' ? 'Administrador' : 'Operador'}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700"
            >
              Salir
            </button>
          </div>
        </header>

        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function SidebarContent({ user, onNavigate }) {
  return (
    <>
      <div className="mb-8 mt-2 flex flex-col items-center gap-1">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-2xl">
          📦
        </div>
        <p className="mt-2 font-bold text-slate-100">{user?.username}</p>
        <span className="rounded-full bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400">
          {user?.role === 'admin' ? 'Administrador' : 'Operador'}
        </span>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV.filter((item) => !item.adminOnly || user?.role === 'admin').map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d={item.icon} />
            </svg>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </>
  )
}
