import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import Login from './pages/Login.jsx'
import Layout from './components/layout/Layout.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Products from './pages/Products.jsx'
import Loans from './pages/Loans.jsx'
import TemporaryStorage from './pages/TemporaryStorage.jsx'
import Prospects from './pages/Prospects.jsx'
import Calendar from './pages/Calendar.jsx'
import CommercialDashboard from './pages/CommercialDashboard.jsx'
import CaptureAdmin from './pages/CaptureAdmin.jsx'
import CaptureDashboard from './pages/CaptureDashboard.jsx'
import CapturePublic from './pages/CapturePublic.jsx'
import History from './pages/History.jsx'
import Admin from './pages/Admin.jsx'
import SuperAdmin from './pages/SuperAdmin.jsx'
import License from './pages/License.jsx'
import ChangePassword from './pages/ChangePassword.jsx'
import { useEffect, useState } from 'react'
import { getLicenseStatus } from './api/index.js'
import TermsModal from './components/TermsModal.jsx'

function Protected({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <FullLoader />
  if (!user) return <Navigate to="/login" replace />
  // Aceptación OBLIGATORIA de términos: mientras no esté aceptada se muestra
  // el modal EN LUGAR de la aplicación (imposible navegar ni cerrarlo).
  if (!user.accepted_terms) return <TermsModal />
  if (user.must_change_password && window.location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />
  }
  return children
}

function LicenseGate({ children }) {
  const { user } = useAuth()
  const [status, setStatus] = useState(null)

  useEffect(() => {
    if (user?.role === 'admin' || user?.role === 'superadmin') {
      setStatus({ active: true })
      return
    }
    getLicenseStatus()
      .then(setStatus)
      .catch(() => setStatus({ active: false }))
  }, [user])

  if (!status) return <FullLoader />
  if (!status.active) return <Navigate to="/license" replace />
  return children
}

function ModuleGate({ module, children }) {
  const { user } = useAuth()
  if (
    user?.role !== 'superadmin' &&
    Array.isArray(user?.modules) &&
    !user.modules.includes(module)
  ) {
    return <Navigate to="/" replace />
  }
  return children
}

export function FullLoader() {
  return (
    <div className="flex h-screen items-center justify-center bg-[#0b1220]">
      <div className="text-center">
        <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <p className="text-sm text-slate-400">Cargando Inventory Master...</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route
          path="/"
          element={
            <LicenseGate>
              <Dashboard />
            </LicenseGate>
          }
        />
        <Route
          path="/products"
          element={
            <LicenseGate>
              <Products />
            </LicenseGate>
          }
        />
        <Route
          path="/loans"
          element={
            <LicenseGate>
              <Loans />
            </LicenseGate>
          }
        />
        <Route
          path="/temporary-storage"
          element={
            <LicenseGate>
              <ModuleGate module="temporary_storage">
                <TemporaryStorage />
              </ModuleGate>
            </LicenseGate>
          }
        />
        <Route
          path="/prospects"
          element={
            <LicenseGate>
              <ModuleGate module="prospects">
                <Prospects />
              </ModuleGate>
            </LicenseGate>
          }
        />
        <Route
          path="/calendar"
          element={
            <LicenseGate>
              <ModuleGate module="calendar">
                <Calendar />
              </ModuleGate>
            </LicenseGate>
          }
        />
        <Route
          path="/commercial"
          element={
            <LicenseGate>
              <ModuleGate module="commercial">
                <CommercialDashboard />
              </ModuleGate>
            </LicenseGate>
          }
        />
        <Route
          path="/captacion"
          element={
            <LicenseGate>
              <ModuleGate module="capture">
                <CaptureAdmin />
              </ModuleGate>
            </LicenseGate>
          }
        />
        <Route
          path="/captacion/dashboard"
          element={
            <LicenseGate>
              <ModuleGate module="capture">
                <CaptureDashboard />
              </ModuleGate>
            </LicenseGate>
          }
        />
        <Route
          path="/history"
          element={
            <LicenseGate>
              <History />
            </LicenseGate>
          }
        />
        <Route path="/license" element={<License />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/superadmin" element={<SuperAdmin />} />
        <Route path="/change-password" element={<ChangePassword />} />
      </Route>
      <Route path="/captacion/tablet" element={<CapturePublic />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
