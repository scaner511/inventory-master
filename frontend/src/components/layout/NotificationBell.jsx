import { useEffect, useRef, useState } from 'react'
import {
  getNotifications,
  getUnreadNotificationsCount,
  markAllNotificationsRead,
  markNotificationRead,
} from '../../api/index.js'

function timeAgo(iso) {
  const then = new Date(iso).getTime()
  const mins = Math.floor((Date.now() - then) / 60000)
  if (mins < 1) return 'ahora'
  if (mins < 60) return `hace ${mins} min`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `hace ${hours} h`
  const days = Math.floor(hours / 24)
  return `hace ${days} d`
}

export default function NotificationBell() {
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const ref = useRef(null)

  async function refreshCount() {
    try {
      setCount(await getUnreadNotificationsCount())
    } catch {
      /* silencio: la campana no debe romper la sesión */
    }
  }

  useEffect(() => {
    refreshCount()
    const id = setInterval(refreshCount, 60000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [open])

  async function openPanel() {
    const next = !open
    setOpen(next)
    if (next) {
      setLoading(true)
      try {
        setItems(await getNotifications({ limit: 50 }))
      } catch {
        setItems([])
      } finally {
        setLoading(false)
      }
    }
  }

  async function handleRead(n) {
    if (!n.read) {
      try {
        await markNotificationRead(n.id)
        setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)))
        setCount((c) => Math.max(0, c - 1))
      } catch {
        /* noop */
      }
    }
  }

  async function handleAll() {
    try {
      await markAllNotificationsRead()
      setItems((prev) => prev.map((x) => ({ ...x, read: true })))
      setCount(0)
    } catch {
      /* noop */
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={openPanel}
        className="relative rounded-lg p-2 text-slate-300 transition hover:bg-slate-800"
        aria-label="Notificaciones"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {count > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-xs font-bold text-white">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-50 w-80 max-w-[90vw] overflow-hidden rounded-xl border border-slate-700 bg-[#0f172a] shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5">
            <span className="text-sm font-semibold text-slate-200">Notificaciones</span>
            {items.some((n) => !n.read) && (
              <button onClick={handleAll} className="text-xs font-medium text-blue-400 hover:text-blue-300">
                Marcar todas
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {loading ? (
              <p className="px-4 py-6 text-center text-sm text-slate-400">Cargando…</p>
            ) : items.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-slate-400">Sin notificaciones</p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => handleRead(n)}
                  className={`block w-full border-b border-slate-800/60 px-4 py-3 text-left transition hover:bg-slate-800/50 ${
                    n.read ? 'opacity-60' : ''
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {!n.read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500" />}
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-slate-100">{n.title}</p>
                      {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-slate-400">{n.body}</p>}
                      <p className="mt-1 text-[11px] text-slate-500">{timeAgo(n.created_at)}</p>
                    </div>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}
