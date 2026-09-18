import { useEffect, useMemo, useState } from 'react'
import { API_URL, api, formatDate, formatMoney } from '../lib/api'

const emptyForm = { name: '', biller: '', category: 'utility', amount: '', due_date: '', recurrence: 'monthly', autopay_enabled: false }

export default function Bills() {
  const [bills, setBills] = useState([])
  const [accounts, setAccounts] = useState([])
  const [form, setForm] = useState(emptyForm)
  const [showForm, setShowForm] = useState(false)
  const [paying, setPaying] = useState(null)
  const [selectedAccount, setSelectedAccount] = useState('')
  const [prepared, setPrepared] = useState(null)
  const [message, setMessage] = useState('')
  const [receiptId, setReceiptId] = useState(null)

  const load = async () => {
    const [billItems, accountItems] = await Promise.all([api('/bills'), api('/accounts')])
    setBills(billItems); setAccounts(accountItems)
    if (accountItems[0]) setSelectedAccount(String(accountItems[0].id))
  }
  useEffect(() => { load().catch((error) => setMessage(error.message)) }, [])
  const totals = useMemo(() => bills.reduce((sum, bill) => bill.status === 'paid' ? sum : sum + Number(bill.amount), 0), [bills])

  const submitBill = async (event) => {
    event.preventDefault()
    await api('/bills', { method: 'POST', body: JSON.stringify({ ...form, amount: Number(form.amount) }) })
    setForm(emptyForm); setShowForm(false); setMessage('Bill added to your timeline.'); await load()
  }

  const prepare = async () => {
    const result = await api('/payments/prepare', { method: 'POST', body: JSON.stringify({ bill_id: paying.id, account_id: Number(selectedAccount), idempotency_key: crypto.randomUUID() }) })
    setPrepared(result)
  }
  const confirm = async () => {
    const result = await api(`/payments/${prepared.id}/confirm`, { method: 'POST' })
    const providerUpdate = result.provider_sync_status === 'confirmed'
      ? ` The provider confirmed ${result.provider_confirmation_id}; its account state is synchronized.`
      : ''
    setMessage(`${paying.name} was paid in sandbox mode.${providerUpdate}`); setReceiptId(prepared.id); setPaying(null); setPrepared(null); await load()
  }
  const closePay = () => { setPaying(null); setPrepared(null) }

  return (
    <div className="page">
      <div className="page-title"><div><span className="eyebrow">All-in-one bill hub</span><h1>Bills & payments</h1><p>Track every obligation and authorize payments from one place.</p></div><button className="button primary" onClick={() => setShowForm(true)}>+ Add bill</button></div>
      {message && <div className="notice"><span>{message} {receiptId && <a href={`${API_URL}/payments/${receiptId}/receipt`} target="_blank" rel="noreferrer"><b>Download PDF receipt →</b></a>}</span><button onClick={() => { setMessage(''); setReceiptId(null) }}>×</button></div>}
      <div className="bill-summary-strip"><div><span>Outstanding</span><b>{formatMoney(totals)}</b></div><div><span>Due items</span><b>{bills.filter((bill) => bill.status !== 'paid').length}</b></div><div><span>Paid</span><b>{bills.filter((bill) => bill.status === 'paid').length}</b></div><p><span className="safety-icon small">✓</span>Sandbox payments require two explicit steps: prepare, then authorize.</p></div>
      <section className="panel table-panel">
        <div className="table-head"><span>Bill</span><span>Category</span><span>Due date</span><span>Amount</span><span>Status</span><span /></div>
        {bills.length ? bills.map((bill) => (
          <div className="table-row" key={bill.id}>
            <div><span className={`category-icon ${bill.category}`}>{categoryIcon(bill.category)}</span><section><b>{bill.name}</b><small>{bill.biller}{bill.provider_connection_id ? ` · provider ${bill.external_status}` : ' · local bill'}</small></section></div>
            <span className="category-label">{bill.category}</span><span>{formatDate(bill.due_date)}</span><strong>{formatMoney(bill.amount)}</strong><span className={`status ${bill.status}`}>{bill.status}</span>
            <button className="button compact" disabled={bill.status === 'paid'} onClick={() => { setPaying(bill); setPrepared(null) }}>{bill.status === 'paid' ? 'Paid' : 'Pay securely'}</button>
          </div>
        )) : <div className="empty-state small"><h2>No bills yet</h2><p>Add your first utility, subscription, EMI, insurance or recharge.</p></div>}
      </section>

      {showForm && <div className="modal-backdrop" onMouseDown={() => setShowForm(false)}><div className="form-modal" onMouseDown={(e) => e.stopPropagation()}><button className="modal-close" onClick={() => setShowForm(false)}>×</button><span className="eyebrow">New obligation</span><h2>Add a bill</h2><form onSubmit={submitBill} className="bill-form"><label>Bill name<input required value={form.name} onChange={(e) => setForm({...form, name:e.target.value})} placeholder="Electricity" /></label><label>Biller<input required value={form.biller} onChange={(e) => setForm({...form, biller:e.target.value})} placeholder="Provider name" /></label><div className="field-grid"><label>Category<select value={form.category} onChange={(e) => setForm({...form, category:e.target.value})}><option value="utility">Utility</option><option value="subscription">Subscription</option><option value="emi">EMI</option><option value="insurance">Insurance</option><option value="recharge">Recharge</option><option value="rent">Rent</option><option value="education">Education</option><option value="other">Other</option></select></label><label>Amount<input type="number" min="1" step=".01" required value={form.amount} onChange={(e) => setForm({...form, amount:e.target.value})} /></label></div><div className="field-grid"><label>Due date<input type="date" required value={form.due_date} onChange={(e) => setForm({...form, due_date:e.target.value})} /></label><label>Repeats<select value={form.recurrence} onChange={(e) => setForm({...form, recurrence:e.target.value})}><option value="once">Once</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></label></div><button className="button primary full">Add to BillFlow</button></form></div></div>}

      {paying && <div className="modal-backdrop" onMouseDown={closePay}><div className="pay-modal" onMouseDown={(e) => e.stopPropagation()}><button className="modal-close" onClick={closePay}>×</button><span className="eyebrow">Provider authorization boundary</span><h2>{prepared ? 'Review and authorize' : `Pay ${paying.name}`}</h2><div className="pay-amount"><small>Amount due</small><b>{formatMoney(paying.amount)}</b><span>Due {formatDate(paying.due_date)}</span></div>{!prepared ? <><label>Funding source<select value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.masked_identifier} · {formatMoney(account.balance)}</option>)}</select></label><div className="security-note"><span>✓</span><p><b>No money moves in this step.</b><br />BillFlow creates an idempotent provider request for your review.</p></div><button className="button primary full" disabled={!selectedAccount} onClick={prepare}>Prepare payment</button></> : <><div className="authorization-card"><span>Ready for your approval</span><p>This demo confirmation represents the UPI PIN, OTP or biometric screen owned by the payment provider.</p><code>Payment #{prepared.id} · {prepared.status}</code></div><button className="button primary full" onClick={confirm}>Authorize sandbox payment</button><button className="button ghost full" onClick={closePay}>Cancel</button></>}</div></div>}
    </div>
  )
}

function categoryIcon(category) { return ({ utility: '⚡', subscription: '▶', emi: '₹', insurance: '◆', recharge: '↗', rent: '⌂', education: '◫' })[category] || '•' }
