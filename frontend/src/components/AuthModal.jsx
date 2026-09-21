import { useState } from 'react'
import { api } from '../lib/api'

export default function AuthModal({ open, onClose, onAuthenticated }) {
  const [mode, setMode] = useState('register')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ full_name: '', email: '', password: '', monthly_income: 65000, minimum_balance: 10000 })

  if (!open) return null

  const update = (event) => setForm({ ...form, [event.target.name]: event.target.value })
  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const path = mode === 'register' ? '/auth/register' : '/auth/login'
      const payload = mode === 'register'
        ? { ...form, monthly_income: Number(form.monthly_income), minimum_balance: Number(form.minimum_balance) }
        : { email: form.email, password: form.password }
      const result = await api(path, { method: 'POST', body: JSON.stringify(payload) })
      onAuthenticated(result.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="auth-modal" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        <div className="eyebrow">Your financial command center</div>
        <h2>{mode === 'register' ? 'Create your secure workspace' : 'Welcome back'}</h2>
        <p className="muted">AI guidance stays explainable. Payments always require your authorization.</p>
        <div className="auth-tabs">
          <button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>Register</button>
          <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Log in</button>
        </div>
        <form onSubmit={submit} className="auth-form">
          {mode === 'register' && (
            <label>Full name<input name="full_name" value={form.full_name} onChange={update} required minLength="2" /></label>
          )}
          <label>Email address<input name="email" type="email" value={form.email} onChange={update} required /></label>
          <label>Password<input name="password" type="password" value={form.password} onChange={update} required minLength="8" /></label>
          {mode === 'register' && (
            <div className="field-grid">
              <label>Monthly income<input name="monthly_income" type="number" min="0" value={form.monthly_income} onChange={update} /></label>
              <label>Safety reserve<input name="minimum_balance" type="number" min="0" value={form.minimum_balance} onChange={update} /></label>
            </div>
          )}
          {error && <div className="form-error">{error}</div>}
          <button className="button primary full" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? 'Create account' : 'Log in'}</button>
        </form>
        <div className="divider"><span>or</span></div>
        <a className="button google full" href="http://localhost:8000/api/v1/auth/google">Continue with Google</a>
      </div>
    </div>
  )
}

