import { api, setToken, clearToken } from './client'

export async function login(username, password) {
  const { data } = await api.post('/auth/login', { username, password })
  setToken(data.access_token)
  return data.user
}

export async function fetchMe() {
  const { data } = await api.get('/auth/me')
  return data
}

export async function acceptTerms() {
  const { data } = await api.post('/auth/accept-terms')
  return data
}

export function logout() {
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
