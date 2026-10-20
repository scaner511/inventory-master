import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  getCaptureCampaigns,
  createCaptureCampaign,
  updateCaptureCampaign,
  deleteCaptureCampaign,
  getCapturePrizes,
  createCapturePrize,
  updateCapturePrize,
  deleteCapturePrize,
  getCaptureConfig,
  updateCaptureConfig,
  getCaptureSessions,
  startCaptureSession,
  closeCaptureSession,
  generateCaptureLink,
  getUsers,
} from '../api/index.js'
import { useAuth } from '../context/AuthContext.jsx'
import Modal from '../components/ui/Modal.jsx'

const TABS = [
  { key: 'session', label: 'Jornada' },
  { key: 'campaigns', label: 'Campañas' },
  { key: 'prizes', label: 'Ruleta y premios' },
  { key: 'config', label: 'Configuración' },
]

const EMPTY_CAMPAIGN = {
  name: '',
  description: '',
  start_date: '',
  end_date: '',
  status: 'activa',
  observations: '',
}

const EMPTY_PRIZE = {
  name: '',
  description: '',
  color: '#3b82f6',
  probability: 10,
  is_active: true,
  stock: '',
  valid_from: '',
  valid_until: '',
  is_no_prize: false,
}

const STATUS_BADGE = {
  borrador: 'bg-slate-700 text-slate-200',
  activa: 'bg-emerald-600/20 text-emerald-400',
  pausada: 'bg-amber-600/20 text-amber-400',
  finalizada: 'bg-slate-600/30 text-slate-400',
}

export default function CaptureAdmin() {
  const { user } = useAuth()
  const [tab, setTab] = useState('session')

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-slate-100">Captación de prospectos</h2>

      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
              tab === t.key ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'session' && <SessionTab user={user} />}
      {tab === 'campaigns' && <CampaignsTab />}
      {tab === 'prizes' && <PrizesTab />}
      {tab === 'config' && <ConfigTab />}
    </div>
  )
}

