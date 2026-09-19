import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { createProduct, deleteAllProducts, deleteProduct, getProducts, updateProduct } from '../api/index.js'
import { api, formatMoney, openAuthenticatedUrl } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import Badge from '../components/ui/Badge.jsx'
import { Button, Field, Input } from '../components/ui/Form.jsx'

const EMPTY_FORM = {
  code: '',
  name: '',
  purchase_price: '',
  sale_price: '',
  locations: [{ location: '', quantity: 0 }],
}

export default function Products() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin'
  const [products, setProducts] = useState([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
  const [deletingAll, setDeletingAll] = useState(false)
  const fileRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setProducts(await getProducts({ q }))
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [q])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_FORM)
    setModalOpen(true)
  }

  function openEdit(p) {
    setEditing(p)
    setForm({
      code: p.code,
      name: p.name,
      purchase_price: p.purchase_price,
      sale_price: p.sale_price,
      locations: (Array.isArray(p.locations) && p.locations.length
        ? p.locations.map((l) => ({ location: l.location, quantity: l.quantity }))
        : [{ location: p.location1 || '', quantity: p.stock }]),
    })
    setModalOpen(true)
  }

  function setLocation(i, key, value) {
    setForm((f) => {
      const next = f.locations.map((l, idx) => (idx === i ? { ...l, [key]: value } : l))
      return { ...f, locations: next }
    })
  }

  function addLocation() {
    setForm((f) => ({ ...f, locations: [...f.locations, { location: '', quantity: 0 }] }))
  }

  function removeLocation(i) {
    setForm((f) => ({
      ...f,
      locations: f.locations.length > 1 ? f.locations.filter((_, idx) => idx !== i) : [{ location: '', quantity: 0 }],
    }))
  }

  const totalStock = form.locations.reduce((acc, l) => acc + (Number(l.quantity) || 0), 0)

  async function handleSave(e) {
    e.preventDefault()
    if (!form.code.trim() || !form.name.trim()) return toast.error('Código y nombre son obligatorios')
    if (form.locations.every((l) => !l.location.trim())) return toast.error('Agrega al menos una ubicación con su cantidad')
    setSaving(true)
    const payload = {
      code: form.code.trim(),
      name: form.name.trim(),
      purchase_price: Number(form.purchase_price) || 0,
      sale_price: Number(form.sale_price) || 0,
      locations: form.locations
        .map((l) => ({ location: l.location.trim(), quantity: Number(l.quantity) || 0 }))
        .filter((l) => l.location),
    }
    try {
      if (editing) {
        await updateProduct(editing.id, payload)
        toast.success('Producto actualizado')
      } else {
        await createProduct(payload)
        toast.success('Producto creado')
      }
      setModalOpen(false)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(p) {
    if (!window.confirm(`¿Eliminar el producto "${p.name}"?`)) return
    try {
      await deleteProduct(p.id)
      toast.success('Producto eliminado')
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleDeleteAll() {
    const total = products.length
    if (total === 0) return toast.error('No hay productos que eliminar')
    const ok = window.confirm(
      `⚠️ ¿Eliminar los ${total} producto(s) del inventario?\n\nEsta acción es IRREVERSIBLE: se borran todos los productos y su stock por ubicación. Solo se permite si no hay préstamos activos.`,
    )
    if (!ok) return
    if (!window.confirm('Confirma de nuevo para continuar: se perderán TODOS los productos del inventario.')) return
    setDeletingAll(true)
    try {
      const res = await deleteAllProducts()
      toast.success(res.message)
      load()
    } catch {
      /* interceptor */
    } finally {
      setDeletingAll(false)
    }
  }

  async function handleImport(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      const { data } = await api.post('/products/import', fd)
      toast.success(data.message)
      load()
    } catch {
      /* interceptor */
    } finally {
      e.target.value = ''
    }
  }

  function renderLocations(p) {
    const locs = Array.isArray(p.locations) && p.locations.length ? p.locations : []
    if (!locs.length) return <span className="text-slate-500">Sin ubicaciones</span>
    return (
      <div className="flex flex-wrap gap-1">
        {locs.map((l) => (
          <span key={l.location} className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
            {l.location}: <span className="font-bold text-slate-100">{l.quantity}</span>
          </span>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white md:text-3xl">Inventario</h2>
          <p className="text-sm text-slate-400">{products.length} producto(s) registrados</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => openAuthenticatedUrl('/reports/daily')}>
            📊 Reporte diario (Excel)
          </Button>
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleImport} />
          <Button variant="ghost" onClick={() => fileRef.current?.click()}>
            📥 Carga masiva
          </Button>
          {isAdmin && (
            <Button variant="danger" onClick={handleDeleteAll} disabled={deletingAll}>
              {deletingAll ? 'Borrando...' : '🗑️ Eliminar todos'}
            </Button>
          )}
          <Button onClick={openCreate}>➕ Nuevo producto</Button>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        El <span className="text-slate-300">stock total</span> es la suma de las cantidades de cada ubicación. En la
        carga masiva: columnas <span className="text-slate-300">codigo, nombre, stock</span> y opcionalmente{' '}
        <span className="text-slate-300">compra, venta, ubicacion1, ubicacion2, ubicacion3</span>. Acepta nombres
        similares y archivos sin encabezados.
      </p>

      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Buscar por código o nombre..."
        className="max-w-md"
      />

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        </div>
      ) : products.length === 0 ? (
        <EmptyState message="No hay productos. Agrega el primero con el botón +" />
      ) : (
        <Table
          columns={[
            { key: 'code', label: 'Código', align: 'center' },
            { key: 'name', label: 'Nombre' },
            { key: 'stock', label: 'Stock', align: 'center' },
            { key: 'loc', label: 'Ubicación (cantidad)' },
            { key: 'buy', label: 'Compra', align: 'center' },
            { key: 'sell', label: 'Venta', align: 'center' },
            { key: 'status', label: 'Estado', align: 'center' },
            { key: 'actions', label: 'Acciones', align: 'center' },
          ]}
        >
          {products.map((p) => (
            <tr key={p.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 text-center font-mono text-xs text-slate-400">{p.code}</td>
              <td className="px-4 py-3 font-medium text-slate-100">{p.name}</td>
              <td className={`px-4 py-3 text-center font-bold ${p.stock === 0 ? 'text-red-400' : p.stock <= 5 ? 'text-amber-400' : 'text-slate-200'}`}>
                {p.stock}
              </td>
              <td className="px-4 py-3">{renderLocations(p)}</td>
              <td className="px-4 py-3 text-center text-slate-300">{formatMoney(p.purchase_price)}</td>
              <td className="px-4 py-3 text-center text-slate-300">{formatMoney(p.sale_price)}</td>
              <td className="px-4 py-3 text-center">
                <Badge status={p.status} />
              </td>
              <td className="px-4 py-3 text-center">
                <div className="flex justify-center gap-1">
                  <button
                    onClick={() => openEdit(p)}
                    className="rounded-lg bg-amber-500/10 p-2 text-amber-400 transition hover:bg-amber-500/20"
                    title="Editar"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleDelete(p)}
                    className="rounded-lg bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                    title="Eliminar"
                  >
                    🗑️
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editing ? 'Editar producto' : 'Nuevo producto'} wide>
        <form onSubmit={handleSave} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Código">
            <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="Ej: 001" required />
          </Field>
          <Field label="Nombre del producto">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </Field>
          <Field label="Precio de compra">
            <Input type="number" step="0.01" min="0" value={form.purchase_price} onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} placeholder="0.00" />
          </Field>
          <Field label="Precio de venta">
            <Input type="number" step="0.01" min="0" value={form.sale_price} onChange={(e) => setForm({ ...form, sale_price: e.target.value })} placeholder="0.00" />
          </Field>

          <div className="sm:col-span-2">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Stock por ubicación
              </span>
              <span className="rounded-lg bg-blue-500/10 px-2.5 py-1 text-sm font-bold text-blue-300">
                Stock total: {totalStock}
              </span>
            </div>
            <div className="space-y-2 rounded-xl border border-slate-700 bg-slate-800/40 p-3">
              {form.locations.map((l, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    value={l.location}
                    onChange={(e) => setLocation(i, 'location', e.target.value)}
                    placeholder="Ubicación (ej: Estante A, Bodega...)"
                    className="flex-1"
                  />
                  <Input
                    type="number"
                    min="0"
                    value={l.quantity}
                    onChange={(e) => setLocation(i, 'quantity', e.target.value)}
                    placeholder="Cantidad"
                    className="w-28"
                  />
                  <button
                    type="button"
                    onClick={() => removeLocation(i)}
                    className="rounded-lg bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                    title="Quitar ubicación"
                  >
                    ✕
                  </button>
                </div>
              ))}
              <Button type="button" variant="ghost" onClick={addLocation}>
                ➕ Agregar ubicación
              </Button>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              La cantidad total se recalcula como la suma de las ubicaciones.
            </p>
          </div>

          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant={editing ? 'warning' : 'success'} disabled={saving}>
              {saving ? 'Guardando...' : editing ? 'Actualizar producto' : 'Guardar producto'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}