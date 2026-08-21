import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  createTenant,
  createTenantUser,
  deleteTenant,
  getGlobalUsers,
  getTenantUsers,
  getTenants,
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
  { id: 'tenants', label: '🏢 Proveedores' },
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

/* ================= PROVEEDORES ================= */

function TenantsTab() {
  const [tenants, setTenants] = useState([])
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', admin_username: '', admin_password: '', admin_email: '' })
  const [saving, setSaving] = useState(false)
  const [usersOpen, setUsersOpen] = useState(null)
  const [tenantUsers, setTenantUsers] = useState([])
  const [addUserOpen, setAddUserOpen] = useState(false)
  const [userForm, setUserForm] = useState({ username: '', email: '', role: 'user' })
  const [resetTarget, setResetTarget] = useState(null)
  const [resetPass, setResetPass] = useState('')

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
        await updateTenant(editing.id, { name: form.name })
        toast.success('Proveedor actualizado')
      } else {
        await createTenant(form)
        toast.success('Proveedor creado')
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
    setForm({ name: t.name, admin_username: '', admin_password: '', admin_email: '' })
    setEditOpen(true)
  }

  function openCreate() {
    setEditing(null)
    setForm({ name: '', admin_username: '', admin_password: '', admin_email: '' })
    setEditOpen(true)
  }

  async function handleToggleActive(t) {
    try {
      await updateTenant(t.id, { is_active: !t.is_active })
      toast.success(t.is_active ? 'Proveedor desactivado' : 'Proveedor activado')
      load()
    } catch {
      /* interceptor */
    }
  }

  async function handleDelete(t) {
    if (!window.confirm(`Se eliminará el proveedor "${t.name}" con TODOS sus usuarios, productos, préstamos e historial. ¿Continuar?`)) return
    try {
      await deleteTenant(t.id)
      toast.success('Proveedor eliminado')
      load()
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
          Cada proveedor tiene sus propios productos, préstamos e historial, con hasta <span className="font-bold text-slate-200">4 usuarios</span>.
        </p>
        <Button onClick={openCreate}>➕ Crear proveedor</Button>
      </div>

      {tenants.length === 0 ? (
        <EmptyState message="Aún no hay proveedores" />
      ) : (
        <Table
          columns={[
            { key: 'name', label: 'Proveedor' },
            { key: 'users', label: 'Usuarios', align: 'center' },
            { key: 'active', label: 'Activo', align: 'center' },
            { key: 'created', label: 'Creado' },
            { key: 'actions', label: 'Acciones', align: 'center' },
          ]}
        >
          {tenants.map((t) => (
            <tr key={t.id} className="transition hover:bg-slate-800/40">
              <td className="px-4 py-3 font-medium text-slate-100">{t.name}</td>
              <td className="px-4 py-3 text-center text-slate-300">{t.users_count}</td>
              <td className="px-4 py-3 text-center">{activeBadge(t.is_active)}</td>
              <td className="px-4 py-3 text-xs text-slate-400">{new Date(t.created_at).toLocaleDateString()}</td>
              <td className="px-4 py-3 text-center">
                <div className="flex justify-center gap-1">
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

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={editing ? 'Editar proveedor' : 'Crear proveedor'}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="Nombre del proveedor">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ej: Ferretería El Tornillo" required />
          </Field>
          {!editing && (
            <>
              <Field label="Usuario administrador" hint="Primer usuario del proveedor (rol Administrador)">
                <Input value={form.admin_username} onChange={(e) => setForm({ ...form, admin_username: e.target.value })} placeholder="Ej: juan_admin" required />
              </Field>
              <Field label="Email del administrador" hint="Opcional">
                <Input type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} placeholder="admin@proveedor.com" />
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
              {saving ? 'Guardando...' : editing ? 'Guardar cambios' : 'Crear proveedor'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(usersOpen)} onClose={() => setUsersOpen(null)} title={`Usuarios del proveedor`} wide>
        <div className="space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setAddUserOpen(true)}>➕ Crear usuario</Button>
          </div>
          {tenantUsers.length === 0 ? (
            <EmptyState message="Este proveedor aún no tiene usuarios" />
          ) : (
            <Table
              columns={[
                { key: 'username', label: 'Usuario' },
                { key: 'role', label: 'Rol', align: 'center' },
                { key: 'active', label: 'Activo', align: 'center' },
                { key: 'created', label: 'Creado' },
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

      <Modal open={addUserOpen} onClose={() => setAddUserOpen(false)} title="Crear usuario del proveedor">
        <form onSubmit={handleAddUser} className="space-y-4">
          <Field label="Usuario">
            <Input value={userForm.username} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })} placeholder="Mínimo 3 caracteres" required />
          </Field>
          <Field label="Email" hint="Opcional">
            <Input type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} placeholder="usuario@proveedor.com" />
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

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">Usuarios de todos los proveedores.</p>
      {users.length === 0 ? (
        <EmptyState message="No hay usuarios" />
      ) : (
        <Table
          columns={[
            { key: 'username', label: 'Usuario' },
            { key: 'tenant', label: 'Proveedor' },
            { key: 'role', label: 'Rol', align: 'center' },
            { key: 'active', label: 'Activo', align: 'center' },
            { key: 'terms', label: 'Términos', align: 'center' },
            { key: 'created', label: 'Creado' },
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
                <div className="flex justify-center gap-1">
                  {u.role !== 'superadmin' && (
                    <>
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
        <p className="text-sm text-slate-400">Gestión global de proveedores, usuarios, empresa y backups</p>
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
