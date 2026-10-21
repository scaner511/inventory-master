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

export async function stockEntry(payload) {
  const { data } = await api.post('/products/stock-entry', payload)
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

export async function returnLoan(id, itemId, returnedQty, locationIn = '') {
  const payload = { item_id: itemId, returned_qty: returnedQty }
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

export async function getLogoUrl() {
  /* El logo está protegido por autenticación; se descarga como blob y se
     convierte a URL local para poder mostrarlo en <img>. */
  const { data } = await api.get('/settings/logo', { responseType: 'blob' })
  return URL.createObjectURL(data)
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

export async function updateUser(id, payload) {
  const { data } = await api.put(`/users/${id}`, payload)
  return data
}

export async function generateCaptureLink(id, regenerate = false) {
  const { data } = await api.post(`/users/${id}/capture-link`, null, {
    params: { regenerate },
  })
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

/* ================= RECEPCIÓN DE MERCANCÍA (depósito temporal) ================= */

export async function getTsLocations() {
  const { data } = await api.get('/temporary-storage/locations')
  return data
}

export async function createTsLocation(payload) {
  const { data } = await api.post('/temporary-storage/locations', payload)
  return data
}

export async function updateTsLocation(id, payload) {
  const { data } = await api.put(`/temporary-storage/locations/${id}`, payload)
  return data
}

export async function deleteTsLocation(id) {
  const { data } = await api.delete(`/temporary-storage/locations/${id}`)
  return data
}

export async function getTemporaryStorage({ q = '', status = '', party = '', locationId = '', dateFrom = '', dateTo = '' } = {}) {
  const params = {}
  if (q) params.q = q
  if (status) params.status = status
  if (party) params.party = party
  if (locationId) params.location_id = locationId
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  const { data } = await api.get('/temporary-storage', { params })
  return data
}

export async function getTemporaryStorageOne(id) {
  const { data } = await api.get(`/temporary-storage/${id}`)
  return data
}

export async function createTemporaryStorage(payload) {
  const { data } = await api.post('/temporary-storage', payload)
  return data
}

export async function updateTemporaryStorage(id, payload) {
  const { data } = await api.put(`/temporary-storage/${id}`, payload)
  return data
}

export async function exitTemporaryStorage(id, payload) {
  const { data } = await api.post(`/temporary-storage/${id}/exit`, payload)
  return data
}

export async function deleteTemporaryStorage(id) {
  const { data } = await api.delete(`/temporary-storage/${id}`)
  return data
}

export async function getTsHistory(id) {
  const { data } = await api.get(`/temporary-storage/${id}/history`)
  return data
}

export async function getTsDashboard() {
  const { data } = await api.get('/temporary-storage/dashboard')
  return data
}

/* ================= GESTIÓN DE PROSPECTOS (CRM comercial) ================= */

export async function getProspects({ q = '', status = '', stage = '', ownerId = '', rating = '' } = {}) {
  const params = {}
  if (q) params.q = q
  if (status) params.status = status
  if (stage) params.stage = stage
  if (ownerId) params.owner_id = ownerId
  if (rating) params.rating = rating
  const { data } = await api.get('/prospects', { params })
  return data
}

export async function getProspect(id) {
  const { data } = await api.get(`/prospects/${id}`)
  return data
}

export async function createProspect(payload) {
  const { data } = await api.post('/prospects', payload)
  return data
}

export async function updateProspect(id, payload) {
  const { data } = await api.put(`/prospects/${id}`, payload)
  return data
}

export async function moveProspect(id, stageSlug) {
  const { data } = await api.post(`/prospects/${id}/move`, { stage_slug: stageSlug })
  return data
}

export async function convertProspect(id, note = null) {
  const { data } = await api.post(`/prospects/${id}/convert`, { note })
  return data
}

export async function deleteProspect(id) {
  const { data } = await api.delete(`/prospects/${id}`)
  return data
}

export async function getProspectNotes(id) {
  const { data } = await api.get(`/prospects/${id}/notes`)
  return data
}

export async function addProspectNote(id, text) {
  const { data } = await api.post(`/prospects/${id}/notes`, { text })
  return data
}

export async function getProspectActivities(id) {
  const { data } = await api.get(`/prospects/${id}/activities`)
  return data
}

export async function addProspectActivity(id, payload) {
  const { data } = await api.post(`/prospects/${id}/activities`, payload)
  return data
}

export async function updateProspectActivity(activityId, payload) {
  const { data } = await api.put(`/prospects/activities/${activityId}`, payload)
  return data
}

export async function getProspectHistory(id) {
  const { data } = await api.get(`/prospects/${id}/history`)
  return data
}

export async function getProspectPipeline() {
  const { data } = await api.get('/prospects/pipeline')
  return data
}

export async function getProspectBoard() {
  const { data } = await api.get('/prospects/board')
  return data
}

export async function getOpportunitySummary() {
  const { data } = await api.get('/prospects/opportunity-summary')
  return data
}

/* ---- Evidencias (adjuntos) y firmas del prospecto ---- */

export async function getProspectFiles(id) {
  const { data } = await api.get(`/prospects/${id}/files`)
  return data
}

export async function uploadProspectFile(id, file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post(`/prospects/${id}/files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function deleteProspectFile(fileId) {
  const { data } = await api.delete(`/prospects/files/${fileId}`)
  return data
}

export async function getProspectSignatures(id) {
  const { data } = await api.get(`/prospects/${id}/signatures`)
  return data
}

export async function saveProspectSignature(id, role, imageData) {
  const { data } = await api.post(`/prospects/${id}/signatures`, { role, image_data: imageData })
  return data
}

/* ================= CITAS, RECORDATORIOS Y NOTIFICACIONES ================= */

export async function getAppointments({ dateFrom = '', dateTo = '', userId = '', status = '' } = {}) {
  const params = {}
  if (dateFrom) params.date_from = dateFrom
  if (dateTo) params.date_to = dateTo
  if (userId) params.user_id = userId
  if (status) params.status = status
  const { data } = await api.get('/appointments', { params })
  return data
}

export async function createAppointment(payload) {
  const { data } = await api.post('/appointments', payload)
  return data
}

export async function updateAppointment(id, payload) {
  const { data } = await api.put(`/appointments/${id}`, payload)
  return data
}

export async function deleteAppointment(id) {
  const { data } = await api.delete(`/appointments/${id}`)
  return data
}

export async function getAppointmentReminders(id) {
  const { data } = await api.get(`/appointments/${id}/reminders`)
  return data
}

export async function closeAppointment(id, payload) {
  const { data } = await api.post(`/appointments/${id}/closure`, payload)
  return data
}

export async function getAppointmentClosure(id) {
  const { data } = await api.get(`/appointments/${id}/closure`)
  return data
}

export async function getCommercialDashboard() {
  const { data } = await api.get('/appointments/dashboard/commercial')
  return data
}

export async function getNotifications({ unreadOnly = false, limit = 50 } = {}) {
  const { data } = await api.get('/notifications', {
    params: { unread_only: unreadOnly, limit },
  })
  return data
}

export async function getUnreadNotificationsCount() {
  const { data } = await api.get('/notifications/unread-count')
  return data.count
}

export async function markNotificationRead(id) {
  const { data } = await api.post(`/notifications/${id}/read`)
  return data
}

export async function markAllNotificationsRead() {
  const { data } = await api.post('/notifications/read-all')
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

export async function resetTenant(id, payload) {
  const { data } = await api.post(`/superadmin/tenants/${id}/reset`, payload)
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

export async function renewUserSubscription(id, days = 30) {
  const { data } = await api.post(`/superadmin/users/${id}/renew`, { days })
  return data
}

export async function renewTenantSubscription(id, days = 30) {
  const { data } = await api.post(`/superadmin/tenants/${id}/renew`, { days })
  return data
}

export async function superadminDeleteUser(id) {
  const { data } = await api.delete(`/superadmin/users/${id}`)
  return data
}

// ===================== CAPTACIÓN PÚBLICA DE PROSPECTOS =====================

export async function getCaptureCampaigns({ status = '' } = {}) {
  const params = {}
  if (status) params.status = status
  const { data } = await api.get('/capture/campaigns', { params })
  return data
}

export async function createCaptureCampaign(payload) {
  const { data } = await api.post('/capture/campaigns', payload)
  return data
}

export async function updateCaptureCampaign(id, payload) {
  const { data } = await api.put(`/capture/campaigns/${id}`, payload)
  return data
}

export async function deleteCaptureCampaign(id) {
  const { data } = await api.delete(`/capture/campaigns/${id}`)
  return data
}

export async function getCapturePrizes() {
  const { data } = await api.get('/capture/prizes')
  return data
}

export async function createCapturePrize(payload) {
  const { data } = await api.post('/capture/prizes', payload)
  return data
}

export async function updateCapturePrize(id, payload) {
  const { data } = await api.put(`/capture/prizes/${id}`, payload)
  return data
}

export async function deleteCapturePrize(id) {
  const { data } = await api.delete(`/capture/prizes/${id}`)
  return data
}

export async function getCaptureConfig() {
  const { data } = await api.get('/capture/config')
  return data
}

export async function updateCaptureConfig(payload) {
  const { data } = await api.put('/capture/config', payload)
  return data
}

export async function getCaptureSessions() {
  const { data } = await api.get('/capture/sessions')
  return data
}

export async function startCaptureSession(payload) {
  const { data } = await api.post('/capture/sessions', payload)
  return data
}

export async function closeCaptureSession(id) {
  const { data } = await api.post(`/capture/sessions/${id}/close`)
  return data
}

export async function reopenCaptureSession(id) {
  const { data } = await api.post(`/capture/sessions/${id}/reopen`)
  return data
}

export async function getCaptureEntries(params = {}) {
  const { data } = await api.get('/capture/entries', { params })
  return data
}

export async function getCaptureHistory(params = {}) {
  const { data } = await api.get('/capture/history', { params })
  return data
}

export async function getCaptureDashboard({ days = 30 } = {}) {
  const { data } = await api.get('/capture/dashboard', { params: { days } })
  return data
}

export function captureExportUrl(kind) {
  // kind: 'excel' | 'csv' | 'pdf'
  return `${API_BASE}/capture/export/${kind}`
}

// --- Endpoints públicos (tablet) con token de jornada --------------------
const CAPTURE_TOKEN_KEY = 'im_capture_token'

export function setCaptureToken(token) {
  if (token) localStorage.setItem(CAPTURE_TOKEN_KEY, token)
}

export function getCaptureToken() {
  return localStorage.getItem(CAPTURE_TOKEN_KEY)
}

export function clearCaptureToken() {
  localStorage.removeItem(CAPTURE_TOKEN_KEY)
}

function captureTokenHeaders(token) {
  return { headers: { 'X-Capture-Token': token || getCaptureToken() || '' } }
}

export async function getPublicCaptureSession(token) {
  const { data } = await api.get('/capture/public/session', captureTokenHeaders(token))
  return data
}

export function getPublicCaptureLogoUrl(token) {
  return `${API_BASE}/capture/public/logo?token=${encodeURIComponent(token || getCaptureToken() || '')}`
}

export async function getPublicCaptureCampaigns(token) {
  const { data } = await api.get('/capture/public/campaigns', captureTokenHeaders(token))
  return data
}

export async function selectPublicCampaign(campaignId, token) {
  const { data } = await api.post(
    '/capture/public/campaign',
    { campaign_id: campaignId },
    captureTokenHeaders(token),
  )
  return data
}

export async function publicCaptureSpin(token) {
  const { data } = await api.post('/capture/public/spin', {}, captureTokenHeaders(token))
  return data
}

export async function publicCheckDuplicate(phone, token) {
  const { data } = await api.post(
    '/capture/public/check-duplicate',
    { phone },
    captureTokenHeaders(token),
  )
  return data
}

export async function publicCaptureRegister(payload, token) {
  const { data } = await api.post('/capture/public/register', payload, captureTokenHeaders(token))
  return data
}
