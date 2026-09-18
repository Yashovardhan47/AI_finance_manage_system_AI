import { useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import { api } from './lib/api'
import Activity from './pages/Activity'
import Bills from './pages/Bills'
import BrowseApps from './pages/BrowseApps'
import Connections from './pages/Connections'
import Intelligence from './pages/Intelligence'
import Landing from './pages/Landing'
import Overview from './pages/Overview'

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [page, setPage] = useState('overview')
  useEffect(() => { api('/auth/me').then(setUser).catch(() => {}).finally(() => setChecking(false)) }, [])
  const logout = async () => { await api('/auth/logout', { method: 'POST' }); setUser(null); setPage('overview') }
  if (checking) return <div className="boot-screen"><span className="brand-mark">B</span><i /></div>
  if (!user) return <Landing onAuthenticated={setUser} />
  const pages = { overview: <Overview user={user} onNavigate={setPage} />, browse: <BrowseApps onNavigate={setPage} />, bills: <Bills />, connections: <Connections />, intelligence: <Intelligence />, activity: <Activity /> }
  return <AppShell user={user} page={page} setPage={setPage} onLogout={logout}>{pages[page]}</AppShell>
}
