import { useEffect, useMemo, useState } from 'react'
import { api, formatMoney } from '../lib/api'

const categoryIcons = { entertainment: '▶', productivity: '◫', wellness: '◆', education: '◇' }

export default function BrowseApps({ onNavigate }) {
  const [apps, setApps] = useState([])
  const [selected, setSelected] = useState(null)
  const [category, setCategory] = useState('all')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [warning, setWarning] = useState(null)

  const loadApps = async () => {
    const data = await api('/marketplace/apps')
    setApps(data.items)
  }

  useEffect(() => {
    loadApps().catch((requestError) => setError(requestError.message)).finally(() => setLoading(false))
  }, [])

  const categories = useMemo(() => ['all', ...new Set(apps.map((item) => item.category))], [apps])
  const visibleApps = category === 'all' ? apps : apps.filter((item) => item.category === category)

  const openApp = async (app) => {
    setBusy(`open:${app.slug}`); setError(''); setMessage('')
    try {
      const detail = await api(`/marketplace/apps/${app.slug}`)
      setSelected(detail)
      api('/marketplace/interactions', {
        method: 'POST', body: JSON.stringify({ app_slug: app.slug, action: 'viewed', context: { surface: 'browse_apps' } }),
      }).catch(() => {})
    } catch (requestError) { setError(requestError.message) } finally { setBusy('') }
  }

  const reloadSelected = async () => {
    if (!selected) return
    const [detail] = await Promise.all([api(`/marketplace/apps/${selected.slug}`), loadApps()])
    setSelected(detail)
  }

  const recordPlanAction = async (plan, action) => {
    setBusy(`${action}:${plan.id}`); setError('')
    try {
      await api('/marketplace/interactions', {
        method: 'POST',
        body: JSON.stringify({ app_slug: selected.slug, plan_id: plan.id, action, context: { surface: 'plan_details' } }),
      })
      setMessage(action === 'shortlisted' ? `${selected.name} ${plan.name} saved to your preference history.` : `${plan.name} dismissed. SafePay will remember this signal.`)
      await reloadSelected()
    } catch (requestError) { setError(requestError.message) } finally { setBusy('') }
  }

  const createIntent = async (plan, override = false) => {
    setBusy(`subscribe:${plan.id}`); setError('')
    try {
      const result = await api('/marketplace/subscribe-intent', {
        method: 'POST',
        body: JSON.stringify({ app_slug: selected.slug, plan_id: plan.id, override_warning_acknowledged: override }),
      })
      setWarning(null)
      setMessage(result.status === 'already_active'
        ? result.message
        : `${selected.name} ${plan.name} was added to Bills & pay. It is not active until you authorize payment.`)
      await reloadSelected()
    } catch (requestError) {
      if (requestError.detail?.code === 'recommendation_acknowledgement_required') {
        setWarning({ plan, ...requestError.detail })
      } else {
        setError(requestError.message)
      }
    } finally { setBusy('') }
  }

  if (loading) return <div className="page"><div className="skeleton title-skeleton" /><div className="skeleton large-skeleton" /></div>

  return (
    <div className="page marketplace-page">
      <div className="page-title"><div><span className="eyebrow">Subscription marketplace</span><h1>Browse apps</h1><p>Compare every plan, then let SafePay test it against your real financial commitments.</p></div><span className="model-badge"><i /> Personalized, explainable</span></div>
      {message && <div className="notice marketplace-notice"><span>{message}</span><div>{message.includes('Bills & pay') && <button className="notice-action" onClick={() => onNavigate('bills')}>Open Bills & pay →</button>}<button onClick={() => setMessage('')}>×</button></div></div>}
      {error && <div className="notice error"><span>{error}</span><button onClick={() => setError('')}>×</button></div>}
      <div className="integration-rule"><span className="safety-icon">✦</span><div><b>Affordability comes before preference</b><p>SafePay considers your 45-day balance forecast, reserve, upcoming deadlines, active subscriptions and past choices. Browsing history can improve plan fit, but it can never make an unaffordable plan look safe. You authorize every payment.</p></div></div>

      {!selected ? <>
        <div className="marketplace-toolbar"><div className="category-tabs">{categories.map((item) => <button key={item} className={category === item ? 'active' : ''} onClick={() => setCategory(item)}>{item}</button>)}</div><small>{visibleApps.length} sandbox applications · full plan catalogs</small></div>
        <section className="app-market-grid">
          {visibleApps.map((app) => <article className={`market-app-card accent-${app.accent}`} key={app.slug}>
            <div className="market-app-top"><span className="market-app-icon">{categoryIcons[app.category] || '◉'}</span><div><small>{app.category}</small><h2>{app.name}</h2></div>{app.state.subscription_status === 'active' && <span className="active-chip">Active</span>}</div>
            <p>{app.tagline}</p>
            <div className="app-price-line"><div><small>Plans from</small><strong>{formatMoney(app.starting_price)}</strong><span>/ month</span></div><b>{app.plan_count} plan{app.plan_count !== 1 ? 's' : ''}</b></div>
            <div className={`advisor-preview ${app.best_match.decision}`}><div><span>SafePay best match</span><b>{app.best_match.plan_name}</b></div><DecisionBadge recommendation={app.best_match} /></div>
            <button className="button primary full" disabled={busy === `open:${app.slug}`} onClick={() => openApp(app)}>{busy === `open:${app.slug}` ? 'Analyzing…' : 'See plans and AI advice'}</button>
          </article>)}
        </section>
      </> : <AppDetail app={selected} busy={busy} onBack={() => { setSelected(null); setMessage(''); setError('') }} onAction={recordPlanAction} onSubscribe={createIntent} />}

      {warning && <div className="modal-backdrop" onMouseDown={() => setWarning(null)}><div className="pay-modal advice-modal" onMouseDown={(event) => event.stopPropagation()}><button className="modal-close" onClick={() => setWarning(null)}>×</button><span className="eyebrow">SafePay review required</span><h2>{warning.recommendation.decision_label}</h2><p className="warning-copy">{warning.message}</p><RecommendationSummary recommendation={warning.recommendation} compact /><div className="authorization-card warning-authorization"><span>Your choice remains final</span><p>Continuing creates a bill only. The subscription remains inactive until you separately review and authorize payment.</p></div><button className="button primary full" disabled={busy === `subscribe:${warning.plan.id}`} onClick={() => createIntent(warning.plan, true)}>I understand — create the bill</button><button className="button ghost full" onClick={() => setWarning(null)}>Go back and wait</button></div></div>}
    </div>
  )
}

