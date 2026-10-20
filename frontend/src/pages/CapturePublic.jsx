import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  getPublicCaptureSession,
  getPublicCaptureCampaigns,
  selectPublicCampaign,
  publicCaptureSpin,
  publicCheckDuplicate,
  publicCaptureRegister,
  setCaptureToken,
} from '../api/index.js'
import { getCaptureToken } from '../api/index.js'

const COLOR_FALLBACK = ['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#06b6d4']

/* Rueda dibujada en SVG a partir de los segmentos. Se rota con transición
   CSS hacia el índice ganador. */
function Wheel({ segments, rotation, spinning, size = 320 }) {
  const n = Math.max(1, segments.length)
  const seg = 360 / n
  const r = size / 2
  const labelRadius = r * 0.62
  const paths = segments.map((s, i) => {
    const a0 = (i * seg - 90) * (Math.PI / 180)
    const a1 = ((i + 1) * seg - 90) * (Math.PI / 180)
    const x0 = r + r * Math.cos(a0)
    const y0 = r + r * Math.sin(a0)
    const x1 = r + r * Math.cos(a1)
    const y1 = r + r * Math.sin(a1)
    const color = s.color || COLOR_FALLBACK[i % COLOR_FALLBACK.length]
    return (
      <path
        key={s.id ?? i}
        d={`M${r},${r} L${x0},${y0} A${r},${r} 0 0 1 ${x1},${y1} Z`}
        fill={color}
        stroke="#0b1220"
        strokeWidth="2"
      />
    )
  })
  const labels = segments.map((s, i) => {
    const mid = i * seg + seg / 2 - 90
    const rad = (mid * Math.PI) / 180
    const x = r + labelRadius * Math.cos(rad)
    const y = r + labelRadius * Math.sin(rad)
    return (
      <text
        key={`lbl-${s.id ?? i}`}
        x={x}
        y={y}
        fill="#0b1220"
        fontSize={Math.max(10, Math.min(16, 140 / n))}
        fontWeight="700"
        textAnchor="middle"
        dominantBaseline="middle"
      >
        {s.label}
      </text>
    )
  })
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <div
        className="h-full w-full"
        style={{
          transform: `rotate(${rotation}deg)`,
          transition: spinning ? 'transform 4s cubic-bezier(0.17,0.67,0.12,1)' : 'none',
        }}
      >
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {paths}
          {labels}
        </svg>
      </div>
      <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="flex h-16 w-16 items-center justify-center rounded-full border-4 border-white bg-slate-900 text-2xl">
          🎁
        </div>
      </div>
      <div className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2">
        <div className="h-0 w-0 border-x-8 border-t-[16px] border-x-transparent border-t-white drop-shadow" />
      </div>
    </div>
  )
}

