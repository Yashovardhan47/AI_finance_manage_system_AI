import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { API_URL, api, formatMoney } from '../lib/api'

const tabs = [
  ['overview', 'Overview'],
  ['subscriptions', 'Subscriptions'],
  ['invoices', 'Invoices'],
  ['recovery', 'Recovery'],
  ['catalog', 'Catalog & customers'],
  ['compliance', 'Tax & audit'],
]
const chartColors = ['#1a6c52', '#77e6bb', '#d6f579', '#e3a13b', '#c65f4b', '#6b78c8', '#87938e']
const blankData = {
  dashboard: null, plans: [], customers: [], subscriptions: [], invoices: [], retries: [],
  taxes: [], taxSummary: { total_tax: 0, items: [] }, notifications: [], audit: [],
}

export default function BillingOperations() {
  const [tab, setTab] = useState('overview')
  const [data, setData] = useState(blankData)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [modal, setModal] = useState(null)
  const [expandedInvoice, setExpandedInvoice] = useState(null)

  const load = async () => {
    const [dashboard, plans, customers, subscriptions, invoices, retries, taxes, taxSummary, notifications, audit] = await Promise.all([
      api('/billing/dashboard'),
      api('/billing/plans?include_archived=true'),
      api('/billing/customers'),
      api('/billing/subscriptions'),
      api('/billing/invoices'),
      api('/billing/retries'),
      api('/billing/tax-rates'),
      api('/billing/tax-summary'),
      api('/billing/notifications'),
      api('/billing/audit'),
    ])
    setData({ dashboard, plans, customers, subscriptions, invoices, retries, taxes, taxSummary, notifications, audit })
  }

  useEffect(() => {
    load().catch((error) => setNotice({ kind: 'error', text: error.message })).finally(() => setLoading(false))
  }, [])

  const act = async (key, success, task) => {
    setBusy(key); setNotice(null)
    try {
      await task()
      setModal(null)
      await load()
      setNotice({ kind: 'success', text: success })
    } catch (error) {
      setNotice({ kind: 'error', text: error.message })
    } finally {
      setBusy('')
    }
  }

  const seed = () => act('seed', 'A realistic billing workspace is ready to explore.', () => api('/billing/demo/seed', { method: 'POST' }))
  const runCycles = () => act('cycles', 'Due billing cycles were evaluated idempotently.', () => api('/billing/cycles/run', { method: 'POST', body: '{}' }))
  const charge = (invoice, outcome) => act(
    `charge-${invoice.id}-${outcome}`,
    outcome === 'success' ? `${invoice.invoice_number} was paid and reconciled.` : `${invoice.invoice_number} failed; day 1, 3 and 7 recovery attempts are queued.`,
    () => api('/billing/mock-gateway/charge', {
      method: 'POST',
      body: JSON.stringify({ invoice_id: invoice.id, outcome, failure_reason: outcome === 'failure' ? 'Operator-triggered sandbox decline' : null, idempotency_key: uid(`charge-${invoice.id}`) }),
    }),
  )
  const runRetry = (retry, outcome) => act(
    `retry-${retry.id}-${outcome}`,
    outcome === 'success' ? 'Recovery succeeded; later attempts were cancelled.' : 'Due recovery attempts were processed as failures.',
    () => api('/billing/retries/run', {
      method: 'POST',
      body: JSON.stringify({ as_of: new Date(new Date(retry.scheduled_for).getTime() + 1000).toISOString(), forced_outcome: outcome }),
    }),
  )
  const pause = (subscription) => act(`pause-${subscription.id}`, `${subscription.customer_name} is paused.`, () => api(`/billing/subscriptions/${subscription.id}/pause`, { method: 'POST', body: '{}' }))
  const resume = (subscription) => act(`resume-${subscription.id}`, `${subscription.customer_name} is active again.`, () => api(`/billing/subscriptions/${subscription.id}/resume`, { method: 'POST' }))
  const archivePlan = (plan) => act(`archive-${plan.id}`, `${plan.name} was archived for new sales. Existing subscriptions are preserved.`, () => api(`/billing/plans/${plan.id}/archive`, { method: 'POST' }))

  if (loading) return <div className="page"><div className="skeleton title-skeleton" /><div className="skeleton large-skeleton" /></div>
  const empty = data.plans.length === 0

  return (
    <div className="page billing-page">
      <div className="page-title billing-title">
        <div><span className="eyebrow">Recurring revenue control plane</span><h1>Billing operations</h1><p>Operate subscriptions, invoices, payments, recovery, tax and audit from one accountable workspace.</p></div>
        <div className="billing-title-actions"><button className="button" disabled={busy === 'cycles' || empty} onClick={runCycles}>{busy === 'cycles' ? 'Running…' : 'Run billing cycle'}</button><button className="button primary" disabled={busy === 'seed' || !empty} onClick={seed}>{empty ? (busy === 'seed' ? 'Preparing…' : 'Load live demo') : 'Workspace ready'}</button></div>
      </div>
      {notice && <div className={`notice ${notice.kind === 'error' ? 'error' : ''}`} role="status"><span>{notice.text}</span><button aria-label="Dismiss" onClick={() => setNotice(null)}>×</button></div>}
      <div className="billing-assurance"><span>✓</span><div><b>Production-shaped, sandbox-safe</b><small>Every operation is tenant-scoped, idempotent and audited. Gateway actions simulate signed provider events; no real money moves.</small></div><code>Celery · PostgreSQL · HMAC · PDF</code></div>
      <nav className="billing-tabs" aria-label="Billing operations sections">
        {tabs.map(([id, label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}
      </nav>

      {empty ? <EmptyBilling onSeed={seed} busy={busy === 'seed'} /> : <>
        {tab === 'overview' && <OverviewTab data={data} onInvoice={(invoice) => { setExpandedInvoice(invoice); setTab('invoices') }} />}
        {tab === 'subscriptions' && <SubscriptionsTab data={data} busy={busy} onOpen={setModal} onPause={pause} onResume={resume} />}
        {tab === 'invoices' && <InvoicesTab invoices={data.invoices} busy={busy} expanded={expandedInvoice} onExpand={setExpandedInvoice} onCharge={charge} onOpen={setModal} />}
        {tab === 'recovery' && <RecoveryTab retries={data.retries} notifications={data.notifications} busy={busy} onRun={runRetry} />}
        {tab === 'catalog' && <CatalogTab data={data} busy={busy} onOpen={setModal} onArchive={archivePlan} />}
        {tab === 'compliance' && <ComplianceTab data={data} onOpen={setModal} />}
      </>}

      {modal && <BillingModal modal={modal} data={data} busy={busy} onClose={() => setModal(null)} act={act} />}
    </div>
  )
}

function EmptyBilling({ onSeed, busy }) {
  return <section className="billing-empty"><span>◎</span><h2>Start with a complete operating scenario</h2><p>Load three plans, four customers, active/trial/past-due/cancelled subscriptions, taxed invoices, payment history, a retry queue and audit events.</p><button className="button primary large" disabled={busy} onClick={onSeed}>{busy ? 'Building workspace…' : 'Load realistic demo data'}</button></section>
}

function OverviewTab({ data, onInvoice }) {
  const dashboard = data.dashboard
  const metrics = dashboard.metrics
  const revenueTrend = dashboard.revenue_trend.length ? dashboard.revenue_trend : [{ month: 'No paid cycles', revenue: 0 }]
  const revenueByPlan = dashboard.revenue_by_plan.length ? dashboard.revenue_by_plan : [{ plan: 'No revenue', revenue: 0 }]
  return <>
    <section className="billing-metrics">
      <Metric label="Monthly recurring revenue" value={formatMoney(metrics.mrr)} note={`${metrics.active_subscriptions} active subscriptions`} tone="mint" />
      <Metric label="Outstanding revenue" value={formatMoney(metrics.outstanding_revenue)} note={`${metrics.past_due_subscriptions} past due`} tone="amber" />
      <Metric label="Trial conversion" value={`${metrics.trial_conversion_percent}%`} note={`${metrics.trial_subscriptions} trials running`} />
      <Metric label="30-day churn" value={`${metrics.churn_rate_percent}%`} note={`${metrics.cancelled_subscriptions} cancelled total`} tone="rose" />
      <Metric label="Recovery queue" value={metrics.queued_retries} note="Day 1 · 3 · 7 policy" tone="blue" />
    </section>
    <section className="billing-chart-grid">
      <article className="panel billing-chart wide"><ChartHeading eyebrow="Collected revenue" title="Revenue trend" note="Net of refunds" /><ResponsiveContainer width="100%" height={260}><AreaChart data={revenueTrend} margin={{ top: 12, right: 10, left: 0, bottom: 0 }}><defs><linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#1a6c52" stopOpacity={0.35}/><stop offset="100%" stopColor="#1a6c52" stopOpacity={0.02}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="#e0e7e1" vertical={false}/><XAxis dataKey="month" tick={{ fontSize: 10 }} axisLine={false}/><YAxis tick={{ fontSize: 9 }} axisLine={false} tickFormatter={compactNumber}/><Tooltip formatter={(value) => formatMoney(value)} /><Area type="monotone" dataKey="revenue" stroke="#1a6c52" strokeWidth={3} fill="url(#revenueFill)" /></AreaChart></ResponsiveContainer></article>
      <article className="panel billing-chart"><ChartHeading eyebrow="Portfolio" title="Revenue by plan" /><ResponsiveContainer width="100%" height={260}><BarChart data={revenueByPlan} layout="vertical" margin={{ top: 12, right: 15, left: 12, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" stroke="#e0e7e1" horizontal={false}/><XAxis type="number" tick={{ fontSize: 9 }} tickFormatter={compactNumber}/><YAxis type="category" dataKey="plan" width={80} tick={{ fontSize: 9 }} axisLine={false}/><Tooltip formatter={(value) => formatMoney(value)} /><Bar dataKey="revenue" fill="#77e6bb" radius={[0, 6, 6, 0]} /></BarChart></ResponsiveContainer></article>
      <article className="panel billing-chart"><ChartHeading eyebrow="Invoice health" title="Status mix" /><ResponsiveContainer width="100%" height={260}><PieChart><Pie data={dashboard.invoice_status} dataKey="count" nameKey="status" innerRadius={58} outerRadius={88} paddingAngle={3}>{dashboard.invoice_status.map((item, index) => <Cell key={item.status} fill={chartColors[index % chartColors.length]} />)}</Pie><Tooltip /><Legend iconType="circle" formatter={(value) => human(value)} /></PieChart></ResponsiveContainer></article>
    </section>
    <section className="panel billing-list-panel"><div className="panel-heading"><div><span className="eyebrow">Latest activity</span><h2>Invoice board</h2></div><small>{data.invoices.length} total invoices</small></div><div className="ops-table invoice-summary-table"><div className="ops-head"><span>Invoice</span><span>Customer / plan</span><span>Due</span><span>Total</span><span>Status</span></div>{dashboard.recent_invoices.slice(0, 8).map((invoice) => <button className="ops-row" key={invoice.id} onClick={() => onInvoice(data.invoices.find((item) => item.id === invoice.id))}><span><b>{invoice.invoice_number}</b><small>{invoice.issue_date}</small></span><span><b>{invoice.customer_name}</b><small>{invoice.plan_name}</small></span><span>{shortDate(invoice.due_date)}</span><strong>{formatMoney(invoice.total, invoice.currency)}</strong><span className={`status ${invoice.status}`}>{human(invoice.status)}</span></button>)}</div></section>
  </>
}

function Metric({ label, value, note, tone = '' }) {
  return <article className={`billing-metric ${tone}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>
}

function ChartHeading({ eyebrow, title, note }) {
  return <div className="panel-heading"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div>{note && <small>{note}</small>}</div>
}

function SubscriptionsTab({ data, busy, onOpen, onPause, onResume }) {
  return <>
    <div className="ops-toolbar"><div><b>Customer subscriptions</b><small>Strict lifecycle: trial → active → past due / paused → cancelled</small></div><div><button className="button" onClick={() => onOpen({ type: 'usage' })}>+ Record usage</button><button className="button primary" onClick={() => onOpen({ type: 'subscription' })}>+ New subscription</button></div></div>
    <section className="subscription-ops-grid">{data.subscriptions.map((subscription) => <article className="subscription-ops-card" key={subscription.id}><div className="subscription-ops-top"><div><span className="avatar-square">{subscription.customer_name[0]}</span><section><h2>{subscription.customer_name}</h2><small>Subscription #{subscription.id} · v{subscription.version}</small></section></div><span className={`status ${subscription.status}`}>{human(subscription.status)}</span></div><div className="subscription-plan-line"><div><small>Current plan</small><b>{subscription.plan_name}</b></div>{subscription.pending_plan_name && <div><small>Next cycle</small><b>{subscription.pending_plan_name}</b></div>}<div><small>Quantity</small><b>{subscription.quantity}</b></div></div><div className="period-track"><span style={{ width: `${periodProgress(subscription)}%` }} /><small>{shortDateTime(subscription.current_period_start)}</small><small>{shortDateTime(subscription.current_period_end)}</small></div><div className="subscription-dates"><span><small>Next billing</small><b>{subscription.next_billing_at ? shortDateTime(subscription.next_billing_at) : 'Stopped'}</b></span><span><small>Trial ends</small><b>{subscription.trial_ends_at ? shortDateTime(subscription.trial_ends_at) : '—'}</b></span></div>{subscription.cancel_at_period_end && <div className="inline-warning">Cancellation scheduled for the period end.</div>}<div className="ops-actions"><button className="button compact" disabled={subscription.status === 'cancelled'} onClick={() => onOpen({ type: 'changePlan', subscription })}>Change plan</button>{['active', 'past_due'].includes(subscription.status) && <button className="button compact" disabled={busy === `pause-${subscription.id}`} onClick={() => onPause(subscription)}>Pause</button>}{subscription.status === 'paused' && <button className="button compact" disabled={busy === `resume-${subscription.id}`} onClick={() => onResume(subscription)}>Resume</button>}<button className="button compact danger" disabled={subscription.status === 'cancelled'} onClick={() => onOpen({ type: 'cancel', subscription })}>Cancel</button></div></article>)}</section>
  </>
}

function InvoicesTab({ invoices, busy, expanded, onExpand, onCharge, onOpen }) {
  const [filter, setFilter] = useState('all')
  const visible = filter === 'all' ? invoices : invoices.filter((invoice) => invoice.status === filter)
  return <>
    <div className="ops-toolbar"><div><b>Invoices and collections</b><small>Unique numbering, plan/proration/usage/tax lines and persisted branded PDFs</small></div><label className="inline-select">Status<select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">All</option>{['open','paid','failed','partially_refunded','refunded'].map((status) => <option key={status} value={status}>{human(status)}</option>)}</select></label></div>
    <section className="panel invoice-board"><div className="ops-table"><div className="ops-head invoice-head"><span>Invoice</span><span>Customer / plan</span><span>Period</span><span>Amount</span><span>Status</span><span>Actions</span></div>{visible.map((invoice) => <div key={invoice.id} className="invoice-wrap"><div className="ops-row invoice-row"><button className="invoice-link" onClick={() => onExpand(expanded?.id === invoice.id ? null : invoice)}><b>{invoice.invoice_number}</b><small>{expanded?.id === invoice.id ? 'Hide line items' : 'View line items'}</small></button><span><b>{invoice.customer_name}</b><small>{invoice.plan_name}</small></span><span><b>{shortDate(invoice.issue_date)} → {shortDate(invoice.due_date)}</b><small>{invoice.payment_terms}</small></span><span><strong>{formatMoney(invoice.total, invoice.currency)}</strong><small>Paid {formatMoney(invoice.amount_paid, invoice.currency)}</small></span><span className={`status ${invoice.status}`}>{human(invoice.status)}</span><div className="row-actions"><a className="icon-button" title="Download PDF" href={`${API_URL}/billing/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">PDF</a>{['open','failed'].includes(invoice.status) && <><button className="icon-button success" disabled={busy.startsWith(`charge-${invoice.id}`)} onClick={() => onCharge(invoice, 'success')}>Pay</button><button className="icon-button danger" disabled={busy.startsWith(`charge-${invoice.id}`)} onClick={() => onCharge(invoice, 'failure')}>Fail</button></>}{['paid','partially_refunded'].includes(invoice.status) && Number(invoice.amount_paid) > Number(invoice.amount_refunded) && <button className="icon-button" onClick={() => onOpen({ type: 'refund', invoice })}>Refund</button>}</div></div>{expanded?.id === invoice.id && <InvoiceLines invoice={invoice} />}</div>)}</div>{!visible.length && <div className="mini-empty">No invoices match this status.</div>}</section>
  </>
}

function InvoiceLines({ invoice }) {
  return <div className="invoice-lines"><div className="invoice-line heading"><span>Type</span><span>Description</span><span>Quantity × rate</span><strong>Amount</strong></div>{invoice.line_items.map((line) => <div className="invoice-line" key={line.id}><span className="line-type">{human(line.line_type)}</span><span>{line.description}</span><span>{line.quantity} × {formatMoney(line.unit_amount, invoice.currency)}</span><strong>{formatMoney(line.amount, invoice.currency)}</strong></div>)}<div className="invoice-total"><span>Subtotal {formatMoney(invoice.subtotal, invoice.currency)} · Usage {formatMoney(invoice.usage_total, invoice.currency)} · Proration {formatMoney(invoice.proration_total, invoice.currency)} · Tax {formatMoney(invoice.tax_total, invoice.currency)}</span><b>Total {formatMoney(invoice.total, invoice.currency)}</b></div></div>
}

function RecoveryTab({ retries, notifications, busy, onRun }) {
  const queued = retries.filter((retry) => retry.status === 'queued')
  return <section className="recovery-grid"><article className="panel retry-panel"><div className="panel-heading"><div><span className="eyebrow">Automated dunning</span><h2>Day 1 · 3 · 7 retry queue</h2></div><span className="count-badge">{queued.length} queued</span></div><div className="retry-list">{retries.map((retry) => <div className="retry-row" key={retry.id}><span className={`retry-step ${retry.status}`}>{retry.attempt_number}</span><div><b>{retry.invoice_number}</b><small>Attempt {retry.attempt_number} · {shortDateTime(retry.scheduled_for)}</small>{retry.last_error && <em>{retry.last_error}</em>}</div><span className={`status ${retry.status}`}>{human(retry.status)}</span>{retry.status === 'queued' ? <div className="row-actions"><button className="icon-button success" disabled={busy.startsWith(`retry-${retry.id}`)} onClick={() => onRun(retry, 'success')}>Recover</button><button className="icon-button danger" disabled={busy.startsWith(`retry-${retry.id}`)} onClick={() => onRun(retry, 'failure')}>Decline</button></div> : <span />}</div>)}{!retries.length && <div className="mini-empty">No payment recovery attempts yet.</div>}</div></article><article className="panel notification-panel"><div className="panel-heading"><div><span className="eyebrow">Durable outbox</span><h2>Customer notifications</h2></div></div>{notifications.slice(0, 12).map((item) => <div className="notification-row" key={item.id}><span>{notificationIcon(item.event_type)}</span><div><b>{human(item.event_type)}</b><small>{item.recipient} · {item.channel}</small></div><span className={`status ${item.status}`}>{item.status}</span></div>)}{!notifications.length && <div className="mini-empty">Events will appear after payment activity.</div>}</article></section>
}

function CatalogTab({ data, busy, onOpen, onArchive }) {
  return <><div className="ops-toolbar"><div><b>Commercial catalog</b><small>Archive replaces deletion so historical invoice references remain intact.</small></div><div><button className="button" onClick={() => onOpen({ type: 'customer' })}>+ Customer</button><button className="button primary" onClick={() => onOpen({ type: 'plan' })}>+ Billing plan</button></div></div><section className="catalog-ops-grid"><article className="panel plan-catalog"><div className="panel-heading"><div><span className="eyebrow">Plans</span><h2>Product catalog</h2></div></div>{data.plans.map((plan) => <div className={`catalog-plan ${plan.is_archived ? 'archived' : ''}`} key={plan.id}><div><span className="plan-code">{plan.code}</span><h3>{plan.name}</h3><p>{plan.description || 'No description'}</p><div className="entitlement-list">{Object.entries(plan.feature_entitlements || {}).map(([key, value]) => <span key={key}>{human(key)}: <b>{String(value)}</b></span>)}</div></div><section><strong>{formatMoney(plan.price, plan.currency)}</strong><small>per {plan.billing_interval === 'annual' ? 'year' : 'month'} · {plan.trial_days}-day trial</small><button className="button compact" disabled={plan.is_archived || busy === `archive-${plan.id}`} onClick={() => onArchive(plan)}>{plan.is_archived ? 'Archived' : 'Archive'}</button></section></div>)}</article><article className="panel customer-catalog"><div className="panel-heading"><div><span className="eyebrow">Accounts</span><h2>Billing customers</h2></div><span className="count-badge">{data.customers.length}</span></div>{data.customers.map((customer) => <div className="customer-row" key={customer.id}><span className="avatar-square">{customer.name[0]}</span><div><b>{customer.name}</b><small>{customer.external_key} · {customer.email}</small><em>{customer.region || 'No region'}, {customer.country_code}{customer.tax_id ? ` · ${customer.tax_id}` : ''}</em></div><section><small>Credit</small><strong>{formatMoney(customer.credit_balance)}</strong></section></div>)}</article></section></>
}

function ComplianceTab({ data, onOpen }) {
  const [customerFilter, setCustomerFilter] = useState('all')
  const audits = customerFilter === 'all' ? data.audit : data.audit.filter((item) => String(item.detail?.customer_id) === customerFilter)
  return <><section className="tax-metrics"><article><span>Tax collected</span><strong>{formatMoney(data.taxSummary.total_tax)}</strong><small>Across generated invoices</small></article><article><span>Active tax rules</span><strong>{data.taxes.filter((item) => item.is_active).length}</strong><small>Country and region priority</small></article><button className="button primary" onClick={() => onOpen({ type: 'tax' })}>+ Tax rate</button></section><section className="compliance-grid"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">Regional tax engine</span><h2>Tax rates & summary</h2></div></div>{data.taxes.map((tax) => <div className="tax-row" key={tax.id}><div><b>{tax.name}</b><small>{tax.country_code} · {tax.region || 'Country default'}</small></div><strong>{tax.rate_percent}%</strong><span className={`status ${tax.is_active ? 'active' : 'cancelled'}`}>{tax.is_active ? 'Active' : 'Inactive'}</span></div>)}<div className="tax-breakdown">{data.taxSummary.items.map((item, index) => <div key={`${item.country_code}-${item.region}-${index}`}><span>{item.tax}<small>{item.region}, {item.country_code}</small></span><b>{formatMoney(item.amount, item.currency)}</b></div>)}</div></article><article className="panel audit-ops"><div className="panel-heading"><div><span className="eyebrow">Immutable evidence</span><h2>Customer audit trail</h2></div><label className="inline-select">Customer<select value={customerFilter} onChange={(event) => setCustomerFilter(event.target.value)}><option value="all">All</option>{data.customers.map((customer) => <option key={customer.id} value={customer.id}>{customer.name}</option>)}</select></label></div>{audits.slice(0, 30).map((item) => <div className="audit-ops-row" key={item.id}><span className="audit-dot"/><div><b>{human(item.action.replace('billing.', ''))}</b><small>{item.entity_type} #{item.entity_id || 'workspace'}</small></div><time>{shortDateTime(item.created_at)}</time></div>)}{!audits.length && <div className="mini-empty">No events for this customer.</div>}</article></section></>
}

function BillingModal({ modal, data, busy, onClose, act }) {
  const defaults = modalDefaults(modal, data)
  const [form, setForm] = useState(defaults)
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const submit = async (event) => {
    event.preventDefault()
    const type = modal.type
    if (type === 'plan') return act('modal', 'Billing plan created.', () => api('/billing/plans', { method: 'POST', body: JSON.stringify({ code: form.code, name: form.name, description: form.description, price: Number(form.price), currency: form.currency, billing_interval: form.billing_interval, trial_days: Number(form.trial_days), feature_entitlements: parseEntitlements(form.entitlements) }) }))
    if (type === 'customer') return act('modal', 'Customer account created.', () => api('/billing/customers', { method: 'POST', body: JSON.stringify({ external_key: form.external_key, name: form.name, email: form.email, country_code: form.country_code, region: form.region || null, tax_id: form.tax_id || null, billing_address: { line1: form.address, city: form.city, country: form.country_code }, metadata: {} }) }))
    if (type === 'subscription') return act('modal', 'Subscription created. Run the billing cycle to invoice active starts.', () => api('/billing/subscriptions', { method: 'POST', body: JSON.stringify({ customer_id: Number(form.customer_id), plan_id: Number(form.plan_id), quantity: Number(form.quantity), start_trial: form.start_trial }) }))
    if (type === 'changePlan') return act('modal', `Plan change ${form.timing === 'immediate' ? 'applied with proration' : 'scheduled for period end'}.`, () => api(`/billing/subscriptions/${modal.subscription.id}/change-plan`, { method: 'POST', body: JSON.stringify({ plan_id: Number(form.plan_id), timing: form.timing }) }))
    if (type === 'cancel') return act('modal', `Cancellation ${form.timing === 'immediate' ? 'completed' : 'scheduled'}.`, () => api(`/billing/subscriptions/${modal.subscription.id}/cancel`, { method: 'POST', body: JSON.stringify({ timing: form.timing, refund_unused: form.refund_unused, reason: form.reason }) }))
    if (type === 'usage') return act('modal', 'Metered usage recorded and ready for the next invoice.', () => api('/billing/usage', { method: 'POST', body: JSON.stringify({ subscription_id: Number(form.subscription_id), metric: form.metric, quantity: Number(form.quantity), unit_price: Number(form.unit_price), idempotency_key: uid('usage') }) }))
    if (type === 'tax') return act('modal', 'Regional tax rule created.', () => api('/billing/tax-rates', { method: 'POST', body: JSON.stringify({ ...form, rate_percent: Number(form.rate_percent), region: form.region || null }) }))
    if (type === 'refund') return act('modal', `${modal.invoice.invoice_number} was refunded. Its PDF will regenerate with the refund line.`, () => api(`/billing/invoices/${modal.invoice.id}/refund`, { method: 'POST', body: JSON.stringify({ amount: form.amount ? Number(form.amount) : null, reason: form.reason }) }))
  }
  return <div className="modal-backdrop" onMouseDown={onClose}><div className="form-modal billing-modal" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" onClick={onClose}>×</button><span className="eyebrow">Billing operations</span><h2>{modalTitle(modal)}</h2><form className="bill-form" onSubmit={submit}>{modalFields(modal, form, update, data)}<button className="button primary full" disabled={busy === 'modal'}>{busy === 'modal' ? 'Saving…' : modalSubmitLabel(modal.type)}</button></form></div></div>
}

function modalFields(modal, form, update, data) {
  switch (modal.type) {
    case 'plan': return <><div className="field-grid"><Field label="Plan code"><input required pattern="[a-z0-9][a-z0-9_-]+" value={form.code} onChange={(e) => update('code', e.target.value.toLowerCase())}/></Field><Field label="Name"><input required value={form.name} onChange={(e) => update('name', e.target.value)}/></Field></div><Field label="Description"><textarea value={form.description} onChange={(e) => update('description', e.target.value)}/></Field><div className="field-grid"><Field label="Price"><input required type="number" min="0.01" step=".01" value={form.price} onChange={(e) => update('price', e.target.value)}/></Field><Field label="Currency"><input required minLength="3" maxLength="3" value={form.currency} onChange={(e) => update('currency', e.target.value.toUpperCase())}/></Field></div><div className="field-grid"><Field label="Interval"><select value={form.billing_interval} onChange={(e) => update('billing_interval', e.target.value)}><option value="monthly">Monthly</option><option value="annual">Annual</option></select></Field><Field label="Trial days"><input type="number" min="0" max="365" value={form.trial_days} onChange={(e) => update('trial_days', e.target.value)}/></Field></div><Field label="Entitlements (feature:value, comma-separated)"><input value={form.entitlements} onChange={(e) => update('entitlements', e.target.value)} placeholder="seats:10, support:priority" /></Field></>
    case 'customer': return <><div className="field-grid"><Field label="External key"><input required value={form.external_key} onChange={(e) => update('external_key', e.target.value)}/></Field><Field label="Customer name"><input required value={form.name} onChange={(e) => update('name', e.target.value)}/></Field></div><Field label="Billing email"><input required type="email" value={form.email} onChange={(e) => update('email', e.target.value)}/></Field><div className="field-grid"><Field label="Country code"><input required minLength="2" maxLength="2" value={form.country_code} onChange={(e) => update('country_code', e.target.value.toUpperCase())}/></Field><Field label="Region"><input value={form.region} onChange={(e) => update('region', e.target.value)}/></Field></div><Field label="Tax ID"><input value={form.tax_id} onChange={(e) => update('tax_id', e.target.value)}/></Field><div className="field-grid"><Field label="Address"><input value={form.address} onChange={(e) => update('address', e.target.value)}/></Field><Field label="City"><input value={form.city} onChange={(e) => update('city', e.target.value)}/></Field></div></>
    case 'subscription': return <><Field label="Customer"><select required value={form.customer_id} onChange={(e) => update('customer_id', e.target.value)}>{data.customers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field><Field label="Plan"><select required value={form.plan_id} onChange={(e) => update('plan_id', e.target.value)}>{data.plans.filter((item) => !item.is_archived).map((item) => <option key={item.id} value={item.id}>{item.name} · {formatMoney(item.price, item.currency)}</option>)}</select></Field><div className="field-grid"><Field label="Quantity"><input type="number" min="1" value={form.quantity} onChange={(e) => update('quantity', e.target.value)}/></Field><label className="check-field"><input type="checkbox" checked={form.start_trial} onChange={(e) => update('start_trial', e.target.checked)}/><span>Start available trial</span></label></div></>
    case 'changePlan': return <><p className="modal-context">{modal.subscription.customer_name} currently uses <b>{modal.subscription.plan_name}</b>.</p><Field label="New plan"><select required value={form.plan_id} onChange={(e) => update('plan_id', e.target.value)}>{data.plans.filter((item) => !item.is_archived && item.id !== modal.subscription.plan_id).map((item) => <option key={item.id} value={item.id}>{item.name} · {formatMoney(item.price, item.currency)}</option>)}</select></Field><Field label="Effective timing"><select value={form.timing} onChange={(e) => update('timing', e.target.value)}><option value="immediate">Immediately, with proration</option><option value="end_of_cycle">At the next cycle</option></select></Field>{form.timing === 'immediate' && <div className="inline-warning">A credit for unused service and a debit for the new plan will be itemized on a proration invoice.</div>}</>
    case 'cancel': return <><p className="modal-context">Cancel {modal.subscription.customer_name} · {modal.subscription.plan_name}</p><Field label="Timing"><select value={form.timing} onChange={(e) => update('timing', e.target.value)}><option value="end_of_cycle">At period end</option><option value="immediate">Immediately</option></select></Field><Field label="Reason"><textarea required minLength="3" value={form.reason} onChange={(e) => update('reason', e.target.value)}/></Field>{form.timing === 'immediate' && <label className="check-field"><input type="checkbox" checked={form.refund_unused} onChange={(e) => update('refund_unused', e.target.checked)}/><span>Refund the unused paid period when eligible</span></label>}</>
    case 'usage': return <><Field label="Subscription"><select required value={form.subscription_id} onChange={(e) => update('subscription_id', e.target.value)}>{data.subscriptions.filter((item) => item.status !== 'cancelled').map((item) => <option key={item.id} value={item.id}>{item.customer_name} · {item.plan_name}</option>)}</select></Field><div className="field-grid"><Field label="Metric"><input required value={form.metric} onChange={(e) => update('metric', e.target.value)} placeholder="api_calls"/></Field><Field label="Quantity"><input required type="number" min="0.0001" step=".0001" value={form.quantity} onChange={(e) => update('quantity', e.target.value)}/></Field></div><Field label="Unit price"><input required type="number" min="0" step=".0001" value={form.unit_price} onChange={(e) => update('unit_price', e.target.value)}/></Field></>
    case 'tax': return <><Field label="Tax name"><input required value={form.name} onChange={(e) => update('name', e.target.value)} placeholder="India GST"/></Field><div className="field-grid"><Field label="Country code"><input required minLength="2" maxLength="2" value={form.country_code} onChange={(e) => update('country_code', e.target.value.toUpperCase())}/></Field><Field label="Region (optional)"><input value={form.region} onChange={(e) => update('region', e.target.value)}/></Field></div><div className="field-grid"><Field label="Rate percent"><input required type="number" min="0" max="100" step=".0001" value={form.rate_percent} onChange={(e) => update('rate_percent', e.target.value)}/></Field><Field label="Effective from"><input required type="date" value={form.effective_from} onChange={(e) => update('effective_from', e.target.value)}/></Field></div></>
    case 'refund': return <><p className="modal-context">Refundable balance: <b>{formatMoney(Number(modal.invoice.amount_paid) - Number(modal.invoice.amount_refunded), modal.invoice.currency)}</b></p><Field label="Amount (leave blank for full balance)"><input type="number" min="0.01" step=".01" value={form.amount} onChange={(e) => update('amount', e.target.value)}/></Field><Field label="Reason"><textarea required minLength="3" value={form.reason} onChange={(e) => update('reason', e.target.value)}/></Field></>
    default: return null
  }
}

function Field({ label, children }) { return <label>{label}{children}</label> }

function modalDefaults(modal, data) {
  const firstPlan = data.plans.find((item) => !item.is_archived)
  if (modal.type === 'plan') return { code: '', name: '', description: '', price: '', currency: 'INR', billing_interval: 'monthly', trial_days: 14, entitlements: '' }
  if (modal.type === 'customer') return { external_key: '', name: '', email: '', country_code: 'IN', region: '', tax_id: '', address: '', city: '' }
  if (modal.type === 'subscription') return { customer_id: data.customers[0]?.id || '', plan_id: firstPlan?.id || '', quantity: 1, start_trial: true }
  if (modal.type === 'changePlan') return { plan_id: data.plans.find((item) => !item.is_archived && item.id !== modal.subscription.plan_id)?.id || '', timing: 'immediate' }
  if (modal.type === 'cancel') return { timing: 'end_of_cycle', refund_unused: false, reason: 'Customer requested cancellation' }
  if (modal.type === 'usage') return { subscription_id: data.subscriptions.find((item) => item.status !== 'cancelled')?.id || '', metric: 'api_calls', quantity: 1, unit_price: 0 }
  if (modal.type === 'tax') return { name: '', country_code: 'IN', region: '', rate_percent: '', effective_from: new Date().toISOString().slice(0, 10) }
  if (modal.type === 'refund') return { amount: '', reason: 'Customer-requested refund' }
  return {}
}

function modalTitle(modal) { return ({ plan: 'Create billing plan', customer: 'Create customer', subscription: 'Start subscription', changePlan: 'Change plan', cancel: 'Cancel subscription', usage: 'Record metered usage', tax: 'Create tax rule', refund: `Refund ${modal.invoice?.invoice_number || 'invoice'}` })[modal.type] }
function modalSubmitLabel(type) { return ({ plan: 'Create plan', customer: 'Create customer', subscription: 'Start subscription', changePlan: 'Apply plan change', cancel: 'Confirm cancellation', usage: 'Record usage', tax: 'Create tax rate', refund: 'Issue refund' })[type] }
function parseEntitlements(value) { return Object.fromEntries(value.split(',').map((item) => item.trim()).filter(Boolean).map((item) => { const [key, ...rest] = item.split(':'); return [key.trim(), rest.join(':').trim() || true] })) }
function human(value = '') { return String(value).replaceAll('_', ' ').replaceAll('.', ' · ').replace(/\b\w/g, (letter) => letter.toUpperCase()) }
function shortDate(value) { if (!value) return '—'; return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value.length === 10 ? `${value}T00:00:00` : value)) }
function shortDateTime(value) { if (!value) return '—'; return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) }
function compactNumber(value) { return new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(value) }
function uid(prefix) { return `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`}` }
function periodProgress(subscription) { const start = new Date(subscription.current_period_start).getTime(); const end = new Date(subscription.current_period_end).getTime(); return Math.min(100, Math.max(0, ((Date.now() - start) / Math.max(1, end - start)) * 100)) }
function notificationIcon(type) { return type.includes('failed') ? '!' : type.includes('refund') ? '↩' : type.includes('cancel') ? '×' : '✓' }
