import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { acceptTerms } from '../api/auth.js'
import { useAuth } from '../context/AuthContext.jsx'
import { Button } from './ui/Form.jsx'
import { PRIVACY_POLICY, TERMS_OF_USE } from '../legal/legalTexts.js'

function LegalDocument({ doc }) {
  return (
    <div className="space-y-5 px-6 py-5 text-sm leading-relaxed text-slate-300">
      <header className="border-b border-slate-700 pb-4 text-center">
        <h3 className="text-lg font-bold tracking-wide text-white">{doc.title}</h3>
        <p className="mt-1 text-xs text-slate-400">
          {doc.system} · Última actualización: {doc.updated}
        </p>
      </header>
      {doc.sections.map((section) => (
        <section key={section.heading}>
          <h4 className="font-bold text-slate-100">{section.heading}</h4>
          {section.paragraphs?.map((p, i) => (
            <p key={i} className="mt-2">
              {p}
            </p>
          ))}
          {section.bullets && (
            <ul className="mt-2 list-inside list-disc space-y-1">
              {section.bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
          {section.footer && <p className="mt-2 italic text-slate-400">{section.footer}</p>}
        </section>
      ))}
      <p className="pb-2 text-center text-xs text-slate-500">— Fin del documento —</p>
    </div>
  )
}

/* Modal OBLIGATORIO de aceptación de términos.
   - No se puede cerrar (sin X, sin ESC, sin clic fuera).
   - Bloquea todo el sistema: se renderiza EN LUGAR de la aplicación
     (App.jsx lo muestra cuando user.accepted_terms es false).
   - El backend además bloquea cualquier otra llamada a la API. */
export default function TermsModal() {
  const { setUser } = useAuth()
  const [tab, setTab] = useState(PRIVACY_POLICY.id)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  async function handleAccept() {
    if (!checked || saving) return
    setSaving(true)
    try {
      const updated = await acceptTerms()
      setUser(updated)
      toast.success('¡Gracias! Ya puedes usar Inventory Master.')
    } catch {
      /* el interceptor muestra el error */
    } finally {
      setSaving(false)
    }
  }

  const doc = tab === PRIVACY_POLICY.id ? PRIVACY_POLICY : TERMS_OF_USE

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-[#0b1220]/95 p-3 backdrop-blur-sm sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="terms-modal-title"
    >
      <div className="flex h-[94vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        {/* Encabezado */}
        <div className="space-y-1 border-b border-slate-700 px-6 py-4 text-center">
          <p className="text-3xl">🔐</p>
          <h2 id="terms-modal-title" className="text-lg font-bold text-white md:text-xl">
            Antes de continuar, lee y acepta nuestros documentos legales
          </h2>
          <span className="inline-block rounded-full bg-red-500/10 px-3 py-0.5 text-xs font-bold text-red-400">
            Aceptación obligatoria para usar el sistema
          </span>
        </div>

        {/* Pestañas de documentos */}
        <div className="flex gap-2 px-6 pt-4">
          {[PRIVACY_POLICY, TERMS_OF_USE].map((d) => (
            <button
              key={d.id}
              onClick={() => setTab(d.id)}
              className={`rounded-lg px-4 py-2 text-xs font-semibold transition sm:text-sm ${
                tab === d.id ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {d.id === 'privacy' ? '🛡️ Política de Privacidad' : '📜 Términos y Condiciones'}
            </button>
          ))}
        </div>

        {/* Contenido con scroll */}
        <div className="mx-4 my-3 flex-1 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/50 sm:mx-6">
          <LegalDocument doc={doc} />
        </div>

        {/* Pie: checkbox + botón */}
        <div className="space-y-3 border-t border-slate-700 px-4 py-4 sm:px-6">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-500"
            />
            <span className="text-sm font-medium text-slate-200">
              He leído y acepto los Términos y Condiciones de Uso y la Política de Privacidad.
            </span>
          </label>
          <Button variant="success" onClick={handleAccept} disabled={!checked || saving} className="w-full justify-center">
            {saving ? 'Registrando aceptación...' : '✅ Aceptar y Continuar'}
          </Button>
          <p className="text-center text-xs text-slate-500">
            La fecha y hora exacta de tu aceptación quedarán registradas en el historial de auditoría del sistema.
          </p>
        </div>
      </div>
    </div>
  )
}
