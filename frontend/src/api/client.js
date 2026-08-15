import axios from 'axios'
import toast from 'react-hot-toast'

const TOKEN_KEY = 'im_token'

// En producción la API vive en otro dominio (Render). VITE_API_URL apunta a su
// base; si no está definido se mantiene el mismo origen con prefijo /api
// (desarrollo). Se agrega /api automáticamente si la URL no lo trae.
const _rawApiUrl = (import.meta.env.VITE_API_URL || '/api').trim().replace(/\/+$/, '')
export const API_BASE = _rawApiUrl.endsWith('/api') ? _rawApiUrl : `${_rawApiUrl}/api`

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }

    if (status === 403 && detail?.code === 'LICENSE_BLOCKED') {
      window.location.href = '/license'
    }

    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message || error.response?.data?.error || 'Ocurrió un error inesperado'
    toast.error(message)
    return Promise.reject(error)
  },
)

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export function formatMoney(value) {
  return new Intl.NumberFormat('es-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(Number(value || 0))
}

export async function openAuthenticatedUrl(url) {
  /* Abre un endpoint que devuelve un archivo (PDF/Excel) enviando el token JWT,
     porque window.open() no puede incluir la cabecera Authorization. */
  const win = window.open('', '_blank')
  try {
    const cleanUrl = url.startsWith('/api/') ? url.slice(4) : url
    const res = await api.get(cleanUrl, { responseType: 'blob' })
    const blobUrl = URL.createObjectURL(res.data)
    if (!win) {
      window.location.href = blobUrl
      return
    }
    win.location.href = blobUrl
  } catch (err) {
    if (win) win.close()
    throw err
  }
}
