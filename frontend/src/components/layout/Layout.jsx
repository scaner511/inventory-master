import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { logout } from '../../api/auth.js'
import { getLogoUrl, getSettings } from '../../api/index.js'
import { useEffect, useState } from 'react'
import NotificationBell from './NotificationBell.jsx'

const NAV = [
  { to: '/', label: 'Dashboard', icon: 'M3 13l9-9 9 9M5 10v10h14V10' },
  { to: '/temporary-storage', label: 'Recepción Mercancía', module: 'temporary_storage', icon: 'M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4' },
  { to: '/prospects', label: 'Prospectos', module: 'prospects', icon: 'M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-2.13a4 4 0 10-4-4 4 4 0 004 4zm6-4a3 3 0 11-3-3 3 3 0 013 3z' },
  { to: '/calendar', label: 'Calendario', module: 'calendar', icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z' },
  { to: '/commercial', label: 'Dashboard Comercial', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 002 2h2a2 2 0 002-2' },
  { to: '/captacion', label: 'Captación', module: 'capture', icon: 'M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7' },
  { to: '/captacion/dashboard', label: 'Dashboard Captación', module: 'capture', icon: 'M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z' },
  { to: '/loans', label: 'PrAcstamos', icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4' },
  { to: '/history', label: 'Historial', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z', adminOnly: true },
  { to: '/admin', label: 'Panel Admin', icon: 'M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z', adminOnly: true },
  { to: '/superadmin', label: 'Super Admin', icon: 'M9 12l2 2 4-4m5.6-2.6A9 9 0 1112 3a9 9 0 018.6 6.4z', superadminOnly: true },
]

export function roleLabel(role) {
  if (role === 'superadmin') return 'Super Admin'
  if (role === 'admin') return 'Administrador'
  return 'Operador'
}

export default function Layout() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  const [logoUrl, setLogoUrl] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function fetchLogo() {
      try {
        const s = await getSettings()
        if (cancelled) return
        if (s?.has_logo) {
          const url = await getLogoUrl()
          if (!cancelled) setLogoUrl(url)
        } else {
          setLogoUrl(null)
        }
      } catch {
        if (!cancelled) setLogoUrl(null)
      }
    }
    fetchLogo()
    const onLogo = () => fetchLogo()
    window.addEventListener('company-logo-updated', onLogo)
    return () => {
      cancelled = true
      window.removeEventListener('company-logo-updated', onLogo)
    }
  }, [user?.tenant_id])

  return (
    <div className="flex min-h-screen bg-[#0b1220]">
      {/* Sidebar escritorio */}
      <aside className="sticky top-0 hidden h-screen w-64 flex-col border-r border-slate-800 bg-[#050a18] p-4 md:flex">
        <SidebarContent user={user} logoUrl={logoUrl} />
      </aside>

      {/* Sidebar móvil */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 bg-[#050a18] p-4 shadow-xl">
            <SidebarContent user={user} logoUrl={logoUrl} onNavigate={() => setOpen(false)} />
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
            <NotificationBell />
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-200">{user?.username}</p>
              <p className="text-xs capitalize text-slate-400">
                {roleLabel(user?.role)}
                {user?.tenant_name ? ` · ${user.tenant_name}` : ''}
              </p>
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

function SidebarContent({ user, logoUrl, onNavigate }) {
  return (
    <>
      <div className="mb-8 mt-2 flex flex-col items-center gap-1">
        {logoUrl ? (
          <div className="flex h-[168px] w-[168px] items-center justify-center overflow-hidden rounded-3xl border border-slate-700 bg-white">
            <img src={logoUrl} alt="Logo" className="h-full w-full object-contain p-2" />
          </div>
        ) : (
          <div className="flex h-[168px] w-[168px] items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 to-indigo-600 text-6xl">
            📦
          </div>
        )}
        <p className="mt-2 font-bold text-slate-100">{user?.username}</p>
        <span className="rounded-full bg-blue-500/10 px-3 py-0.5 text-xs font-semibold text-blue-400">
          {roleLabel(user?.role)}
        </span>
      </div>

      <nav className="flex flex-col gap-1">
        {NAV.filter((item) => {
          if (item.superadminOnly) return user?.role === 'superadmin'
          if (item.adminOnly) return user?.role === 'admin'
          // Módulos restringidos: admin/superadmin ven todo; operador solo lo habilitado.
          if (item.module && user?.role === 'user') {
            return Array.isArray(user.modules) && user.modules.includes(item.module)
          }
          return true
        }).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/' || item.to === '/captacion'}
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
