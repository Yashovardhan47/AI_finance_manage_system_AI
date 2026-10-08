import { lazy, Suspense, useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import { api } from './lib/api'
import Activity from './pages/Activity'
import Bills from './pages/Bills'
import BrowseApps from './pages/BrowseApps'
import Connections from './pages/Connections'
import Intelligence from './pages/Intelligence'
import Landing from './pages/Landing'
import Overview from './pages/Overview'

const BillingOperations = lazy(() => import('./pages/BillingOperations'))
const FinancialOperations = lazy(() => import('./pages/FinancialOperations'))

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [page, setPage] = useState('overview')
  const [authError, setAuthError] = useState('')
  useEffect(() => {
    const isCallback = window.location.pathname === '/auth/callback'
    const params = new URLSearchParams(window.location.search)
    const callbackFailed = isCallback && params.get('status') === 'error'
    if (callbackFailed) setAuthError(oauthErrorMessage(params.get('error')))
    api('/auth/me')
      .then(setUser)
      .catch(() => {
        if (isCallback && !callbackFailed) setAuthError('Google sign-in completed without a valid BillFlow session. Please try again.')
      })
      .finally(() => {
        if (isCallback) window.history.replaceState({}, '', '/')
        setChecking(false)
      })
  }, [])
  const authenticated = (value) => { setAuthError(''); setUser(value) }
  const logout = async () => { await api('/auth/logout', { method: 'POST' }); setUser(null); setPage('overview') }
  if (checking) return <div className="boot-screen"><span className="brand-mark">B</span><i /></div>
  if (!user) return <Landing onAuthenticated={authenticated} authError={authError} onAuthErrorDismissed={() => setAuthError('')} />
  const pages = { overview: <Overview user={user} onNavigate={setPage} />, autopilot: <Suspense fallback={<div className="page"><div className="skeleton large-skeleton" /></div>}><FinancialOperations /></Suspense>, browse: <BrowseApps onNavigate={setPage} />, bills: <Bills />, billing: <Suspense fallback={<div className="page"><div className="skeleton large-skeleton" /></div>}><BillingOperations /></Suspense>, connections: <Connections />, intelligence: <Intelligence />, activity: <Activity /> }
  return <AppShell user={user} page={page} setPage={setPage} onLogout={logout}>{pages[page]}</AppShell>
}

function oauthErrorMessage(code) {
  const messages = {
    google_access_denied: 'Google sign-in was cancelled. No BillFlow account was changed.',
    google_account_conflict: 'This email is already linked to a different Google identity. Sign in with the original method or contact support.',
    google_not_configured: 'Google sign-in is not configured for this deployment.',
    invalid_oauth_state: 'The Google sign-in request expired or did not match this browser. Please start again.',
    missing_authorization_code: 'Google did not return an authorization code. Please try again.',
    google_token_exchange_failed: 'BillFlow could not complete the secure Google token exchange. Please try again.',
    google_identity_invalid: 'Google returned an identity that BillFlow could not verify.',
    google_provider_error: 'Google could not complete sign-in. Please try again.',
  }
  return messages[code] || 'Google sign-in could not be completed. Please try again.'
}
