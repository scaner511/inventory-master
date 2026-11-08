// build-trigger-2: VITE_API_URL -> inventorymasteros.duckdns.org
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster, ToastBar, toast } from 'react-hot-toast'
import App from './App.jsx'
import { AuthProvider } from './context/AuthContext.jsx'
import './index.css'

/* Notificaciones flexibles: duran 30 segundos (en vez de los 4 s por defecto)
   y permiten cerrarse manualmente con la ✕. Solo las de tipo 'loading'
   no se cierran solas (deben hacerlo sus callers con toast.dismiss). */
function AppToaster() {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 30000,
        style: {
          background: '#1e293b',
          color: '#f1f5f9',
          border: '1px solid #334155',
          borderRadius: 10,
          fontSize: '0.875rem',
          maxWidth: 420,
        },
      }}
    >
      {(t) => (
        <ToastBar toast={t}>
          {({ icon, message }) => (
            <span className="flex w-full items-start gap-2 px-1 py-0.5">
              <span className="mt-0.5 shrink-0">{icon}</span>
              <span className="flex-1 break-words">{message}</span>
              {t.type !== 'loading' && (
                <button
                  onClick={() => toast.dismiss(t.id)}
                  className="shrink-0 rounded-md px-1.5 py-0.5 text-slate-400 transition hover:bg-slate-700 hover:text-white"
                  aria-label="Cerrar notificación"
                >
                  ✕
                </button>
              )}
            </span>
          )}
        </ToastBar>
      )}
    </Toaster>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
        <AppToaster />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)