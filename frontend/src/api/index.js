import { api, API_BASE, getToken } from './client'

export async function getDashboard() {
  const { data } = await api.get('/dashboard')
  return data
}

export async function getProducts({ q = '', lowStockOnly = false } = {}) {
  const params = {}
  if (q) params.q = q
  if (lowStockOnly) params.low_stock_only = true
  const { data } = await api.get('/products', { params })
  return data
}

export async function createProduct(payload) {
  const { data } = await api.post('/products', payload)
  return data
}

export async function updateProduct(id, payload) {
  const { data } = await api.put(`/products/${id}`, payload)
  return data
}

export async function deleteProduct(id) {
  const { data } = await api.delete(`/products/${id}`)
  return data
}

export async function deleteAllProducts() {
  const { data } = await api.delete('/products/all')
  return data
}

export async function getLoans({ q = '', status = '', date = '' } = {}) {
  const params = {}
  if (q) params.q = q
  if (status) params.status = status
  if (date) params.date = date
  const { data } = await api.get('/loans', { params })
  return data
}

export async function createLoan(payload) {
  const { data } = await api.post('/loans', payload)
  return data
}

export async function updateLoan(id, payload) {
  const { data } = await api.put(`/loans/${id}`, payload)
  return data
}

export async function returnLoan(id, returnedQty, locationIn = '') {
  const payload = { returned_qty: returnedQty }
  if (locationIn) payload.location_in = locationIn
  const { data } = await api.post(`/loans/${id}/return`, payload)
  return data
}

export async function extendLoan(id, days) {
  const { data } = await api.post(`/loans/${id}/extend?days=${days}`)
  return data
}

export async function getAudit({ q = '', day = '' } = {}) {
  const params = {}
  if (q) params.q = q
  if (day) params.day = day
  const { data } = await api.get('/audit', { params })
  return data
}

export async function getLicenseStatus() {
  const { data } = await api.get('/license/status')
  return data
}

export async function activateLicense(key) {
  const { data } = await api.post('/license/activate', { key })
  return data
}

export async function getMachineCode() {
  const { data } = await api.get('/license/machine-code')
  return data
}

export async function activateOfflineLicense(key) {
  const { data } = await api.post('/license/offline/activate', { key })
  return data
}

export async function getSettings() {
  const { data } = await api.get('/settings')
  return data
}

export async function updateSettings(payload) {
  const { data } = await api.put('/settings', payload)
  return data
}

export async function getUsers() {
  const { data } = await api.get('/users')
  return data
}

export async function getTermsAcceptances() {
  const { data } = await api.get('/users/terms-acceptances')
  return data
}

export async function createUser(payload) {
  const { data } = await api.post('/users', payload)
  return data
}

export async function deleteUser(id) {
  const { data } = await api.delete(`/users/${id}`)
  return data
}

export async function adminResetPassword(id, newPassword) {
  const { data } = await api.post(`/users/${id}/reset-password`, { new_password: newPassword })
  return data
}

export async function setSecurityQuestion(question, answer) {
  const { data } = await api.put('/settings/security-question', { question, answer })
  return data
}

export async function runBackup() {
  const { data } = await api.post('/backup/run')
  return data
}

export async function listBackups() {
  const { data } = await api.get('/backup/list')
  return data
}

export async function restoreBackup(file) {
  const fd = new FormData()
  fd.append('file', file)
  const { data } = await api.post('/backup/restore', fd)
  return data
}

export async function purgeBackups() {
  const { data } = await api.post('/backup/purge')
  return data
}

export async function getDriveStatus() {
  const { data } = await api.get('/backup/drive/status')
  return data
}

export async function testDriveConnection() {
  const { data } = await api.post('/backup/drive/test')
  return data
}

export async function uploadBackupToDrive(name) {
  const { data } = await api.post(`/backup/drive/upload/${encodeURIComponent(name)}`)
  return data
}

export async function listDriveBackups() {
  const { data } = await api.get('/backup/drive/list')
  return data
}

export async function restoreFromDrive(fileId) {
  const { data } = await api.post(`/backup/drive/restore/${encodeURIComponent(fileId)}`)
  return data
}

/* URL para iniciar el flujo "Conectar con Google Drive" (navegación completa,
   el JWT viaja como parámetro porque Google redirige sin cabeceras). */
export function connectDriveUrl(returnPath = window.location.pathname) {
  const token = getToken()
  return `${API_BASE}/backup/drive/oauth/start?token=${encodeURIComponent(token)}&return_path=${encodeURIComponent(returnPath)}`
}

export async function disconnectDrive() {
  const { data } = await api.post('/backup/drive/oauth/disconnect')
  return data
}

/* ================= SUPER ADMIN (multi-cliente) ================= */

export async function getTenants() {
  const { data } = await api.get('/superadmin/tenants')
  return data
}

export async function createTenant(payload) {
  const { data } = await api.post('/superadmin/tenants', payload)
  return data
}

export async function updateTenant(id, payload) {
  const { data } = await api.put(`/superadmin/tenants/${id}`, payload)
  return data
}

export async function deleteTenant(id) {
  const { data } = await api.delete(`/superadmin/tenants/${id}`)
  return data
}

export async function getTenantUsers(tenantId) {
  const { data } = await api.get(`/superadmin/tenants/${tenantId}/users`)
  return data
}

export async function createTenantUser(tenantId, payload) {
  const { data } = await api.post(`/superadmin/tenants/${tenantId}/users`, payload)
  return data
}

export async function getGlobalUsers() {
  const { data } = await api.get('/superadmin/users')
  return data
}

export async function superadminUpdateUser(id, payload) {
  const { data } = await api.put(`/superadmin/users/${id}`, payload)
  return data
}

export async function superadminResetPassword(id, newPassword) {
  const { data } = await api.post(`/superadmin/users/${id}/reset-password`, { new_password: newPassword })
  return data
}

export async function superadminDeleteUser(id) {
  const { data } = await api.delete(`/superadmin/users/${id}`)
  return data
}
