import Brand from './Brand'

const navItems = [
  ['overview', '⌂', 'Overview'],
  ['browse', '◎', 'Browse apps'],
  ['bills', '▣', 'Bills & pay'],
  ['connections', '⇄', 'Connected apps'],
  ['intelligence', '✦', 'SafePay AI'],
  ['activity', '↻', 'Activity'],
]

export default function AppShell({ user, page, setPage, onLogout, children }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand />
        <nav>
          {navItems.map(([id, icon, label]) => (
            <button key={id} className={page === id ? 'active' : ''} onClick={() => setPage(id)}>
              <span>{icon}</span>{label}
            </button>
          ))}
        </nav>
        <div className="sidebar-safety">
          <span className="safety-icon">✓</span>
          <div><b>Protected mode</b><small>Approval required for every payment</small></div>
        </div>
        <button className="logout" onClick={onLogout}>Sign out</button>
      </aside>
      <main className="main-panel">
        <header className="app-header">
          <div><span className="mobile-brand"><Brand compact /></span><span className="header-kicker">Personal finance OS</span></div>
          <div className="user-chip"><span>{user.full_name?.[0]?.toUpperCase()}</span><div><b>{user.full_name}</b><small>{user.email}</small></div></div>
        </header>
        {children}
      </main>
    </div>
  )
}
