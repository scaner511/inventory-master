import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import {
  activateLicense,
  activateOfflineLicense,
  capturePaypalOrder,
  createPaypalOrder,
  getLicenseStatus,
  getMachineCode,
  getPaypalConfig,
} from '../api/index.js'
import { formatMoney } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import { Button, Field, Input } from '../components/ui/Form.jsx'

export default function License() {
  const { user } = useAuth()
  const isSuper = user?.role === 'superadmin'
  const [status, setStatus] = useState(null)
  const [key, setKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [machineCode, setMachineCode] = useState('')
  const [offlineKey, setOfflineKey] = useState('')
  const [offlineLoading, setOfflineLoading] = useState(false)

  const load = useCallback(() => {
    getLicenseStatus().then(setStatus).catch(() => {})
  }, [])

  useEffect(load, [load])

  async function handleActivate(e) {
    e.preventDefault()
    if (!key.trim()) return toast.error('Ingresa una clave de licencia')
    setLoading(true)
    try {
      await activateLicense(key.trim().toUpperCase())
      toast.success('Licencia activada correctamente')
      setKey('')
      load()
    } catch {
      /* interceptor */
    } finally {
      setLoading(false)
    }
  }

  async function handleMachineCode() {
    try {
      const { code } = await getMachineCode()
      setMachineCode(code)
    } catch {
      /* interceptor */
    }
  }

  async function handleOfflineActivate() {
    if (!offlineKey.trim()) return toast.error('Pega la clave de licencia')
    setOfflineLoading(true)
    try {
      const { expires_at } = await activateOfflineLicense(offlineKey.trim())
      toast.success(`Licencia activada correctamente (vence el ${expires_at})`)
      setOfflineKey('')
      load()
    } catch {
      /* interceptor */
    } finally {
      setOfflineLoading(false)
    }
  }

  const active = status?.active

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white md:text-3xl">Licencia del sistema</h2>
        <p className="text-sm text-slate-400">Activa o renueva tu licencia</p>
      </div>

      <div className={`rounded-2xl border p-6 ${isSuper || active ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
        <div className="flex items-center gap-3">
          <span className="text-3xl">{isSuper || active ? '✅' : '🔒'}</span>
          <div>
            <p className={`text-lg font-bold ${isSuper || active ? 'text-emerald-400' : 'text-red-400'}`}>
              {isSuper ? 'Super Admin: sin restricción de licencia' : active ? 'Licencia activa' : 'Licencia requerida o vencida'}
            </p>
            {isSuper ? (
              <p className="text-sm text-slate-400">El Super Admin no requiere licencia ni tiene fecha de vencimiento.</p>
            ) : (
              status?.expires_at && (
                <p className="text-sm text-slate-400">
                  Vence el <span className="font-semibold text-slate-200">{status.expires_at}</span>
                  {status.days_left > 0 && status.days_left <= 7 && (
                    <span className="ml-2 text-amber-400">⚠️ solo {status.days_left} día(s) restante(s)</span>
                  )}
                </p>
              )
            )}
          </div>
        </div>
      </div>

      {!isSuper && (
        <>
          <form onSubmit={handleActivate} className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-bold text-slate-100">Activar o renovar licencia</h3>
        <Field label="Clave de licencia" hint="Formato: MC26-XXXX-XXXX. La vigencia depende de la clave emitida">
          <Input
            value={key}
            onChange={(e) => setKey(e.target.value.toUpperCase())}
            placeholder="MC26-XXXX-XXXX"
            className="font-mono tracking-widest"
          />
        </Field>
        <Button type="submit" variant="success" disabled={loading}>
          {loading ? 'Activando...' : 'Activar licencia'}
        </Button>
      </form>

      <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-bold text-slate-100">Licencia offline (activación por equipo)</h3>
        <p className="text-sm text-slate-400">
          Genera la clave con{' '}
          <span className="font-mono text-slate-200">tools/generador_licencias_offline</span> usando el código de este
          equipo y actívala aquí. La clave queda ligada a esta máquina.
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <Button variant="ghost" onClick={handleMachineCode}>
            Obtener código de activación
          </Button>
          {machineCode && (
            <span className="flex flex-wrap items-center gap-3">
              <code className="rounded-lg bg-slate-800 px-4 py-2 font-mono text-lg font-bold tracking-widest text-emerald-400">
                {machineCode}
              </code>
              <Button
                variant="ghost"
                onClick={() => {
                  navigator.clipboard.writeText(machineCode)
                  toast.success('Código copiado al portapapeles')
                }}
              >
                📋 Copiar
              </Button>
            </span>
          )}
        </div>

        <Field label="Clave de licencia" hint="Formato: LIC.<datos>.<firma>">
          <Input
            value={offlineKey}
            onChange={(e) => setOfflineKey(e.target.value.trim())}
            placeholder="LIC........"
            className="font-mono tracking-widest"
          />
        </Field>
        <Button variant="success" onClick={handleOfflineActivate} disabled={offlineLoading}>
          {offlineLoading ? 'Activando...' : 'Activar licencia'}
        </Button>
      </div>

      <PayWithPayPal onPaid={load} />
        </>
      )}
    </div>
  )
}

function PayWithPayPal({ onPaid }) {
  const containerRef = useRef(null)
  const [config, setConfig] = useState(null)
  const [sdkReady, setSdkReady] = useState(false)

  useEffect(() => {
    getPaypalConfig().then(setConfig).catch(() => setConfig({ enabled: false }))
  }, [])

  useEffect(() => {
    if (!config?.enabled) return
    if (window.paypal) {
      setSdkReady(true)
      return
    }
    const base = config.mode === 'live' ? 'https://www.paypal.com' : 'https://www.sandbox.paypal.com'
    const script = document.createElement('script')
    script.src = `${base}/sdk/js?client-id=${config.client_id}&currency=${config.currency}`
    script.async = true
    script.onload = () => setSdkReady(true)
    document.body.appendChild(script)
  }, [config])

  useEffect(() => {
    if (!config?.enabled || !sdkReady || !window.paypal) return
    let mounted = true
    let buttons
    const container = containerRef.current
    if (!container) return

    container.innerHTML = ''
    window.paypal
      .Buttons({
        style: { color: 'gold', shape: 'rect', label: 'paypal', height: 46 },
        createOrder: () => createPaypalOrder().then((r) => r.id),
        onApprove: async (data) => {
          try {
            const res = await capturePaypalOrder(data.orderID)
            toast.success(res.message || 'Pago confirmado')
            onPaid(res)
          } catch {
            /* interceptor */
          }
        },
        onCancel: () => toast('Pago cancelado. Puedes volver a intentar cuando quieras.'),
      })
      .render(container)
      .then((btn) => {
        if (mounted) buttons = btn
      })

    return () => {
      mounted = false
      try {
        buttons?.close?.()
      } catch {
        /* noop */
      }
    }
  }, [config, onPaid, sdkReady])

  if (!config) return null

  return (
    <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <h3 className="font-bold text-slate-100">Pagar y activar con PayPal</h3>
      {config.enabled ? (
        <>
          <p className="text-sm text-slate-400">
            Paga <span className="font-semibold text-slate-200">{formatMoney(config.amount)} ({config.currency})</span> y tu
            licencia se extiende <span className="font-semibold text-emerald-400">{config.days} días automáticamente</span> —
            sin esperar a que alguien te envíe una clave.
          </p>
          <div ref={containerRef} className="w-full max-w-[320px]" />
        </>
      ) : (
        <p className="text-sm text-slate-400">
          El pago con PayPal aún no está habilitado por el proveedor. Usa una de las opciones de arriba.
        </p>
      )}
    </div>
  )
}
