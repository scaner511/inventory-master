import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { createLoan, extendLoan, getLoans, getProducts, returnLoan, updateLoan } from '../api/index.js'
import { openAuthenticatedUrl } from '../api/client.js'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import Badge from '../components/ui/Badge.jsx'
import { Button, Field, Input, Select } from '../components/ui/Form.jsx'

const EMPTY_FORM = { seller: '', phone: '', due_date: '', note: '' }

function loanTotals(loan) {
  const quantity = loan.items.reduce((s, i) => s + i.quantity, 0)
  const returned = loan.items.reduce((s, i) => s + i.returned_qty, 0)
  return { quantity, returned, pending: quantity - returned }
}

export default function Loans() {
  const [loans, setLoans] = useState([])
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [dateFilter, setDateFilter] = useState('')
  const [loading, setLoading] = useState(true)

  const [registerOpen, setRegisterOpen] = useState(false)
  const [products, setProducts] = useState([])
  const [productSearch, setProductSearch] = useState('')
  const [cart, setCart] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const [returnTarget, setReturnTarget] = useState(null)
  const [returnItemId, setReturnItemId] = useState(null)
  const [returnQty, setReturnQty] = useState(1)
  const [returnLocation, setReturnLocation] = useState('')
  const [returnProducts, setReturnProducts] = useState([])
  const [extendTarget, setExtendTarget] = useState(null)
  const [extendDays, setExtendDays] = useState(7)

  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [editLocked, setEditLocked] = useState(false)
  const [completedOpen, setCompletedOpen] = useState(false)

  const getProduct = useCallback(
    (id) => products.find((p) => String(p.id) === String(id)),
    [products],
  )

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
    setForm(EMPTY_FORM)
    setProductSearch('')
    setCart([])
    getProducts()
      .then((p) => setProducts(p))
      .catch(() => {})
    setRegisterOpen(true)
  }

  function addToCart(productId) {
    const p = getProduct(productId)
    if (!p) return
    setCart((prev) => [
      ...prev,
      { key: `${Date.now()}_${Math.random()}`, product_id: p.id, quantity: 1, location_out: '' },
    ])
  }

  function updateCartItem(key, patch) {
    setCart((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch } : it)))
  }

  function removeCartItem(key) {
    setCart((prev) => prev.filter((it) => it.key !== key))
  }

  const filteredProducts = products.filter((p) => {
    const s = productSearch.trim().toLowerCase()
    if (!s) return true
    return p.code.toLowerCase().includes(s) || p.name.toLowerCase().includes(s)
  })

  const cartTotalQty = cart.reduce((s, it) => s + (Number(it.quantity) || 0), 0)

  function formatLoanDate(value) {
    if (!value) return '—'
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value
    const dd = String(d.getDate()).padStart(2, '0')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    return `${dd}/${mm}/${d.getFullYear()}`
  }

  function buildTicketMessage(loan) {
    const lines = [
      `TICKET DE PRESTAMO No. ${loan.id}`,
      '=====================================',
      '',
      `Vendedor: ${loan.seller}`,
    ]
    loan.items.forEach((it, idx) => {
      lines.push(`${idx + 1}. ${it.product_name} (x${it.quantity})`)
      if (it.location_out) lines.push(`   Ubicación: ${it.location_out}`)
    })
    const t = loanTotals(loan)
    lines.push('')
    lines.push(`Total: ${loan.items.length} producto(s) · ${t.quantity} unidad(es)`)
    lines.push('')
    lines.push(`Fecha del préstamo: ${formatLoanDate(loan.loan_date)}`)
    lines.push(`Fecha de devolución: ${formatLoanDate(loan.due_date)}`)
    if (loan.note) lines.push('', `Nota: ${loan.note}`)
    lines.push('', 'Por favor conserva este ticket y entrega el producto en buen estado dentro de la fecha indicada. Gracias.')
    return lines.join('\n')
  }

  function buildReminderMessage(loan) {
    const items = loan.items.map((it) => `• ${it.product_name} (${it.quantity} unidad(es))`).join('\n')
    return (
      `RECORDATORIO DE DEVOLUCION\n` +
      `=====================================\n\n` +
      `Hola ${loan.seller},\n\n` +
      `Este mensaje es para recordarte que tu préstamo vence el ${formatLoanDate(loan.due_date)}:\n\n${items}\n\n` +
      `Te pedimos devolver los productos en buen estado dentro de esta fecha. Si necesitas una prórroga, contáctanos.\n\nGracias.`
    )
  }

  async function handleCreate(e) {
    e.preventDefault()
    if (cart.length === 0) {
      return toast.error('Agrega al menos un producto al préstamo')
    }
    for (const it of cart) {
      const p = getProduct(it.product_id)
      const qty = Number(it.quantity)
      if (!p || !qty || qty < 1) {
        return toast.error(`Indica una cantidad válida para "${p?.name || 'el producto'}"`)
      }
      if ((p.locations || []).length > 0 && !it.location_out) {
        return toast.error(`Elige la ubicación de dónde sale "${p.name}"`)
      }
    }
    if (!form.seller.trim()) return toast.error('Indica el nombre del vendedor')
    if (!form.due_date) return toast.error('Indica la fecha de devolución')

    setSaving(true)
    try {
      const loan = await createLoan({
        seller: form.seller.trim(),
        phone: form.phone.trim() || null,
        due_date: form.due_date,
        note: form.note.trim() || null,
        items: cart.map((it) => ({
          product_id: Number(it.product_id),
          quantity: Number(it.quantity),
          location_out: it.location_out || null,
        })),
      })
      toast.success('Préstamo registrado correctamente')
      setRegisterOpen(false)
      setCart([])
      load()

      const whatsapp = window.confirm('¿Abrir WhatsApp para notificar al vendedor?')
      if (whatsapp && form.phone.trim()) {
        const msg = encodeURIComponent(buildTicketMessage(loan))
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

  function openReturn(loan) {
    const pendingItems = loan.items.filter((i) => i.pending > 0)
    if (pendingItems.length === 0) return
    const first = pendingItems[0]
    setReturnTarget(loan)
    setReturnItemId(first.id)
    setReturnQty(first.pending)
    setReturnLocation(first.location_out || '')
    getProducts()
      .then((p) => setReturnProducts(p))
      .catch(() => setReturnProducts([]))
  }

  const returnItem = returnTarget?.items.find((i) => i.id === returnItemId)

  async function handleReturn() {
    if (!returnTarget || !returnItem) return
    const qty = Number(returnQty)
    if (!qty || qty < 1 || qty > returnItem.pending) {
      return toast.error(`La cantidad debe estar entre 1 y ${returnItem.pending}`)
    }
    setSaving(true)
    try {
      await returnLoan(returnTarget.id, returnItem.id, qty, returnLocation)
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
    setEditLocked(loan.items.some((i) => i.returned_qty > 0))
    setEditForm({
      seller: loan.seller,
      phone: loan.phone || '',
      due_date: loan.due_date,
      note: loan.note || '',
      items: loan.items.map((i) => ({
        key: `old_${i.id}`,
        id: i.id,
        product_id: i.product_id ?? '',
        quantity: i.quantity,
        location_out: i.location_out || '',
      })),
    })
    getProducts()
      .then((p) => setProducts(p))
      .catch(() => {})
  }

  function addEditItem() {
    setEditForm((f) => ({
      ...f,
      items: [...f.items, { key: `${Date.now()}_${Math.random()}`, id: undefined, product_id: '', quantity: 1, location_out: '' }],
    }))
  }

  function updateEditItem(key, patch) {
    setEditForm((f) => ({ ...f, items: f.items.map((it) => (it.key === key ? { ...it, ...patch } : it)) }))
  }

  function removeEditItem(key) {
    setEditForm((f) => ({ ...f, items: f.items.filter((it) => it.key !== key) }))
  }

  async function handleEdit(e) {
    e.preventDefault()
    if (!editTarget) return
    const payload = {}
    if (editForm.seller.trim() && editForm.seller.trim() !== editTarget.seller) payload.seller = editForm.seller.trim()
    if (editForm.phone.trim() !== (editTarget.phone || '')) payload.phone = editForm.phone.trim() || null
    if (editForm.due_date && editForm.due_date !== editTarget.due_date) payload.due_date = editForm.due_date
    if (editForm.note.trim() !== (editTarget.note || '')) payload.note = editForm.note.trim() || null

    if (!editLocked) {
      const validItems = editForm.items.filter((it) => it.product_id && Number(it.quantity) >= 1)
      if (validItems.length === 0) {
        return toast.error('El préstamo debe tener al menos un producto con cantidad válida')
      }
      for (const it of validItems) {
        const p = getProduct(it.product_id)
        if ((p?.locations || []).length > 0 && !it.location_out) {
          return toast.error(`Elige la ubicación de dónde sale "${p.name}"`)
        }
      }
      const normalized = (items) =>
        JSON.stringify(
          items.map((it) => ({
            product_id: Number(it.product_id),
            quantity: Number(it.quantity),
            location_out: it.location_out || null,
          })),
        )
      const oldItems = normalized(editTarget.items)
      const newItems = normalized(validItems)
      if (oldItems !== newItems) {
        payload.items = validItems.map((it) => ({
          id: it.id,
          product_id: Number(it.product_id),
          quantity: Number(it.quantity),
          location_out: it.location_out || null,
        }))
      }
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

  function renderLoanTable(rows) {
    return (
      <Table
        columns={[
          { key: 'seller', label: 'Vendedor' },
          { key: 'product', label: 'Productos' },
          { key: 'qty', label: 'Entregado / Total', align: 'center' },
          { key: 'from', label: 'Entrega' },
          { key: 'due', label: 'Límite' },
          { key: 'status', label: 'Estado', align: 'center' },
          { key: 'actions', label: 'Acciones', align: 'center' },
        ]}
      >
        {rows.map((loan) => {
          const totals = loanTotals(loan)
          return (
            <tr key={loan.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3">
                <p className="font-medium text-slate-100">{loan.seller}</p>
                {loan.phone && <p className="text-xs text-slate-500">{loan.phone}</p>}
              </td>
              <td className="px-4 py-3">
                <div className="space-y-1">
                  {loan.items.map((it) => (
                    <div key={it.id}>
                      <p className="text-slate-300">
                        {it.product_name} <span className="text-slate-500">×{it.quantity}</span>
                        {it.completed && <span className="ml-1 text-[11px] text-emerald-400">devuelto</span>}
                      </p>
                      {it.location_out && (
                        <span className="mt-0.5 inline-block rounded-md bg-violet-500/10 px-1.5 py-0.5 text-[11px] text-violet-300">
                          Salida: {it.location_out}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </td>
              <td className="px-4 py-3 text-center">
                <span className="font-mono text-sm font-bold text-slate-200">
                  {totals.returned} / {totals.quantity}
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
                      onClick={() => openReturn(loan)}
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
                          `https://wa.me/${loan.phone}?text=${encodeURIComponent(buildReminderMessage(loan))}`,
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
          )
        })}
      </Table>
    )
  }

  const completedOnly = status === 'COMPLETADO'
  const activeLoans = loans.filter((l) => !l.completed)
  const completedLoans = loans.filter((l) => l.completed)

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
        <>
          {completedOnly ? (
            renderLoanTable(loans)
          ) : activeLoans.length === 0 ? (
            <p className="rounded-lg border border-slate-700/60 px-4 py-6 text-center text-sm text-slate-400">
              No hay préstamos activos; todos han sido devueltos.
            </p>
          ) : (
            renderLoanTable(activeLoans)
          )}

          {!completedOnly && completedLoans.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-slate-700/60">
              <button
                type="button"
                onClick={() => setCompletedOpen((v) => !v)}
                className="flex w-full items-center justify-between gap-2 bg-slate-800/60 px-4 py-3 text-left transition hover:bg-slate-800"
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                  <span className="text-emerald-400">✅</span> Préstamos completados ({completedLoans.length})
                </span>
                <span className="text-slate-400">{completedOpen ? '▾ Cerrar' : '▸ Abrir'}</span>
              </button>
              {completedOpen && (
                <div className="max-h-[28rem] overflow-y-auto">{renderLoanTable(completedLoans)}</div>
              )}
            </div>
          )}
        </>
      )}

      {/* Modal registrar préstamo */}
      <Modal open={registerOpen} onClose={() => setRegisterOpen(false)} title="Registrar préstamo" wide>
        <form onSubmit={handleCreate} className="space-y-4">
          <Field label="Buscar producto">
            <Input
              type="text"
              value={productSearch}
              onChange={(e) => setProductSearch(e.target.value)}
              placeholder="🔍 Buscar producto..."
            />
          </Field>

          {filteredProducts.length > 0 && (
            <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-slate-700/60 p-2">
              {filteredProducts.slice(0, 8).map((p) => (
                <button
                  type="button"
                  key={p.id}
                  onClick={() => addToCart(p.id)}
                  className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left transition hover:bg-slate-700/40"
                >
                  <span className="text-sm text-slate-200">
                    <span className="font-mono text-violet-300">{p.code}</span> — {p.name}
                  </span>
                  <span className="ml-2 shrink-0 rounded-md bg-violet-500/10 px-1.5 py-0.5 text-[11px] text-violet-300">
                    + Agregar · stock {p.stock}
                  </span>
                </button>
              ))}
            </div>
          )}
          {productSearch.trim() && filteredProducts.length === 0 && (
            <p className="text-xs text-red-400">No se encontró ningún producto</p>
          )}

          {cart.length > 0 && (
            <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-semibold text-violet-300">
                  Productos seleccionados ({cart.length})
                </p>
                <p className="text-xs text-slate-400">{cartTotalQty} unidad(es) en total</p>
              </div>
              <div className="space-y-2">
                {cart.map((it) => {
                  const p = getProduct(it.product_id)
                  const hasLocations = (p?.locations || []).length > 0
                  return (
                    <div key={it.key} className="grid grid-cols-1 gap-2 rounded-md bg-slate-800/50 p-2 sm:grid-cols-[1fr_80px_auto]">
                      <div>
                        <p className="text-sm text-slate-200">{p?.name}</p>
                        <p className="text-xs text-slate-500">
                          {p?.code} · stock disponible: {p?.stock}
                        </p>
                      </div>
                      <Input
                        type="number"
                        min="1"
                        value={it.quantity}
                        onChange={(e) => updateCartItem(it.key, { quantity: e.target.value })}
                        aria-label={`Cantidad de ${p?.name || 'producto'}`}
                      />
                      {hasLocations ? (
                        <div className="flex items-center gap-2">
                          <Select
                            value={it.location_out}
                            onChange={(e) => updateCartItem(it.key, { location_out: e.target.value })}
                            required
                            aria-label="Ubicación de salida"
                            className="flex-1"
                          >
                            <option value="">¿Ubicación de salida?</option>
                            {p.locations.map((l) => (
                              <option key={l.location} value={l.location}>
                                {l.location} (disponible: {l.quantity})
                              </option>
                            ))}
                          </Select>
                          <button
                            type="button"
                            onClick={() => removeCartItem(it.key)}
                            className="rounded-md bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                            title="Quitar producto"
                          >
                            ✕
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => removeCartItem(it.key)}
                          className="rounded-md bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                          title="Quitar producto"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
          </div>

          <div className="flex justify-end gap-2">
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
          <form onSubmit={handleEdit} className="space-y-4">
            {editLocked && (
              <p className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-300">
                ⚠️ Este préstamo ya tiene devoluciones; no se pueden cambiar los productos ni las cantidades.
              </p>
            )}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
            </div>

            <div className="rounded-lg border border-slate-700/60 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-200">Productos del préstamo</p>
                {!editLocked && (
                  <Button type="button" variant="ghost" onClick={addEditItem} className="!px-2 !py-1 text-xs">
                    + Agregar producto
                  </Button>
                )}
              </div>
              <div className="space-y-2">
                {editForm.items.map((it) => {
                  const p = getProduct(it.product_id)
                  const hasLocations = (p?.locations || []).length > 0
                  return (
                    <div key={it.key} className="grid grid-cols-1 gap-2 rounded-md bg-slate-800/50 p-2 sm:grid-cols-[1fr_90px_auto]">
                      <Select
                        value={it.product_id}
                        onChange={(e) => updateEditItem(it.key, { product_id: e.target.value, location_out: '' })}
                        disabled={editLocked}
                        required
                        aria-label="Producto"
                      >
                        <option value="">Selecciona un producto...</option>
                        {products.map((pp) => (
                          <option key={pp.id} value={pp.id}>
                            {pp.code} — {pp.name} (stock: {pp.stock})
                          </option>
                        ))}
                      </Select>
                      <Input
                        type="number"
                        min="1"
                        value={it.quantity}
                        onChange={(e) => updateEditItem(it.key, { quantity: e.target.value })}
                        disabled={editLocked}
                        required
                        aria-label="Cantidad"
                      />
                      <div className="flex items-center gap-2">
                        {hasLocations ? (
                          <Select
                            value={it.location_out}
                            onChange={(e) => updateEditItem(it.key, { location_out: e.target.value })}
                            disabled={editLocked}
                            required
                            aria-label="Ubicación de salida"
                            className="flex-1"
                          >
                            <option value="">¿Ubicación de salida?</option>
                            {p.locations.map((l) => (
                              <option key={l.location} value={l.location}>
                                {l.location} (disponible: {l.quantity})
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <span className="text-xs text-slate-500 flex-1">Sin ubicaciones</span>
                        )}
                        {!editLocked && (
                          <button
                            type="button"
                            onClick={() => removeEditItem(it.key)}
                            className="rounded-md bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                            title="Quitar producto"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="flex justify-end gap-2">
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
              Devolución de <span className="font-bold">{returnTarget.seller}</span> · vence el{' '}
              <span className="font-semibold text-amber-400">{returnTarget.due_date}</span>
            </p>
            <Field label="Producto a devolver">
              <Select
                value={String(returnItemId)}
                onChange={(e) => {
                  const id = Number(e.target.value)
                  const it = returnTarget.items.find((i) => i.id === id)
                  if (it) {
                    setReturnItemId(id)
                    setReturnQty(it.pending)
                    setReturnLocation(it.location_out || '')
                  }
                }}
              >
                {returnTarget.items
                  .filter((i) => i.pending > 0)
                  .map((it) => (
                    <option key={it.id} value={it.id}>
                      {it.product_name} (pendiente: {it.pending})
                    </option>
                  ))}
              </Select>
            </Field>
            {returnItem && (
              <p className="text-xs text-slate-500">Pendiente por devolver: {returnItem.pending} unidades</p>
            )}
            <Field label="Cantidad que entrega hoy">
              <Input
                type="number"
                min="1"
                max={returnItem?.pending || 1}
                value={returnQty}
                onChange={(e) => setReturnQty(e.target.value)}
              />
            </Field>
            <Field label="Ubicación donde se recibe">
              <Select value={returnLocation} onChange={(e) => setReturnLocation(e.target.value)}>
                <option value="">Misma de salida ({returnItem?.location_out || '—'})</option>
                {returnItem?.location_out && <option value={returnItem.location_out}>{returnItem.location_out}</option>}
                {(returnProducts.find((p) => String(p.id) === String(returnItem?.product_id))?.locations || []).map((l) => (
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