import { createContext, useContext, useEffect, useState } from 'react'
import { fetchMe, logout as doLogout, login as doLogin, ping, releaseSession } from '../api/auth'
import { getToken } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      if (!getToken()) {
        setLoading(false)
        return
      }
      try {
        const me = await fetchMe()
        setUser(me)
      } catch {
        /* token inválido: el interceptor redirige */
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // Heartbeat: mientras haya token, se mantiene viva la sesión única cada 5
  // minutos. Al cerrar la pestaña se libera la sesión para permitir reingresar
  // desde otro equipo de inmediato.
  useEffect(() => {
    if (!getToken()) return
    const id = setInterval(() => {
      if (getToken()) ping().catch(() => {})
    }, 5 * 60 * 1000)

    const onUnload = () => releaseSession()
    window.addEventListener('pagehide', onUnload)
    window.addEventListener('beforeunload', onUnload)

    return () => {
      clearInterval(id)
      window.removeEventListener('pagehide', onUnload)
      window.removeEventListener('beforeunload', onUnload)
    }
  }, [user])

  const login = async (username, password) => {
    const u = await doLogin(username, password)
    setUser(u)
    return u
  }

  const logout = async (e) => {
    if (e) e.preventDefault()
    setUser(null)
    await doLogout()
  }

  return (
    <AuthContext.Provider value={{ user, setUser, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
