import { useEffect, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { getPublicCalculatorStatus, requestPublicCalculatorAccess } from '../api/index.js'
import Calculator from './Calculator.jsx'

const DEVICE_KEY = 'im_calc_device_id'
const LAST_TOKEN_KEY = 'im_calc_last_token'

function getDeviceId() {
  try {
    let id = localStorage.getItem(DEVICE_KEY)
    if (!id) {
      id =
        globalThis.crypto?.randomUUID?.() ||
        `dev-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
      localStorage.setItem(DEVICE_KEY, id)
    }
    return id
  } catch {
    return `dev-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
  }
}

// Nombre legible para que el administrador identifique el equipo que pide acceso.
function describeDevice() {
  const ua = navigator.userAgent || ''
  let platform = 'Dispositivo'
  if (/iPad|Tablet/i.test(ua)) platform = 'Tablet'
  else if (/iPhone/i.test(ua)) platform = 'iPhone'
  else if (/Android/i.test(ua)) platform = 'Android'
  else if (/Windows/i.test(ua)) platform = 'Windows'
  else if (/Macintosh|Mac OS X/i.test(ua)) platform = 'Mac'
  else if (/Linux/i.test(ua)) platform = 'Linux'

  let browser = 'Navegador'
  if (/Edg\//.test(ua)) browser = 'Edge'
  else if (/Chrome\//.test(ua)) browser = 'Chrome'
  else if (/Safari\//.test(ua)) browser = 'Safari'
  else if (/Firefox\//.test(ua)) browser = 'Firefox'

  return `${platform} · ${browser}`.slice(0, 120)
}

function Centered({ children }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0b1220] p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 text-center shadow-xl">
        {children}
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
  )
}

export default function PublicCalculator() {
  const { token } = useParams()
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  let lastToken = null
  try {
    lastToken = localStorage.getItem(LAST_TOKEN_KEY)
  } catch {
    lastToken = null
  }

  useEffect(() => {
    if (!token) return
    try {
      localStorage.setItem(LAST_TOKEN_KEY, token)
    } catch {
      /* almacenamiento no disponible */
    }
  }, [token])

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }
    let cancelled = false
    let timer = null
    const deviceId = getDeviceId()
    const deviceName = describeDevice()

    async function check(claim = false) {
      try {
        const data = claim
          ? await requestPublicCalculatorAccess(token, deviceId, deviceName)
          : await getPublicCalculatorStatus(token, deviceId)
        if (cancelled) return
        setInfo(data)
        setError('')
        setLoading(false)
        if (data.status === 'pending') {
          // Esperando aprobación: consultar con frecuencia (sin reclamar).
          timer = setTimeout(() => check(false), 5000)
        } else if (data.status === 'active') {
          // Revalidar de vez en cuando para detectar revocaciones/liberaciones.
          timer = setTimeout(() => check(false), 120000)
        }
      } catch (err) {
        if (cancelled) return
        setError(err?.message || 'No se pudo abrir el enlace de la calculadora')
        setInfo(null)
        setLoading(false)
      }
    }

    // Solo el primer contacto reclama el enlace; el resto son consultas.
    check(true)
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [token])

  if (!token) {
    // La app instalada (PWA) abre /calculator/public: se reutiliza el último
    // enlace usado en este dispositivo.
    if (lastToken) {
      return <Navigate to={`/calculator/public/${lastToken}`} replace />
    }
    return (
      <Centered>
        <div className="mb-4 text-4xl">🔒</div>
        <h1 className="mb-2 text-xl font-bold text-white">Enlace requerido</h1>
        <p className="text-sm text-slate-400">
          Para usar la calculadora necesitas el enlace público que te compartió tu proveedor.
        </p>
      </Centered>
    )
  }

  if (loading) {
    return (
      <Centered>
        <Spinner />
        <p className="mt-4 text-sm text-slate-400">Verificando enlace…</p>
      </Centered>
    )
  }

  if (error) {
    return (
      <Centered>
        <div className="mb-4 text-4xl">⚠️</div>
        <h1 className="mb-2 text-xl font-bold text-white">No se pudo abrir el enlace</h1>
        <p className="mb-4 text-sm text-slate-400">{error}</p>
        <button
          onClick={() => window.location.reload()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Reintentar
        </button>
      </Centered>
    )
  }

  if (info?.status === 'pending') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">⏳</div>
        <h1 className="mb-2 text-xl font-bold text-white">Solicitud enviada</h1>
        <p className="mb-3 text-sm text-slate-400">
          Este dispositivo está esperando la aprobación del administrador
          {info.tenant_name ? ` de ${info.tenant_name}` : ''}.
        </p>
        <p className="mb-5 text-xs text-slate-500">
          Deja esta ventana abierta: se actualizará automáticamente cuando sea aprobado.
        </p>
        <Spinner />
      </Centered>
    )
  }

  if (info?.status === 'in_use') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">📵</div>
        <h1 className="mb-2 text-xl font-bold text-white">Enlace en uso</h1>
        <p className="text-sm text-slate-400">
          {info.message || 'Este enlace ya está vinculado a otro dispositivo.'}
        </p>
        <p className="mt-3 text-xs text-slate-500">
          Si necesitas usar la calculadora en este equipo, pide al administrador que libere el
          enlace o te cree uno nuevo.
        </p>
      </Centered>
    )
  }

  if (info?.status === 'expired') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">⏰</div>
        <h1 className="mb-2 text-xl font-bold text-white">Enlace vencido</h1>
        <p className="text-sm text-slate-400">
          {info.message || 'Este enlace alcanzó su fecha de vencimiento.'}
        </p>
        {info.expires_at && (
          <p className="mt-3 text-xs text-slate-500">
            Venció el {new Date(info.expires_at).toLocaleString()}
          </p>
        )}
      </Centered>
    )
  }

  if (info?.status === 'revoked') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">🚫</div>
        <h1 className="mb-2 text-xl font-bold text-white">Enlace revocado</h1>
        <p className="text-sm text-slate-400">
          {info.message || 'Este enlace fue revocado por el administrador.'}
        </p>
      </Centered>
    )
  }

  if (info?.status === 'disabled') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">🔒</div>
        <h1 className="mb-2 text-xl font-bold text-white">Calculadora no disponible</h1>
        <p className="text-sm text-slate-400">
          {info.message || 'La calculadora no está habilitada para este cliente.'}
        </p>
      </Centered>
    )
  }

  if (info?.status === 'available') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">🔓</div>
        <h1 className="mb-2 text-xl font-bold text-white">Enlace liberado</h1>
        <p className="text-sm text-slate-400">
          {info.message || 'Este enlace no tiene un dispositivo autorizado.'}
        </p>
        <p className="mt-3 text-xs text-slate-500">
          Si necesitas usarlo en este equipo, recarga la página para enviar una nueva solicitud
          de aprobación.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Solicitar acceso de nuevo
        </button>
      </Centered>
    )
  }

  if (info?.status !== 'active') {
    return (
      <Centered>
        <div className="mb-4 text-4xl">⚠️</div>
        <h1 className="mb-2 text-xl font-bold text-white">Estado desconocido</h1>
        <p className="text-sm text-slate-400">Vuelve a abrir el enlace para intentarlo de nuevo.</p>
      </Centered>
    )
  }

  return (
    <div className="min-h-screen bg-[#0b1220] p-4">
      <div className="mx-auto mb-4 max-w-4xl rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 text-center text-xs text-emerald-300">
        Dispositivo autorizado
        {info.tenant_name ? ` · ${info.tenant_name}` : ''}
        {info.label ? ` · ${info.label}` : ''}
      </div>
      <Calculator key={token} storageKey={`calculator:${token}`} />
    </div>
  )
}