export default function CapturePublic() {
  const [params] = useSearchParams()
  const token = params.get('token') || getCaptureToken()

  const [info, setInfo] = useState(null)
  const [error, setError] = useState(null)
  const [phase, setPhase] = useState('idle') // idle | spinning | form | done
  const [segments, setSegments] = useState([])
  const [rotation, setRotation] = useState(0)
  const [spinning, setSpinning] = useState(false)
  const [prize, setPrize] = useState(null)
  const [duplicate, setDuplicate] = useState(null)
  const [saving, setSaving] = useState(false)
  const [campaigns, setCampaigns] = useState([])
  const rotationRef = useRef(0)

  const [form, setForm] = useState({
    full_name: '',
    phone: '',
    address: '',
    marital_status: '',
    knows_brand: '',
    notes: '',
  })

  useEffect(() => {
    if (token) setCaptureToken(token)
  }, [token])

  useEffect(() => {
    if (!token) {
      setError('Falta el código del sorteo.')
      return
    }
    getPublicCaptureSession(token)
      .then((data) => {
        setInfo(data)
        setSegments(data.session ? [] : [])
      })
      .catch(() => setError('Enlace inválido. Pídele a tu administrador el enlace correcto.'))
    getPublicCaptureCampaigns(token)
      .then(setCampaigns)
      .catch(() => {})
  }, [token])

  const chooseCampaign = async (campaignId) => {
    try {
      const updated = await selectPublicCampaign(campaignId || null, token)
      setInfo(updated)
      toast.success('Campaña actualizada')
    } catch {
      /* noop */
    }
  }

  const vendorLabel = useMemo(() => info?.vendor_name || 'Vendedor', [info])

  const spin = async () => {
    if (spinning) return
    try {
      const res = await publicCaptureSpin(token)
      const n = Math.max(1, res.segments.length)
      setSegments(res.segments)
      setPrize(res.prize)
      setSpinning(true)
      // Gira varias vueltas y aterriza en el índice ganador.
      const seg = 360 / n
      const target = 360 * 5 - (res.wheel_index * seg + seg / 2)
      const next = rotationRef.current + target
      rotationRef.current = next
      setRotation(next)
      setTimeout(() => {
        setSpinning(false)
        setPhase('form')
      }, 4200)
    } catch {
      /* noop */
    }
  }

  const onPhoneBlur = async () => {
    if (!form.phone) return
    try {
      const res = await publicCheckDuplicate(form.phone, token)
      setDuplicate(res.exists ? res : null)
    } catch {
      /* noop */
    }
  }

  const submit = async (duplicateChoice) => {
    if (!form.full_name.trim() || !form.phone.trim()) {
      toast.error('Nombre y teléfono son obligatorios')
      return
    }
    setSaving(true)
    try {
      await publicCaptureRegister(
        {
          full_name: form.full_name,
          phone: form.phone,
          address: form.address || null,
          marital_status: form.marital_status || null,
          knows_brand: form.knows_brand === '' ? null : form.knows_brand === 'si',
          notes: form.notes || null,
          prize_id: prize?.id || null,
          duplicate_choice: duplicateChoice || null,
        },
        token,
      )
      setPhase('done')
    } catch (e) {
      if (e?.response?.status === 409) {
        toast.error('Esta persona ya fue registrada.')
      }
      /* el interceptor muestra el error */
    } finally {
      setSaving(false)
    }
  }

  const reset = () => {
    setPhase('idle')
    setPrize(null)
    setDuplicate(null)
    setForm({ full_name: '', phone: '', address: '', marital_status: '', knows_brand: '', notes: '' })
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0b1220] p-6">
        <div className="max-w-md rounded-2xl border border-red-700/50 bg-red-900/10 p-8 text-center">
          <p className="text-lg font-bold text-red-300">No se pudo abrir el sorteo</p>
          <p className="mt-2 text-sm text-slate-400">{error}</p>
        </div>
      </div>
    )
  }

  if (!info) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0b1220]">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0b1220] to-[#0a1a35] p-4 text-slate-100 md:p-8">
      <header className="mx-auto mb-6 max-w-4xl text-center">
        <p className="text-xs uppercase tracking-widest text-blue-400">Sorteo gratis</p>
        <h1 className="text-2xl font-extrabold md:text-3xl">{info.campaign?.name || '¡Gira la ruleta y gana!'}</h1>
        <p className="mt-1 text-sm text-slate-400">
          {vendorLabel}
          {info.location ? ` · ${info.location}` : ''}
        </p>
        {campaigns.length > 0 && (
          <div className="mt-3 flex justify-center">
            <select
              className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-100"
              value={info.campaign?.id || ''}
              onChange={(e) => chooseCampaign(e.target.value)}
            >
              <option value="">Sin campaña</option>
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </header>

      <div className="mx-auto flex max-w-4xl flex-col items-center gap-6">
        {phase === 'idle' && (
          <>
            <Wheel segments={segments} rotation={rotation} spinning={spinning} />
            <button
              onClick={spin}
              disabled={spinning}
              className="rounded-2xl bg-gradient-to-r from-amber-500 to-orange-600 px-12 py-5 text-2xl font-extrabold text-white shadow-2xl shadow-orange-600/30 transition active:scale-95 disabled:opacity-60"
            >
              🎡 GIRAR RULETA
            </button>
          </>
        )}

        {phase === 'form' && (
          <div className="w-full max-w-xl space-y-4 rounded-2xl border border-slate-800 bg-slate-900/70 p-6">
            {prize && (
              <div className="rounded-xl border border-amber-600/40 bg-amber-900/10 p-4 text-center">
                <p className="text-xs uppercase tracking-wide text-amber-300">Resultado</p>
                <p className="text-xl font-extrabold text-amber-200">
                  {prize.is_no_prize ? info.no_prize_message : `¡Ganaste: ${prize.name}!`}
                </p>
              </div>
            )}

            {duplicate?.exists && (
              <div className="rounded-xl border border-amber-600/40 bg-amber-900/10 p-4">
                <p className="text-sm font-semibold text-amber-300">
                  Ya registramos a esta persona anteriormente.
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <PubField label="Nombre completo *">
                <input
                  className={PUBINPUT}
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                />
              </PubField>
              <PubField label="Teléfono *">
                <input
                  className={PUBINPUT}
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  onBlur={onPhoneBlur}
                />
              </PubField>
              <PubField label="Dirección">
                <input className={PUBINPUT} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
              </PubField>
              <PubField label="Estado civil">
                <input className={PUBINPUT} value={form.marital_status} onChange={(e) => setForm({ ...form, marital_status: e.target.value })} />
              </PubField>
              <PubField label="¿Conoce la marca?">
                <select className={PUBINPUT} value={form.knows_brand} onChange={(e) => setForm({ ...form, knows_brand: e.target.value })}>
                  <option value="">Sin especificar</option>
                  <option value="si">Sí</option>
                  <option value="no">No</option>
                </select>
              </PubField>
            </div>
            <PubField label={`Notas (${form.notes.length}/500)`}>
              <textarea
                rows={3}
                maxLength={500}
                className={PUBINPUT}
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </PubField>

            {duplicate?.exists ? (
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => submit('actualizar')}
                  disabled={saving}
                  className="flex-1 rounded-xl bg-blue-600 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  Actualizar datos
                </button>
                <button
                  onClick={() => submit('nueva_interaccion')}
                  disabled={saving}
                  className="flex-1 rounded-xl bg-slate-700 py-3 font-semibold text-white hover:bg-slate-600 disabled:opacity-50"
                >
                  Nueva interacción
                </button>
                <button
                  onClick={reset}
                  className="rounded-xl border border-slate-700 px-4 py-3 font-semibold text-slate-300 hover:bg-slate-800"
                >
                  Cancelar
                </button>
              </div>
            ) : (
              <button
                onClick={() => submit(null)}
                disabled={saving}
                className="w-full rounded-xl bg-emerald-600 py-4 text-lg font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {saving ? 'Guardando…' : 'GUARDAR'}
              </button>
            )}
          </div>
        )}

        {phase === 'done' && (
          <div className="w-full max-w-md space-y-4 rounded-2xl border border-emerald-600/40 bg-emerald-900/10 p-8 text-center">
            <p className="text-4xl">✅</p>
            <p className="text-xl font-extrabold text-emerald-300">¡Registro exitoso!</p>
            <p className="text-sm text-slate-400">¡Gracias por participar! Nos pondremos en contacto contigo.</p>
            <button
              onClick={reset}
              className="mt-2 w-full rounded-xl bg-blue-600 py-3 font-semibold text-white hover:bg-blue-700"
            >
              Participar de nuevo
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

const PUBINPUT =
  'mt-1 w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-3 text-base text-slate-100 focus:border-blue-500 focus:outline-none'

function PubField({ label, children }) {
  return (
    <label className="block text-xs text-slate-400">
      {label}
      {children}
    </label>
  )
}
