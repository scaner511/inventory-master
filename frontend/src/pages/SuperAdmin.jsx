import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  createTenant,
  createTenantUser,
  deleteTenant,
  getGlobalUsers,
  getTenantUsers,
  getTenants,
  renewTenantSubscription,
  renewUserSubscription,
  resetTenant,
  superadminDeleteUser,
  superadminResetPassword,
  superadminUpdateUser,
  updateTenant,
} from '../api/index.js'
import { useAuth } from '../context/AuthContext.jsx'
import { AccountTab, BackupsTab, CompanyTab } from './Admin.jsx'
import Modal from '../components/ui/Modal.jsx'
import Table, { EmptyState } from '../components/ui/Table.jsx'
import { Button, Field, Input, Select } from '../components/ui/Form.jsx'

const TABS = [
  { id: 'tenants', label: '🏢 Clientes' },
  { id: 'users', label: '👥 Usuarios' },
  { id: 'company', label: '🏭 Empresa' },
  { id: 'backups', label: '💾 Backups' },
  { id: 'account', label: '🔑 Mi cuenta' },
]

function roleBadge(role) {
  if (role === 'superadmin') return <span className="rounded-full bg-purple-500/10 px-2.5 py-0.5 text-xs font-bold text-purple-400">Super Admin</span>
  if (role === 'admin') return <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-xs font-bold text-blue-400">Administrador</span>
  return <span className="rounded-full bg-slate-500/10 px-2.5 py-0.5 text-xs font-bold text-slate-400">Operador</span>
}

function activeBadge(active) {
  return active ? <span className="text-sm text-emerald-400">✓</span> : <span className="text-sm text-red-400">✗</span>
}

/* ================= CLIENTES ================= */

