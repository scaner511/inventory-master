import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { createLoan, extendLoan, getLoans, getProducts, returnLoan, updateLoan } from '../api/index.js'
import { openAuthenticatedUrl } from '../api/client.js'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import Badge from '../components/ui/Badge.jsx'
import BarcodeScanner from '../components/BarcodeScanner.jsx'
import { Button, Field, Input, Select } from '../components/ui/Form.jsx'

const EMPTY_FORM = { seller: '', phone: '', due_date: '', note: '' }

function findProductByCode(list, code) {
  const clean = String(code || '').trim().toLowerCase()
  return list.find((p) => String(p.code || '').trim().toLowerCase() === clean)
}

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
  const [returnSel, setReturnSel] = useState({}) // { [itemId]: { checked, qty, location } }
  const [scanTarget, setScanTarget] = useState(null) // 'loan' | 'return'
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
    const sel = {}
    pendingItems.forEach((it) => {
      sel[it.id] = { checked: pendingItems.length === 1, qty: it.pending, location: it.location_out || '' }
    })
    setReturnTarget(loan)
    setReturnSel(sel)
    getProducts()
      .then((p) => setReturnProducts(p))
      .catch(() => setReturnProducts([]))
  }

  const pendingReturnItems = returnTarget ? returnTarget.items.filter((i) => i.pending > 0) : []
  const selectedReturnItems = pendingReturnItems.filter((i) => returnSel[i.id]?.checked)
  const allReturnSelected =
    pendingReturnItems.length > 0 && selectedReturnItems.length === pendingReturnItems.length

  function updateReturnSel(itemId, patch) {
    setReturnSel((prev) => ({ ...prev, [itemId]: { ...prev[itemId], ...patch } }))
  }

  function toggleAllReturn(checked) {
    setReturnSel((prev) => {
      const next = { ...prev }
      pendingReturnItems.forEach((it) => {
        next[it.id] = { ...next[it.id], checked }
      })
      return next
    })
  }

  async function handleReturn() {
    if (!returnTarget) return
    if (selectedReturnItems.length === 0) {
      return toast.error('Selecciona al menos un producto a devolver')
    }
    for (const it of selectedReturnItems) {
      const qty = Number(returnSel[it.id]?.qty)
      if (!qty || qty < 1 || qty > it.pending) {
        return toast.error(`La cantidad de "${it.product_name}" debe estar entre 1 y ${it.pending}`)
      }
    }
    setSaving(true)
    let done = 0
    try {
      for (const it of selectedReturnItems) {
        const sel = returnSel[it.id]
        await returnLoan(returnTarget.id, it.id, Number(sel.qty), sel.location)
        done += 1
      }
      toast.success(done === 1 ? 'Devolución registrada' : `Devolución registrada (${done} productos)`)
      setReturnTarget(null)
    } catch {
      /* interceptor */
      if (done > 0) {
        toast(`Se registraron ${done} de ${selectedReturnItems.length} productos`, { icon: '⚠️' })
        setReturnTarget(null)
      }
    } finally {
      setSaving(false)
      if (done > 0) load()
    }
  }

  function handleScanCode(code) {
    const target = scanTarget
    setScanTarget(null)
    if (target === 'loan') {
      const p = findProductByCode(products, code)
      if (!p) {
        setProductSearch(code)
        return toast.error(`No se encontró ningún producto con el código "${code}"`)
      }
      const existing = cart.find((it) => String(it.product_id) === String(p.id))
      if (existing) {
        updateCartItem(existing.key, { quantity: (Number(existing.quantity) || 0) + 1 })
      } else {
        addToCart(p.id)
      }
      toast.success(`Agregado: ${p.name}`)
    } else if (target === 'return' && returnTarget) {
      const p = findProductByCode(returnProducts, code)
      const it = p && pendingReturnItems.find((i) => String(i.product_id) === String(p.id))
      if (!it) return toast.error(`El código "${code}" no está pendiente en este préstamo`)
      updateReturnSel(it.id, { checked: true })
      toast.success(`Seleccionado: ${it.product_name}`)
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

    if (editLocked) {
      // Con devoluciones solo se permite cambiar la ubicación de salida.
      for (const it of editForm.items) {
        const old = editTarget.items.find((o) => o.id === it.id)
        if (old && (Number(it.product_id) !== old.product_id || Number(it.quantity) !== old.quantity)) {
          return toast.error('No puedes cambiar el producto ni la cantidad porque el préstamo ya tiene devoluciones')
        }
      }
      const newLocked = JSON.stringify(
        editForm.items.map((it) => ({
          product_id: Number(it.product_id),
          quantity: Number(it.quantity),
          location_out: it.location_out || null,
        })),
      )
      const oldLocked = JSON.stringify(
        editTarget.items.map((it) => ({
          product_id: Number(it.product_id),
          quantity: Number(it.quantity),
          location_out: it.location_out || null,
        })),
      )
      if (newLocked !== oldLocked) {
        payload.items = editForm.items.map((it) => ({
          id: it.id,
          product_id: Number(it.product_id),
          quantity: Number(it.quantity),
          location_out: it.location_out || null,
        }))
      }
    } else {
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
      const payloadItems = validItems.map((it) => ({
        id: it.id,
        product_id: Number(it.product_id),
        quantity: Number(it.quantity),
        location_out: it.location_out || null,
      }))
      const newItems = JSON.stringify(payloadItems)
      const oldItems = JSON.stringify(
        editTarget.items.map((it) => ({
          product_id: Number(it.product_id),
          quantity: Number(it.quantity),
          location_out: it.location_out || null,
        })),
      )
      if (newItems !== oldItems) {
        payload.items = payloadItems
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
          <div className="flex items-end gap-2">
            <div className="min-w-0 flex-1">
              <Field label="Buscar producto">
                <Input
                  type="text"
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                  placeholder="🔍 Buscar producto..."
                />
              </Field>
            </div>
            <Button type="button" variant="ghost" onClick={() => setScanTarget('loan')}>
              📷 Escanear
            </Button>
          </div>

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
                      <div className="flex items-center gap-2">
                        <div className="min-w-0 flex-1">
                          {hasLocations ? (
                            <Select
                              value={it.location_out}
                              onChange={(e) => updateCartItem(it.key, { location_out: e.target.value })}
                              required
                              aria-label="Ubicación de salida"
                            >
                              <option value="">¿Ubicación de salida?</option>
                              {p.locations.map((l) => (
                                <option key={l.location} value={l.location}>
                                  {l.location} (disponible: {l.quantity})
                                </option>
                              ))}
                            </Select>
                          ) : (
                            <Input
                              type="text"
                              value={it.location_out}
                              onChange={(e) => updateCartItem(it.key, { location_out: e.target.value })}
                              placeholder="Ubicación de salida (opcional)"
                              aria-label="Ubicación de salida"
                            />
                          )}
                        </div>
                        <button
                          type="button"
                          onClick={() => removeCartItem(it.key)}
                          className="rounded-md bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                          title="Quitar producto"
                        >
                          ✕
                        </button>
                      </div>
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
                ⚠️ Este préstamo ya tiene devoluciones: no se pueden cambiar los productos ni las cantidades, pero sí la
                ubicación de salida.
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
                        <div className="min-w-0 flex-1">
                          {hasLocations ? (
                            <Select
                              value={it.location_out}
                              onChange={(e) => updateEditItem(it.key, { location_out: e.target.value })}
                              required
                              aria-label="Ubicación de salida"
                            >
                              <option value="">¿Ubicación de salida?</option>
                              {p.locations.map((l) => (
                                <option key={l.location} value={l.location}>
                                  {l.location} (disponible: {l.quantity})
                                </option>
                              ))}
                            </Select>
                          ) : (
                            <Input
                              type="text"
                              value={it.location_out}
                              onChange={(e) => updateEditItem(it.key, { location_out: e.target.value })}
                              placeholder="Ubicación de salida (opcional)"
                              aria-label="Ubicación de salida"
                            />
                          )}
                        </div>
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
            <div className="flex items-center justify-between gap-2">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={allReturnSelected}
                  onChange={(e) => toggleAllReturn(e.target.checked)}
                  className="h-4 w-4 accent-emerald-500"
                />
                Seleccionar todos
              </label>
              <Button type="button" variant="ghost" onClick={() => setScanTarget('return')}>
                📷 Escanear
              </Button>
            </div>
            <div className="max-h-[50vh] space-y-2 overflow-y-auto">
              {pendingReturnItems.map((it) => {
                const sel = returnSel[it.id] || {}
                const productLocations =
                  returnProducts.find((p) => String(p.id) === String(it.product_id))?.locations || []
                return (
                  <div
                    key={it.id}
                    className={`rounded-lg border p-3 ${
                      sel.checked ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-slate-700/60'
                    }`}
                  >
                    <label className="flex items-center gap-2 text-sm text-slate-200">
                      <input
                        type="checkbox"
                        checked={Boolean(sel.checked)}
                        onChange={(e) => updateReturnSel(it.id, { checked: e.target.checked })}
                        className="h-4 w-4 accent-emerald-500"
                      />
                      <span className="flex-1">{it.product_name}</span>
                      <span className="text-xs text-slate-500">pendiente: {it.pending}</span>
                    </label>
                    {sel.checked && (
                      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <Field label="Cantidad que entrega hoy">
                          <Input
                            type="number"
                            min="1"
                            max={it.pending}
                            value={sel.qty}
                            onChange={(e) => updateReturnSel(it.id, { qty: e.target.value })}
                          />
                        </Field>
                        <Field label="Ubicación donde se recibe">
                          <Select
                            value={sel.location}
                            onChange={(e) => updateReturnSel(it.id, { location: e.target.value })}
                          >
                            <option value="">Misma de salida ({it.location_out || '—'})</option>
                            {it.location_out && <option value={it.location_out}>{it.location_out}</option>}
                            {productLocations.map((l) => (
                              <option key={l.location} value={l.location}>
                                {l.location} (disponible: {l.quantity})
                              </option>
                            ))}
                          </Select>
                        </Field>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setReturnTarget(null)}>
                Cancelar
              </Button>
              <Button variant="success" onClick={handleReturn} disabled={saving || selectedReturnItems.length === 0}>
                {saving ? 'Registrando...' : `Confirmar entrega (${selectedReturnItems.length})`}
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

      <BarcodeScanner open={scanTarget !== null} onClose={() => setScanTarget(null)} onCode={handleScanCode} />
    </div>
  )
}