/* ---------------------------------------------------------------------- */
function SessionTab({ user }) {
  const [users, setUsers] = useState([])
  const [campaigns, setCampaigns] = useState([])
  const [sessions, setSessions] = useState([])
  const [form, setForm] = useState({ user_id: '', vendor_name: '', campaign_id: '', location: '', observations: '' })
  const [active, setActive] = useState(null) // { session, session_token }
  const [loading, setLoading] = useState(true)

  const refresh = () =>
    Promise.all([getCaptureSessions(), getCaptureCampaigns(), getUsers()])
      .then(([s, c, u]) => {
        setSessions(s)
        setCampaigns(c.filter((x) => x.status === 'activa' || x.status === 'borrador'))
        setUsers(u)
      })
      .catch(() => {})
      .finally(() => setLoading(false))

  useEffect(() => {
    refresh()
  }, [])

  const start = async () => {
    try {
      const payload = {
        user_id: form.user_id ? Number(form.user_id) : null,
        vendor_name: form.vendor_name || null,
        campaign_id: form.campaign_id ? Number(form.campaign_id) : null,
        location: form.location || null,
        observations: form.observations || null,
      }
      const res = await startCaptureSession(payload)
      setActive(res)
      toast.success('Jornada iniciada')
      refresh()
    } catch {
      /* el interceptor muestra el error */
    }
  }

  const close = async (id) => {
    try {
      await closeCaptureSession(id)
      toast.success('Jornada finalizada')
      if (active?.session?.id === id) setActive(null)
      refresh()
    } catch {
      /* noop */
    }
  }

  const openTablet = async () => {
    const vendorId = active?.session?.user_id
    if (!vendorId) return
    try {
      const { capture_token } = await generateCaptureLink(vendorId)
      window.open(`/captacion/tablet?token=${capture_token}`, '_blank')
    } catch {
      /* noop */
    }
  }

  const copyTabletLink = async () => {
    const vendorId = active?.session?.user_id
    if (!vendorId) return
    try {
      const { capture_token } = await generateCaptureLink(vendorId)
      await navigator.clipboard?.writeText(`${window.location.origin}/captacion/tablet?token=${capture_token}`)
      toast.success('Enlace copiado')
    } catch {
      /* noop */
    }
  }

  if (loading) return <p className="py-6 text-sm text-slate-400">Cargando…</p>

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <p className="mb-3 text-sm font-semibold text-slate-200">Iniciar jornada de captación</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs text-slate-400">
            Vendedor
            <select
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100"
              value={form.user_id}
              onChange={(e) => setForm({ ...form, user_id: e.target.value })}
            >
              <option value="">Yo ({user?.username})</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.username}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            Nombre del vendedor (manual, opcional)
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100"
              value={form.vendor_name}
              onChange={(e) => setForm({ ...form, vendor_name: e.target.value })}
              placeholder="Si lo dejas vacío, se usa el usuario elegido"
            />
          </label>
          <label className="text-xs text-slate-400">
            Campaña activa
            <select
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100"
              value={form.campaign_id}
              onChange={(e) => setForm({ ...form, campaign_id: e.target.value })}
            >
              <option value="">Sin campaña</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-400">
            Ubicación
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="Ej. Plaza principal"
            />
          </label>
          <label className="text-xs text-slate-400">
            Observaciones
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100"
              value={form.observations}
              onChange={(e) => setForm({ ...form, observations: e.target.value })}
            />
          </label>
        </div>
        <button
          onClick={start}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          INICIAR JORNADA
        </button>
      </div>

      {active?.session && (
        <div className="rounded-xl border border-emerald-700/50 bg-emerald-900/10 p-4">
          <p className="text-sm font-semibold text-emerald-300">Jornada activa</p>
          <p className="mt-1 text-xs text-slate-400">
            El vendedor tiene un enlace fijo para esta jornada (y las siguientes). Ábrelo o cópialo:
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              onClick={openTablet}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Abrir tablet
            </button>
            <button
              onClick={copyTabletLink}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
            >
              Copiar enlace fijo
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 text-left text-xs uppercase text-slate-400">
            <tr>
              <th className="px-3 py-2">Inicio</th>
              <th className="px-3 py-2">Vendedor</th>
              <th className="px-3 py-2">Campaña</th>
              <th className="px-3 py-2">Ubicación</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {sessions.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                  Sin jornadas registradas
                </td>
              </tr>
            )}
            {sessions.map((s) => (
              <tr key={s.id} className="border-t border-slate-800 text-slate-300">
                <td className="px-3 py-2">{new Date(s.started_at).toLocaleString()}</td>
                <td className="px-3 py-2">{s.user_name || '—'}</td>
                <td className="px-3 py-2">{s.campaign_name || '—'}</td>
                <td className="px-3 py-2">{s.location || '—'}</td>
                <td className="px-3 py-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                      s.status === 'abierta'
                        ? 'bg-emerald-600/20 text-emerald-400'
                        : 'bg-slate-700 text-slate-300'
                    }`}
                  >
                    {s.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  {s.status === 'abierta' && (
                    <button
                      onClick={() => close(s.id)}
                      className="rounded-lg border border-red-700/50 px-3 py-1 text-xs font-semibold text-red-400 hover:bg-red-900/20"
                    >
                      Finalizar
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------------- */
function CampaignsTab() {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_CAMPAIGN)

  const refresh = () => getCaptureCampaigns().then(setRows).catch(() => {})
  useEffect(() => {
    refresh()
  }, [])

  const openNew = () => {
    setEditing(null)
    setForm(EMPTY_CAMPAIGN)
    setOpen(true)
  }
  const openEdit = (c) => {
    setEditing(c)
    setForm({
      name: c.name,
      description: c.description || '',
      start_date: c.start_date || '',
      end_date: c.end_date || '',
      status: c.status,
      observations: c.observations || '',
    })
    setOpen(true)
  }

  const save = async () => {
    const payload = {
      ...form,
      description: form.description || null,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      observations: form.observations || null,
    }
    try {
      if (editing) await updateCaptureCampaign(editing.id, payload)
      else await createCaptureCampaign(payload)
      toast.success('Campaña guardada')
      setOpen(false)
      refresh()
    } catch {
      /* noop */
    }
  }

  const remove = async (c) => {
    if (!window.confirm(`¿Eliminar la campaña "${c.name}"?`)) return
    try {
      await deleteCaptureCampaign(c.id)
      toast.success('Campaña eliminada')
      refresh()
    } catch {
      /* noop */
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button
          onClick={openNew}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          + Nueva campaña
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900/80 text-left text-xs uppercase text-slate-400">
            <tr>
              <th className="px-3 py-2">Nombre</th>
              <th className="px-3 py-2">Inicio</th>
              <th className="px-3 py-2">Fin</th>
              <th className="px-3 py-2">Estado</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} className="border-t border-slate-800 text-slate-300">
                <td className="px-3 py-2 font-medium text-slate-100">{c.name}</td>
                <td className="px-3 py-2">{c.start_date || '—'}</td>
                <td className="px-3 py-2">{c.end_date || '—'}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_BADGE[c.status] || ''}`}>
                    {c.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-right">
                  <button onClick={() => openEdit(c)} className="mr-2 text-xs text-blue-400 hover:underline">
                    Editar
                  </button>
                  <button onClick={() => remove(c)} className="text-xs text-red-400 hover:underline">
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                  Sin campañas
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? 'Editar campaña' : 'Nueva campaña'}>
        <div className="space-y-3">
          <Field label="Nombre">
            <input className={INPUT} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Descripción">
            <textarea
              rows={2}
              className={INPUT}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Fecha inicio">
              <input type="date" className={INPUT} value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
            </Field>
            <Field label="Fecha fin">
              <input type="date" className={INPUT} value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
            </Field>
          </div>
          <Field label="Estado">
            <select className={INPUT} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
              <option value="borrador">Borrador</option>
              <option value="activa">Activa</option>
              <option value="pausada">Pausada</option>
              <option value="finalizada">Finalizada</option>
            </select>
          </Field>
          <Field label="Observaciones">
            <textarea rows={2} className={INPUT} value={form.observations} onChange={(e) => setForm({ ...form, observations: e.target.value })} />
          </Field>
          <button onClick={save} className="w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700">
            Guardar
          </button>
        </div>
      </Modal>
    </div>
  )
}

