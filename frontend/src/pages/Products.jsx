import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { createProduct, deleteProduct, getProducts, updateProduct } from '../api/index.js'
import { api, formatMoney, openAuthenticatedUrl } from '../api/client.js'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import Badge from '../components/ui/Badge.jsx'
import { Button, Field, Input } from '../components/ui/Form.jsx'

const EMPTY_FORM = {
  code: '',
  name: '',
  stock: 0,
  purchase_price: '',
  sale_price: '',
  location1: '',
  location2: '',
  location3: '',
}

export default function Products() {
  const [products, setProducts] = useState([])
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)
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
      stock: p.stock,
      purchase_price: p.purchase_price,
      sale_price: p.sale_price,
      location1: p.location1 || '',
      location2: p.location2 || '',
      location3: p.location3 || '',
    })
    setModalOpen(true)
  }

  async function handleSave(e) {
    e.preventDefault()
    if (!form.code.trim() || !form.name.trim()) return toast.error('Código y nombre son obligatorios')
    setSaving(true)
    const payload = {
      code: form.code.trim(),
      name: form.name.trim(),
      stock: Number(form.stock) || 0,
      purchase_price: Number(form.purchase_price) || 0,
      sale_price: Number(form.sale_price) || 0,
      location1: form.location1.trim() || null,
      location2: form.location2.trim() || null,
      location3: form.location3.trim() || null,
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
          <Button onClick={openCreate}>➕ Nuevo producto</Button>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Carga masiva: columnas <span className="text-slate-300">codigo, nombre, stock</span> y opcionalmente{' '}
        <span className="text-slate-300">compra, venta, ubicacion1, ubicacion2, ubicacion3</span>. Acepta nombres
        similares (Código, Cantidad, Precio de Compra...) y archivos sin encabezados (orden: codigo, nombre, stock, compra,
        venta, ubicacion1, ubicacion2, ubicacion3). Las filas sin código (vacío o "-") reciben código automático (AUTO1,
        AUTO2...).
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
            { key: 'buy', label: 'Compra', align: 'center' },
            { key: 'sell', label: 'Venta', align: 'center' },
            { key: 'loc', label: 'Ubicación' },
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
              <td className="px-4 py-3 text-center text-slate-300">{formatMoney(p.purchase_price)}</td>
              <td className="px-4 py-3 text-center text-slate-300">{formatMoney(p.sale_price)}</td>
              <td className="px-4 py-3 text-xs text-slate-400">{p.location || 'Sin asignar'}</td>
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
          <Field label="Stock">
            <Input type="number" min="0" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value })} />
          </Field>
          <Field label="Nombre del producto">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </Field>
          <div className="hidden sm:block" />
          <Field label="Precio de compra">
            <Input type="number" step="0.01" min="0" value={form.purchase_price} onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} placeholder="0.00" />
          </Field>
          <Field label="Precio de venta">
            <Input type="number" step="0.01" min="0" value={form.sale_price} onChange={(e) => setForm({ ...form, sale_price: e.target.value })} placeholder="0.00" />
          </Field>
          <Field label="Ubicación 1 (principal)">
            <Input value={form.location1} onChange={(e) => setForm({ ...form, location1: e.target.value })} />
          </Field>
          <Field label="Ubicación 2">
            <Input value={form.location2} onChange={(e) => setForm({ ...form, location2: e.target.value })} />
          </Field>
          <Field label="Ubicación 3">
            <Input value={form.location3} onChange={(e) => setForm({ ...form, location3: e.target.value })} />
          </Field>
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
