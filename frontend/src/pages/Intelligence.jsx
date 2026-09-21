import { useEffect, useState } from 'react'
import ForecastChart from '../components/ForecastChart'
import { api, formatDate, formatMoney } from '../lib/api'

export default function Intelligence() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { Promise.all([api('/ai/safe-pay-plan'), api('/ai/forecast?days=45'), api('/ai/anomalies'), api('/ai/health')]).then(([plan, forecast, anomalies, health]) => setData({ plan, forecast, anomalies, health })).catch((err) => setError(err.message)) }, [])
  if (error) return <div className="page"><div className="notice error">{error}</div></div>
  if (!data) return <div className="page"><div className="skeleton large-skeleton" /></div>
  const { plan, forecast, anomalies, health } = data
  return (
    <div className="page intelligence-page">
      <div className="page-title"><div><span className="eyebrow">SafePay Intelligence Engine</span><h1>Your explainable payment plan</h1><p>A constrained forecast—not a black-box order. You approve every action.</p></div><span className="model-badge"><i /> Hybrid AI · active</span></div>
      <div className="intelligence-hero"><div><span>Financial health</span><strong>{health.score}<small>/100</small></strong><b>{health.label}</b></div><section><span>Policy being protected</span><h2>Keep at least {formatMoney(plan.policy.minimum_balance)} available</h2><p>{plan.policy.objective}. Recommendations are recalculated when your balance, bills or spending changes.</p></section><aside><span>Safe</span><b>{plan.safe_count}</b><span>Review</span><b>{plan.attention_count}</b></aside></div>
      <div className="intelligence-grid">
        <section className="panel plan-panel"><div className="panel-heading"><div><span className="eyebrow">Ranked by urgency</span><h2>Payment decisions</h2></div><small>Updated just now</small></div><div className="plan-list">{plan.items.length ? plan.items.map((item, index) => <article key={item.bill_id}><span className="plan-index">{String(index + 1).padStart(2,'0')}</span><div className="plan-main"><div><h3>{item.bill}</h3><span className={`status ${item.status}`}>{item.status.replaceAll('_',' ')}</span></div><p>{item.explanation}</p><small>Pay {formatMoney(item.amount)} on <b>{formatDate(item.recommended_date)}</b> from <b>{item.account}</b></small></div><div className="confidence-stack"><b>{Math.round(item.confidence * 100)}%</b><span>confidence</span></div></article>) : <div className="mini-empty">Add bills and accounts to generate your first plan.</div>}</div></section>
        <section className="panel forecast-panel compact-forecast"><div className="panel-heading"><div><span className="eyebrow">45-day simulation</span><h2>Liquidity path</h2></div></div><ForecastChart points={forecast.points} /><div className="forecast-summary"><div><small>Projected low</small><b>{formatMoney(forecast.lowest_projected_balance)}</b></div><div><small>Model confidence</small><b>{Math.round(forecast.confidence * 100)}%</b></div></div><p className="fine-print">Method: {forecast.method}.</p></section>
        <section className="panel anomalies-panel"><div className="panel-heading"><div><span className="eyebrow">Needs your eyes</span><h2>Unusual activity</h2></div><span className="alert-count">{anomalies.count}</span></div>{anomalies.items.length ? anomalies.items.map((item) => <article key={item.transaction_id}><span className="anomaly-mark">!</span><div><b>{item.merchant}</b><p>{item.explanation}</p><small>{item.category} · {Math.round(item.confidence*100)}% statistical confidence</small></div><strong>{formatMoney(item.amount)}</strong></article>) : <div className="mini-empty">No statistical outliers found with current data.</div>}<p className="fine-print">{anomalies.disclaimer}</p></section>
        <section className="panel method-panel"><span className="eyebrow">Why this is different</span><h2>Four engines, one accountable answer.</h2><div><span>01</span><p><b>Forecasting</b> simulates future daily liquidity.</p><span>02</span><p><b>Constraint planning</b> respects due dates and your reserve.</p><span>03</span><p><b>Robust detection</b> identifies category-level spending outliers.</p><span>04</span><p><b>Explanation</b> exposes evidence, policy and confidence.</p></div></section>
      </div>
    </div>
  )
}