/* ---------------------------------------------------------------------- */
function PrizesTab() {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_PRIZE)

  const refresh = () => getCapturePrizes().then(setRows).catch(() => {})
  useEffect(() => {
    refresh()
  }, [])

  const openNew = () => {
    setEditing(null)
    setForm(EMPTY_PRIZE)
    setOpen(true)
  }
  const openEdit = (p) => {
    setEditing(p)
    setForm({
      name: p.name,
      description: p.description || '',
      color: p.color || '#3b82f6',
      probability: p.probability,
      is_active: p.is_active,
      stock: p.stock === null || p.stock === undefined ? '' : p.stock,
      valid_from: p.valid_from || '',
      valid_until: p.valid_until || '',
      is_no_prize: p.is_no_prize,
    })
    setOpen(true)
  }

  const save = async () => {
    const payload = {
      name: form.name,
      description: form.description || null,
      color: form.color || null,
      probability: Number(form.probability) || 0,
      is_active: form.is_active,
      stock: form.stock === '' ? null : Number(form.stock),
      valid_from: form.valid_from || null,
      valid_until: form.valid_until || null,
      is_no_prize: form.is_no_prize,
    }
    try {
      if (editing) await updateCapturePrize(editing.id, payload)
      else await createCapturePrize(payload)
      toast.success('Premio guardado')
      setOpen(false)
      refresh()
    } catch {
      /* noop */
    }
  }

  const remove = async (p) => {
    if (!window.confirm(`¿Eliminar "${p.name}"?`)) return
    try {
      await deleteCapturePrize(p.id)
      toast.success('Premio eliminado')
      refresh()
    } catch {
      /* noop */
    }
  }

  const toggleActive = async (p) => {
    try {
      await updateCapturePrize(p.id, { is_active: !p.is_active })
      refresh()
    } catch {
      /* noop */
    }
  }

  const total = rows.reduce((sum, p) => sum + (p.is_active ? p.probability : 0), 0)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-400">
          Peso total activo: <span className="font-semibold text-slate-200">{total}</span>
        </p>
        <button onClick={openNew} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
          + Nuevo premio
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((p) => (
          <div key={p.id} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center gap-2">
              <span className="h-4 w-4 rounded-full" style={{ background: p.color || '#3b82f6' }} />
              <p className="font-semibold text-slate-100">{p.name}</p>
              {p.is_no_prize && <span className="rounded bg-slate-700 px-1.5 text-xs text-slate-300">sin premio</span>}
            </div>
            <p className="mt-1 text-xs text-slate-400">Probabilidad: {p.probability}</p>
            <p className="text-xs text-slate-400">Stock: {p.stock === null ? '∞' : p.stock}</p>
            <div className="mt-3 flex items-center gap-3 text-xs">
              <button onClick={() => toggleActive(p)} className={p.is_active ? 'text-emerald-400' : 'text-slate-500'}>
                {p.is_active ? '● Activo' : '○ Pausado'}
              </button>
              <button onClick={() => openEdit(p)} className="text-blue-400 hover:underline">
                Editar
              </button>
              <button onClick={() => remove(p)} className="text-red-400 hover:underline">
                Eliminar
              </button>
            </div>
          </div>
        ))}
        {rows.length === 0 && (
          <p className="col-span-full py-6 text-center text-slate-500">Sin premios configurados</p>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title={editing ? 'Editar premio' : 'Nuevo premio'}>
        <div className="space-y-3">
          <Field label="Nombre">
            <input className={INPUT} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Descripción">
            <textarea rows={2} className={INPUT} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Probabilidad">
              <input type="number" className={INPUT} value={form.probability} onChange={(e) => setForm({ ...form, probability: e.target.value })} />
            </Field>
            <Field label="Stock (vacío = ∞)">
              <input type="number" className={INPUT} value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} />
            </Field>
            <Field label="Color">
              <input type="color" className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-800" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Vigente desde">
              <input type="date" className={INPUT} value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
            </Field>
            <Field label="Vigente hasta">
              <input type="date" className={INPUT} value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            Activo en la ruleta
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={form.is_no_prize} onChange={(e) => setForm({ ...form, is_no_prize: e.target.checked })} />
            Es "sin premio" (no descuenta stock)
          </label>
          <button onClick={save} className="w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white hover:bg-blue-700">
            Guardar
          </button>
        </div>
      </Modal>
    </div>
  )
}

