import { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { changePassword } from '../api/auth.js'
import {
  adminResetPassword,
  connectDriveUrl,
  createUser,
  deleteUser,
  disconnectDrive,
  getDriveStatus,
  getSettings,
  getUsers,
  listBackups,
  purgeBackups,
  restoreBackup,
  runBackup,
  setSecurityQuestion,
  testDriveConnection,
  updateSettings,
  uploadBackupToDrive,
} from '../api/index.js'
import { api, API_BASE, openAuthenticatedUrl } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import { Button, Field, Input, Select } from '../components/ui/Form.jsx'

const TABS = [
  { id: 'users', label: '👥 Usuarios' },
  { id: 'company', label: '🏢 Empresa' },
  { id: 'backups', label: '💾 Backups' },
  { id: 'account', label: '🔑 Mi cuenta' },
]

export default function Admin() {
  const { user } = useAuth()

  // Permite abrir directamente en una pestaña: /admin?tab=backups
  const [tab, setTab] = useState(() => {
    const t = new URLSearchParams(window.location.search).get('tab')
    return TABS.some((x) => x.id === t) ? t : 'users'
  })

  if (user?.role !== 'admin') {
    return (
      <div className="mx-auto mt-20 max-w-md rounded-2xl border border-red-500/30 bg-red-500/5 p-8 text-center">
        <p className="text-4xl">🚫</p>
        <h2 className="mt-3 text-xl font-bold text-red-400">Acceso denegado</h2>
        <p className="mt-2 text-sm text-slate-400">Solo los administradores pueden acceder al panel de control.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white md:text-3xl">Panel de control administrativo</h2>
        <p className="text-sm text-slate-400">Gestión de usuarios de tu proveedor y de tu cuenta</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
              tab === t.id ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'users' && <UsersTab />}
      {tab === 'company' && <CompanyTab />}
      {tab === 'backups' && <BackupsTab />}
      {tab === 'account' && <AccountTab />}
    </div>
  )
}

/* ================= USUARIOS ================= */

const MAX_USERS = 4

function UsersTab() {
  const [users, setUsers] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({ username: '', role: 'user', security_question: '', security_answer: '' })
  const [saving, setSaving] = useState(false)
  const [resetTarget, setResetTarget] = useState(null)
  const [resetPass, setResetPass] = useState('')

  const load = useCallback(async () => {
    try {
      setUsers(await getUsers())
    } catch {
      /* interceptor */
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate(e) {
    e.preventDefault()
    if (form.username.length < 3) {
      return toast.error('El usuario debe tener al menos 3 caracteres')
    }
    setSaving(true)
    try {
      await createUser(form)
      toast.success('Usuario creado')
      setCreateOpen(false)
      setForm({ username: '', role: 'user', security_question: '', security_answer: '' })
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(u) {
    if (!window.confirm(`¿Eliminar al usuario "${u.username}"?`)) return
    try {
      await deleteUser(u.id)
      toast.success('Usuario eliminado')
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleReset(e) {
    e.preventDefault()
    if (!resetTarget) return
    setSaving(true)
    try {
      await adminResetPassword(resetTarget.id, resetPass)
      toast.success(`Contraseña de ${resetTarget.username} actualizada`)
      setResetTarget(null)
      setResetPass('')
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-400">
          Usuarios de tu proveedor: <span className="font-bold text-slate-200">{users.length}/{MAX_USERS}</span>
        </p>
        {users.length < MAX_USERS && <Button onClick={() => setCreateOpen(true)}>➕ Crear usuario</Button>}
      </div>

      {users.length === 0 ? (
        <EmptyState message="No hay usuarios" />
      ) : (
        <Table
          columns={[
            { key: 'username', label: 'Usuario' },
            { key: 'role', label: 'Rol', align: 'center' },
            { key: 'active', label: 'Activo', align: 'center' },
            { key: 'mustChange', label: 'Contraseña', align: 'center' },
            { key: 'created', label: 'Creado' },
            { key: 'actions', label: 'Acciones', align: 'center' },
          ]}
        >
          {users.map((u) => (
            <tr key={u.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 font-medium text-slate-100">{u.username}</td>
              <td className="px-4 py-3 text-center">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${u.role === 'admin' ? 'bg-blue-500/10 text-blue-400' : u.role === 'superadmin' ? 'bg-purple-500/10 text-purple-400' : 'bg-slate-500/10 text-slate-400'}`}>
                  {u.role === 'admin' ? 'Administrador' : u.role === 'superadmin' ? 'Super Admin' : 'Operador'}
                </span>
              </td>
              <td className="px-4 py-3 text-center">
                <span className={`text-sm ${u.is_active ? 'text-emerald-400' : 'text-red-400'}`}>{u.is_active ? '✓' : '✗'}</span>
              </td>
              <td className="px-4 py-3 text-center">
                {u.must_change_password ? (
                  <span className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-bold text-amber-400" title="Debe cambiarla en su primer acceso">
                    Cambio pendiente
                  </span>
                ) : (
                  <span className="rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-bold text-emerald-400">✓ Actualizada</span>
                )}
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(u.created_at).toLocaleDateString()}</td>
              <td className="px-4 py-3 text-center">
                <div className="flex justify-center gap-1">
                  <button
                    onClick={() => {
                      setResetTarget(u)
                      setResetPass('')
                    }}
                    className="rounded-lg bg-amber-500/10 p-2 text-amber-400 transition hover:bg-amber-500/20"
                    title="Restablecer contraseña"
                  >
                    🔑
                  </button>
                  {u.username !== 'admin' && (
                    <button
                      onClick={() => handleDelete(u)}
                      className="rounded-lg bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                      title="Eliminar"
                    >
                      🗑️
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Crear nuevo usuario" wide>
        <form onSubmit={handleCreate} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nombre de usuario">
            <Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} required />
          </Field>
          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3 text-xs text-slate-300">
            🔑 La contraseña inicial será <span className="font-mono font-bold text-blue-300">Cambiar123!</span>
            <br />
            El usuario deberá cambiarla en su primer inicio de sesión.
          </div>
          <Field label="Rol">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="user">Operador (usuario normal)</option>
              <option value="admin">Administrador</option>
            </Select>
          </Field>
          <div className="hidden sm:block" />
          <Field label="Pregunta de seguridad" hint="Para recuperación de contraseña (opcional)">
            <Input value={form.security_question} onChange={(e) => setForm({ ...form, security_question: e.target.value })} placeholder="Ej: ¿Nombre de tu primera mascota?" />
          </Field>
          <Field label="Respuesta de seguridad">
            <Input value={form.security_answer} onChange={(e) => setForm({ ...form, security_answer: e.target.value })} />
          </Field>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant="success" disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar usuario'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(resetTarget)} onClose={() => setResetTarget(null)} title="Restablecer contraseña">
        <form onSubmit={handleReset} className="space-y-4">
          <p className="text-sm text-slate-300">
            Nueva contraseña para <span className="font-bold">{resetTarget?.username}</span>
          </p>
          <Field label="Nueva contraseña">
            <Input type="text" value={resetPass} onChange={(e) => setResetPass(e.target.value)} placeholder="Mínimo 6 caracteres" required />
          </Field>
          <p className="text-xs text-slate-500">El usuario deberá volver a cambiarla en su próximo inicio de sesión.</p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setResetTarget(null)}>
              Cancelar
            </Button>
            <Button type="submit" variant="warning" disabled={saving}>
              Guardar
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

/* ================= EMPRESA ================= */

export function CompanyTab() {
  const [settings, setSettings] = useState(null)
  const [name, setName] = useState('')
  const [threshold, setThreshold] = useState(5)
  const [saving, setSaving] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    getSettings().then((s) => {
      setSettings(s)
      setName(s.company_name || '')
      setThreshold(s.low_stock_threshold)
    }).catch(() => {})
  }, [])

  async function handleSave() {
    setSaving(true)
    try {
      await updateSettings({ company_name: name, low_stock_threshold: Number(threshold) })
      toast.success('Configuración guardada')
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleLogo(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      const { data } = await api.post('/settings/logo', fd)
      toast.success(data.message)
      setSettings({ ...settings, has_logo: true })
    } catch {
      /* interceptor */
    } finally {
      e.target.value = ''
    }
  }

  return (
    <div className="grid max-w-3xl grid-cols-1 gap-6 md:grid-cols-2">
      <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-bold text-slate-100">Datos de la empresa</h3>
        <Field label="Nombre de la empresa" hint="Se usa en los comprobantes PDF">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Umbral de stock bajo" hint="Productos con stock igual o menor a este valor se alertan">
          <Input type="number" min="1" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
        </Field>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar cambios'}
        </Button>
      </div>

      <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-bold text-slate-100">Logo de empresa</h3>
        {settings?.has_logo ? (
          <img src={`${API_BASE}/settings/logo`} alt="Logo" className="max-h-32 rounded-lg border border-slate-700 bg-white object-contain p-2" />
        ) : (
          <p className="text-sm text-slate-500">Aún no hay logo configurado. Se usará el título genérico en los PDFs.</p>
        )}
        <input ref={fileRef} type="file" accept=".png,.jpg,.jpeg,.bmp,.webp" className="hidden" onChange={handleLogo} />
        <Button variant="ghost" onClick={() => fileRef.current?.click()}>
          {settings?.has_logo ? '🔄 Cambiar logo' : '🖼️ Subir logo'}
        </Button>
      </div>
    </div>
  )
}

/* ================= BACKUPS ================= */

export function BackupsTab() {
  const [backups, setBackups] = useState([])
  const [running, setRunning] = useState(false)
  const [busy, setBusy] = useState(false)
  const [drive, setDrive] = useState(null)
  const [testing, setTesting] = useState(false)
  const [uploadingName, setUploadingName] = useState(null)
  const restoreRef = useRef(null)

  const load = useCallback(async () => {
    try {
      setBackups(await listBackups())
    } catch {
      /* interceptor */
    }
    try {
      setDrive(await getDriveStatus())
    } catch {
      setDrive({ configured: false, mode: null, folder_id: null, auto_upload: false, oauth_available: false })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Resultado del flujo "Conectar con Google Drive" (?drive=ok | drive=error:...)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const flag = params.get('drive')
    if (!flag) return
    if (flag === 'ok') toast.success('Google Drive conectado correctamente')
    else if (flag.startsWith('error:')) toast.error(`No se pudo conectar Drive: ${decodeURIComponent(flag.slice(6))}`)
    params.delete('drive')
    const qs = params.toString()
    window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''))
  }, [])

  async function handleRun() {
    setRunning(true)
    try {
      const res = await runBackup()
      let msg = `${res.message} (${res.kind})`
      if (res.drive?.uploaded) msg += ' · subido a Drive ✓'
      if (res.drive && res.drive.uploaded === false) toast.error(`No se pudo subir a Drive: ${res.drive.error}`)
      toast.success(msg)
      load()
    } catch {
      /* interceptor */
    } finally {
      setRunning(false)
    }
  }

  async function handleTestDrive() {
    setTesting(true)
    try {
      const res = await testDriveConnection()
      toast.success(res.message)
    } catch {
      /* interceptor */
    } finally {
      setTesting(false)
    }
  }

  async function handleDisconnectDrive() {
    if (!window.confirm('Se desconectará Google Drive. Los backups seguirán creándose localmente. ¿Continuar?')) return
    setBusy(true)
    try {
      const res = await disconnectDrive()
      toast.success(res.message)
      load()
    } catch {
      /* interceptor */
    } finally {
      setBusy(false)
    }
  }

  async function handleUploadToDrive(name) {
    setUploadingName(name)
    try {
      const res = await uploadBackupToDrive(name)
      toast.success(res.message)
    } catch {
      /* interceptor */
    } finally {
      setUploadingName(null)
    }
  }

  async function handlePurge() {
    if (!window.confirm('Se eliminarán TODOS los backups excepto el más reciente. ¿Continuar?')) return
    setBusy(true)
    try {
      const res = await purgeBackups()
      toast.success(res.message)
      load()
    } catch {
      /* interceptor */
    } finally {
      setBusy(false)
    }
  }

  async function handleRestore(e) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!window.confirm('Esto REEMPLAZARÁ todos los datos actuales (productos, préstamos, usuarios, historial) con los del respaldo. ¿Continuar?')) {
      e.target.value = ''
      return
    }
    setBusy(true)
    try {
      const res = await restoreBackup(file)
      toast.success(res.message)
      load()
    } catch {
      /* interceptor */
    } finally {
      setBusy(false)
      e.target.value = ''
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div>
          <h3 className="font-bold text-slate-100">Backups automáticos</h3>
          <p className="text-sm text-slate-400">
            Se genera un respaldo diario a las 03:00 con retención de 30 días. La copia se crea con pg_dump (o Excel si pg_dump no está disponible).
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input ref={restoreRef} type="file" accept=".xlsx" className="hidden" onChange={handleRestore} />
          <Button variant="ghost" onClick={() => restoreRef.current?.click()} disabled={busy}>
            📂 Cargar base de datos anterior
          </Button>
          <Button variant="warning" onClick={handlePurge} disabled={busy}>
            🧹 Borrar todas menos la última
          </Button>
          <Button variant="success" onClick={handleRun} disabled={running || busy}>
            {running ? 'Generando...' : '💾 Hacer backup ahora'}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <div>
          <h3 className="font-bold text-slate-100">
            Google Drive{' '}
            {drive?.mode === 'oauth' && (
              <span className="ml-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400">Conectado</span>
            )}
            {drive?.mode === 'service_account' && (
              <span className="ml-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400">Conectado (cuenta de servicio)</span>
            )}
            {!drive?.configured && (
              <span className="ml-1 rounded-full bg-slate-500/10 px-2 py-0.5 text-xs font-semibold text-slate-400">No conectado</span>
            )}
            {drive?.auto_upload && (
              <span className="ml-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs font-semibold text-blue-400">Auto-subida activada</span>
            )}
          </h3>
          {drive?.mode === 'oauth' ? (
            <p className="text-sm text-slate-400">
              Conectado a la cuenta <span className="text-slate-200">{drive.email}</span>
              {drive.folder_name && (
                <> · carpeta <span className="font-mono text-xs text-slate-300">{drive.folder_name}</span></>
              )}. Usa ⬆️ para subir cualquier copia manualmente.
            </p>
          ) : drive?.mode === 'service_account' ? (
            <p className="text-sm text-slate-400">
              Carpeta destino: <span className="font-mono text-xs text-slate-300">{drive.folder_id}</span> (cuenta de servicio).
            </p>
          ) : drive?.oauth_available ? (
            <p className="text-sm text-slate-400">
              Guarda tus backups automáticamente en tu propio Google Drive. Autoriza el acceso con tu cuenta y listo.
            </p>
          ) : (
            <p className="text-sm text-slate-400">
              Para usar Drive configura en el servidor GOOGLE_OAUTH_CLIENT_ID/SECRET (botón Conectar) o las variables de cuenta de servicio (ver .env.example).
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!drive?.configured && drive?.oauth_available && (
            <Button variant="success" onClick={() => { window.location.href = connectDriveUrl() }}>
              🔗 Conectar con Google Drive
            </Button>
          )}
          {drive?.configured && (
            <Button variant="ghost" onClick={handleTestDrive} disabled={testing}>
              {testing ? 'Probando...' : '🔌 Probar conexión'}
            </Button>
          )}
          {drive?.mode === 'oauth' && (
            <Button variant="warning" onClick={handleDisconnectDrive} disabled={busy}>
              Desconectar
            </Button>
          )}
        </div>
      </div>

      {backups.length === 0 ? (
        <EmptyState message="Aún no hay backups" />
      ) : (
        <Table
          columns={[
            { key: 'name', label: 'Archivo' },
            { key: 'size', label: 'Tamaño', align: 'center' },
            { key: 'created', label: 'Creado' },
            { key: 'download', label: '', align: 'center' },
          ]}
        >
          {backups.map((b) => (
            <tr key={b.name} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 font-mono text-xs text-slate-200">{b.name}</td>
              <td className="px-4 py-3 text-center text-slate-300">{b.size_kb} KB</td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(b.created).toLocaleString('es-US')}</td>
              <td className="px-4 py-3 text-center">
                <div className="flex items-center justify-center gap-1">
                  {drive?.configured && (
                    <button
                      onClick={() => handleUploadToDrive(b.name)}
                      disabled={uploadingName === b.name}
                      className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400 transition hover:bg-emerald-500/20 disabled:opacity-50"
                      title={uploadingName === b.name ? 'Subiendo...' : 'Subir a Google Drive'}
                    >
                      ⬆️
                    </button>
                  )}
                  <button
                    onClick={() => openAuthenticatedUrl(b.url)}
                    className="rounded-lg bg-blue-500/10 p-2 text-blue-400 transition hover:bg-blue-500/20"
                    title="Descargar"
                  >
                    ⬇️
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  )
}

/* ================= MI CUENTA ================= */

export function AccountTab() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')

  async function handlePass(e) {
    e.preventDefault()
    if (next.length < 6) return toast.error('La nueva contraseña debe tener al menos 6 caracteres')
    try {
      await changePassword(current, next)
      toast.success('Contraseña actualizada')
      setCurrent('')
      setNext('')
    } catch {
      /* interceptor */
    }
  }

  async function handleQuestion(e) {
    e.preventDefault()
    if (!question.trim() || !answer.trim()) return toast.error('Completa pregunta y respuesta')
    try {
      await setSecurityQuestion(question.trim(), answer.trim())
      toast.success('Pregunta de seguridad guardada')
      setQuestion('')
      setAnswer('')
    } catch {
      /* interceptor */
    }
  }

  return (
    <div className="grid max-w-3xl grid-cols-1 gap-6 md:grid-cols-2">
      <form onSubmit={handlePass} className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-bold text-slate-100">Cambiar mi contraseña</h3>
        <Field label="Contraseña actual">
          <Input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </Field>
        <Field label="Nueva contraseña">
          <Input type="password" value={next} onChange={(e) => setNext(e.target.value)} required />
        </Field>
        <Button type="submit">Actualizar contraseña</Button>
      </form>

      <form onSubmit={handleQuestion} className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-bold text-slate-100">Pregunta de seguridad</h3>
        <p className="text-xs text-slate-500">Se usa para recuperar tu contraseña si la olvidas.</p>
        <Field label="Pregunta">
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ej: ¿Nombre de tu primera mascota?" />
        </Field>
        <Field label="Respuesta">
          <Input value={answer} onChange={(e) => setAnswer(e.target.value)} />
        </Field>
        <Button type="submit" variant="success">
          Guardar pregunta
        </Button>
      </form>
    </div>
  )
}
