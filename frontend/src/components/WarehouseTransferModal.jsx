import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Modal from './ui/Modal.jsx'
import { Button, Field, Input, Select } from './ui/Form.jsx'
import { createWarehouseTransfer, getSettings } from '../api/index.js'

export default function WarehouseTransferModal({ open, onClose, products = [], onDone }) {
  const [names, setNames] = useState(['Almacén Principal', 'Vehículo', 'Almacén Secundario'])
  const [fromSlot, setFromSlot] = useState(1)
  const [toSlot, setToSlot] = useState(2)
  const [note, setNote] = useState('')
  const [items, setItems] = useState([]) // { product_id, code, name, quantity, available }
  const [search, setSearch] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    getSettings()
      .then((s) => setNames([s.warehouse1_name || 'Almacén Principal', s.warehouse2_name || 'Vehículo', s.warehouse3_name || 'Almacén Secundario']))
      .catch(() => {})
    setItems([])
    setNote('')
    setSearch('')
  }, [open])

  const availableProducts = useMemo(() => {
    const q = search.trim().toLowerCase()
    const used = new Set(items.map((i) => i.product_id))
    return products.filter((p) => !used.has(p.id) && (!q || (p.code + ' ' + p.name).toLowerCase().includes(q)))
  }, [products, items, search])

  function addItem(p) {
    const slots = Array.isArray(p.stock_slots) ? p.stock_slots : [p.stock || 0, 0, 0]
    const available = Number(slots[fromSlot - 1]) || 0
    setItems((prev) => [...prev, { product_id: p.id, code: p.code, name: p.name, quantity: 1, available }])
  }

  function updateQty(idx, val) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, quantity: val } : it)))
  }

  function removeItem(idx) {
    setItems((prev) => prev.filter((_, i) => i !== idx))
  }

  async function submit() {
    const valid = items.filter((it) => Number(it.quantity) > 0 && Number(it.quantity) <= it.available)
    if (!valid.length) return toast.error('No hay items válidos para transferir')
    if (fromSlot === toSlot) return toast.error('Origen y destino no pueden ser iguales')
    setSaving(true)
    try {
      await createWarehouseTransfer({
        from_slot: fromSlot,
        to_slot: toSlot,
        note: note || null,
        items: valid.map((it) => ({ product_id: it.product_id, quantity: Number(it.quantity) })),
      })
      toast.success('Transferencia realizada')
      onDone?.()
      onClose()
    } catch (e) {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Transferencia entre almacenes" wide>
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Almacén origen">
            <Select value={fromSlot} onChange={(e) => { setFromSlot(Number(e.target.value)); setItems([]) }}>
              {[1, 2, 3].map((s) => (
                <option key={s} value={s} disabled={s === toSlot}>{names[s - 1]}</option>
              ))}
            </Select>
          </Field>
          <Field label="Almacén destino">
            <Select value={toSlot} onChange={(e) => setToSlot(Number(e.target.value))}>
              {[1, 2, 3].map((s) => (
                <option key={s} value={s} disabled={s === fromSlot}>{names[s - 1]}</option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Nota (opcional)">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ej: Marlin se llevó mercancía" />
        </Field>

        <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-3">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Productos a transferir</p>
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar producto por código o nombre..."
            className="mb-2"
          />
          {availableProducts.length > 0 && search.trim() && (
            <div className="mb-3 max-h-40 overflow-auto rounded-lg border border-slate-700 bg-slate-900">
              {availableProducts.slice(0, 8).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => { addItem(p); setSearch('') }}
                  className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-800"
                >
                  <span className="font-mono text-xs text-slate-400">{p.code}</span>
                  <span className="flex-1 px-2 text-slate-200">{p.name}</span>
                  <span className="text-xs text-slate-500">disp: {Array.isArray(p.stock_slots) ? p.stock_slots[fromSlot - 1] : p.stock}</span>
                </button>
              ))}
            </div>
          )}

          {items.length === 0 ? (
            <p className="text-xs text-slate-500">Agrega productos buscándolos arriba.</p>
          ) : (
            <div className="space-y-2">
              {items.map((it, idx) => (
                <div key={it.product_id} className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/40 p-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-200">{it.name}</p>
                    <p className="text-xs text-slate-500">{it.code} · disponible: {it.available}</p>
                  </div>
                  <Input
                    type="number"
                    min="1"
                    max={it.available}
                    value={it.quantity}
                    onChange={(e) => updateQty(idx, e.target.value)}
                    className="w-24 text-center"
                  />
                  <button
                    type="button"
                    onClick={() => removeItem(idx)}
                    className="rounded px-2 py-1 text-xs text-red-400 hover:bg-slate-800"
                  >
                    Quitar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-800 pt-4">
          <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Cancelar</Button>
          <Button type="button" variant="success" onClick={submit} disabled={saving || !items.length}>
            {saving ? 'Transfiriendo...' : 'Confirmar transferencia'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
PY