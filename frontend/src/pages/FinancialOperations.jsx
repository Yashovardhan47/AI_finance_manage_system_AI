import { useCallback, useEffect, useMemo, useState } from 'react'
import ForecastChart from '../components/ForecastChart'
import { api, formatDate, formatMoney } from '../lib/api'

const futureDate = (days) => new Date(Date.now() + days * 86400000).toISOString().slice(0, 10)
const human = (value = '') => String(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

const emptyObligation = {
  name: '', counterparty: '', category: 'subscription', amount: '', due_date: futureDate(14),
  recurrence: 'monthly', priority: 3, essential: false,
}

const emptyScenario = {
  name: 'New subscription decision', amount: '', due_date: futureDate(10), category: 'subscription',
  essential: false, recurring_monthly: true,
}

export default function FinancialOperations() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [policy, setPolicy] = useState(null)
  const [scenarioForm, setScenarioForm] = useState(emptyScenario)
  const [scenario, setScenario] = useState(null)
  const [obligationForm, setObligationForm] = useState(emptyObligation)

  const load = useCallback(async (refreshIfEmpty = true) => {
    setError('')
    let center = await api('/operations/command-center')
    if (refreshIfEmpty && center.summary.active_obligations > 0 && center.summary.pending_decisions === 0) {
      await api('/operations/recommendations/refresh', { method: 'POST' })
      center = await api('/operations/command-center')
    }
    setData(center)
    setPolicy({
      autonomy_mode: center.policy.autonomy_mode,
      minimum_reserve: center.policy.minimum_reserve,
      max_preparable_amount: center.policy.max_preparable_amount,
      require_provider_confirmation: center.policy.require_provider_confirmation,
      protect_essential_first: center.policy.protect_essential_first,
    })
  }, [])

  useEffect(() => { load().catch((err) => setError(err.message)) }, [load])

  const obligationMap = useMemo(
    () => Object.fromEntries((data?.obligations || []).map((item) => [item.id, item])),
    [data],
  )

  const perform = async (key, operation, message) => {
    setBusy(key); setError(''); setNotice('')
    try {
      await operation()
      if (message) setNotice(message)
      await load(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const loadDemo = () => perform('demo', async () => {
    await api('/demo/seed', { method: 'POST' })
    await api('/operations/bootstrap', { method: 'POST' })
  }, 'A realistic obligation graph and decision inbox are ready.')

  const refreshDecisions = () => perform('refresh', () => api('/operations/recommendations/refresh', { method: 'POST' }), 'Forecast and decisions recalculated.')

  const decide = (recommendation, decision) => perform(`decision-${recommendation.id}`, () => api(`/operations/recommendations/${recommendation.id}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      decision,
      idempotency_key: `${decision}-${recommendation.id}-${globalThis.crypto?.randomUUID?.() || Date.now()}`,
      note: decision === 'approve' ? 'Reviewed in the Financial Autopilot command center' : 'User declined this recommendation',
    }),
  }), decision === 'approve' ? 'Decision approved. The action is prepared within your policy boundary.' : 'Recommendation declined.')

  const savePolicy = () => perform('policy', () => api('/operations/policy', {
    method: 'PUT',
    body: JSON.stringify({
      ...policy,
      minimum_reserve: Number(policy.minimum_reserve),
      max_preparable_amount: Number(policy.max_preparable_amount),
    }),
  }), 'Autopilot policy saved. No payment authority was changed.')

  const runScenario = async (event) => {
    event.preventDefault(); setBusy('scenario'); setError('')
    try {
      const result = await api('/operations/scenarios', {
        method: 'POST',
        body: JSON.stringify({ ...scenarioForm, amount: Number(scenarioForm.amount) }),
      })
      setScenario(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const addObligation = async (event) => {
    event.preventDefault()
    await perform('obligation', async () => {
      await api('/operations/obligations', {
        method: 'POST',
        body: JSON.stringify({ ...obligationForm, amount: Number(obligationForm.amount), priority: Number(obligationForm.priority) }),
      })
      await api('/operations/recommendations/refresh', { method: 'POST' })
      setObligationForm(emptyObligation)
    }, 'Obligation added and included in the 90-day forecast.')
  }

  const flagMismatch = (obligation) => perform(`mismatch-${obligation.id}`, () => api('/operations/outcomes', {
    method: 'POST',
    body: JSON.stringify({
      obligation_id: obligation.id,
      event_type: 'provider_status_checked',
      source: 'user',
      status: 'mismatch',
      expected_status: obligation.contract_terms?.service_action === 'activate_subscription' ? 'active' : 'cleared',
      actual_status: 'not_updated',
      evidence: { reported_from: 'financial_command_center' },
    }),
  }), 'Mismatch recorded. An exception case was opened without assuming success.')

  const resolveCase = (item) => perform(`resolve-${item.id}`, () => api(`/operations/exceptions/${item.id}/resolve`, {
    method: 'POST', body: JSON.stringify({ resolution: 'User reviewed the provider evidence and marked this case resolved.' }),
  }), 'Exception resolved with an audit record.')

  if (error && !data) return <div className="page"><div className="notice error">{error}</div></div>
  if (!data || !policy) return <div className="page"><div className="skeleton large-skeleton" /></div>

  const { summary, forecast, recommendations, obligations, categories, exceptions, actions } = data

  return (
    <div className="page operations-page">
      <div className="page-title operations-title">
        <div>
          <span className="eyebrow">BillFlow Financial Operations OS</span>
          <h1>Financial Autopilot</h1>
          <p>One accountable loop for obligations, decisions, approvals, provider outcomes and recovery.</p>
        </div>
        <div className="operations-title-actions">
          <button className="button subtle" disabled={!!busy} onClick={refreshDecisions}>{busy === 'refresh' ? 'Recalculating…' : '↻ Recalculate'}</button>
          <button className="button primary" disabled={!!busy} onClick={loadDemo}>{busy === 'demo' ? 'Preparing…' : 'Load secure demo'}</button>
        </div>
      </div>

      {error && <div className="notice error">{error}</div>}
      {notice && <div className="notice success">{notice}</div>}

      <div className="operations-boundary">
        <span>✓</span>
        <div><b>Decision-to-outcome control, not invisible money movement</b><small>{data.execution_boundary}</small></div>
        <code>{human(policy.autonomy_mode)} mode</code>
      </div>

      <section className="operations-metrics">
        <article className={summary.reserve_at_risk ? 'danger' : 'safe'}><span>90-day projected low</span><strong>{formatMoney(summary.projected_lowest_balance)}</strong><small>{summary.reserve_at_risk ? 'Below protected reserve' : 'Reserve remains protected'}</small></article>
        <article><span>Active obligations</span><strong>{summary.active_obligations}</strong><small>{summary.due_within_7_days} due within seven days</small></article>
        <article><span>Decision inbox</span><strong>{summary.pending_decisions}</strong><small>Each requires your review</small></article>
        <article className={summary.open_exceptions ? 'danger' : ''}><span>Open exceptions</span><strong>{summary.open_exceptions}</strong><small>Payment-to-provider mismatches</small></article>
      </section>

      <div className="operations-top-grid">
        <section className="panel twin-panel">
          <div className="panel-heading"><div><span className="eyebrow">Financial digital twin</span><h2>90-day liquidity path</h2></div><span className="model-badge"><i /> {Math.round(forecast.confidence * 100)}% confidence</span></div>
          <ForecastChart points={scenario?.result?.points || forecast.points} />
          <div className="twin-stats">
            <div><small>Starting balance</small><b>{formatMoney(forecast.starting_balance)}</b></div>
            <div><small>Projected low</small><b>{formatMoney(scenario?.result?.projected_lowest_balance ?? forecast.lowest_projected_balance)}</b></div>
            <div><small>Average daily spend</small><b>{formatMoney(forecast.average_daily_spend)}</b></div>
          </div>
          <p className="fine-print">{scenario ? scenario.result.explanation : forecast.method} Calculations are deterministic and inspectable.</p>
        </section>

        <section className="panel policy-panel">
          <div className="panel-heading"><div><span className="eyebrow">Guardrail engine</span><h2>Autopilot policy</h2></div><span className="policy-lock">User controlled</span></div>
          <label>Autonomy level<select value={policy.autonomy_mode} onChange={(event) => setPolicy({ ...policy, autonomy_mode: event.target.value })}><option value="advise">Advise only</option><option value="prepare">Prepare for approval</option><option value="execute_authorized">Authorized-partner handoff</option></select></label>
          <div className="policy-fields">
            <label>Protected reserve<input type="number" min="0" value={policy.minimum_reserve} onChange={(event) => setPolicy({ ...policy, minimum_reserve: event.target.value })} /></label>
            <label>Preparation limit<input type="number" min="0" value={policy.max_preparable_amount} onChange={(event) => setPolicy({ ...policy, max_preparable_amount: event.target.value })} /></label>
          </div>
          <label className="operations-check"><input type="checkbox" checked={policy.protect_essential_first} onChange={(event) => setPolicy({ ...policy, protect_essential_first: event.target.checked })} /><span>Protect essential obligations first</span></label>
          <label className="operations-check"><input type="checkbox" checked={policy.require_provider_confirmation} onChange={(event) => setPolicy({ ...policy, require_provider_confirmation: event.target.checked })} /><span>Require provider outcome confirmation</span></label>
          <button className="button primary full-button" disabled={!!busy} onClick={savePolicy}>{busy === 'policy' ? 'Saving…' : 'Save policy'}</button>
          <small className="policy-note">Even authorized mode creates a partner handoff; it does not bypass consent, mandates or provider authorization.</small>
        </section>
      </div>

      <section className="panel decision-inbox">
        <div className="panel-heading"><div><span className="eyebrow">Explainable AI decisions</span><h2>Today’s decision inbox</h2></div><span className="count-badge">{recommendations.length}</span></div>
        {recommendations.length ? recommendations.map((item) => {
          const obligation = obligationMap[item.obligation_id]
          return <article className={`decision-card risk-${item.risk_level}`} key={item.id}>
            <div className="decision-icon">{item.action === 'hold' ? 'Ⅱ' : item.action === 'pay_now' ? '!' : '→'}</div>
            <div className="decision-copy">
              <div><span className={`status ${item.risk_level}`}>{item.risk_level} risk</span><small>{Math.round(Number(item.confidence) * 100)}% confidence · {item.model_version}</small></div>
              <h3>{human(item.action)} · {obligation?.name || 'Financial obligation'}</h3>
              <p>{item.rationale.summary}</p>
              <div className="evidence-row">{item.rationale.evidence?.map((value) => <span key={value}>{value}</span>)}</div>
            </div>
            <div className="decision-amount"><strong>{formatMoney(item.proposed_amount)}</strong><small>{item.proposed_date ? formatDate(item.proposed_date) : 'No payment date'}</small><div><button className="icon-button" disabled={!!busy} onClick={() => decide(item, 'reject')}>Decline</button><button className="icon-button success" disabled={!!busy} onClick={() => decide(item, 'approve')}>Approve</button></div></div>
          </article>
        }) : <div className="operations-empty"><span>✓</span><h3>No pending decisions</h3><p>Add an obligation or recalculate when your finances change.</p></div>}
      </section>

      <div className="operations-middle-grid">
        <section className="panel obligation-graph">
          <div className="panel-heading"><div><span className="eyebrow">Universal obligation graph</span><h2>Where your future money is committed</h2></div></div>
          <div className="category-nodes">{categories.length ? categories.map((item, index) => <article key={item.category} style={{ '--node-index': index }}><span>{human(item.category).slice(0, 1)}</span><div><b>{human(item.category)}</b><small>{item.count} obligation{item.count === 1 ? '' : 's'}</small></div><strong>{formatMoney(item.total)}</strong></article>) : <div className="mini-empty">Load demo data or add your first obligation.</div>}</div>
        </section>

        <section className="panel scenario-panel">
          <div className="panel-heading"><div><span className="eyebrow">Before you commit</span><h2>What-if simulator</h2></div></div>
          <form onSubmit={runScenario}>
            <label>Decision name<input value={scenarioForm.name} onChange={(event) => setScenarioForm({ ...scenarioForm, name: event.target.value })} required /></label>
            <div><label>Amount<input type="number" min="1" value={scenarioForm.amount} onChange={(event) => setScenarioForm({ ...scenarioForm, amount: event.target.value })} required /></label><label>First due date<input type="date" value={scenarioForm.due_date} onChange={(event) => setScenarioForm({ ...scenarioForm, due_date: event.target.value })} required /></label></div>
            <label className="operations-check"><input type="checkbox" checked={scenarioForm.recurring_monthly} onChange={(event) => setScenarioForm({ ...scenarioForm, recurring_monthly: event.target.checked })} /><span>Repeat monthly in the simulation</span></label>
            <button className="button primary full-button" disabled={busy === 'scenario'}>{busy === 'scenario' ? 'Simulating…' : 'Simulate 90-day impact'}</button>
          </form>
          {scenario && <div className={`scenario-result ${scenario.result.reserve_breach ? 'danger' : 'safe'}`}><span>{scenario.result.reserve_breach ? '!' : '✓'}</span><div><b>{human(scenario.result.decision)}</b><p>{scenario.result.explanation}</p><small>Cash impact {formatMoney(scenario.result.cash_impact)} · projected low {formatMoney(scenario.result.projected_lowest_balance)}</small></div></div>}
        </section>
      </div>

      <div className="operations-bottom-grid">
        <section className="panel obligation-register">
          <div className="panel-heading"><div><span className="eyebrow">Detected, linked and manual</span><h2>Obligation register</h2></div><span className="count-badge">{obligations.length}</span></div>
          <div className="obligation-list">{obligations.slice(0, 8).map((item) => <article key={item.id}><span className={`obligation-priority p${item.priority}`}>{item.priority}</span><div><b>{item.name}</b><small>{item.counterparty} · {human(item.category)} · {item.source}</small></div><section><strong>{formatMoney(item.amount)}</strong><small>{formatDate(item.due_date)}</small></section><span className={`status ${item.status}`}>{human(item.status)}</span>{item.provider_connection_id && <button className="icon-button" disabled={!!busy} onClick={() => flagMismatch(item)}>Flag mismatch</button>}</article>)}</div>
          <details className="add-obligation"><summary>+ Add obligation</summary><form onSubmit={addObligation}><input placeholder="Obligation name" value={obligationForm.name} onChange={(event) => setObligationForm({ ...obligationForm, name: event.target.value })} required /><input placeholder="Provider or counterparty" value={obligationForm.counterparty} onChange={(event) => setObligationForm({ ...obligationForm, counterparty: event.target.value })} required /><div><input type="number" min="1" placeholder="Amount" value={obligationForm.amount} onChange={(event) => setObligationForm({ ...obligationForm, amount: event.target.value })} required /><input type="date" value={obligationForm.due_date} onChange={(event) => setObligationForm({ ...obligationForm, due_date: event.target.value })} required /><select value={obligationForm.category} onChange={(event) => setObligationForm({ ...obligationForm, category: event.target.value })}><option value="subscription">Subscription</option><option value="utility">Utility</option><option value="health">Health</option><option value="insurance">Insurance</option><option value="rent">Rent</option><option value="education">Education</option><option value="emi">EMI</option><option value="tax">Tax</option><option value="other">Other</option></select></div><label className="operations-check"><input type="checkbox" checked={obligationForm.essential} onChange={(event) => setObligationForm({ ...obligationForm, essential: event.target.checked, priority: event.target.checked ? 5 : 3 })} /><span>Essential commitment</span></label><button className="button primary" disabled={busy === 'obligation'}>Add and analyze</button></form></details>
        </section>

        <section className="panel exception-center">
          <div className="panel-heading"><div><span className="eyebrow">Closed-loop verification</span><h2>Outcome exceptions</h2></div><span className={`count-badge ${exceptions.length ? 'danger' : ''}`}>{exceptions.length}</span></div>
          {exceptions.length ? exceptions.map((item) => <article key={item.id}><span>!</span><div><b>{human(item.case_type)}</b><p>{item.summary}</p><small>{human(item.severity)} severity · evidence preserved</small></div><button className="icon-button success" disabled={!!busy} onClick={() => resolveCase(item)}>Resolve</button></article>) : <div className="operations-empty compact"><span>✓</span><h3>Outcomes reconciled</h3><p>No unresolved provider mismatches.</p></div>}
          {!!actions.length && <div className="action-trail"><h3>Recent approved actions</h3>{actions.slice(0, 4).map((item) => <div key={item.id}><span>{human(item.action_type)}</span><b>{human(item.status)}</b></div>)}</div>}
        </section>
      </div>
    </div>
  )
}
