import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { changePassword, logout } from '../api/auth.js'
import { useAuth } from '../context/AuthContext.jsx'
import { Button, Field, Input } from '../components/ui/Form.jsx'

export default function ChangePassword() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (next.length < 6) return toast.error('La nueva contraseña debe tener al menos 6 caracteres')
    if (next !== confirm) return toast.error('Las contraseñas no coinciden')
    if (next === current) return toast.error('La nueva contraseña debe ser diferente a la actual')

    setSaving(true)
    try {
      await changePassword(current, next)
      setUser({ ...user, must_change_password: false })
      toast.success('Contraseña cambiada correctamente')
      navigate('/', { replace: true })
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-2xl border border-blue-500/30 bg-blue-500/5 p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600/20 text-xl">🔒</div>
          <div>
            <h2 className="text-lg font-bold text-white">Cambia tu contraseña</h2>
            <p className="text-xs text-slate-400">Por seguridad, debes cambiarla antes de continuar.</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Contraseña actual">
            <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required autoFocus />
          </Field>
          <Field label="Nueva contraseña" hint="Mínimo 6 caracteres">
            <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} required />
          </Field>
          <Field label="Confirmar nueva contraseña">
            <Input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={saving} className="flex-1">
              {saving ? 'Guardando...' : 'Guardar contraseña'}
            </Button>
            <Button type="button" variant="ghost" onClick={logout}>
              Cerrar sesión
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