function AppDetail({ app, busy, onBack, onAction, onSubscribe }) {
  return <section className="market-detail">
    <button className="back-link" onClick={onBack}>← All applications</button>
    <div className="market-detail-hero"><div className={`market-app-icon large accent-${app.accent}`}>{categoryIcons[app.category] || '◉'}</div><div><span className="eyebrow">{app.category} · sandbox catalog</span><h2>{app.name}</h2><p>{app.description}</p></div><div className="provider-truth"><span>{app.state.connected ? 'Connected account' : 'Not connected yet'}</span><b>{app.state.subscription_status.replaceAll('_', ' ')}</b>{app.state.active_plan && <small>{app.state.active_plan}</small>}</div></div>
    <div className="catalog-disclaimer">ⓘ {app.provider_notice}</div>
    <div className="subscription-plan-grid">{app.plans.map((plan) => <PlanCard key={plan.id} app={app} plan={plan} busy={busy} onAction={onAction} onSubscribe={onSubscribe} />)}</div>
  </section>
}

function PlanCard({ app, plan, busy, onAction, onSubscribe }) {
  const recommended = app.recommended_plan_id === plan.id
  return <article className={`subscription-plan-card ${recommended ? 'recommended' : ''}`}>
    {recommended && <span className="recommended-ribbon">Best current fit</span>}
    <div className="plan-card-heading"><div><small>{app.name}</small><h3>{plan.name}</h3></div><div className="plan-price"><b>{formatMoney(plan.price)}</b><span>/ {plan.billing_cycle.replace('ly', '')}</span></div></div>
    <div className="trial-line">{plan.trial_days ? `${plan.trial_days}-day trial` : 'No free trial'} <span>·</span> {plan.auto_renews ? 'Auto-renews' : 'Manual renewal'}</div>
    <ul className="feature-checks">{plan.features.map((feature) => <li key={feature}>✓ <span>{feature}</span></li>)}</ul>
    <div className="plan-limits"><span>Included limits</span>{Object.entries(plan.limits).map(([key, value]) => <div key={key}><small>{key.replaceAll('_', ' ')}</small><b>{String(value)}</b></div>)}</div>
    <details className="plan-terms"><summary>Cancellation and refund details</summary><p><b>Cancellation:</b> {plan.cancellation}</p><p><b>Refunds:</b> {plan.refund_policy}</p></details>
    <RecommendationSummary recommendation={plan.recommendation} />
    <div className="plan-actions"><button className="button primary" disabled={busy === `subscribe:${plan.id}`} onClick={() => onSubscribe(plan)}>{plan.recommendation.pending_bill_id ? `Open bill #${plan.recommendation.pending_bill_id}` : 'Choose this plan'}</button><button className="button" disabled={busy === `shortlisted:${plan.id}`} onClick={() => onAction(plan, 'shortlisted')}>☆ Shortlist</button><button className="text-button dismiss-plan" disabled={busy === `dismissed:${plan.id}`} onClick={() => onAction(plan, 'dismissed')}>Not for me</button></div>
  </article>
}

function DecisionBadge({ recommendation }) {
  return <span className={`decision-badge ${recommendation.decision}`}>{recommendation.decision_label} · {recommendation.score}</span>
}

function RecommendationSummary({ recommendation, compact = false }) {
  return <div className={`plan-advice ${recommendation.decision} ${compact ? 'compact' : ''}`}>
    <div className="advice-heading"><div><small>SafePay recommendation</small><DecisionBadge recommendation={recommendation} /></div><span>{Math.round(recommendation.confidence * 100)}% data confidence</span></div>
    <div className="advice-metrics"><div><small>45-day low after plan</small><b>{formatMoney(recommendation.projected_lowest_balance)}</b></div><div><small>Your reserve</small><b>{formatMoney(recommendation.minimum_reserve)}</b></div><div><small>Income share</small><b>{recommendation.monthly_income_share_percent == null ? 'Unknown' : `${recommendation.monthly_income_share_percent}%`}</b></div></div>
    <ul className="advice-reasons">{recommendation.reasons.slice(0, compact ? 3 : 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
    {!!recommendation.risks.length && <div className="risk-note"><b>Watch:</b> {recommendation.risks.join(' ')}</div>}
    {!compact && !!recommendation.conflicting_deadlines.length && <details className="deadline-details"><summary>{recommendation.conflicting_deadlines.length} competing deadline{recommendation.conflicting_deadlines.length > 1 ? 's' : ''}</summary>{recommendation.conflicting_deadlines.map((bill) => <div key={bill.bill_id}><span>{bill.name} · due {bill.days_until_due <= 0 ? 'now' : `in ${bill.days_until_due} days`}</span><b>{formatMoney(bill.amount)}</b></div>)}</details>}
  </div>
}
