import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function Activity() {
  const [logs, setLogs] = useState([])
  useEffect(() => { api('/audit-logs').then(setLogs) }, [])
  return <div className="page"><div className="page-title"><div><span className="eyebrow">Transparent by design</span><h1>Activity & audit trail</h1><p>Every meaningful state change is visible and timestamped.</p></div></div><section className="panel audit-panel">{logs.length ? logs.map((log) => <div className="audit-row" key={log.id}><span className="audit-dot" /><div><b>{log.action.replaceAll('.',' · ')}</b><small>{log.entity_type}{log.entity_id ? ` #${log.entity_id}` : ''}</small></div><time>{new Date(log.created_at).toLocaleString('en-IN')}</time></div>) : <div className="mini-empty">Your audit trail will appear here.</div>}</section></div>
}