/* ---------------------------------------------------------------------- */
function ConfigTab() {
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getCaptureConfig().then(setForm).catch(() => {})
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await updateCaptureConfig({
        duplicate_action: form.duplicate_action,
        no_prize_message: form.no_prize_message,
      })
      toast.success('Configuración guardada')
    } catch {
      /* noop */
    } finally {
      setSaving(false)
    }
  }

  if (!form) return <p className="py-6 text-sm text-slate-400">Cargando…</p>

  return (
    <div className="max-w-lg space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <Field label="Cuando el teléfono ya existe">
        <select
          className={INPUT}
          value={form.duplicate_action}
          onChange={(e) => setForm({ ...form, duplicate_action: e.target.value })}
        >
          <option value="actualizar">Actualizar el prospecto existente</option>
          <option value="nueva_interaccion">Registrar nueva interacción</option>
          <option value="bloquear">Bloquear (no permitir duplicados)</option>
        </select>
      </Field>
      <Field label="Mensaje de 'sin premio'">
        <input
          className={INPUT}
          value={form.no_prize_message}
          onChange={(e) => setForm({ ...form, no_prize_message: e.target.value })}
        />
      </Field>
      <button
        onClick={save}
        disabled={saving}
        className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {saving ? 'Guardando…' : 'Guardar configuración'}
      </button>
    </div>
  )
}

/* ---------------------------------------------------------------------- */
const INPUT =
  'mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-blue-500 focus:outline-none'

function Field({ label, children }) {
  return (
    <label className="block text-xs text-slate-400">
      {label}
      {children}
    </label>
  )
}
