import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { createLoan, extendLoan, getLoans, getProducts, returnLoan, updateLoan } from '../api/index.js'
import { openAuthenticatedUrl } from '../api/client.js'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import Badge from '../components/ui/Badge.jsx'
import { Button, Field, Input, Select } from '../components/ui/Form.jsx'

export default function Loans() {
  const [loans, setLoans] = useState([])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [dateFilter, setDateFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const [registerOpen, setRegisterOpen] = useState(false)
  const [products, setProducts] = useState([])
  const [form, setForm] = useState({ product_id: '', quantity: 1, seller: '', phone: '', due_date: '', note: '', location_out: '' })
  const [saving, setSaving] = useState(false)

  const [returnTarget, setReturnTarget] = useState(null)
  const [returnQty, setReturnQty] = useState(1)
  const [returnLocation, setReturnLocation] = useState('')
  const [returnProducts, setReturnProducts] = useState([])
  const [extendTarget, setExtendTarget] = useState(null)
  const [extendDays, setExtendDays] = useState(7)

  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [editLocked, setEditLocked] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setLoans(await getLoans({ q, status, date: dateFilter }))
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }, [q, status, dateFilter])

  useEffect(() => {
    const timer = setTimeout(load, 250)
    return () => clearTimeout(timer)
  }, [load])

  function openRegister() {
    setForm({ product_id: '', quantity: 1, seller: '', phone: '', due_date: '', note: '', location_out: '' })
    getProducts()
      .then((p) => setProducts(p))
      .catch(() => {})
    setRegisterOpen(true)
  }

  const selectedProduct = products.find((p) => String(p.id) === String(form.product_id))

  async function handleCreate(e) {
    e.preventDefault()
    if (!form.product_id || !form.seller.trim() || !form.due_date) {
      return toast.error('Completa producto, vendedor y fecha de devolución')
    }
    const withLocations = (selectedProduct?.locations || []).length > 0
    if (withLocations && !form.location_out) {
      return toast.error('Elige la ubicación de dónde sale el producto')
    }
    setSaving(true)
    try {
      const loan = await createLoan({
        product_id: Number(form.product_id),
        quantity: Number(form.quantity),
        seller: form.seller.trim(),
        phone: form.phone.trim() || null,
        due_date: form.due_date,
        note: form.note.trim() || null,
        location_out: form.location_out || null,
      })
      toast.success('Préstamo registrado correctamente')
      setRegisterOpen(false)
      load()

      const whatsapp = window.confirm('¿Abrir WhatsApp para notificar al vendedor?')
      if (whatsapp && form.phone.trim()) {
        const msg = encodeURIComponent(
          `✅ *Ticket de Préstamo*\n\n👤 *Vendedor:* ${loan.seller}\n📦 *Producto:* ${loan.product_name}\n🔢 *Cantidad:* ${loan.quantity}\n📅 *Devolución:* ${loan.due_date}`,
        )
        window.open(`https://wa.me/${form.phone.trim()}?text=${msg}`, '_blank')
      }

      const pdf = window.confirm('¿Generar el comprobante en PDF?')
      if (pdf) openAuthenticatedUrl(`/reports/loan-ticket/${loan.id}`)
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleReturn() {
    if (!returnTarget) return
    const qty = Number(returnQty)
    if (!qty || qty < 1 || qty > returnTarget.pending) {
      return toast.error(`La cantidad debe estar entre 1 y ${returnTarget.pending}`)
    }
    setSaving(true)
    try {
      await returnLoan(returnTarget.id, qty, returnLocation)
      toast.success('Devolución registrada')
      setReturnTarget(null)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleExtend() {
    if (!extendTarget) return
    setSaving(true)
    try {
      await extendLoan(extendTarget.id, Number(extendDays))
      toast.success('Prórroga aplicada')
      setExtendTarget(null)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  function openEdit(loan) {
    setEditTarget(loan)
    setEditLocked(loan.returned_qty > 0)
    setEditForm({
      product_id: loan.product_id ?? '',
      quantity: loan.quantity,
      seller: loan.seller,
      phone: loan.phone || '',
      due_date: loan.due_date,
      note: loan.note || '',
      location_out: loan.location_out || '',
    })
    getProducts()
      .then((p) => setProducts(p))
      .catch(() => {})
  }

  async function handleEdit(e) {
    e.preventDefault()
    if (!editTarget) return
    const payload = {}
    if (editForm.seller.trim() && editForm.seller.trim() !== editTarget.seller) payload.seller = editForm.seller.trim()
    if (editForm.phone.trim() !== (editTarget.phone || '')) payload.phone = editForm.phone.trim() || null
    if (editForm.due_date && editForm.due_date !== editTarget.due_date) payload.due_date = editForm.due_date
    if (editForm.note.trim() !== (editTarget.note || '')) payload.note = editForm.note.trim() || null
    if (editForm.location_out.trim() !== (editTarget.location_out || '')) payload.location_out = editForm.location_out.trim() || null
    if (!editLocked) {
      if (editForm.product_id !== (editTarget.product_id ?? '')) payload.product_id = Number(editForm.product_id)
      if (Number(editForm.quantity) !== editTarget.quantity) payload.quantity = Number(editForm.quantity)
    }
    if (Object.keys(payload).length === 0) {
      toast.error('No hay cambios que guardar')
      return
    }
    setSaving(true)
    try {
      await updateLoan(editTarget.id, payload)
      toast.success('Préstamo actualizado')
      setEditTarget(null)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white md:text-3xl">Préstamos</h2>
          <p className="text-sm text-slate-400">Registro, devolución y seguimiento</p>
        </div>
        <Button onClick={openRegister}>🤝 Registrar préstamo</Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por vendedor o producto..." className="max-w-xs" />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44">
          <option value="">Todos los estados</option>
          <option value="ACTIVO">Activos</option>
          <option value="VENCIDO">Vencidos</option>
          <option value="VENCE_HOY">Vencen hoy</option>
          <option value="COMPLETADO">Completados</option>
        </Select>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-slate-500">Fecha:</span>
          <Input type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} className="w-40" />
          {dateFilter && (
            <button
              onClick={() => setDateFilter('')}
              className="rounded-lg bg-slate-600/20 px-2 py-1 text-xs text-slate-300 transition hover:bg-slate-600/40"
            >
              ✕ Quitar
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-violet-500 border-t-transparent" />
        </div>
      ) : loans.length === 0 ? (
        <EmptyState message="No hay préstamos con los filtros actuales" />
      ) : (
        <Table
          columns={[
            { key: 'seller', label: 'Vendedor' },
            { key: 'product', label: 'Producto' },
            { key: 'qty', label: 'Entregado / Total', align: 'center' },
            { key: 'from', label: 'Entrega' },
            { key: 'due', label: 'Límite' },
            { key: 'status', label: 'Estado', align: 'center' },
            { key: 'actions', label: 'Acciones', align: 'center' },
          ]}
        >
          {loans.map((loan) => (
            <tr key={loan.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3">
                <p className="font-medium text-slate-100">{loan.seller}</p>
                {loan.phone && <p className="text-xs text-slate-500">{loan.phone}</p>}
              </td>
              <td className="px-4 py-3">
                <p className="text-slate-300">{loan.product_name}</p>
                {loan.location_out && (
                  <span className="mt-0.5 inline-block rounded-md bg-violet-500/10 px-1.5 py-0.5 text-[11px] text-violet-300">
                    Salida: {loan.location_out}
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-center">
                <span className="font-mono text-sm font-bold text-slate-200">
                  {loan.returned_qty} / {loan.quantity}
                </span>
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(loan.loan_date).toLocaleDateString()}</td>
              <td className={`px-4 py-3 text-xs font-medium ${loan.overdue ? 'text-red-400' : 'text-slate-300'}`}>{loan.due_date}</td>
              <td className="px-4 py-3 text-center">
                <Badge status={loan.status} />
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap justify-center gap-1">
                  <button
                    onClick={() => openEdit(loan)}
                    className="rounded-lg bg-slate-500/10 p-2 text-slate-300 transition hover:bg-slate-500/25"
                    title="Editar préstamo"
                  >
                    ✏️
                  </button>
                  {!loan.completed && (
                    <button
                      onClick={() => {
                        setReturnTarget(loan)
                        setReturnQty(loan.pending)
                        setReturnLocation(loan.location_out || '')
                        getProducts()
                          .then((p) => setReturnProducts(p))
                          .catch(() => setReturnProducts([]))
                      }}
                      className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400 transition hover:bg-emerald-500/20"
                      title="Registrar devolución"
                    >
                      📥
                    </button>
                  )}
                  {!loan.completed && (
                    <button
                      onClick={() => setExtendTarget(loan)}
                      className="rounded-lg bg-amber-500/10 p-2 text-amber-400 transition hover:bg-amber-500/20"
                      title="Dar prórroga"
                    >
                      ⏳
                    </button>
                  )}
                  <button
                    onClick={() => openAuthenticatedUrl(`/reports/loan-ticket/${loan.id}`)}
                    className="rounded-lg bg-blue-500/10 p-2 text-blue-400 transition hover:bg-blue-500/20"
                    title="Comprobante PDF"
                  >
                    📄
                  </button>
                  {loan.phone && (
                    <button
                      onClick={() =>
                        window.open(
                          `https://wa.me/${loan.phone}?text=${encodeURIComponent('Recordatorio: tu préstamo de ' + loan.product_name + ' vence el ' + loan.due_date)}`,
                          '_blank',
                        )
                      }
                      className="rounded-lg bg-green-500/10 p-2 text-green-400 transition hover:bg-green-500/20"
                      title="Enviar recordatorio WhatsApp"
                    >
                      💬
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {/* Modal registrar préstamo */}
      <Modal open={registerOpen} onClose={() => setRegisterOpen(false)} title="Registrar préstamo" wide>
        <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Producto">
            <Select value={form.product_id} onChange={(e) => setForm({ ...form, product_id: e.target.value })} required>
              <option value="">Selecciona un producto...</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {p.name} (stock: {p.stock})
                </option>
              ))}
            </Select>
          </Field>
          {(selectedProduct?.locations || []).length > 0 && (
            <Field label="Ubicación de salida">
              <Select value={form.location_out} onChange={(e) => setForm({ ...form, location_out: e.target.value })} required>
                <option value="">¿De dónde sale?</option>
                {selectedProduct.locations.map((l) => (
                  <option key={l.location} value={l.location}>
                    {l.location} (disponible: {l.quantity})
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Cantidad a prestar">
            <Input type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} required />
          </Field>
          <Field label="Vendedor">
            <Input value={form.seller} onChange={(e) => setForm({ ...form, seller: e.target.value })} placeholder="Nombre completo" required />
          </Field>
          <Field label="Teléfono (WhatsApp)">
            <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Ej: 18091234567" />
          </Field>
          <Field label="Fecha de devolución">
            <Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} required />
          </Field>
          <Field label="Nota (opcional)">
            <Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </Field>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={() => setRegisterOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant="success" disabled={saving}>
              {saving ? 'Registrando...' : 'Finalizar y generar ticket'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Modal editar préstamo */}
      <Modal open={Boolean(editTarget)} onClose={() => setEditTarget(null)} title={`Editar préstamo · ${editTarget?.seller || ''}`} wide>
        {editForm && (
          <form onSubmit={handleEdit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {editLocked && (
              <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-300 sm:col-span-2">
                ⚠️ Este préstamo ya tiene devoluciones; no se puede cambiar el producto ni la cantidad.
              </p>
            )}
            <Field label="Producto">
              <Select
                value={editForm.product_id}
                onChange={(e) => setEditForm({ ...editForm, product_id: e.target.value })}
                disabled={editLocked}
                required
              >
                <option value="">Selecciona un producto...</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} — {p.name} (stock: {p.stock})
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Cantidad prestada">
              <Input
                type="number"
                min="1"
                value={editForm.quantity}
                onChange={(e) => setEditForm({ ...editForm, quantity: e.target.value })}
                disabled={editLocked}
                required
              />
            </Field>
            <Field label="Ubicación de salida">
              <Select
                value={editForm.location_out}
                onChange={(e) => setEditForm({ ...editForm, location_out: e.target.value })}
                disabled={editLocked}
              >
                <option value="">Sin ubicación</option>
                {editForm.product_id &&
                  (products.find((p) => String(p.id) === String(editForm.product_id))?.locations || []).map((l) => (
                    <option key={l.location} value={l.location}>
                      {l.location} (disponible: {l.quantity})
                    </option>
                  ))}
              </Select>
            </Field>
            <Field label="Vendedor">
              <Input value={editForm.seller} onChange={(e) => setEditForm({ ...editForm, seller: e.target.value })} required />
            </Field>
            <Field label="Teléfono (WhatsApp)">
              <Input value={editForm.phone} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} placeholder="Ej: 18091234567" />
            </Field>
            <Field label="Fecha de devolución">
              <Input type="date" value={editForm.due_date} onChange={(e) => setEditForm({ ...editForm, due_date: e.target.value })} required />
            </Field>
            <Field label="Nota (opcional)">
              <Input value={editForm.note} onChange={(e) => setEditForm({ ...editForm, note: e.target.value })} />
            </Field>
            <div className="flex justify-end gap-2 sm:col-span-2">
              <Button type="button" variant="ghost" onClick={() => setEditTarget(null)}>
                Cancelar
              </Button>
              <Button type="submit" variant="success" disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar cambios'}
              </Button>
            </div>
          </form>
        )}
      </Modal>

      {/* Modal devolución */}
      <Modal open={Boolean(returnTarget)} onClose={() => setReturnTarget(null)} title="Registrar devolución">
        {returnTarget && (
          <div className="space-y-4">
            <p className="text-sm text-slate-300">
              Devolución de <span className="font-bold">{returnTarget.seller}</span> · {returnTarget.product_name}
              <br />
              <span className="text-slate-500">Pendiente por devolver: {returnTarget.pending} unidades</span>
            </p>
            <Field label="Cantidad que entrega hoy">
              <Input type="number" min="1" max={returnTarget.pending} value={returnQty} onChange={(e) => setReturnQty(e.target.value)} />
            </Field>
            <Field label="Ubicación donde se recibe">
              <Select value={returnLocation} onChange={(e) => setReturnLocation(e.target.value)}>
                <option value="">Misma de salida ({returnTarget.location_out || '—'})</option>
                {returnTarget.location_out && <option value={returnTarget.location_out}>{returnTarget.location_out}</option>}
                {(returnProducts
                  .find((p) => String(p.id) === String(returnTarget.product_id))
                  ?.locations || [])
                  .map((l) => (
                    <option key={l.location} value={l.location}>
                      {l.location} (disponible: {l.quantity})
                    </option>
                  ))}
              </Select>
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setReturnTarget(null)}>
                Cancelar
              </Button>
              <Button variant="success" onClick={handleReturn} disabled={saving}>
                Confirmar entrega
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Modal prórroga */}
      <Modal open={Boolean(extendTarget)} onClose={() => setExtendTarget(null)} title="Dar prórroga">
        {extendTarget && (
          <div className="space-y-4">
            <p className="text-sm text-slate-300">
              Prórroga para <span className="font-bold">{extendTarget.seller}</span> · vence el{' '}
              <span className="font-semibold text-amber-400">{extendTarget.due_date}</span>
            </p>
            <Field label="Días adicionales">
              <Input type="number" min="1" max="365" value={extendDays} onChange={(e) => setExtendDays(e.target.value)} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setExtendTarget(null)}>
                Cancelar
              </Button>
              <Button variant="warning" onClick={handleExtend} disabled={saving}>
                Aplicar prórroga
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
