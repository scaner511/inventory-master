import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  closeAppointment,
  createAppointment,
  deleteAppointment,
  getAppointmentClosure,
  getAppointments,
  getProspects,
  getUsers,
  updateAppointment,
} from '../api/index.js'
import { useAuth } from '../context/AuthContext.jsx'
import { API_BASE, openAuthenticatedUrl } from '../api/client.js'
import Modal from '../components/ui/Modal.jsx'
import { Button, Field, Input, Select, Textarea } from '../components/ui/Form.jsx'

const REMINDER_OPTIONS = [
  { value: 15, label: '15 minutos antes' },
  { value: 30, label: '30 minutos antes' },
  { value: 60, label: '1 hora antes' },
  { value: 120, label: '2 horas antes' },
  { value: 240, label: '4 horas antes' },
  { value: 480, label: '8 horas antes' },
  { value: 1440, label: '24 horas antes' },
]

const APPT_STATUS = {
  programada: { label: 'Programada', cls: 'bg-blue-500/15 text-blue-300 border-blue-500/40' },
  confirmada: { label: 'Confirmada', cls: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/40' },
  en_proceso: { label: 'En proceso', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
  completada: { label: 'Completada', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
  cancelada: { label: 'Cancelada', cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
  reagendada: { label: 'Reagendada', cls: 'bg-violet-500/15 text-violet-300 border-violet-500/40' },
}

const RESULT_OPTIONS = [
  { value: 'venta_realizada', label: 'Venta realizada' },
  { value: 'interesado', label: 'Interesado' },
  { value: 'requiere_seguimiento', label: 'Requiere seguimiento' },
  { value: 'pendiente_decision', label: 'Pendiente de decisión' },
  { value: 'solicito_propuesta', label: 'Solicitó propuesta' },
  { value: 'solicito_demostracion', label: 'Solicitó demostración' },
  { value: 'no_interesado', label: 'No interesado' },
  { value: 'no_estaba', label: 'No estaba / no atendió' },
  { value: 'reagendar', label: 'Reagendar' },
]

function pad(n) {
  return String(n).padStart(2, '0')
}
function toDateKey(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function startOfWeek(d) {
  const x = new Date(d)
  const day = (x.getDay() + 6) % 7 // lunes = 0
  x.setDate(x.getDate() - day)
  x.setHours(0, 0, 0, 0)
  return x
}
function addDays(d, n) {
  const x = new Date(d)
  x.setDate(x.getDate() + n)
  return x
}
function hhmm(iso) {
  const d = new Date(iso)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function toLocalInput(iso) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function Calendar() {
  const { user } = useAuth()
  const [view, setView] = useState('month')
  const [cursor, setCursor] = useState(() => new Date())
  const [appts, setAppts] = useState([])
  const [prospects, setProspects] = useState([])
  const [users, setUsers] = useState([])
  const [userFilter, setUserFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(null)
  const [closureAppt, setClosureAppt] = useState(null)
  const [closureForm, setClosureForm] = useState(null)

  const range = useMemo(() => {
    if (view === 'day') {
      const d = new Date(cursor)
      d.setHours(0, 0, 0, 0)
      return { from: d, to: d }
    }
    if (view === 'week') {
      const from = startOfWeek(cursor)
      return { from, to: addDays(from, 6) }
    }
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
    const from = startOfWeek(first)
    const last = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0)
    return { from, to: addDays(startOfWeek(last), 6) }
  }, [view, cursor])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getAppointments({
        dateFrom: toDateKey(range.from),
        dateTo: toDateKey(range.to),
        userId: userFilter,
      })
      setAppts(data)
    } catch {
      toast.error('No se pudieron cargar las citas')
    } finally {
      setLoading(false)
    }
  }, [range.from, range.to, userFilter])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    getProspects().then(setProspects).catch(() => {})
    getUsers().then(setUsers).catch(() => {})
  }, [])

  const prospectName = useCallback(
    (id) => prospects.find((p) => p.id === id)?.full_name || `Prospecto #${id}`,
    [prospects]
  )

  function openCreate(dateKey, hour = 9) {
    setEditing(null)
    const start = `${dateKey}T${pad(hour)}:00`
    setForm({
      prospect_id: '', start_at: start, end_at: '',
      user_id: user?.id || '', address: '', phone: '',
      observation: '', status: 'programada', reminder_minutes: [60],
    })
    setModalOpen(true)
  }

  function openEdit(appt) {
    setEditing(appt)
    setForm({
      prospect_id: appt.prospect_id,
      start_at: toLocalInput(appt.start_at),
      end_at: appt.end_at ? toLocalInput(appt.end_at) : '',
      user_id: appt.user_id || '',
      address: appt.address || '',
      phone: appt.phone || '',
      observation: appt.observation || '',
      status: appt.status,
      reminder_minutes: [],
    })
    setModalOpen(true)
  }

  async function save(e) {
    e.preventDefault()
    if (!form.prospect_id) return toast.error('Selecciona un prospecto')
    const payload = {
      prospect_id: Number(form.prospect_id),
      start_at: new Date(form.start_at).toISOString().slice(0, 19),
      end_at: form.end_at ? new Date(form.end_at).toISOString().slice(0, 19) : null,
      user_id: form.user_id ? Number(form.user_id) : null,
      address: form.address, phone: form.phone, observation: form.observation,
      status: form.status,
      reminder_minutes: form.reminder_minutes,
    }
    try {
      if (editing) {
        await updateAppointment(editing.id, { ...payload, reschedule: form.start_at !== toLocalInput(editing.start_at) })
        toast.success('Cita actualizada')
      } else {
        await createAppointment(payload)
        toast.success('Cita creada')
      }
      setModalOpen(false)
      load()
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al guardar la cita')
    }
  }

  async function remove(appt) {
    if (!window.confirm('¿Cancelar esta cita?')) return
    try {
      await deleteAppointment(appt.id)
      toast.success('Cita cancelada')
      setModalOpen(false)
      load()
    } catch {
      toast.error('No se pudo cancelar')
    }
  }

  async function onDrop(e, dateKey, hour) {
    e.preventDefault()
    const id = Number(e.dataTransfer.getData('text/appt'))
    const appt = appts.find((a) => a.id === id)
    if (!appt) return
    const dur = appt.end_at
      ? new Date(appt.end_at).getTime() - new Date(appt.start_at).getTime()
      : 3600000
    const newStart = new Date(`${dateKey}T${pad(hour)}:00:00`)
    const newEnd = new Date(newStart.getTime() + dur)
    try {
      await updateAppointment(appt.id, {
        start_at: newStart.toISOString().slice(0, 19),
        end_at: newEnd.toISOString().slice(0, 19),
        reschedule: true,
      })
      toast.success('Cita reagendada')
      load()
    } catch {
      toast.error('No se pudo reagendar')
    }
  }

  function openClosure(appt) {
    setClosureAppt(appt)
    setClosureForm({
      visit_date: toDateKey(new Date(appt.start_at)),
      arrival_time: hhmm(appt.start_at),
      departure_time: appt.end_at ? hhmm(appt.end_at) : '',
      result: 'interesado', result_detail: '', markers: [],
      interest_level: 3, demo_done: false, demo_description: '',
      interest_products: [], delivered_info: [], commercial_status: '',
      next_followup_at: '', next_followup_kind: 'llamada', next_followup_observation: '',
      convert: false,
      has_budget: '', is_decision_maker: '', close_probability: 50,
      monthly_value: '', setup_value: '',
      lost_reason: '', lost_reason_detail: '',
    })
  }

  async function saveClosure(e) {
    e.preventDefault()
    if (!closureForm.result_detail.trim()) return toast.error('Describe el resultado de la visita')
    const payload = {
      ...closureForm,
      close_probability: Number(closureForm.close_probability),
      monthly_value: closureForm.monthly_value === '' ? null : Number(closureForm.monthly_value),
      setup_value: closureForm.setup_value === '' ? null : Number(closureForm.setup_value),
      has_budget: closureForm.has_budget || null,
      is_decision_maker: closureForm.is_decision_maker || null,
      lost_reason: closureForm.lost_reason || null,
      lost_reason_detail: closureForm.lost_reason_detail || null,
      next_followup_at: closureForm.next_followup_at
        ? new Date(closureForm.next_followup_at).toISOString().slice(0, 19)
        : null,
    }
    try {
      await closeAppointment(closureAppt.id, payload)
      toast.success('Cierre de visita guardado')
      setClosureAppt(null)
      load()
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Error al guardar el cierre')
    }
  }

  async function viewClosure(appt) {
    try {
      const c = await getAppointmentClosure(appt.id)
      toast.success(`Cierre: ${c.result.replace('_', ' ')} · ${c.total_minutes || '—'} min`)
    } catch {
      openClosure(appt)
    }
  }

  const title = useMemo(() => {
    const meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
    if (view === 'day') return `${cursor.getDate()} de ${meses[cursor.getMonth()]} ${cursor.getFullYear()}`
    if (view === 'week') {
      const f = startOfWeek(cursor)
      const t = addDays(f, 6)
      return `${f.getDate()} ${meses[f.getMonth()].slice(0, 3)} – ${t.getDate()} ${meses[t.getMonth()].slice(0, 3)} ${t.getFullYear()}`
    }
    return `${meses[cursor.getMonth()]} ${cursor.getFullYear()}`
  }, [view, cursor])

  function move(dir) {
    const x = new Date(cursor)
    if (view === 'day') x.setDate(x.getDate() + dir)
    else if (view === 'week') x.setDate(x.getDate() + dir * 7)
    else x.setMonth(x.getMonth() + dir)
    setCursor(x)
  }

  const byDay = useMemo(() => {
    const map = {}
    for (const a of appts) {
      const k = toDateKey(new Date(a.start_at))
      ;(map[k] ||= []).push(a)
    }
    return map
  }, [appts])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-bold text-slate-100">Calendario comercial</h2>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Select value={userFilter} onChange={(e) => setUserFilter(e.target.value)} className="w-48">
            <option value="">Todos los usuarios</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.username}</option>
            ))}
          </Select>
          <div className="flex overflow-hidden rounded-lg border border-slate-700">
            {['day', 'week', 'month'].map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-2 text-sm font-medium transition ${view === v ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}
              >
                {v === 'day' ? 'Día' : v === 'week' ? 'Semana' : 'Mes'}
              </button>
            ))}
          </div>
          <Button variant="ghost" onClick={() => move(-1)}>‹</Button>
          <Button variant="ghost" onClick={() => setCursor(new Date())}>Hoy</Button>
          <Button variant="ghost" onClick={() => move(1)}>›</Button>
          <Button variant="ghost" onClick={() => openAuthenticatedUrl(`${API_BASE}/appointments/export/excel`)}>Excel</Button>
          <Button variant="ghost" onClick={() => openAuthenticatedUrl(`${API_BASE}/appointments/export/csv`)}>CSV</Button>
          <Button onClick={() => openCreate(toDateKey(cursor))}>+ Nueva cita</Button>
        </div>
      </div>

      <p className="text-sm font-semibold capitalize text-slate-300">{title}</p>

      {loading ? (
        <p className="py-10 text-center text-sm text-slate-400">Cargando…</p>
      ) : view === 'month' ? (
        <MonthGrid range={range} byDay={byDay} prospectName={prospectName} onDrop={onDrop} onOpen={openEdit} onAdd={openCreate} />
      ) : view === 'week' ? (
        <WeekGrid range={range} byDay={byDay} prospectName={prospectName} onDrop={onDrop} onOpen={openEdit} onAdd={openCreate} />
      ) : (
        <DayView date={cursor} items={byDay[toDateKey(cursor)] || []} prospectName={prospectName} onDrop={onDrop} onOpen={openEdit} onAdd={openCreate} />
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Editar cita' : 'Nueva cita'} wide>
        {form && (
          <form onSubmit={save} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Field label="Prospecto">
                <Select value={form.prospect_id} onChange={(e) => setForm({ ...form, prospect_id: e.target.value })} required>
                  <option value="">Selecciona…</option>
                  {prospects.map((p) => (
                    <option key={p.id} value={p.id}>{p.full_name}{p.phone ? ` · ${p.phone}` : ''}</option>
                  ))}
                </Select>
              </Field>
            </div>
            <Field label="Inicio">
              <Input type="datetime-local" value={form.start_at} onChange={(e) => setForm({ ...form, start_at: e.target.value })} required />
            </Field>
            <Field label="Fin (opcional)">
              <Input type="datetime-local" value={form.end_at} onChange={(e) => setForm({ ...form, end_at: e.target.value })} />
            </Field>
            <Field label="Responsable">
              <Select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })}>
                <option value="">Yo</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.username}</option>
                ))}
              </Select>
            </Field>
            <Field label="Estado">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {Object.entries(APPT_STATUS).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Dirección">
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </Field>
            <Field label="Teléfono">
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Observaciones">
                <Textarea value={form.observation} onChange={(e) => setForm({ ...form, observation: e.target.value })} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">Recordatorios</span>
              <div className="flex flex-wrap gap-2">
                {REMINDER_OPTIONS.map((o) => (
                  <label key={o.value} className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200">
                    <input
                      type="checkbox"
                      checked={form.reminder_minutes.includes(o.value)}
                      onChange={(e) => {
                        const set = new Set(form.reminder_minutes)
                        e.target.checked ? set.add(o.value) : set.delete(o.value)
                        setForm({ ...form, reminder_minutes: [...set] })
                      }}
                    />
                    {o.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 sm:col-span-2">
              {editing && <Button type="button" variant="danger" onClick={() => remove(editing)}>Cancelar cita</Button>}
              {editing && editing.status !== 'completada' && (
                <Button type="button" variant="success" onClick={() => { setModalOpen(false); openClosure(editing) }}>
                  Cerrar visita
                </Button>
              )}
              {editing && editing.status === 'completada' && (
                <Button type="button" variant="ghost" onClick={() => viewClosure(editing)}>Ver cierre</Button>
              )}
              <Button type="submit">Guardar</Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={!!closureAppt} onClose={() => setClosureAppt(null)} title="Cierre de visita" wide>
        {closureForm && (
          <form onSubmit={saveClosure} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Fecha de visita">
              <Input type="date" value={closureForm.visit_date} onChange={(e) => setClosureForm({ ...closureForm, visit_date: e.target.value })} required />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Hora llegada">
                <Input type="time" value={closureForm.arrival_time} onChange={(e) => setClosureForm({ ...closureForm, arrival_time: e.target.value })} />
              </Field>
              <Field label="Hora salida">
                <Input type="time" value={closureForm.departure_time} onChange={(e) => setClosureForm({ ...closureForm, departure_time: e.target.value })} />
              </Field>
            </div>
            <Field label="Resultado">
              <Select value={closureForm.result} onChange={(e) => setClosureForm({ ...closureForm, result: e.target.value })}>
                {RESULT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Nivel de interés (1-5)">
              <Select value={closureForm.interest_level} onChange={(e) => setClosureForm({ ...closureForm, interest_level: Number(e.target.value) })}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Detalle del resultado (obligatorio)">
                <Textarea value={closureForm.result_detail} onChange={(e) => setClosureForm({ ...closureForm, result_detail: e.target.value })} required />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={closureForm.demo_done} onChange={(e) => setClosureForm({ ...closureForm, demo_done: e.target.checked })} />
                Se realizó demostración
              </label>
              {closureForm.demo_done && (
                <Textarea className="mt-2" placeholder="Descripción de la demo" value={closureForm.demo_description} onChange={(e) => setClosureForm({ ...closureForm, demo_description: e.target.value })} />
              )}
            </div>

            <Field label="¿Tiene presupuesto?">
              <Select value={closureForm.has_budget} onChange={(e) => setClosureForm({ ...closureForm, has_budget: e.target.value })}>
                <option value="">—</option>
                <option value="si">Sí</option>
                <option value="no">No</option>
                <option value="desconocido">Desconocido</option>
              </Select>
            </Field>
            <Field label="¿Es quien decide?">
              <Select value={closureForm.is_decision_maker} onChange={(e) => setClosureForm({ ...closureForm, is_decision_maker: e.target.value })}>
                <option value="">—</option>
                <option value="si">Sí</option>
                <option value="no">No</option>
                <option value="debe_consultar">Debe consultar</option>
              </Select>
            </Field>
            <Field label="Valor mensual (USD)">
              <Input type="number" min="0" step="0.01" value={closureForm.monthly_value} onChange={(e) => setClosureForm({ ...closureForm, monthly_value: e.target.value })} />
            </Field>
            <Field label="Valor instalación (USD)">
              <Input type="number" min="0" step="0.01" value={closureForm.setup_value} onChange={(e) => setClosureForm({ ...closureForm, setup_value: e.target.value })} />
            </Field>
            <div className="sm:col-span-2">
              <Field label={`Probabilidad de cierre: ${closureForm.close_probability}%`}>
                <input
                  type="range" min="0" max="100" step="5" value={closureForm.close_probability}
                  onChange={(e) => setClosureForm({ ...closureForm, close_probability: Number(e.target.value) })}
                  className="w-full accent-blue-500"
                />
              </Field>
            </div>

            <Field label="Estado comercial">
              <Select value={closureForm.commercial_status} onChange={(e) => setClosureForm({ ...closureForm, commercial_status: e.target.value })}>
                <option value="">—</option>
                <option value="interesado">Interesado</option>
                <option value="cliente_potencial">Cliente potencial</option>
                <option value="propuesta_enviada">Propuesta enviada</option>
                <option value="negociacion">Negociación</option>
                <option value="cliente_convertido">Cliente convertido</option>
                <option value="no_interesado">No interesado</option>
              </Select>
            </Field>
            <Field label="Motivo de no compra">
              <Select value={closureForm.lost_reason} onChange={(e) => setClosureForm({ ...closureForm, lost_reason: e.target.value })}>
                <option value="">—</option>
                <option value="precio">Precio</option>
                <option value="sin_presupuesto">Sin presupuesto</option>
                <option value="no_necesita">No lo necesita</option>
                <option value="compro_competencia">Compró a la competencia</option>
                <option value="no_decision">No es quien decide</option>
                <option value="otro">Otro</option>
              </Select>
            </Field>
            {closureForm.lost_reason && (
              <div className="sm:col-span-2">
                <Field label="Detalle del motivo">
                  <Textarea value={closureForm.lost_reason_detail} onChange={(e) => setClosureForm({ ...closureForm, lost_reason_detail: e.target.value })} />
                </Field>
              </div>
            )}

            <div className="sm:col-span-2">
              <Field label="Próximo seguimiento (fecha/hora)">
                <Input type="datetime-local" value={closureForm.next_followup_at} onChange={(e) => setClosureForm({ ...closureForm, next_followup_at: e.target.value })} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input type="checkbox" checked={closureForm.convert} onChange={(e) => setClosureForm({ ...closureForm, convert: e.target.checked })} />
                Convertir en cliente
              </label>
            </div>
            <div className="flex justify-end gap-2 sm:col-span-2">
              <Button type="button" variant="ghost" onClick={() => setClosureAppt(null)}>Cancelar</Button>
              <Button type="submit" variant="success">Guardar cierre</Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}

function StatusPill({ status }) {
  const meta = APPT_STATUS[status] || APPT_STATUS.programada
  return <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold ${meta.cls}`}>{meta.label}</span>
}

function MonthGrid({ range, byDay, prospectName, onDrop, onOpen, onAdd }) {
  const days = []
  for (let d = new Date(range.from); d <= range.to; d = addDays(d, 1)) days.push(new Date(d))
  const today = toDateKey(new Date())
  return (
    <div className="overflow-hidden rounded-xl border border-slate-800">
      <div className="grid grid-cols-7 bg-slate-900/60 text-center text-xs font-semibold uppercase text-slate-400">
        {['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'].map((d) => <div key={d} className="py-2">{d}</div>)}
      </div>
      <div className="grid grid-cols-7">
        {days.map((d) => {
          const key = toDateKey(d)
          const items = byDay[key] || []
          const outMonth = d.getMonth() !== range.from.getMonth() && d.getMonth() !== range.to.getMonth()
          return (
            <div
              key={key}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDrop(e, key, 9)}
              onDoubleClick={() => onAdd(key)}
              className={`min-h-24 border-b border-r border-slate-800 p-1.5 ${outMonth ? 'opacity-40' : ''} ${key === today ? 'bg-blue-500/5' : ''}`}
            >
              <div className="mb-1 text-xs font-semibold text-slate-400">{d.getDate()}</div>
              <div className="space-y-1">
                {items.map((a) => (
                  <div
                    key={a.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData('text/appt', String(a.id))}
                    onClick={() => onOpen(a)}
                    className="cursor-pointer rounded bg-slate-800 px-1.5 py-1 text-[11px] text-slate-200 hover:bg-slate-700"
                  >
                    <span className="font-semibold">{hhmm(a.start_at)}</span> {prospectName(a.prospect_id)}
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function WeekGrid({ range, byDay, prospectName, onDrop, onOpen, onAdd }) {
  const days = []
  for (let i = 0; i < 7; i++) days.push(addDays(range.from, i))
  const hours = Array.from({ length: 13 }, (_, i) => i + 7)
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <div className="grid min-w-[720px] grid-cols-[60px_repeat(7,1fr)]">
        <div />
        {days.map((d) => (
          <div key={toDateKey(d)} className="border-b border-l border-slate-800 bg-slate-900/60 py-2 text-center text-xs font-semibold text-slate-300">
            {['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][(d.getDay() + 6) % 7]} {d.getDate()}
          </div>
        ))}
        {hours.map((h) => (
          <div key={h} className="contents">
            <div className="border-b border-slate-800 px-1 py-1 text-right text-[11px] text-slate-500">{pad(h)}:00</div>
            {days.map((d) => {
              const key = toDateKey(d)
              const items = (byDay[key] || []).filter((a) => new Date(a.start_at).getHours() === h)
              return (
                <div
                  key={`${key}-${h}`}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => onDrop(e, key, h)}
                  onDoubleClick={() => onAdd(key, h)}
                  className="min-h-12 border-b border-l border-slate-800 p-0.5"
                >
                  {items.map((a) => (
                    <div
                      key={a.id}
                      draggable
                      onDragStart={(e) => e.dataTransfer.setData('text/appt', String(a.id))}
                      onClick={() => onOpen(a)}
                      className="cursor-pointer rounded bg-blue-600/70 px-1 py-0.5 text-[10px] text-white hover:bg-blue-500"
                      title={prospectName(a.prospect_id)}
                    >
                      {hhmm(a.start_at)} {prospectName(a.prospect_id)}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

function DayView({ items, prospectName, onDrop, onOpen, onAdd, date }) {
  const key = toDateKey(date)
  const hours = Array.from({ length: 15 }, (_, i) => i + 7)
  return (
    <div className="rounded-xl border border-slate-800">
      {hours.map((h) => {
        const at = items.filter((a) => new Date(a.start_at).getHours() === h)
        return (
          <div
            key={h}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => onDrop(e, key, h)}
            onDoubleClick={() => onAdd(key, h)}
            className="flex min-h-14 items-stretch border-b border-slate-800 last:border-b-0"
          >
            <div className="w-16 shrink-0 border-r border-slate-800 px-2 py-1 text-right text-xs text-slate-500">{pad(h)}:00</div>
            <div className="flex flex-1 flex-wrap items-center gap-2 p-1.5">
              {at.map((a) => (
                <div
                  key={a.id}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData('text/appt', String(a.id))}
                  onClick={() => onOpen(a)}
                  className="cursor-pointer rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-100 hover:bg-slate-700"
                >
                  <span className="font-semibold">{hhmm(a.start_at)}</span> · {prospectName(a.prospect_id)}
                  <span className="ml-2"><StatusPill status={a.status} /></span>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
