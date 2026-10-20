import { api, setToken, clearToken, getToken, API_BASE } from './client'

export async function login(username, password) {
  const { data } = await api.post('/auth/login', { username, password })
  setToken(data.access_token)
  return data.user
}

export async function fetchMe() {
  const { data } = await api.get('/auth/me')
  return data
}

// Mantiene viva la sesión única mientras la pestaña está abierta.
export async function ping() {
  await api.get('/auth/me')
}

// Libera la sesión al cerrar la pestaña/ventana. Usa sendBeacon porque los
// navegadores no esperan a peticiones normales durante 'unload'.
export function releaseSession() {
  const token = getToken()
  if (!token) return
  const url = `${API_BASE}/auth/logout`
  try {
    const headers = { Authorization: `Bearer ${token}` }
    const blob = new Blob([JSON.stringify({})], { type: 'application/json' })
    if (navigator.sendBeacon) {
      // sendBeacon no permite cabeceras personalizadas: se envía el token por
      // query para que el backend pueda liberar la sesión igualmente.
      navigator.sendBeacon(`${url}?token=${encodeURIComponent(token)}`, blob)
      return
    }
    fetch(url, { method: 'POST', headers, keepalive: true })
  } catch {
    /* noop */
  }
}

export async function acceptTerms() {
  const { data } = await api.post('/auth/accept-terms')
  return data
}

export async function logout() {
  try {
    await api.post('/auth/logout')
  } catch {
    /* aunque falle, se limpia el token local */
  }
  clearToken()
  window.location.href = '/login'
}

export async function forgotPassword(username, answer) {
  const { data } = await api.post('/auth/forgot-password', { username, answer })
  return data.reset_token
}

export async function resetPassword(resetToken, newPassword) {
  const { data } = await api.post(`/auth/reset-password?reset_token=${resetToken}`, { new_password: newPassword })
  return data
}

export async function changePassword(currentPassword, newPassword) {
  const { data } = await api.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword })
  return data
}
