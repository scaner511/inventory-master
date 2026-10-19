import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import {
  createTemporaryStorage,
  createTsLocation,
  deleteTemporaryStorage,
  deleteTsLocation,
  exitTemporaryStorage,
  getProducts,
  getTemporaryStorage,
  getTsDashboard,
  getTsHistory,
  getTsLocations,
  updateTemporaryStorage,
  updateTsLocation,
} from '../api/index.js'
import { openAuthenticatedUrl, API_BASE } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Modal from '../components/ui/Modal.jsx'
import BarcodeScanner from '../components/BarcodeScanner.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import { Button, Field, Input, Select, Textarea } from '../components/ui/Form.jsx'

const STATUS_META = {
  recibido: { label: 'Recibido', cls: 'bg-blue-500/10 text-blue-400 border-blue-500/30' },
  almacenado: { label: 'Almacenado', cls: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30' },
  proximo_vencer: { label: 'Próximo a vencer', cls: 'bg-amber-500/10 text-amber-400 border-amber-500/30' },
  vencido: { label: 'Vencido', cls: 'bg-red-500/10 text-red-400 border-red-500/30' },
  devuelto: { label: 'Devuelto', cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' },
  retirado: { label: 'Retirado', cls: 'bg-slate-500/10 text-slate-300 border-slate-500/30' },
}

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.recibido
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${meta.cls}`}>
      {meta.label}
    </span>
  )
}

function expiryLabel(row) {
  if (row.status === 'devuelto' || row.status === 'retirado') return '—'
  const d = row.days_left
  if (d < 0) return `Vencido hace ${Math.abs(d)} d`
  if (d === 0) return 'Vence hoy'
  return `${d} d`
}

const EMPTY_ITEM = { product_id: null, product_name: '', barcode: '', quantity: 1, note: '' }
const EMPTY_FORM = {
  entry_date: new Date().toISOString().slice(0, 10),
  deadline_date: '',
  party_name: '',
  party_company: '',
  party_phone: '',
  party_email: '',
  reference_document: '',
  location_id: '',
  note: '',
  items: [{ ...EMPTY_ITEM }],
}

function fold(s) {
  return (s || '').toString().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

export default function TemporaryStorage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'

  const [tab, setTab] = useState('list')
  const [rows, setRows] = useState([])
  const [locations, setLocations] = useState([])
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(true)

  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [party, setParty] = useState('')
  const [locationId, setLocationId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [products, setProducts] = useState([])
  const [productSearch, setProductSearch] = useState('')
  const [scannerIdx, setScannerIdx] = useState(null)

  const [exitTarget, setExitTarget] = useState(null)
  const [exitForm, setExitForm] = useState({ exit_type: 'retirado', responsible: '', document: '', note: '' })

  const [detail, setDetail] = useState(null)
  const [history, setHistory] = useState([])

  const [locModalOpen, setLocModalOpen] = useState(false)
  const [locEditing, setLocEditing] = useState(null)
  const [locForm, setLocForm] = useState({ name: '', description: '', is_active: true })

  const loadLocations = useCallback(async () => {
    try {
      setLocations(await getTsLocations())
    } catch {
      /* interceptor */
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, dash] = await Promise.all([
        getTemporaryStorage({ q, status, party, locationId, dateFrom, dateTo }),
        getTsDashboard(),
      ])
      setRows(list)
      setDashboard(dash)
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [q, status, party, locationId, dateFrom, dateTo])

  useEffect(() => {
    loadLocations()
  }, [loadLocations])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  const loadProducts = useCallback(() => {
    getProducts().then(setProducts).catch(() => {})
  }, [])

  const filteredProducts = useMemo(() => {
    const term = fold(productSearch).trim()
    if (!term) return products.slice(0, 8)
    return products.filter((p) => fold(`${p.name} ${p.code}`).includes(term)).slice(0, 8)
  }, [products, productSearch])

  /* ---------------- Recepción (crear/editar) ---------------- */
  function openCreate() {
    setEditing(null)
    setForm({ ...EMPTY_FORM, items: [{ ...EMPTY_ITEM }] })
    setProductSearch('')
    loadProducts()
    setModalOpen(true)
  }

  function openEdit(row) {
    setEditing(row)
    setForm({
      entry_date: row.entry_date,
      deadline_date: row.deadline_date,
      party_name: row.party_name,
      party_company: row.party_company || '',
      party_phone: row.party_phone || '',
      party_email: row.party_email || '',
      reference_document: row.reference_document || '',
      location_id: row.location_id || '',
      note: row.note || '',
      items: row.items.map((it) => ({
        product_id: it.product_id,
        product_name: it.product_name,
        barcode: it.barcode || '',
        quantity: it.quantity,
        note: it.note || '',
      })),
    })
    setProductSearch('')
    loadProducts()
    setModalOpen(true)
  }

  function updateItem(idx, patch) {
    setForm((f) => ({ ...f, items: f.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)) }))
  }

  function addItem(initial = {}) {
    setForm((f) => ({ ...f, items: [...f.items, { ...EMPTY_ITEM, ...initial }] }))
  }

  function removeItem(idx) {
    setForm((f) => ({ ...f, items: f.items.filter((_, i) => i !== idx) }))
  }

  function applyBarcodeToItem(idx, code) {
    const found = products.find((p) => fold(p.code) === fold(code))
    updateItem(idx, { barcode: code, ...(found ? { product_id: found.id, product_name: found.name } : {}) })
    toast[found ? 'success' : 'error'](found ? `Producto: ${found.name}` : 'Código no encontrado en catálogo: agrega el nombre')
  }

  async function handleSave(e) {
    e.preventDefault()
    if (!form.party_name.trim()) return toast.error('Indica el tercero/vendedor')
    if (!form.deadline_date) return toast.error('Indica la fecha límite')
    const items = form.items.filter((it) => it.product_name.trim() && Number(it.quantity) > 0)
    if (!items.length) return toast.error('Agrega al menos un producto con cantidad')

    const payload = {
      entry_date: form.entry_date || undefined,
      deadline_date: form.deadline_date,
      party_name: form.party_name.trim(),
      party_company: form.party_company.trim() || null,
      party_phone: form.party_phone.trim() || null,
      party_email: form.party_email.trim() || null,
      reference_document: form.reference_document.trim() || null,
      location_id: form.location_id ? Number(form.location_id) : null,
      note: form.note.trim() || null,
      items: items.map((it) => ({
        product_id: it.product_id || null,
        product_name: it.product_name.trim(),
        barcode: it.barcode.trim() || null,
        quantity: Number(it.quantity),
        note: it.note.trim() || null,
      })),
    }
    setSaving(true)
    try {
      if (editing) {
        await updateTemporaryStorage(editing.id, payload)
        toast.success('Recepción actualizada')
      } else {
        await createTemporaryStorage(payload)
        toast.success('Recepción registrada')
      }
      setModalOpen(false)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  /* ---------------- Salida ---------------- */
  function openExit(row) {
    setExitTarget(row)
    setExitForm({ exit_type: 'retirado', responsible: '', document: '', note: '' })
  }

  async function handleExit(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await exitTemporaryStorage(exitTarget.id, {
        exit_type: exitForm.exit_type,
        responsible: exitForm.responsible.trim() || null,
        document: exitForm.document.trim() || null,
        note: exitForm.note.trim() || null,
      })
      toast.success(`Mercancía marcada como ${exitForm.exit_type}`)
      setExitTarget(null)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(row) {
    if (!window.confirm(`¿Eliminar la recepción ${row.number}? Esta acción no se puede deshacer.`)) return
    try {
      await deleteTemporaryStorage(row.id)
      toast.success('Recepción eliminada')
      load()
    } catch {
      /* interceptor */
    }
  }

  function openDetail(row) {
    setDetail(row)
    setHistory([])
    getTsHistory(row.id).then(setHistory).catch(() => {})
  }

  /* ---------------- Ubicaciones ---------------- */
  function openLocCreate() {
    setLocEditing(null)
    setLocForm({ name: '', description: '', is_active: true })
    setLocModalOpen(true)
  }

  function openLocEdit(loc) {
    setLocEditing(loc)
    setLocForm({ name: loc.name, description: loc.description || '', is_active: loc.is_active })
    setLocModalOpen(true)
  }

  async function handleLocSave(e) {
    e.preventDefault()
    if (!locForm.name.trim()) return toast.error('Indica el nombre de la ubicación')
    setSaving(true)
    try {
      const payload = {
        name: locForm.name.trim(),
        description: locForm.description.trim() || null,
        is_active: locForm.is_active,
      }
      if (locEditing) await updateTsLocation(locEditing.id, payload)
      else await createTsLocation(payload)
      toast.success(locEditing ? 'Ubicación actualizada' : 'Ubicación creada')
      setLocModalOpen(false)
      loadLocations()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleLocDelete(loc) {
    if (!window.confirm(`¿Eliminar la ubicación "${loc.name}"?`)) return
    try {
      await deleteTsLocation(loc.id)
      toast.success('Ubicación eliminada')
      loadLocations()
    } catch {
      /* interceptor */
    }
  }

  const columns = [
    { key: 'number', label: 'No. Recepción' },
    { key: 'party', label: 'Tercero' },
    { key: 'products', label: 'Productos' },
    { key: 'location', label: 'Ubicación' },
    { key: 'deadline', label: 'Vence' },
    { key: 'status', label: 'Estado', align: 'center' },
    { key: 'actions', label: 'Acciones', align: 'center' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-100">Recepción de Mercancía</h2>
          <p className="text-sm text-slate-400">
            Depósito temporal de mercancía de terceros. No afecta el inventario oficial.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => openAuthenticatedUrl(`${API_BASE}/temporary-storage/export/excel`)}>
            Excel
          </Button>
          <Button variant="ghost" onClick={() => openAuthenticatedUrl(`${API_BASE}/temporary-storage/export/csv`)}>
            CSV
          </Button>
          <Button onClick={openCreate}>+ Nueva recepción</Button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-800">
        {[
          ['list', 'Recepciones'],
          ['dashboard', 'Dashboard'],
          ['locations', 'Ubicaciones'],
        ].map(([key, label]) => (
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
          <div className="grid gap-3 md:grid-cols-4 lg:grid-cols-6">
            <Input placeholder="Buscar..." value={q} onChange={(e) => setQ(e.target.value)} />
            <Select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Todos los estados</option>
              {Object.entries(STATUS_META).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </Select>
            <Input placeholder="Tercero / empresa" value={party} onChange={(e) => setParty(e.target.value)} />
            <Select value={locationId} onChange={(e) => setLocationId(e.target.value)}>
              <option value="">Todas las ubicaciones</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </Select>
            <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} title="Desde" />
            <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} title="Hasta" />
          </div>

          {loading ? (
            <p className="py-10 text-center text-sm text-slate-400">Cargando...</p>
          ) : rows.length === 0 ? (
            <Table columns={columns}>
              <tr>
                <td colSpan={columns.length}>
                  <EmptyState message="No hay recepciones registradas" />
                </td>
              </tr>
            </Table>
          ) : (
            <Table columns={columns}>
              {rows.map((row) => {
                const out = row.status === 'devuelto' || row.status === 'retirado'
                return (
                  <tr key={row.id} className="text-slate-200">
                    <td className="px-4 py-3">
                      <button className="font-semibold text-blue-400 hover:underline" onClick={() => openDetail(row)}>
                        {row.number}
                      </button>
                      <div className="text-xs text-slate-500">{row.short_code}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{row.party_name}</div>
                      {row.party_company && <div className="text-xs text-slate-500">{row.party_company}</div>}
                    </td>
                    <td className="px-4 py-3">
                      <div>{row.items.length} prod.</div>
                      <div className="text-xs text-slate-500">{row.total_units} und.</div>
                    </td>
                    <td className="px-4 py-3">{row.location_name || '—'}</td>
                    <td className="px-4 py-3">
                      <div>{row.deadline_date}</div>
                      <div
                        className={`text-xs ${
                          out ? 'text-slate-500' : row.days_left < 0 ? 'text-red-400' : row.days_left <= 7 ? 'text-amber-400' : 'text-slate-500'
                        }`}
                      >
                        {expiryLabel(row)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <StatusBadge status={row.computed_status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap justify-center gap-1">
                        <button className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" onClick={() => openDetail(row)}>
                          Ver
                        </button>
                        <button
                          className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                          onClick={() => openAuthenticatedUrl(`${API_BASE}/temporary-storage/${row.id}/ticket`)}
                        >
                          PDF
                        </button>
                        {!out && (
                          <>
                            <button className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" onClick={() => openEdit(row)}>
                              Editar
                            </button>
                            <button className="rounded px-2 py-1 text-xs text-amber-400 hover:bg-slate-800" onClick={() => openExit(row)}>
                              Salida
                            </button>
                          </>
                        )}
                        {isAdmin && (
                          <button className="rounded px-2 py-1 text-xs text-red-400 hover:bg-slate-800" onClick={() => handleDelete(row)}>
                            Eliminar
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </Table>
          )}
        </>
      )}

      {tab === 'dashboard' && dashboard && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ['Recepciones activas', dashboard.active_receptions, 'text-blue-400'],
              ['Productos almacenados', dashboard.stored_products, 'text-indigo-400'],
              ['Unidades almacenadas', dashboard.stored_units, 'text-emerald-400'],
              ['Próximos a vencer (≤7d)', dashboard.expiring_soon, 'text-amber-400'],
              ['Vencidos', dashboard.expired, 'text-red-400'],
              ['Salidas este mes', dashboard.returned_this_month, 'text-slate-300'],
            ].map(([label, value, color]) => (
              <div key={label} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
                <p className={`mt-2 text-3xl font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              <h3 className="mb-3 text-sm font-bold text-slate-200">Top terceros (activos)</h3>
              {dashboard.by_party.length === 0 ? (
                <p className="text-sm text-slate-500">Sin datos</p>
              ) : (
                dashboard.by_party.map((r) => (
                  <div key={r.party} className="flex items-center justify-between border-b border-slate-800 py-2 text-sm">
                    <span className="text-slate-300">{r.party}</span>
                    <span className="font-semibold text-slate-100">{r.count}</span>
                  </div>
                ))
              )}
            </div>
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
              <h3 className="mb-3 text-sm font-bold text-slate-200">Por ubicación</h3>
              {dashboard.by_location.length === 0 ? (
                <p className="text-sm text-slate-500">Sin datos</p>
              ) : (
                dashboard.by_location.map((r) => (
                  <div key={r.location} className="flex items-center justify-between border-b border-slate-800 py-2 text-sm">
                    <span className="text-slate-300">{r.location}</span>
                    <span className="font-semibold text-slate-100">{r.count}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {tab === 'locations' && (
        <div className="space-y-4">
          <div className="flex justify-end">
            {isAdmin && <Button onClick={openLocCreate}>+ Nueva ubicación</Button>}
          </div>
          {locations.length === 0 ? (
            <Table columns={[{ key: 'name', label: 'Ubicación' }]}>
              <tr>
                <td>
                  <EmptyState message="No hay ubicaciones temporales" />
                </td>
              </tr>
            </Table>
          ) : (
            <Table columns={[{ key: 'name', label: 'Ubicación' }, { key: 'desc', label: 'Descripción' }, { key: 'active', label: 'Activa', align: 'center' }, { key: 'actions', label: 'Acciones', align: 'center' }]}>
              {locations.map((loc) => (
                <tr key={loc.id} className="text-slate-200">
                  <td className="px-4 py-3 font-medium">{loc.name}</td>
                  <td className="px-4 py-3 text-slate-400">{loc.description || '—'}</td>
                  <td className="px-4 py-3 text-center">{loc.is_active ? 'Sí' : 'No'}</td>
                  <td className="px-4 py-3">
                    <div className="flex justify-center gap-1">
                      {isAdmin && (
                        <>
                          <button className="rounded px-2 py-1 text-xs text-slate-300 hover:bg-slate-800" onClick={() => openLocEdit(loc)}>
                            Editar
                          </button>
                          <button className="rounded px-2 py-1 text-xs text-red-400 hover:bg-slate-800" onClick={() => handleLocDelete(loc)}>
                            Eliminar
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      )}

      {/* Modal recepción */}
      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? `Editar ${editing.number}` : 'Nueva recepción'} wide>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Fecha de entrada">
              <Input type="date" value={form.entry_date} onChange={(e) => setForm({ ...form, entry_date: e.target.value })} />
            </Field>
            <Field label="Fecha límite *">
              <Input type="date" value={form.deadline_date} onChange={(e) => setForm({ ...form, deadline_date: e.target.value })} required />
            </Field>
            <Field label="Ubicación">
              <Select value={form.location_id} onChange={(e) => setForm({ ...form, location_id: e.target.value })}>
                <option value="">Sin ubicación</option>
                {locations.filter((l) => l.is_active).map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </Select>
            </Field>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Tercero / Vendedor *">
              <Input value={form.party_name} onChange={(e) => setForm({ ...form, party_name: e.target.value })} required />
            </Field>
            <Field label="Empresa">
              <Input value={form.party_company} onChange={(e) => setForm({ ...form, party_company: e.target.value })} />
            </Field>
            <Field label="Teléfono">
              <Input value={form.party_phone} onChange={(e) => setForm({ ...form, party_phone: e.target.value })} />
            </Field>
            <Field label="Correo">
              <Input type="email" value={form.party_email} onChange={(e) => setForm({ ...form, party_email: e.target.value })} />
            </Field>
            <Field label="Documento de referencia">
              <Input value={form.reference_document} onChange={(e) => setForm({ ...form, reference_document: e.target.value })} />
            </Field>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Productos</span>
              <Button type="button" variant="ghost" onClick={() => addItem()}>+ Agregar</Button>
            </div>
            <div className="space-y-2">
              {form.items.map((it, idx) => (
                <div key={idx} className="grid grid-cols-12 items-end gap-2 rounded-lg border border-slate-800 p-2">
                  <div className="col-span-5">
                    <Input
                      placeholder="Nombre del producto"
                      value={it.product_name}
                      onChange={(e) => updateItem(idx, { product_name: e.target.value, product_id: null })}
                    />
                  </div>
                  <div className="col-span-3">
                    <Input
                      placeholder="Código de barras"
                      value={it.barcode}
                      onChange={(e) => updateItem(idx, { barcode: e.target.value })}
                    />
                  </div>
                  <div className="col-span-1">
                    <Input
                      type="number"
                      min="1"
                      value={it.quantity}
                      onChange={(e) => updateItem(idx, { quantity: e.target.value })}
                    />
                  </div>
                  <div className="col-span-2">
                    <Button type="button" variant="ghost" onClick={() => setScannerIdx(idx)} className="w-full">
                      Escanear
                    </Button>
                  </div>
                  <div className="col-span-1">
                    <button
                      type="button"
                      onClick={() => removeItem(idx)}
                      disabled={form.items.length === 1}
                      className="w-full rounded-lg bg-red-600/20 py-2 text-xs text-red-400 disabled:opacity-40"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Buscar en catálogo (opcional)
            </p>
            <Input placeholder="Nombre o código..." value={productSearch} onChange={(e) => setProductSearch(e.target.value)} />
            {productSearch && (
              <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">
                {filteredProducts.length === 0 ? (
                  <p className="text-xs text-slate-500">Sin resultados. Escribe el nombre manualmente.</p>
                ) : (
                  filteredProducts.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => addItem({ product_id: p.id, product_name: p.name, barcode: p.code, quantity: 1 })}
                      className="block w-full rounded px-2 py-1 text-left text-sm text-slate-200 hover:bg-slate-800"
                    >
                      {p.name} <span className="text-xs text-slate-500">({p.code})</span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          <Field label="Observaciones">
            <Textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </Field>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Guardando...' : 'Guardar'}</Button>
          </div>
        </form>
      </Modal>

      {/* Modal salida */}
      <Modal open={!!exitTarget} onClose={() => setExitTarget(null)} title={`Registrar salida — ${exitTarget?.number || ''}`}>
        <form onSubmit={handleExit} className="space-y-4">
          <Field label="Tipo de salida *">
            <Select value={exitForm.exit_type} onChange={(e) => setExitForm({ ...exitForm, exit_type: e.target.value })}>
              <option value="retirado">Retirado (lo toma el tercero)</option>
              <option value="devuelto">Devuelto (se envía de vuelta)</option>
            </Select>
          </Field>
          <Field label="Responsable">
            <Input value={exitForm.responsible} onChange={(e) => setExitForm({ ...exitForm, responsible: e.target.value })} />
          </Field>
          <Field label="Documento">
            <Input value={exitForm.document} onChange={(e) => setExitForm({ ...exitForm, document: e.target.value })} />
          </Field>
          <Field label="Observaciones">
            <Textarea value={exitForm.note} onChange={(e) => setExitForm({ ...exitForm, note: e.target.value })} />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setExitTarget(null)}>Cancelar</Button>
            <Button type="submit" variant="warning" disabled={saving}>{saving ? 'Guardando...' : 'Confirmar salida'}</Button>
          </div>
        </form>
      </Modal>

      {/* Modal detalle */}
      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? `Recepción ${detail.number}` : ''} wide>
        {detail && (
          <div className="space-y-4 text-sm">
            <div className="flex items-center justify-between">
              <StatusBadge status={detail.computed_status} />
              <Button variant="ghost" onClick={() => openAuthenticatedUrl(`${API_BASE}/temporary-storage/${detail.id}/ticket`)}>
                Descargar PDF
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2 text-slate-300">
              <div><span className="text-slate-500">Tercero:</span> {detail.party_name}</div>
              <div><span className="text-slate-500">Empresa:</span> {detail.party_company || '—'}</div>
              <div><span className="text-slate-500">Teléfono:</span> {detail.party_phone || '—'}</div>
              <div><span className="text-slate-500">Correo:</span> {detail.party_email || '—'}</div>
              <div><span className="text-slate-500">Entrada:</span> {detail.entry_date}</div>
              <div><span className="text-slate-500">Límite:</span> {detail.deadline_date}</div>
              <div><span className="text-slate-500">Ubicación:</span> {detail.location_name || '—'}</div>
              <div><span className="text-slate-500">Documento:</span> {detail.reference_document || '—'}</div>
            </div>
            {detail.exit_type && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-amber-200">
                <p className="font-semibold">{detail.exit_type === 'devuelto' ? 'Devuelto' : 'Retirado'}</p>
                <p className="text-xs">Responsable: {detail.exit_responsible || '—'} · Doc: {detail.exit_document || '—'}</p>
              </div>
            )}
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Productos</p>
              <div className="rounded-lg border border-slate-800">
                {detail.items.map((it) => (
                  <div key={it.id} className="flex justify-between border-b border-slate-800 px-3 py-2 last:border-0">
                    <span className="text-slate-200">{it.product_name}</span>
                    <span className="text-slate-400">{it.quantity} und.</span>
                  </div>
                ))}
              </div>
            </div>
            {detail.note && <p className="text-slate-400"><span className="text-slate-500">Obs.:</span> {detail.note}</p>}
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Historial</p>
              <div className="max-h-48 space-y-1 overflow-y-auto text-xs">
                {history.length === 0 ? (
                  <p className="text-slate-500">Sin movimientos</p>
                ) : (
                  history.map((h) => (
                    <div key={h.id} className="flex justify-between border-b border-slate-800 py-1">
                      <span className="text-slate-400">{new Date(h.timestamp).toLocaleString()}</span>
                      <span className="text-slate-200">{h.action}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Modal ubicación */}
      <Modal open={locModalOpen} onClose={() => setLocModalOpen(false)} title={locEditing ? 'Editar ubicación' : 'Nueva ubicación'}>
        <form onSubmit={handleLocSave} className="space-y-4">
          <Field label="Nombre *">
            <Input value={locForm.name} onChange={(e) => setLocForm({ ...locForm, name: e.target.value })} required />
          </Field>
          <Field label="Descripción">
            <Input value={locForm.description} onChange={(e) => setLocForm({ ...locForm, description: e.target.value })} />
          </Field>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={locForm.is_active}
              onChange={(e) => setLocForm({ ...locForm, is_active: e.target.checked })}
            />
            Activa
          </label>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setLocModalOpen(false)}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Guardando...' : 'Guardar'}</Button>
          </div>
        </form>
      </Modal>

      <BarcodeScanner
        open={scannerIdx !== null}
        onClose={() => setScannerIdx(null)}
        onCode={(code) => {
          if (scannerIdx !== null) applyBarcodeToItem(scannerIdx, code)
          setScannerIdx(null)
        }}
      />
    </div>
  )
}
