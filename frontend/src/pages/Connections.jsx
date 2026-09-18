import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const categoryIcon = { home: '⌂', health: '✚', entertainment: '▶', 'multi-category': '◎' }

export default function Connections() {
  const [catalog, setCatalog] = useState([])
  const [connections, setConnections] = useState([])
  const [events, setEvents] = useState([])
  const [selected, setSelected] = useState(null)
  const [customerId, setCustomerId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(null)
  const [message, setMessage] = useState('')

  const load = async () => {
    const [catalogData, connectionData, eventData] = await Promise.all([
      api('/integrations/catalog'), api('/integrations/connections'), api('/integrations/events'),
    ])
    setCatalog(catalogData.items); setConnections(connectionData); setEvents(eventData)
  }
  useEffect(() => { load().catch((error) => setMessage(error.message)) }, [])

  const connect = async (event) => {
    event.preventDefault(); setBusy('connect'); setMessage('')
    try {
      const connection = await api('/integrations/connections', {
        method: 'POST',
        body: JSON.stringify({ provider_slug: selected.slug, external_customer_id: customerId, display_name: displayName || selected.name }),
      })
      await api(`/integrations/connections/${connection.id}/sync`, { method: 'POST' })
      setSelected(null); setCustomerId(''); setDisplayName('')
      setMessage(`${connection.provider_name} connected and its current obligation was imported.`)
      await load()
    } catch (error) { setMessage(error.message) } finally { setBusy(null) }
  }

  const sync = async (connection) => {
    setBusy(connection.id); setMessage('')
    try {
      const result = await api(`/integrations/connections/${connection.id}/sync`, { method: 'POST' })
      setMessage(`${result.provider} synchronized: ${result.imported} imported, ${result.updated} updated.`)
      await load()
    } catch (error) { setMessage(error.message) } finally { setBusy(null) }
  }

  const connectionFor = (slug) => connections.find((connection) => connection.provider_slug === slug)

  return (
    <div className="page connections-page">
      <div className="page-title"><div><span className="eyebrow">Official account linking</span><h1>Connected applications</h1><p>Import provider bills and synchronize the real service state after settlement.</p></div><span className="model-badge"><i /> Provider source of truth</span></div>
      {message && <div className="notice"><span>{message}</span><button onClick={() => setMessage('')}>×</button></div>}
      <div className="integration-rule"><span className="safety-icon">✓</span><div><b>One identity link per provider</b><p>Google login identifies you to BillFlow only. Each home, health or entertainment account needs its own official OAuth/API connection or customer reference. Passwords, UPI PINs and OTPs are never collected.</p></div></div>
      <section className="connector-grid">
        {catalog.map((provider) => {
          const connection = connectionFor(provider.slug)
          return <article className={`connector-card ${provider.enabled ? '' : 'disabled'}`} key={provider.slug}>
            <div className="connector-top"><span className={`provider-icon ${provider.category}`}>{categoryIcon[provider.category] || '•'}</span><div><small>{provider.category}</small><h2>{provider.name}</h2></div><span className={`connection-mode ${provider.connection_type}`}>{provider.connection_type.replace('_',' ')}</span></div>
            <p>{provider.description}</p>
            <div className="capability-list">{provider.capabilities.map((item) => <span key={item}>✓ {item.replaceAll('_',' ')}</span>)}</div>
            {connection ? <ConnectedState connection={connection} onSync={() => sync(connection)} busy={busy === connection.id} /> : <button className="button primary full" disabled={!provider.enabled} onClick={() => { setSelected(provider); setDisplayName(provider.name) }}>{provider.enabled ? 'Connect provider account' : 'Partner onboarding required'}</button>}
            {!provider.production_ready && <small className="sandbox-label">Demonstration connector · same lifecycle as an official API</small>}
          </article>
        })}
      </section>

      <section className="panel provider-events"><div className="panel-heading"><div><span className="eyebrow">Reconciliation evidence</span><h2>Provider synchronization events</h2></div></div>{events.length ? events.slice(0,8).map((event) => <div className="provider-event" key={event.id}><span className="event-check">✓</span><div><b>{event.event_type.replaceAll('.',' · ').replaceAll('_',' ')}</b><small>{event.provider_reference || `Connection #${event.connection_id}`}</small></div><span className={`status ${event.status}`}>{event.status}</span><time>{new Date(event.created_at).toLocaleString('en-IN')}</time></div>) : <div className="mini-empty">Connect and synchronize an account to create provider events.</div>}</section>

      {selected && <div className="modal-backdrop" onMouseDown={() => setSelected(null)}><div className="form-modal" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" onClick={() => setSelected(null)}>×</button><span className="eyebrow">Connect {selected.category} account</span><h2>{selected.name}</h2><p className="muted connector-onboarding">{selected.onboarding}</p><form className="bill-form" onSubmit={connect}><label>Provider customer/account ID<input required minLength="3" value={customerId} onChange={(event) => setCustomerId(event.target.value)} placeholder="Example: ACCOUNT-123456" /></label><label>Name shown in BillFlow<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><div className="security-note"><span>✓</span><p><b>This sandbox form accepts only an account reference.</b><br />A production connector redirects to the provider’s official consent page.</p></div><button className="button primary full" disabled={busy === 'connect'}>{busy === 'connect' ? 'Connecting…' : 'Connect and import bills'}</button></form></div></div>}
    </div>
  )
}

function ConnectedState({ connection, onSync, busy }) {
  const stateEntries = Object.entries(connection.provider_state || {}).filter(([key]) => !['source_of_truth','last_payment_at'].includes(key))
  return <div className="connected-state"><div className="connected-heading"><span><i /> Connected</span><small>{connection.external_customer_id}</small></div><div className="provider-state-grid">{stateEntries.map(([key,value]) => <div key={key}><span>{key.replaceAll('_',' ')}</span><b>{value === null ? '—' : String(value).replace('T',' ').slice(0,24)}</b></div>)}</div><button className="button full" onClick={onSync} disabled={busy}>{busy ? 'Synchronizing…' : 'Synchronize provider state'}</button></div>
}

