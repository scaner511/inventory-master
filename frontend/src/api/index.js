import { api, getToken } from './client'

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

export async function getLoans({ q = '', status = '' } = {}) {
  const params = {}
  if (q) params.q = q
  if (status) params.status = status
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

export async function returnLoan(id, returnedQty) {
  const { data } = await api.post(`/loans/${id}/return`, { returned_qty: returnedQty })
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
