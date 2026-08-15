import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { activateLicense, getLicenseStatus, getMachineCode } from '../api/index.js'
import { Button, Field, Input } from '../components/ui/Form.jsx'

export default function License() {
  const [status, setStatus] = useState(null)
  const [key, setKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [machineCode, setMachineCode] = useState('')

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

  const active = status?.active

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white md:text-3xl">Licencia del sistema</h2>
        <p className="text-sm text-slate-400">Activa o renueva tu licencia</p>
      </div>

      <div className={`rounded-2xl border p-6 ${active ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
        <div className="flex items-center gap-3">
          <span className="text-3xl">{active ? '✅' : '🔒'}</span>
          <div>
            <p className={`text-lg font-bold ${active ? 'text-emerald-400' : 'text-red-400'}`}>
              {active ? 'Licencia activa' : 'Licencia requerida o vencida'}
            </p>
            {status?.expires_at && (
              <p className="text-sm text-slate-400">
                Vence el <span className="font-semibold text-slate-200">{status.expires_at}</span>
                {status.days_left > 0 && status.days_left <= 7 && (
                  <span className="ml-2 text-amber-400">⚠️ solo {status.days_left} día(s) restante(s)</span>
                )}
              </p>
            )}
          </div>
        </div>
      </div>

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
        <h3 className="font-bold text-slate-100">Activación por equipo (licencia offline)</h3>
        <p className="text-sm text-slate-400">
          Obtén el código de activación de este equipo, genéralo con{' '}
          <span className="font-mono text-slate-200">tools/generador_licencias_offline.py</span> y pégalo donde
          corresponda.
        </p>
        <Button variant="ghost" onClick={handleMachineCode} disabled={loading}>
          Obtener código de activación
        </Button>
        {machineCode && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
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
          </div>
        )}
      </div>
    </div>
  )
}
