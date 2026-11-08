import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  addProspectActivity,
  addProspectNote,
  convertProspect,
  createProspect,
  deleteProspect,
  deleteProspectFile,
  getOpportunitySummary,
  getProspectActivities,
  getProspectBoard,
  getProspectFiles,
  getProspectHistory,
  getProspectNotes,
  getProspectSignatures,
  getProspects,
  moveProspect,
  saveProspectSignature,
  updateProspect,
  uploadProspectFile,
} from '../api/index.js'
import { openAuthenticatedUrl, API_BASE, formatMoney } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import { Button, Field, Input, Select, Textarea } from '../components/ui/Form.jsx'

const STATUS_META = {
  nuevo: { label: 'Nuevo', cls: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  contactado: { label: 'Contactado', cls: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30' },
  interesado: { label: 'Interesado', cls: 'bg-violet-500/10 text-violet-400 border-violet-500/30' },
  pendiente_cita: { label: 'Pendiente de cita', cls: 'bg-sky-500/10 text-sky-400 border-sky-500/30' },
  visitado: { label: 'Visitado', cls: 'bg-teal-500/10 text-teal-400 border-teal-500/30' },
  cliente_potencial: { label: 'Cliente potencial', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/30' },
  cliente_convertido: { label: 'Cliente convertido', cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' },
  no_interesado: { label: 'No interesado', cls: 'bg-red-500/10 text-red-400 border-red-500/30' },
}

const ACTIVITY_KINDS = {
  llamada: 'Llamada', whatsapp: 'WhatsApp', correo: 'Correo',
  visita: 'Visita', videollamada: 'Videollamada', otro: 'Otro',
}

const PRODUCTS = ['inventory_master', 'inventario', 'prestamos', 'deposito_temporal', 'crm_comercial', 'otro']

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.nuevo
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${meta.cls}`}>
      {meta.label}
    </span>
  )
}

function Stars({ value, onChange, readOnly = false }) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          disabled={readOnly}
          onClick={() => onChange && onChange(n)}
          className={`text-lg leading-none ${n <= value ? 'text-amber-400' : 'text-slate-600'} ${readOnly ? '' : 'hover:text-amber-300'}`}
          title={`${n} estrella${n > 1 ? 's' : ''}`}
        >
          ★
        </button>
      ))}
    </div>
  )
}

const EMPTY_FORM = {
  full_name: '', phone: '', address: '', marital_status: '', occupation: '', prospector_name: '', knows_brand: '',
  notes: '', status: 'nuevo', rating: 3, stage_slug: 'nuevo',
  has_budget: '', is_decision_maker: '', close_probability: 0,
  monthly_value: '', setup_value: '', interested_products: [],
}

export default function Prospects() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  const [tab, setTab] = useState('list')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [rating, setRating] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const [detail, setDetail] = useState(null)
  const [notes, setNotes] = useState([])
  const [activities, setActivities] = useState([])
  const [history, setHistory] = useState([])
  const [newNote, setNewNote] = useState('')
  const [activityForm, setActivityForm] = useState({ kind: 'llamada', scheduled_at: '', observation: '', result: '', status: 'pendiente' })
  const [files, setFiles] = useState([])
  const [signatures, setSignatures] = useState([])
  const [sigRole, setSigRole] = useState('cliente')
  const [uploading, setUploading] = useState(false)

  const [board, setBoard] = useState(null)
  const [dragging, setDragging] = useState(null)
  const [summary, setSummary] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setRows(await getProspects({ q, status, rating }))
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [q, status, rating])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  const loadBoard = useCallback(async () => {
    try {
      const [b, s] = await Promise.all([getProspectBoard(), getOpportunitySummary()])
      setBoard(b)
      setSummary(s)
    } catch {
      /* interceptor */
    }
  }, [])

  useEffect(() => {
    if (tab === 'board') loadBoard()
  }, [tab, loadBoard])

  function openCreate() {
    setEditing(null)
    setForm({ ...EMPTY_FORM })
    setModalOpen(true)
  }

  function openEdit(p) {
    setEditing(p)
    setForm({
      full_name: p.full_name, phone: p.phone || '', address: p.address || '',
      marital_status: p.marital_status || '', occupation: p.occupation || '', prospector_name: p.prospector_name || '', knows_brand: p.knows_brand === true ? 'si' : p.knows_brand === false ? 'no' : '',
      notes: p.notes || '', status: p.status, rating: p.rating, stage_slug: p.stage_slug,
      has_budget: p.has_budget || '', is_decision_maker: p.is_decision_maker || '',
      close_probability: p.close_probability, monthly_value: p.monthly_value || '',
      setup_value: p.setup_value || '', interested_products: p.interested_products || [],
    })
    setModalOpen(true)
  }

  async function handleSave(e) {
    e.preventDefault()
    if (!form.full_name.trim()) return toast.error('Indica el nombre completo')
    const payload = {
      full_name: form.full_name.trim(),
      phone: form.phone.trim() || null,
      address: form.address.trim() || null,
      marital_status: form.marital_status.trim() || null,
      occupation: form.occupation.trim() || null,
      prospector_name: form.prospector_name.trim() || null,
      knows_brand: form.knows_brand === 'si' ? true : form.knows_brand === 'no' ? false : null,
      notes: form.notes.trim() || null,
      status: form.status,
      rating: Number(form.rating),
      stage_slug: form.stage_slug,
      has_budget: form.has_budget || null,
      is_decision_maker: form.is_decision_maker || null,
      close_probability: Number(form.close_probability),
      monthly_value: Number(form.monthly_value) || 0,
      setup_value: Number(form.setup_value) || 0,
      interested_products: form.interested_products,
    }
    setSaving(true)
    try {
      if (editing) {
        await updateProspect(editing.id, payload)
        toast.success('Prospecto actualizado')
      } else {
        await createProspect(payload)
        toast.success('Prospecto registrado')
      }
      setModalOpen(false)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  function openDetail(p) {
    setDetail(p)
    setNotes([]); setActivities([]); setHistory([]); setFiles([]); setSignatures([])
    getProspectNotes(p.id).then(setNotes).catch(() => {})
    getProspectActivities(p.id).then(setActivities).catch(() => {})
    getProspectHistory(p.id).then(setHistory).catch(() => {})
    getProspectFiles(p.id).then(setFiles).catch(() => {})
    getProspectSignatures(p.id).then(setSignatures).catch(() => {})
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadProspectFile(detail.id, file)
      setFiles(await getProspectFiles(detail.id))
      setHistory(await getProspectHistory(detail.id))
      toast.success('Evidencia adjuntada')
    } catch {
      /* interceptor */
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function handleDeleteFile(fileId) {
    if (!window.confirm('¿Eliminar esta evidencia?')) return
    try {
      await deleteProspectFile(fileId)
      setFiles(await getProspectFiles(detail.id))
      toast.success('Evidencia eliminada')
    } catch {
      /* interceptor */
    }
  }

  async function handleSaveSignature() {
    const canvas = document.getElementById('signature-pad')
    if (!canvas) return
    const dataUrl = canvas.toDataURL('image/png')
    try {
      await saveProspectSignature(detail.id, sigRole, dataUrl)
      setSignatures(await getProspectSignatures(detail.id))
      setHistory(await getProspectHistory(detail.id))
      clearSignature()
      toast.success('Firma guardada')
    } catch {
      /* interceptor */
    }
  }

  function clearSignature() {
    const canvas = document.getElementById('signature-pad')
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }

  async function handleAddNote() {
    if (!newNote.trim()) return
    try {
      await addProspectNote(detail.id, newNote.trim())
      setNewNote('')
      setNotes(await getProspectNotes(detail.id))
      setHistory(await getProspectHistory(detail.id))
    } catch {
      /* interceptor */
    }
  }

  async function handleAddActivity(e) {
    e.preventDefault()
    try {
      await addProspectActivity(detail.id, {
        kind: activityForm.kind,
        scheduled_at: activityForm.scheduled_at ? new Date(activityForm.scheduled_at).toISOString() : null,
        observation: activityForm.observation.trim() || null,
        result: activityForm.result.trim() || null,
        status: activityForm.status,
      })
      setActivityForm({ kind: 'llamada', scheduled_at: '', observation: '', result: '', status: 'pendiente' })
      setActivities(await getProspectActivities(detail.id))
      setHistory(await getProspectHistory(detail.id))
      toast.success('Seguimiento registrado')
    } catch {
      /* interceptor */
    }
  }

  async function handleConvert() {
    if (!window.confirm('¿Convertir este prospecto en cliente?')) return
    try {
      const updated = await convertProspect(detail.id)
      toast.success('Prospecto convertido en cliente')
      setDetail(updated)
      setHistory(await getProspectHistory(detail.id))
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleDelete(p) {
    if (!window.confirm(`¿Eliminar el prospecto "${p.full_name}"?`)) return
    try {
      await deleteProspect(p.id)
      toast.success('Prospecto eliminado')
      load()
    } catch {
      /* interceptor */
    }
  }

  /* Kanban drag & drop */
  function onDrop(stageSlug) {
    if (!dragging) return
    const moved = dragging
    setDragging(null)
    setBoard((b) => {
      if (!b) return b
      const columns = { ...b.columns }
      for (const key of Object.keys(columns)) {
        columns[key] = columns[key].filter((p) => p.id !== moved.id)
      }
      columns[stageSlug] = [{ ...moved, stage_slug: stageSlug }, ...(columns[stageSlug] || [])]
      return { ...b, columns }
    })
    moveProspect(moved.id, stageSlug)
      .then(() => {
        toast.success('Etapa actualizada')
        loadBoard()
      })
      .catch(() => loadBoard())
  }

  const columns = [
    { key: 'name', label: 'Prospecto' },
    { key: 'phone', label: 'Teléfono' },
    { key: 'prospector', label: 'Prospectado por' },
    { key: 'status', label: 'Estado', align: 'center' },
    { key: 'rating', label: 'Calificación', align: 'center' },
    { key: 'value', label: 'Oportunidad' },
    { key: 'actions', label: 'Acciones', align: 'center' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-100">Gestión de Prospectos</h2>
          <p className="text-sm text-slate-400">Proceso comercial: contacto, seguimiento y conversión.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => openAuthenticatedUrl(`${API_BASE}/prospects/export/excel`)}>Excel</Button>
          <Button onClick={openCreate}>+ Nuevo prospecto</Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-800">
        {[['list', 'Prospectos'], ['board', 'Embudo / Kanban']].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-semibold transition ${
              tab === key ? 'border-b-2 border-blue-500 text-blue-400' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'list' && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Input placeholder="Buscar por nombre, teléfono o dirección..." value={q} onChange={(e) => setQ(e.target.value)} />
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Todos los estados</option>
              {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </Select>
            <Select value={rating} onChange={(e) => setRating(e.target.value)}>
              <option value="">Todas las calificaciones</option>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{'★'.repeat(n)}</option>)}
            </Select>
          </div>

          {loading ? (
            <p className="py-10 text-center text-sm text-slate-400">Cargando...</p>
          ) : rows.length === 0 ? (
            <Table columns={columns}>
              <tr><td colSpan={columns.length}><EmptyState message="No hay prospectos registrados" /></td></tr>
            </Table>
          ) : (
            <Table columns={columns}>
              {rows.map((p) => (
                <tr key={p.id} className="text-slate-200">
                  <td className="px-4 py-3">
                    <button className="font-semibold text-blue-400 hover:underline" onClick={() => openDetail(p)}>{p.full_name}</button>
                    {p.address && <div className="text-xs text-slate-500">{p.address}</div>}
                  </td>
                  <td className="px-4 py-3">{p.phone || '—'}</td>
                  <td className="px-4 py-3">{p.prospector_name || '—'}</td>
                  <td className="px-4 py-3 text-center"><StatusBadge status={p.status} /></td>
                  <td className="px-4 py-3 text-center"><Stars value={p.rating} readOnly /></td>
                  <td className="px-4 py-3">{formatMoney(p.opportunity_value)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap justify-center gap-1">
                      <button className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" onClick={() => openDetail(p)}>Ver</button>
                      <button className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" onClick={() => openEdit(p)}>Editar</button>
                      {isAdmin && <button className="rounded px-2 py-1 text-xs text-red-400 hover:bg-slate-800" onClick={() => handleDelete(p)}>Eliminar</button>}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </>
      )}

      {tab === 'board' && board && (
        <div className="space-y-4">
          {summary && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ['Valor del pipeline', formatMoney(summary.total_value), 'text-blue-400'],
                ['Valor ponderado', formatMoney(summary.weighted_value), 'text-emerald-400'],
                ['Prospectos', rows.length, 'text-indigo-400'],
                ['Convertidos', (summary.by_status.find((s) => s.status === 'cliente_convertido')?.count) || 0, 'text-amber-400'],
              ].map(([label, value, color]) => (
                <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                  <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
                  <p className={`mt-2 text-2xl font-bold ${color}`}>{value}</p>
                </div>
              ))}
            </div>
          )}
          <div className="flex gap-3 overflow-x-auto pb-4">
            {board.stages.map((stage) => (
              <div
                key={stage.slug}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(stage.slug)}
                className="flex w-64 shrink-0 flex-col rounded-xl border border-slate-800 bg-slate-900/60"
              >
                <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
                  <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: stage.color || '#64748b' }} />
                    {stage.name}
                  </span>
                  <span className="text-xs text-slate-500">{board.columns[stage.slug]?.length || 0}</span>
                </div>
                <div className="flex-1 space-y-2 p-2">
                  {(board.columns[stage.slug] || []).map((p) => (
                    <div
                      key={p.id}
                      draggable
                      onDragStart={() => setDragging(p)}
                      onDragEnd={() => setDragging(null)}
                      onClick={() => openDetail(p)}
                      className="cursor-grab rounded-lg border border-slate-700 bg-slate-800 p-2 text-sm text-slate-200 shadow hover:border-blue-500 active:cursor-grabbing"
                    >
                      <p className="font-medium">{p.full_name}</p>
                      <p className="text-xs text-slate-500">{p.phone || '—'}</p>
                      <div className="mt-1 flex items-center justify-between">
                        <Stars value={p.rating} readOnly />
                        <span className="text-xs text-slate-400">{formatMoney(p.opportunity_value)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal crear/editar */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? `Editar: ${editing.full_name}` : 'Nuevo prospecto'} wide>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Nombre completo *">
              <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required />
            </Field>
            <Field label="Teléfono">
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            <Field label="Dirección">
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </Field>
            <Field label="Estado civil">
              <Select value={form.marital_status} onChange={(e) => setForm({ ...form, marital_status: e.target.value })}>
                <option value="">—</option>
                <option value="soltero">Soltero(a)</option>
                <option value="casado">Casado(a)</option>
                <option value="union_libre">Unión libre</option>
                <option value="divorciado">Divorciado(a)</option>
                <option value="viudo">Viudo(a)</option>
              </Select>
            </Field>
            <Field label="¿A qué se dedica?">
              <Input
                value={form.occupation}
                onChange={(e) => setForm({ ...form, occupation: e.target.value })}
                placeholder="Ej. Comerciante, empleado…"
              />
            </Field>
            <Field label="Prospectado por">
              <Input
                value={form.prospector_name}
                onChange={(e) => setForm({ ...form, prospector_name: e.target.value })}
                placeholder="Nombre de quien prospectó"
              />
            </Field>
            <Field label="¿Conoce la marca?">
              <Select value={form.knows_brand} onChange={(e) => setForm({ ...form, knows_brand: e.target.value })}>
                <option value="">—</option>
                <option value="si">Sí</option>
                <option value="no">No</option>
              </Select>
            </Field>
            <Field label="Estado">
              <Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </Field>
            <Field label="Calificación">
              <Stars value={form.rating} onChange={(n) => setForm({ ...form, rating: n })} />
            </Field>
            <Field label="¿Tiene presupuesto?">
              <Select value={form.has_budget} onChange={(e) => setForm({ ...form, has_budget: e.target.value })}>
                <option value="">—</option>
                <option value="si">Sí</option>
                <option value="no">No</option>
                <option value="desconocido">Desconocido</option>
              </Select>
            </Field>
            <Field label="¿Es quien decide?">
              <Select value={form.is_decision_maker} onChange={(e) => setForm({ ...form, is_decision_maker: e.target.value })}>
                <option value="">—</option>
                <option value="si">Sí</option>
                <option value="no">No</option>
                <option value="debe_consultar">Debe consultar</option>
              </Select>
            </Field>
          </div>

          <Field label={`Probabilidad de cierre: ${form.close_probability}%`}>
            <input
              type="range" min="0" max="100" step="5" value={form.close_probability}
              onChange={(e) => setForm({ ...form, close_probability: e.target.value })}
              className="w-full accent-blue-500"
            />
          </Field>

          <div>
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-400">Interés en productos</span>
            <div className="flex flex-wrap gap-2">
              {PRODUCTS.map((prod) => {
                const active = form.interested_products.includes(prod)
                return (
                  <button
                    key={prod}
                    type="button"
                    onClick={() => setForm((f) => ({
                      ...f,
                      interested_products: active
                        ? f.interested_products.filter((x) => x !== prod)
                        : [...f.interested_products, prod],
                    }))}
                    className={`rounded-full border px-3 py-1 text-xs font-medium ${
                      active ? 'border-blue-500 bg-blue-500/20 text-blue-300' : 'border-slate-700 text-slate-400 hover:border-slate-500'
                    }`}
                  >
                    {prod.replace(/_/g, ' ')}
                  </button>
                )
              })}
            </div>
          </div>

          <Field label={`Notas (${form.notes.length}/500)`}>
            <Textarea maxLength={500} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Guardando...' : 'Guardar'}</Button>
          </div>
        </form>
      </Modal>

      {/* Modal detalle */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? detail.full_name : ''} wide>
        {detail && (
          <div className="space-y-4 text-sm">
            <div className="flex items-center justify-between">
              <StatusBadge status={detail.status} />
              <Stars value={detail.rating} readOnly />
            </div>
            <div className="grid grid-cols-2 gap-2 text-slate-300">
              <div><span className="text-slate-500">Teléfono:</span> {detail.phone || '—'}</div>
              <div><span className="text-slate-500">Dirección:</span> {detail.address || '—'}</div>
              <div><span className="text-slate-500">Estado civil:</span> {detail.marital_status || '—'}</div>
              <div><span className="text-slate-500">¿A qué se dedica?:</span> {detail.occupation || '—'}</div>
              <div><span className="text-slate-500">Prospectado por:</span> {detail.prospector_name || '—'}</div>
              <div><span className="text-slate-500">Conoce marca:</span> {detail.knows_brand === true ? 'Sí' : detail.knows_brand === false ? 'No' : '—'}</div>
              <div><span className="text-slate-500">Oportunidad:</span> {formatMoney(detail.opportunity_value)}</div>
              <div><span className="text-slate-500">Probabilidad:</span> {detail.close_probability}%</div>
            </div>

            {!detail.converted_at && (
              <Button variant="success" onClick={handleConvert}>Convertir en cliente</Button>
            )}
            {detail.converted_at && (
              <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-2 text-emerald-300">
                Convertido en cliente el {new Date(detail.converted_at).toLocaleString()}
              </p>
            )}

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Seguimientos</p>
              <form onSubmit={handleAddActivity} className="grid grid-cols-12 gap-2">
                <Select className="col-span-3" value={activityForm.kind} onChange={(e) => setActivityForm({ ...activityForm, kind: e.target.value })}>
                  {Object.entries(ACTIVITY_KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </Select>
                <Input className="col-span-3" type="datetime-local" value={activityForm.scheduled_at} onChange={(e) => setActivityForm({ ...activityForm, scheduled_at: e.target.value })} />
                <Input className="col-span-4" placeholder="Resultado / observación" value={activityForm.result} onChange={(e) => setActivityForm({ ...activityForm, result: e.target.value })} />
                <Button type="submit" className="col-span-2">Agregar</Button>
              </form>
              <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">
                {activities.length === 0 ? <p className="text-xs text-slate-500">Sin seguimientos</p> : activities.map((a) => (
                  <div key={a.id} className="flex justify-between border-b border-slate-800 py-1 text-xs">
                    <span className="text-slate-300">{ACTIVITY_KINDS[a.kind] || a.kind} · {a.result || a.observation || '—'}</span>
                    <span className="text-slate-500">{a.status}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Notas</p>
              <div className="flex gap-2">
                <Input maxLength={500} placeholder="Nueva nota..." value={newNote} onChange={(e) => setNewNote(e.target.value)} />
                <Button type="button" onClick={handleAddNote}>Agregar</Button>
              </div>
              <div className="mt-2 max-h-32 space-y-1 overflow-y-auto">
                {notes.length === 0 ? <p className="text-xs text-slate-500">Sin notas</p> : notes.map((n) => (
                  <p key={n.id} className="border-b border-slate-800 py-1 text-xs text-slate-300">{n.text}</p>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Historial</p>
              <div className="max-h-40 space-y-1 overflow-y-auto text-xs">
                {history.length === 0 ? <p className="text-slate-500">Sin movimientos</p> : history.map((h) => (
                  <div key={h.id} className="flex justify-between border-b border-slate-800 py-1">
                    <span className="text-slate-400">{new Date(h.timestamp).toLocaleString()} · {h.action}</span>
                    <span className="text-slate-500">{h.detail}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Evidencias</p>
              <input
                type="file"
                onChange={handleUpload}
                disabled={uploading}
                className="block w-full text-xs text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-700 file:px-3 file:py-1.5 file:text-xs file:text-slate-200"
              />
              <div className="mt-2 max-h-32 space-y-1 overflow-y-auto">
                {files.length === 0 ? <p className="text-xs text-slate-500">Sin archivos</p> : files.map((f) => (
                  <div key={f.id} className="flex items-center justify-between border-b border-slate-800 py-1 text-xs">
                    <span className="truncate text-slate-300">{f.filename} {f.size ? `(${Math.round(f.size / 1024)} KB)` : ''}</span>
                    <button onClick={() => handleDeleteFile(f.id)} className="ml-2 text-red-400 hover:text-red-300">Eliminar</button>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Firma digital</p>
              <div className="flex flex-wrap items-center gap-2">
                <Select className="w-40" value={sigRole} onChange={(e) => setSigRole(e.target.value)}>
                  <option value="cliente">Cliente</option>
                  <option value="representante">Representante</option>
                </Select>
                <Button type="button" variant="ghost" onClick={clearSignature}>Limpiar</Button>
                <Button type="button" onClick={handleSaveSignature}>Guardar firma</Button>
              </div>
              <SignaturePad />
              <div className="mt-2 space-y-1">
                {signatures.length === 0 ? <p className="text-xs text-slate-500">Sin firmas registradas</p> : signatures.map((s) => (
                  <p key={s.id} className="border-b border-slate-800 py-1 text-xs capitalize text-slate-300">
                    {s.role} · {new Date(s.created_at).toLocaleString()}
                  </p>
                ))}
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

function SignaturePad() {
  const canvasRef = useRef(null)
  const drawing = useRef(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.width = canvas.offsetWidth
    canvas.height = 140
    const ctx = canvas.getContext('2d')
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.strokeStyle = '#e2e8f0'
  }, [])

  function pos(e) {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const point = e.touches ? e.touches[0] : e
    return { x: point.clientX - rect.left, y: point.clientY - rect.top }
  }

  function start(e) {
    e.preventDefault()
    drawing.current = true
    const ctx = canvasRef.current.getContext('2d')
    const { x, y } = pos(e)
    ctx.beginPath()
    ctx.moveTo(x, y)
  }
  function move(e) {
    if (!drawing.current) return
    e.preventDefault()
    const ctx = canvasRef.current.getContext('2d')
    const { x, y } = pos(e)
    ctx.lineTo(x, y)
    ctx.stroke()
  }
  function end() {
    drawing.current = false
  }

  return (
    <canvas
      id="signature-pad"
      ref={canvasRef}
      onMouseDown={start}
      onMouseMove={move}
      onMouseUp={end}
      onMouseLeave={end}
      onTouchStart={start}
      onTouchMove={move}
      onTouchEnd={end}
      className="mt-2 w-full touch-none rounded-lg border border-dashed border-slate-600 bg-slate-900"
    />
  )
}
