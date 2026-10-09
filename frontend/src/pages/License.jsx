import { useCallback, useEffect, useState } from 'react'
import { getLicenseStatus } from '../api/index.js'
import { useAuth } from '../context/AuthContext.jsx'

export default function License() {
  const { user } = useAuth()
  const isSuper = user?.role === 'superadmin'
  const [status, setStatus] = useState(null)

  const load = useCallback(() => {
    getLicenseStatus().then(setStatus).catch(() => {})
  }, [])

  useEffect(load, [load])

  const active = status?.active

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white md:text-3xl">Suscripción</h2>
        <p className="text-sm text-slate-400">
          Cada usuario tiene una vigencia de 30 días. Al vencer sin renovar, el acceso se bloquea automáticamente.
        </p>
      </div>

      <div className={`rounded-2xl border p-6 ${isSuper || active ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5'}`}>
        <div className="flex items-center gap-3">
          <span className="text-3xl">{isSuper || active ? '✅' : '🔒'}</span>
          <div>
            <p className={`text-lg font-bold ${isSuper || active ? 'text-emerald-400' : 'text-red-400'}`}>
              {isSuper ? 'Super Admin: sin restricción' : active ? 'Suscripción activa' : 'Suscripción vencida'}
            </p>
            {isSuper ? (
              <p className="text-sm text-slate-400">El Super Admin es el operador del sistema y no tiene vencimiento.</p>
            ) : active ? (
              status?.expires_at && (
                <p className="text-sm text-slate-400">
                  Vence el <span className="font-semibold text-slate-200">{status.expires_at}</span>
                  {status.days_left > 0 && status.days_left <= 7 && (
                    <span className="ml-2 text-amber-400">⚠️ solo {status.days_left} día(s) restante(s)</span>
                  )}
                </p>
              )
            ) : (
              <p className="text-sm text-slate-300">
                Tu acceso está bloqueado hasta renovar la suscripción. Contacta a tu proveedor para registrar el pago.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}