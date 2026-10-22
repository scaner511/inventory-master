import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Modal from './ui/Modal.jsx'
import { Button, Field, Input, Select } from './ui/Form.jsx'
import { getAiConfig } from '../api/index.js'
import { extractDocument, isAccepted, matchRows, parseDocumentRows } from '../ocr/index.js'

// Umbral de confianza a partir del cual pedimos verificación manual.
const CONFIDENCE_WARN = 80

const EMPTY_ROW = { code: '', description: '', quantity: 1, pallets: 0, exists: false, product: null, ok: true }

/**
 * Flujo de "Recepción Inteligente": sube imagen/PDF, corre OCR, muestra una
 * tabla editable para validar y devuelve las filas mediante `onApply`.
 *
 * @param mode 'inventory' => código+nombre+cantidad (inventario normal)
 *             'storage'   => código+descripción+cantidad+tarimas (terceros)
 * @param products catálogo para detectar productos existentes
 * @param onApply(rows) entrega las filas validadas
 */
export default function SmartReceptionModal({ open, onClose, mode = 'inventory', products = [], onApply }) {
  const fileRef = useRef(null)
  const cameraRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [statusText, setStatusText] = useState('')
  const [confidence, setConfidence] = useState(null)
  const [rawText, setRawText] = useState('')
  const [engine, setEngine] = useState('')
  const [rows, setRows] = useState([])
  const [fileName, setFileName] = useState('')
  const [previewUrl, setPreviewUrl] = useState('')
  const [showText, setShowText] = useState(false)
  const [aiConfig, setAiConfig] = useState({ enabled: false, provider: 'puter', token: null, model: null })

  const isStorage = mode === 'storage'
  const lowConfidence = confidence !== null && confidence < CONFIDENCE_WARN

  // Carga la config de IA del cliente (habilitada por el Super Admin).
  useEffect(() => {
    if (!open) return
    getAiConfig()
      .then((cfg) => setAiConfig(cfg || { enabled: false }))
      .catch(() => setAiConfig({ enabled: false, provider: 'puter', token: null, model: null }))
  }, [open])

  const reset = () => {
    setBusy(false)
    setProgress(0)
    setStatusText('')
    setConfidence(null)
    setRawText('')
    setEngine('')
    setRows([])
    setFileName('')
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl('')
    setShowText(false)
  }

  function close() {
    reset()
    onClose()
  }

  async function handleFile(file) {
    if (!file) return
    if (!isAccepted(file)) {
      toast.error('Formato no soportado. Usa JPG, PNG, WEBP o PDF.')
      return
    }
    setBusy(true)
    setRows([])
    setConfidence(null)
    setFileName(file.name)
    if (file.type.startsWith('image/')) {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPreviewUrl(URL.createObjectURL(file))
    } else {
      setPreviewUrl('')
    }
    try {
      const result = await extractDocument(file, {
        engine: aiConfig.enabled ? 'auto' : 'ocr',
        aiProvider: aiConfig.provider || 'puter',
        token: aiConfig.token,
        model: aiConfig.model,
        onProgress: ({ status, progress: p }) => {
          setStatusText(status || '')
          setProgress(Math.round((p || 0) * 100))
        },
      })
      setRawText(result.text || '')
      setConfidence(Math.round(result.confidence || 0))
      setEngine(result.engine || 'ocr')
      // Si la IA ya devolvió filas estructuradas, se usan tal cual.
      const baseRows = result.rows?.length ? result.rows : parseDocumentRows(result.text || '').rows
      const matched = matchRows(baseRows, products).map((r) => ({
        ...r,
        quantity: r.quantity || 1,
        pallets: r.pallets || 0,
        ok: !!(r.code || r.description) && (r.quantity || 0) > 0,
      }))
      if (!matched.length) {
        toast.error('No se detectaron filas. Revisa el texto o agrega filas manualmente.')
        setRows([{ ...EMPTY_ROW }])
      } else {
        setRows(matched)
        toast.success(`${matched.length} fila(s) detectadas`)
      }
    } catch (err) {
      toast.error(err?.message || 'Error al procesar el documento')
    } finally {
      setBusy(false)
      setStatusText('')
      setProgress(0)
    }
  }

  const stats = useMemo(() => {
    const total = rows.length
    const withQty = rows.filter((r) => (r.quantity || 0) > 0).length
    const existing = rows.filter((r) => r.exists).length
    const unknown = total - existing
    const invalid = rows.filter((r) => !r.ok).length
    return { total, withQty, existing, unknown, invalid }
  }, [rows])

  function updateRow(idx, patch) {
    setRows((prev) =>
      prev.map((r, i) => {
        if (i !== idx) return r
        const next = { ...r, ...patch }
        next.ok = !!(next.code || next.description) && (next.quantity || 0) > 0
        return next
      }),
    )
  }

  function addRow() {
    setRows((prev) => [...prev, { ...EMPTY_ROW }])
  }

  function removeRow(idx) {
    setRows((prev) => prev.filter((_, i) => i !== idx))
  }

  function apply() {
    const valid = rows.filter((r) => r.ok)
    if (!valid.length) {
      toast.error('No hay filas válidas para aplicar.')
      return
    }
    onApply(valid)
    close()
  }

  const fileInputProps = {
    type: 'file',
    accept: 'image/jpeg,image/png,image/webp,application/pdf',
    capture: undefined,
  }

  return (
    <Modal open={open} onClose={close} title="Recepción Inteligente" wide>
      <div className="space-y-4">
        <div className="rounded-xl border border-slate-700 bg-slate-800/40 p-4">
          <p className="text-sm text-slate-300">
            Sube una <span className="text-slate-100">foto, imagen o PDF</span> (remisión, packing slip, factura). El
            sistema detecta código, descripción, cantidad y tarimas. <span className="text-amber-400">Nada se
            guarda</span> hasta que valides y confirmes la tabla.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button type="button" onClick={() => fileRef.current?.click()} disabled={busy}>
              📄 Elegir archivo / PDF
            </Button>
            <Button type="button" variant="ghost" onClick={() => cameraRef.current?.click()} disabled={busy}>
              📷 Tomar foto
            </Button>
            <Button type="button" variant="ghost" onClick={reset} disabled={busy}>
              Limpiar
            </Button>
          </div>
          <input
            ref={fileRef}
            {...fileInputProps}
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
        </div>

        {busy && (
          <div className="space-y-2">
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-slate-400">
              Procesando… {statusText ? `(${statusText}) ` : ''}{progress}%
            </p>
          </div>
        )}

        {fileName && !busy && (
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <span>Archivo: <span className="text-slate-200">{fileName}</span></span>
            {engine === 'ai' ? (
              <span className="rounded-md bg-blue-500/15 px-2 py-0.5 font-semibold text-blue-300">
                🤖 Analizado con IA
              </span>
            ) : confidence !== null ? (
              <span
                className={`rounded-md px-2 py-0.5 font-semibold ${
                  lowConfidence ? 'bg-amber-500/15 text-amber-400' : 'bg-emerald-500/15 text-emerald-400'
                }`}
              >
                Confianza OCR: {confidence}%
              </span>
            ) : null}
            {rawText && (
              <button className="text-blue-400 hover:underline" onClick={() => setShowText((v) => !v)}>
                {showText ? 'Ocultar texto' : 'Ver texto detectado'}
              </button>
            )}
          </div>
        )}

        {(lowConfidence || (engine === 'ai' && rows.length > 0)) && (
          <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
            ⚠️ Verifique los datos antes de guardar.
          </div>
        )}

        {showText && (
          <pre className="max-h-40 overflow-auto rounded-lg border border-slate-700 bg-slate-950 p-3 text-xs text-slate-400">
            {rawText || '(sin texto)'}
          </pre>
        )}

        {previewUrl && (
          <div className="overflow-hidden rounded-lg border border-slate-700">
            <img src={previewUrl} alt="Documento" className="max-h-52 w-full object-contain bg-slate-950" />
          </div>
        )}

        {rows.length > 0 && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="rounded bg-slate-800 px-2 py-0.5">{stats.total} filas</span>
              <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-emerald-400">
                {stats.existing} existentes
              </span>
              <span className="rounded bg-amber-500/15 px-2 py-0.5 text-amber-400">{stats.unknown} nuevos</span>
              {stats.invalid > 0 && (
                <span className="rounded bg-red-500/15 px-2 py-0.5 text-red-400">{stats.invalid} por corregir</span>
              )}
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-sm">
                <thead className="bg-slate-800/60 text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-3 py-2 text-left">Código</th>
                    <th className="px-3 py-2 text-left">{isStorage ? 'Descripción' : 'Nombre'}</th>
                    <th className="px-3 py-2 text-center">Cantidad</th>
                    {isStorage && <th className="px-3 py-2 text-center">Tarimas</th>}
                    <th className="px-3 py-2 text-center">Estado</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, idx) => (
                    <tr key={idx} className="border-t border-slate-800">
                      <td className="px-3 py-2">
                        <Input
                          value={r.code}
                          onChange={(e) => updateRow(idx, { code: e.target.value })}
                          className="min-w-[7rem] font-mono text-xs"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          value={isStorage ? r.description : r.name || r.description || ''}
                          onChange={(e) =>
                            isStorage
                              ? updateRow(idx, { description: e.target.value })
                              : updateRow(idx, { name: e.target.value, description: e.target.value })
                          }
                          className="min-w-[12rem]"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          type="number"
                          min="1"
                          value={r.quantity}
                          onChange={(e) => updateRow(idx, { quantity: parseInt(e.target.value, 10) || 0 })}
                          className="w-24 text-center"
                        />
                      </td>
                      {isStorage && (
                        <td className="px-3 py-2">
                          <Input
                            type="number"
                            min="0"
                            value={r.pallets}
                            onChange={(e) => updateRow(idx, { pallets: parseInt(e.target.value, 10) || 0 })}
                            className="w-20 text-center"
                          />
                        </td>
                      )}
                      <td className="px-3 py-2 text-center">
                        {r.exists ? (
                          <span className="rounded-md bg-emerald-500/15 px-2 py-1 text-xs font-semibold text-emerald-400">
                            Existente
                          </span>
                        ) : (
                          <span className="rounded-md bg-amber-500/15 px-2 py-1 text-xs font-semibold text-amber-400">
                            Nuevo
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button
                          className="rounded px-2 py-1 text-xs text-red-400 hover:bg-slate-800"
                          onClick={() => removeRow(idx)}
                        >
                          Quitar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Button type="button" variant="ghost" onClick={addRow}>
              + Agregar fila manualmente
            </Button>
          </div>
        )}

        <div className="flex justify-end gap-2 border-t border-slate-800 pt-4">
          <Button type="button" variant="ghost" onClick={close}>
            Cancelar
          </Button>
          <Button type="button" variant="success" onClick={apply} disabled={!rows.some((r) => r.ok)}>
            Aplicar {stats.withQty > 0 ? `(${stats.withQty})` : ''}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
