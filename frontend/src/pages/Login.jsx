import { useEffect, useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext.jsx'
import { forgotPassword, resetPassword } from '../api/auth.js'
import Modal from '../components/ui/Modal.jsx'
import { Button, Field, Input } from '../components/ui/Form.jsx'

const REMEMBER_KEY = 'im_remember_user'

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState(() => localStorage.getItem(REMEMBER_KEY) || '')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(Boolean(localStorage.getItem(REMEMBER_KEY)))
  const [showPass, setShowPass] = useState(false)
  const [loading, setLoading] = useState(false)

  const [showRecovery, setShowRecovery] = useState(false)
  const [step, setStep] = useState(1)
  const [recUser, setRecUser] = useState('')
  const [answer, setAnswer] = useState('')
  const [resetToken, setResetToken] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [recoveryLoading, setRecoveryLoading] = useState(false)

  useEffect(() => {
    if (user) navigate('/', { replace: true })
  }, [user, navigate])

  if (user) return <Navigate to="/" replace />

  async function handleLogin(e) {
    e.preventDefault()
    if (!username || !password) return toast.error('Completa usuario y contraseña')
    setLoading(true)
    try {
      await login(username.trim(), password)
      if (remember) localStorage.setItem(REMEMBER_KEY, username.trim())
      else localStorage.removeItem(REMEMBER_KEY)
      navigate('/', { replace: true })
    } catch {
      /* error mostrado por el interceptor */
    } finally {
      setLoading(false)
    }
  }

  async function handleAskQuestion(e) {
    e.preventDefault()
    if (!recUser || !answer) return toast.error('Completa usuario y respuesta de seguridad')
    setRecoveryLoading(true)
    try {
      const token = await forgotPassword(recUser.trim(), answer)
      setResetToken(token)
      setStep(2)
      toast.success('Respuesta correcta. Define tu nueva contraseña.')
    } catch {
      /* error mostrado por el interceptor */
    } finally {
      setRecoveryLoading(false)
    }
  }

  async function handleReset(e) {
    e.preventDefault()
    if (newPassword.length < 6) return toast.error('La contraseña debe tener al menos 6 caracteres')
    setRecoveryLoading(true)
    try {
      await resetPassword(resetToken, newPassword)
      toast.success('Contraseña restablecida. Inicia sesión.')
      setShowRecovery(false)
      setStep(1)
      setRecUser('')
      setAnswer('')
      setNewPassword('')
      setPassword('')
    } catch {
      /* error mostrado por el interceptor */
    } finally {
      setRecoveryLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#050a18] via-[#0b1220] to-[#111c33] p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 to-indigo-600 text-4xl shadow-2xl shadow-blue-600/30">
            📦
          </div>
          <h1 className="text-2xl font-extrabold text-white">Inventory Master OS</h1>
          <p className="mt-1 text-sm text-slate-400">Control Total de Inventario y Préstamos</p>
        </div>

        <form
          onSubmit={handleLogin}
          className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl backdrop-blur"
        >
          <Field label="Usuario">
            <Input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="usuario"
              autoFocus
              autoComplete="username"
            />
          </Field>

          <div className="mt-4">
            <Field label="Contraseña">
              <div className="relative">
                <Input
                  type={showPass ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="contraseña"
                  autoComplete="current-password"
                  className="pr-12"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                  aria-label="Mostrar contraseña"
                >
                  {showPass ? '🙈' : '👁️'}
                </button>
              </div>
            </Field>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-800 accent-blue-600"
              />
              Recordar usuario
            </label>
            <button
              type="button"
              onClick={() => {
                setShowRecovery(true)
                setStep(1)
                setRecUser(username)
              }}
              className="text-xs font-medium text-blue-400 hover:text-blue-300"
            >
              ¿Olvidaste tu contraseña?
            </button>
          </div>

          <Button type="submit" disabled={loading} className="mt-6 w-full py-3 text-base">
            {loading ? 'Ingresando...' : 'Iniciar Sesión'}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-500">
          Sistema multiusuario en red local · v2026
        </p>
      </div>

      {/* Modal de recuperación */}
      <Modal open={showRecovery} onClose={() => setShowRecovery(false)} title="Recuperar contraseña">
        {step === 1 ? (
          <form onSubmit={handleAskQuestion} className="space-y-4">
            <p className="text-sm text-slate-400">
              Responde la pregunta de seguridad configurada en tu cuenta para restablecer la contraseña.
            </p>
            <Field label="Usuario">
              <Input value={recUser} onChange={(e) => setRecUser(e.target.value)} placeholder="usuario" />
            </Field>
            <Field label="Respuesta de seguridad" hint="Si no la configuraste, pide al administrador que restablezca tu contraseña.">
              <Input value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Tu respuesta" />
            </Field>
            <Button type="submit" disabled={recoveryLoading} className="w-full">
              {recoveryLoading ? 'Verificando...' : 'Continuar'}
            </Button>
          </form>
        ) : (
          <form onSubmit={handleReset} className="space-y-4">
            <Field label="Nueva contraseña">
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Mínimo 6 caracteres"
              />
            </Field>
            <Button type="submit" disabled={recoveryLoading} className="w-full" variant="success">
              {recoveryLoading ? 'Guardando...' : 'Restablecer contraseña'}
            </Button>
          </form>
        )}
      </Modal>
    </div>
  )
}