function TenantsTab() {
  const [tenants, setTenants] = useState([])
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', admin_username: '', admin_password: '', admin_email: '', max_users: '' })
  const [saving, setSaving] = useState(false)
  const [usersOpen, setUsersOpen] = useState(null)
  const [tenantUsers, setTenantUsers] = useState([])
  const [addUserOpen, setAddUserOpen] = useState(false)
  const [userForm, setUserForm] = useState({ username: '', email: '', role: 'user' })
  const [resetTarget, setResetTarget] = useState(null)
  const [resetPass, setResetPass] = useState('')
  const [resetOpen, setResetOpen] = useState(false)
  const [resetTenantInfo, setResetTenantInfo] = useState(null)
  const [resetAdmins, setResetAdmins] = useState([])
  const [resetKeepId, setResetKeepId] = useState('')

  const load = useCallback(async () => {
    try {
      setTenants(await getTenants())
    } catch {
      /* interceptor */
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    try {
      if (editing) {
        await updateTenant(editing.id, {
          name: form.name,
          max_users: form.max_users === '' ? null : Number(form.max_users),
        })
        toast.success('Cliente actualizado')
      } else {
        await createTenant({
          name: form.name,
          admin_username: form.admin_username,
          admin_password: form.admin_password,
          admin_email: form.admin_email,
          max_users: form.max_users === '' ? null : Number(form.max_users),
        })
        toast.success('Cliente creado')
      }
      setEditOpen(false)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  function openEdit(t) {
    setEditing(t)
    setForm({
      name: t.name,
      admin_username: '',
      admin_password: '',
      admin_email: '',
      max_users: t.max_users ? String(t.max_users) : '',
    })
    setEditOpen(true)
  }

  function openCreate() {
    setEditing(null)
    setForm({ name: '', admin_username: '', admin_password: '', admin_email: '', max_users: '' })
    setEditOpen(true)
  }

  async function handleToggleActive(t) {
    try {
      await updateTenant(t.id, { is_active: !t.is_active })
      toast.success(t.is_active ? 'Cliente desactivado' : 'Cliente activado')
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleDelete(t) {
    if (!window.confirm(`Se eliminará el cliente "${t.name}" con TODOS sus usuarios, productos, préstamos e historial. ¿Continuar?`)) return
    try {
      await deleteTenant(t.id)
      toast.success('Cliente eliminado')
      load()
    } catch {
      /* interceptor */
    }
  }

  async function openReset(t) {
    setResetTenantInfo(t)
    try {
      const users = await getTenantUsers(t.id)
      const admins = users.filter((u) => u.role === 'admin')
      setResetAdmins(admins)
      setResetKeepId(admins.length ? String(admins[0].id) : '')
    } catch {
      /* interceptor */
    }
    setResetOpen(true)
  }

  async function handleConfirmReset() {
    if (!resetTenantInfo || !resetKeepId) return
    try {
      const res = await resetTenant(resetTenantInfo.id, { preserve_user_id: Number(resetKeepId) })
      toast.success(res.message, { duration: 6000 })
      setResetOpen(false)
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleRenew(user) {
    try {
      const res = await renewUserSubscription(user.id, 30)
      toast.success(res.message)
      load()
      loadUsers(usersOpen)
    } catch {
      /* interceptor */
    }
  }

  async function handleRenewTenant(t) {
    try {
      const res = await renewTenantSubscription(t.id, 30)
      toast.success(res.message)
      load()
      loadUsers(usersOpen)
    } catch {
      /* interceptor */
    }
  }

  async function loadUsers(tenantId) {
    try {
      setTenantUsers(await getTenantUsers(tenantId))
    } catch {
      /* interceptor */
    }
  }

  async function handleAddUser(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await createTenantUser(usersOpen, userForm)
      toast.success('Usuario creado')
      setAddUserOpen(false)
      setUserForm({ username: '', email: '', role: 'user' })
      loadUsers(usersOpen)
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleReset(e) {
    e.preventDefault()
    if (!resetTarget) return
    setSaving(true)
    try {
      await superadminResetPassword(resetTarget.id, resetPass)
      toast.success(`Contraseña de ${resetTarget.username} actualizada`)
      setResetTarget(null)
      setResetPass('')
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleTenantUserDelete(u) {
    if (!window.confirm(`¿Eliminar al usuario "${u.username}"?`)) return
    try {
      await superadminDeleteUser(u.id)
      toast.success('Usuario eliminado')
      loadUsers(usersOpen)
    } catch {
      /* interceptor */
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-400">
          Cada cliente tiene sus propios productos, préstamos e historial, con hasta <span className="font-bold text-slate-200">4 usuarios</span>.
        </p>
        <Button onClick={openCreate}>➕ Crear cliente</Button>
      </div>

      {tenants.length === 0 ? (
        <EmptyState message="Aún no hay clientes" />
      ) : (
        <Table
          columns={[
            { key: 'name', label: 'Cliente' },
            { key: 'users', label: 'Usuarios', align: 'center' },
            { key: 'limit', label: 'Límite', align: 'center' },
            { key: 'active', label: 'Activo', align: 'center' },
            { key: 'license', label: 'Licencia', align: 'center' },
            { key: 'created', label: 'Creado' },
            { key: 'actions', label: 'Acciones', align: 'center' },
          ]}
        >
          {tenants.map((t) => (
            <tr key={t.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 font-medium text-slate-100">{t.name}</td>
              <td className="px-4 py-3 text-center text-slate-300">{t.users_count}</td>
              <td className="px-4 py-3 text-center">
                <span className="rounded-full bg-slate-700/40 px-2.5 py-0.5 text-xs font-bold text-slate-300">
                  {t.max_users ?? 'Sin límite'}
                </span>
              </td>
              <td className="px-4 py-3 text-center">
                {t.subscription_days_left == null ? (
                  <span className="text-xs text-slate-500">—</span>
                ) : t.subscription_days_left < 0 ? (
                  <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-bold text-red-400" title={`Vence el ${t.subscription_expires_at}`}>
                    Vencida
                  </span>
                ) : (
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                      t.subscription_days_left <= 7
                        ? 'bg-amber-500/10 text-amber-400'
                        : 'bg-emerald-500/10 text-emerald-400'
                    }`}
                    title={`Vence el ${t.subscription_expires_at}`}
                  >
                    {t.subscription_days_left} día(s)
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(t.created_at).toLocaleDateString()}</td>
              <td className="px-4 py-3 text-center">
                <div className="flex justify-center gap-1">
                  <button
                    onClick={() => handleRenewTenant(t)}
                    className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400 transition hover:bg-emerald-500/20"
                    title="Renovar licencia del cliente (30 días)"
                  >
                    💰
                  </button>
                  <button
                    onClick={() => {
                      setUsersOpen(t.id)
                      loadUsers(t.id)
                    }}
                    className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400 transition hover:bg-emerald-500/20"
                    title="Usuarios"
                  >
                    👥
                  </button>
                  <button
                    onClick={() => openEdit(t)}
                    className="rounded-lg bg-blue-500/10 p-2 text-blue-400 transition hover:bg-blue-500/20"
                    title="Editar"
                  >
                    ✏️
                  </button>
                  <button
                    onClick={() => handleToggleActive(t)}
                    className="rounded-lg bg-amber-500/10 p-2 text-amber-400 transition hover:bg-amber-500/20"
                    title={t.is_active ? 'Desactivar' : 'Activar'}
                  >
                    {t.is_active ? '⏸️' : '▶️'}
                  </button>
                  <button
                    onClick={() => openReset(t)}
                    className="rounded-lg bg-purple-500/10 p-2 text-purple-400 transition hover:bg-purple-500/20"
                    title="Restablecer a estado de fábrica"
                  >
                    🔄
                  </button>
                  <button
                    onClick={() => handleDelete(t)}
                    className="rounded-lg bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                    title="Eliminar"
                  >
                    🗑️
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={editing ? 'Editar cliente' : 'Crear cliente'}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Nombre del cliente">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ej: Ferretería El Tornillo" required />
          </Field>
          <Field label="Límite de usuarios del cliente" hint="Incluye al administrador. Déjalo vacío para usar el límite global del sistema">
            <Input
              type="number"
              min="1"
              value={form.max_users}
              onChange={(e) => setForm({ ...form, max_users: e.target.value })}
              placeholder="Ej: 5"
            />
          </Field>
          {!editing && (
            <>
              <Field label="Usuario administrador" hint="Primer usuario del cliente (rol Administrador)">
                <Input value={form.admin_username} onChange={(e) => setForm({ ...form, admin_username: e.target.value })} placeholder="Ej: juan_admin" required />
              </Field>
              <Field label="Email del administrador" hint="Opcional">
                <Input type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} placeholder="admin@cliente.com" />
              </Field>
              <Field label="Contraseña inicial" hint="Si se deja vacía, se usará la genérica">
                <Input value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} placeholder="Mínimo 6 caracteres" />
              </Field>
              <p className="text-xs text-slate-500">El administrador deberá cambiar su contraseña en el primer inicio de sesión.</p>
            </>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setEditOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant="success" disabled={saving}>
              {saving ? 'Guardando...' : editing ? 'Guardar cambios' : 'Crear cliente'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(usersOpen)} onClose={() => setUsersOpen(null)} title={`Usuarios del cliente`} wide>
        <div className="space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setAddUserOpen(true)}>➕ Crear usuario</Button>
          </div>
          {tenantUsers.length === 0 ? (
            <EmptyState message="Este cliente aún no tiene usuarios" />
          ) : (
            <Table
              columns={[
                { key: 'username', label: 'Usuario' },
                { key: 'role', label: 'Rol', align: 'center' },
                { key: 'active', label: 'Activo', align: 'center' },
                { key: 'created', label: 'Creado' },
                { key: 'subscription', label: 'Suscripción', align: 'center' },
                { key: 'actions', label: 'Acciones', align: 'center' },
              ]}
            >
              {tenantUsers.map((u) => (
                <tr key={u.id} className="transition hover:bg-slate-800/40">
                  <td className="px-4 py-3 font-medium text-slate-100">{u.username}</td>
                  <td className="px-4 py-3 text-center">{roleBadge(u.role)}</td>
                  <td className="px-4 py-3 text-center">{activeBadge(u.is_active)}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-center">
                    {u.subscription_days_left == null ? (
                      <span className="text-xs text-slate-500">—</span>
                    ) : u.subscription_days_left < 0 ? (
                      <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-bold text-red-400" title={`Vence el ${u.subscription_expires_at}`}>
                        Vencida
                      </span>
                    ) : (
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                          u.subscription_days_left <= 7
                            ? 'bg-amber-500/10 text-amber-400'
                            : 'bg-emerald-500/10 text-emerald-400'
                        }`}
                        title={`Vence el ${u.subscription_expires_at}`}
                      >
                        {u.subscription_days_left} día(s)
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex justify-center gap-1">
                      {u.role !== 'superadmin' && (
                        <button
                          onClick={() => handleRenew(u)}
                          className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400 transition hover:bg-emerald-500/20"
                          title="Renovar suscripción (30 días)"
                        >
                          💰
                        </button>
                      )}
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
                      <button
                        onClick={() => handleTenantUserDelete(u)}
                        className="rounded-lg bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                        title="Eliminar"
                      >
                        🗑️
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      </Modal>

      <Modal open={addUserOpen} onClose={() => setAddUserOpen(false)} title="Crear usuario del cliente">
        <form onSubmit={handleAddUser} className="space-y-4">
          <Field label="Usuario">
            <Input value={userForm.username} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })} placeholder="Mínimo 3 caracteres" required />
          </Field>
          <Field label="Email" hint="Opcional">
            <Input type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} placeholder="usuario@cliente.com" />
          </Field>
          <Field label="Rol">
            <Select value={userForm.role} onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}>
              <option value="user">Operador (usuario normal)</option>
              <option value="admin">Administrador</option>
            </Select>
          </Field>
          <p className="text-xs text-slate-500">La contraseña inicial será la genérica y deberá cambiarse en el primer inicio de sesión.</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setAddUserOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" variant="success" disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar usuario'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={resetOpen} onClose={() => setResetOpen(false)} title="Restablecer a estado de fábrica">
        <div className="space-y-4">
          <p className="text-sm text-slate-300">
            Se borrarán <span className="font-bold text-red-400">TODOS</span> los productos, préstamos e historial de{' '}
            <span className="font-bold">{resetTenantInfo?.name}</span>, y sus demás usuarios. Solo quedará el
            administrador seleccionado con la contraseña genérica, que deberá cambiarla en su primer inicio de sesión.
          </p>
          <Field label="Administrador a conservar">
            <Select value={resetKeepId} onChange={(e) => setResetKeepId(e.target.value)}>
              {resetAdmins.map((a) => (
                <option key={a.id} value={String(a.id)}>
                  {a.username} ({a.email || 'sin email'})
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setResetOpen(false)}>
              Cancelar
            </Button>
            <Button type="button" variant="danger" onClick={handleConfirmReset} disabled={!resetKeepId}>
              🔄 Restablecer
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={Boolean(resetTarget)} onClose={() => setResetTarget(null)} title="Restablecer contraseña">
        <form onSubmit={handleReset} className="space-y-4">
          <p className="text-sm text-slate-300">
            Nueva contraseña para <span className="font-bold">{resetTarget?.username}</span>
          </p>
          <Field label="Nueva contraseña">
            <Input type="text" value={resetPass} onChange={(e) => setResetPass(e.target.value)} placeholder="Mínimo 6 caracteres" required />
          </Field>
          <p className="text-xs text-slate-500">El usuario deberá cambiarla en su próximo inicio de sesión.</p>
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

/* ================= USUARIOS GLOBALES ================= */

function UsersTab() {
  const [users, setUsers] = useState([])
  const [editTarget, setEditTarget] = useState(null)
  const [editForm, setEditForm] = useState({ role: 'user', is_active: true })
  const [saving, setSaving] = useState(false)
  const [resetTarget, setResetTarget] = useState(null)
  const [resetPass, setResetPass] = useState('')

  const load = useCallback(async () => {
    try {
      setUsers(await getGlobalUsers())
    } catch {
      /* interceptor */
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  function openEdit(u) {
    setEditTarget(u)
    setEditForm({ role: u.role === 'superadmin' ? 'admin' : u.role, is_active: u.is_active })
  }

  async function handleEdit(e) {
    e.preventDefault()
    if (!editTarget) return
    setSaving(true)
    try {
      await superadminUpdateUser(editTarget.id, editForm)
      toast.success('Usuario actualizado')
      setEditTarget(null)
      load()
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleReset(e) {
    e.preventDefault()
    if (!resetTarget) return
    setSaving(true)
    try {
      await superadminResetPassword(resetTarget.id, resetPass)
      toast.success(`Contraseña de ${resetTarget.username} actualizada`)
      setResetTarget(null)
      setResetPass('')
    } catch {
      /* interceptor */
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(u) {
    if (!window.confirm(`¿Eliminar al usuario "${u.username}"?`)) return
    try {
      await superadminDeleteUser(u.id)
      toast.success('Usuario eliminado')
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleRenew(u) {
    try {
      const res = await renewUserSubscription(u.id, 30)
      toast.success(res.message)
      load()
    } catch {
      /* interceptor */
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">Usuarios de todos los clientes.</p>
      {users.length === 0 ? (
        <EmptyState message="No hay usuarios" />
      ) : (
        <Table
          columns={[
            { key: 'username', label: 'Usuario' },
            { key: 'tenant', label: 'Cliente' },
            { key: 'role', label: 'Rol', align: 'center' },
            { key: 'active', label: 'Activo', align: 'center' },
            { key: 'terms', label: 'Términos', align: 'center' },
            { key: 'created', label: 'Creado' },
            { key: 'subscription', label: 'Vigencia', align: 'center' },
            { key: 'actions', label: 'Acciones', align: 'center' },
          ]}
        >
          {users.map((u) => (
            <tr key={u.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 font-medium text-slate-100">{u.username}</td>
              <td className="px-4 py-3 text-slate-300">{u.tenant_name || '—'}</td>
              <td className="px-4 py-3 text-center">{roleBadge(u.role)}</td>
              <td className="px-4 py-3 text-center">{activeBadge(u.is_active)}</td>
              <td className="px-4 py-3 text-center">
                {u.accepted_terms ? (
                  <span
                    className="text-sm text-emerald-400"
                    title={`Aceptado el ${new Date(u.accepted_terms_date).toLocaleString('es-US')}`}
                  >
                    ✓
                  </span>
                ) : (
                  <span className="text-sm text-red-400" title="Pendiente de aceptar términos">
                    ✗
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(u.created_at).toLocaleDateString()}</td>
              <td className="px-4 py-3 text-center">
                {u.subscription_days_left == null ? (
                  <span className="text-xs text-slate-500">—</span>
                ) : u.subscription_days_left < 0 ? (
                  <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-bold text-red-400" title={`Vence el ${u.subscription_expires_at}`}>
                    Vencida
                  </span>
                ) : (
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                      u.subscription_days_left <= 7
                        ? 'bg-amber-500/10 text-amber-400'
                        : 'bg-emerald-500/10 text-emerald-400'
                    }`}
                    title={`Vence el ${u.subscription_expires_at}`}
                  >
                    {u.subscription_days_left} día(s)
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-center">
                <div className="flex justify-center gap-1">
                  {u.role !== 'superadmin' && (
                    <>
                      <button
                        onClick={() => handleRenew(u)}
                        className="rounded-lg bg-emerald-500/10 p-2 text-emerald-400 transition hover:bg-emerald-500/20"
                        title="Renovar suscripción (30 días)"
                      >
                        💰
                      </button>
                      <button
                        onClick={() => openEdit(u)}
                        className="rounded-lg bg-blue-500/10 p-2 text-blue-400 transition hover:bg-blue-500/20"
                        title="Editar"
                      >
                        ✏️
                      </button>
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
                      <button
                        onClick={() => handleDelete(u)}
                        className="rounded-lg bg-red-500/10 p-2 text-red-400 transition hover:bg-red-500/20"
                        title="Eliminar"
                      >
                        🗑️
                      </button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal open={Boolean(editTarget)} onClose={() => setEditTarget(null)} title={`Editar ${editTarget?.username}`}>
        <form onSubmit={handleEdit} className="space-y-4">
          <Field label="Rol">
            <Select value={editForm.role} onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}>
              <option value="user">Operador (usuario normal)</option>
              <option value="admin">Administrador</option>
            </Select>
          </Field>
          <Field label="Estado">
            <Select value={String(editForm.is_active)} onChange={(e) => setEditForm({ ...editForm, is_active: e.target.value === 'true' })}>
              <option value="true">Activo</option>
              <option value="false">Inactivo</option>
            </Select>
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setEditTarget(null)}>
              Cancelar
            </Button>
            <Button type="submit" variant="success" disabled={saving}>
              {saving ? 'Guardando...' : 'Guardar'}
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
          <p className="text-xs text-slate-500">El usuario deberá cambiarla en su próximo inicio de sesión.</p>
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

/* ================= PÁGINA ================= */

export default function SuperAdmin() {
  const { user } = useAuth()
  // Permite abrir directamente en una pestaña: /superadmin?tab=backups
  const [tab, setTab] = useState(() => {
    const t = new URLSearchParams(window.location.search).get('tab')
    return TABS.some((x) => x.id === t) ? t : 'tenants'
  })

  if (user?.role !== 'superadmin') {
    return (
      <div className="mx-auto mt-20 max-w-md rounded-2xl border border-red-500/30 bg-red-500/5 p-8 text-center">
        <p className="text-4xl">🚫</p>
        <h2 className="mt-3 text-xl font-bold text-red-400">Acceso denegado</h2>
        <p className="mt-2 text-sm text-slate-400">Solo el Super Admin puede acceder a esta sección.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white md:text-3xl">Panel de Super Admin</h2>
        <p className="text-sm text-slate-400">Gestión global de clientes, usuarios, empresa y backups</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
              tab === t.id ? 'bg-purple-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'tenants' && <TenantsTab />}
      {tab === 'users' && <UsersTab />}
      {tab === 'company' && <CompanyTab />}
      {tab === 'backups' && <BackupsTab />}
      {tab === 'account' && <AccountTab />}
    </div>
  )
}
