import { useEffect, useState } from 'react'
import ForecastChart from '../components/ForecastChart'
import { api, formatDate, formatMoney } from '../lib/api'

export default function Overview({ user, onNavigate }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [summary, health, forecast, plan, anomalies] = await Promise.all([
        api('/dashboard/summary'), api('/ai/health'), api('/ai/forecast?days=30'), api('/ai/safe-pay-plan'), api('/ai/anomalies'),
      ])
      setData({ summary, health, forecast, plan, anomalies })
    } catch (error) {
      setMessage(error.message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const seed = async () => {
    const result = await api('/demo/seed', { method: 'POST' })
    setMessage(result.message)
    await load()
  }

  if (loading) return <PageSkeleton />
  if (!data) return <div className="page"><div className="empty-state"><h2>We could not load your dashboard</h2><p>{message}</p><button className="button primary" onClick={load}>Try again</button></div></div>
  const { summary, health, forecast, plan, anomalies } = data
  const hasData = summary.active_accounts > 0

  return (
    <div className="page overview-page">
      <div className="page-title"><div><span className="eyebrow">Friday financial briefing</span><h1>Good morning, {user.full_name.split(' ')[0]}.</h1><p>Here is what your money needs from you today.</p></div>{!hasData && <button className="button primary" onClick={seed}>Load secure demo data</button>}</div>
      {message && <div className="notice">{message}</div>}
      <div className="metric-grid">
        <Metric label="Available balance" value={formatMoney(summary.total_balance)} meta={`${summary.active_accounts} connected accounts`} tone="mint" />
        <Metric label="Bills due in 30 days" value={formatMoney(summary.upcoming_30_days)} meta={`${summary.unpaid_bills} upcoming obligations`} />
        <Metric label="Spent this month" value={formatMoney(summary.spent_this_month)} meta="Posted transactions" />
        <Metric label="Financial health" value={`${health.score}/100`} meta={health.label} tone={health.score >= 60 ? 'mint' : 'amber'} />
      </div>
      <div className="dashboard-grid">
        <section className="panel forecast-panel">
          <div className="panel-heading"><div><span className="eyebrow">30-day projection</span><h2>Cash-flow outlook</h2></div><div className="confidence">{Math.round(forecast.confidence * 100)}% confidence</div></div>
          <div className="forecast-summary"><div><small>Projected low</small><b>{formatMoney(forecast.lowest_projected_balance)}</b></div><div><small>Daily flexible spend</small><b>{formatMoney(forecast.average_daily_spend)}</b></div></div>
          <ForecastChart points={forecast.points} />
        </section>
        <section className="panel health-panel">
          <div className="panel-heading"><div><span className="eyebrow">Health breakdown</span><h2>{health.label}</h2></div><div className="score-ring" style={{ '--score': `${health.score * 3.6}deg` }}><span>{health.score}</span></div></div>
          <div className="health-bars">{Object.entries(health.components).map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><div><i style={{ width: `${value}%` }} /></div><b>{value}</b></div>)}</div>
          <p className="fine-print">{health.explanation}</p>
        </section>
        <section className="panel bills-panel">
          <div className="panel-heading"><div><span className="eyebrow">Next up</span><h2>Upcoming bills</h2></div><button className="text-button" onClick={() => onNavigate('bills')}>View all →</button></div>
          <div className="bill-list">{summary.upcoming_bills.length ? summary.upcoming_bills.map((bill) => <div className="bill-row" key={bill.id}><span className={`category-icon ${bill.category}`}>{categoryIcon(bill.category)}</span><div><b>{bill.name}</b><small>{bill.biller} · {formatDate(bill.due_date)}</small></div><strong>{formatMoney(bill.amount)}</strong></div>) : <EmptyMini text="Add a bill to build your timeline." />}</div>
        </section>
        <section className="panel ai-panel">
          <div className="ai-glow" /><div className="panel-heading"><div><span className="eyebrow light-text">✦ SafePay briefing</span><h2>Your next best actions</h2></div></div>
          <div className="ai-stat-row"><div><b>{plan.safe_count}</b><span>safe to schedule</span></div><div><b>{plan.attention_count}</b><span>need attention</span></div><div><b>{anomalies.count}</b><span>unusual charges</span></div></div>
          {plan.items[0] ? <div className="ai-recommendation"><span>Recommended</span><p><b>{plan.items[0].bill}</b> on {formatDate(plan.items[0].recommended_date)} from {plan.items[0].account}.</p><small>{plan.items[0].explanation}</small></div> : <EmptyMini text="Your plan appears after bills and accounts are added." />}
          <button className="button ai-button" onClick={() => onNavigate('intelligence')}>Open full intelligence plan →</button>
        </section>
      </div>
    </div>
  )
}

function Metric({ label, value, meta, tone = '' }) { return <div className={`metric-card ${tone}`}><span>{label}</span><strong>{value}</strong><small>{meta}</small></div> }
function EmptyMini({ text }) { return <div className="mini-empty">{text}</div> }
function categoryIcon(category) { return ({ utility: '⚡', subscription: '▶', emi: '₹', insurance: '◆', recharge: '↗', rent: '⌂', education: '◫' })[category] || '•' }
function PageSkeleton() { return <div className="page"><div className="skeleton title-skeleton" /><div className="metric-grid">{[1,2,3,4].map((x) => <div className="skeleton metric-card" key={x} />)}</div><div className="skeleton large-skeleton" /></div> }

