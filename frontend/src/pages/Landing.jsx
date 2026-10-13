import { useEffect, useState } from 'react'
import Brand from '../components/Brand'
import AuthModal from '../components/AuthModal'

const capabilities = [
  { icon: '▦', label: 'Organize', title: 'Unified bill hub', text: 'Normalize utilities, rent, EMIs, insurance, recharges and subscriptions into one obligation timeline.', note: 'Due dates · recurrence · payment state' },
  { icon: '◎', label: 'Discover', title: 'Browse apps & plans', text: 'Compare provider plans, trial periods, renewal terms and account impact before starting a subscription.', note: 'Plan catalog · fit analysis · entitlement state' },
  { icon: '✦', label: 'Decide', title: 'SafePay AI', text: 'Forecast liquidity, protect a minimum reserve and explain whether to pay, delay, switch funding source or skip.', note: 'Cash-flow forecast · evidence · confidence' },
  { icon: '◇', label: 'Coordinate', title: 'Financial Autopilot', text: 'Turn approved policies into a prioritized plan while keeping OTP, PIN and final authorization with the user.', note: 'Policy guardrails · approval inbox · scenarios' },
  { icon: '!', label: 'Protect', title: 'Payment incident engine', text: 'Track pending, failed and stopped payments with retries, escalation, delivery receipts and live dashboard events.', note: 'Celery · outbox · SSE · queue health' },
  { icon: '⇄', label: 'Verify', title: 'Provider reconciliation', text: 'Poll gateways, consume signed webhooks and reconcile the bill, payment and provider-account outcome.', note: 'Status polling · audit trail · service sync' },
]

const categories = ['Home & utilities', 'Health & insurance', 'Entertainment', 'Education', 'Rent & EMI', 'Telecom & recharges', 'Productivity', 'Cards & accounts']

const features = [
  { number: '01', title: 'One bill universe', text: 'See every obligation in a single calm timeline instead of searching across unrelated provider apps.' },
  { number: '02', title: 'SafePay intelligence', text: 'Choose a safer date and funding source before a payment creates a cash-flow problem.' },
  { number: '03', title: 'Explainable alerts', text: 'Review anomalies and payment risks with evidence, confidence and a reason you can understand.' },
  { number: '04', title: 'Human permission', text: 'Automation follows your reserve policy. PIN, OTP and final provider authorization remain with you.' },
]

export default function Landing({ onAuthenticated, authError = '', onAuthErrorDismissed }) {
  const [authOpen, setAuthOpen] = useState(Boolean(authError))

  useEffect(() => {
    if (authError) setAuthOpen(true)
  }, [authError])

  return (
    <div className="landing public-interface">
      <nav className="landing-nav" aria-label="Public navigation">
        <Brand />
        <div className="nav-links"><a href="#platform">Platform</a><a href="#intelligence">Intelligence</a><a href="#workflow">How it works</a><a href="#trust">Trust</a></div>
        <button className="button nav-button" onClick={() => setAuthOpen(true)}>Sign in / create account</button>
      </nav>

      <section className="hero public-hero">
        <div className="hero-copy">
          <div className="interface-label"><span>Public main interface</span><small>No personal finance data shown</small></div>
          <div className="hero-pill"><span /> Intelligent finance, with human permission</div>
          <h1>Every bill.<br /><em>One clear decision.</em></h1>
          <p>BillFlow AI is an all-in-one financial operations platform that discovers obligations, forecasts affordability, coordinates authorized payment and verifies the outcome.</p>
          <div className="hero-actions">
            <button className="button primary large" onClick={() => setAuthOpen(true)}>Open your financial Home <span>→</span></button>
            <a className="text-link" href="#platform">Explore the complete platform ↓</a>
          </div>
          <div className="trust-row"><span>✓ Public product tour first</span><span>✓ Personal Home after sign-in</span><span>✓ No silent payments</span></div>
        </div>
        <div className="hero-visual" aria-label="BillFlow AI platform preview">
          <div className="orb orb-one" /><div className="orb orb-two" />
          <div className="preview-window">
            <div className="preview-top"><div className="mini-brand">B</div><div className="preview-context"><span>PLATFORM MAP</span><b>One operating layer</b></div><div className="preview-dots"><i /><i /><i /></div></div>
            <div className="preview-heading"><span>Illustrative product view</span><b>Financial health <strong>82</strong></b></div>
            <div className="preview-balance"><small>Obligations understood</small><strong>8 categories</strong><span>From discovery to reconciled outcome</span></div>
            <div className="preview-grid">
              <div className="preview-chart"><small>30-day liquidity outlook</small><svg viewBox="0 0 240 72"><path d="M0 54 C28 48 36 58 62 42 S100 48 120 30 S163 37 180 22 S217 26 240 8" fill="none" stroke="#77e6bb" strokeWidth="3" /><path d="M0 54 C28 48 36 58 62 42 S100 48 120 30 S163 37 180 22 S217 26 240 8 L240 72 L0 72Z" fill="url(#heroGradient)" /><defs><linearGradient id="heroGradient" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#77e6bb" stopOpacity=".25"/><stop offset="1" stopColor="#77e6bb" stopOpacity="0"/></linearGradient></defs></svg></div>
              <div className="preview-safe"><span>✦</span><small>SafePay plan</small><b>4 safe</b><em>1 needs review</em></div>
            </div>
            <div className="floating-card bill-card"><span className="icon-box">⚡</span><div><small>Electricity</small><b>Due-state verified</b></div><strong>₹1,840</strong></div>
            <div className="floating-card ai-card"><span>✦</span><div><b>AI found a safer route</b><small>Keep ₹10,000 in reserve</small></div></div>
          </div>
        </div>
      </section>

      <section className="proof-strip"><span>One intelligent layer above</span><b>Banks</b><b>UPI</b><b>Cards</b><b>Utilities</b><b>Subscriptions</b></section>

      <section className="section platform-perspective" id="platform">
        <div className="section-heading platform-heading"><div><span className="eyebrow">Complete platform perspective</span><h2>The full system,<br />before it becomes yours.</h2></div><p>This public interface explains every major capability. Sign in only when you are ready to enter a personalized Home with balances, deadlines and recommendations.</p></div>
        <div className="platform-map">
          {capabilities.map((item) => <article key={item.title}><div className="platform-card-top"><span>{item.icon}</span><small>{item.label}</small></div><h3>{item.title}</h3><p>{item.text}</p><em>{item.note}</em></article>)}
        </div>
        <div className="coverage-band">
          <div><span className="eyebrow">One place for every obligation</span><h3>Built around real household categories</h3></div>
          <div className="coverage-list">{categories.map((category) => <span key={category}>{category}</span>)}</div>
        </div>
        <div className="surface-comparison">
          <article><span>Before authentication</span><h3>Main interface</h3><p>Understand the product, supported categories, intelligence, safeguards and provider boundary without exposing any personal data.</p><a href="#workflow">Continue the platform tour →</a></article>
          <article><span>After login or signup</span><h3>Your financial Home</h3><p>See your money snapshot, upcoming obligations, AI briefing, payment incidents and the fastest next actions in one private workspace.</p><button onClick={() => setAuthOpen(true)}>Sign in to open Home →</button></article>
        </div>
      </section>

      <section className="section features" id="intelligence">
        <div className="section-heading"><div><span className="eyebrow">Beyond an expense tracker</span><h2>An intelligence layer<br />that thinks before it acts.</h2></div><p>BillFlow models what may happen next, then turns that outlook into a permission-based plan with an auditable reason.</p></div>
        <div className="feature-grid">{features.map((feature) => <article key={feature.number}><span>{feature.number}</span><h3>{feature.title}</h3><p>{feature.text}</p></article>)}</div>
      </section>

      <section className="section workflow" id="workflow">
        <div className="workflow-copy"><span className="eyebrow">End-to-end operating loop</span><h2>Discover. Forecast. Authorize. Verify.</h2><p>BillFlow separates recommendation from authority. It can organize, simulate, monitor and reconcile, while regulated payment and account changes pass through supported providers and user consent.</p><button className="button primary" onClick={() => setAuthOpen(true)}>Create my financial Home</button></div>
        <div className="workflow-steps">
          <div><span>1</span><section><b>Connect or add</b><p>Import supported accounts and bills, or manage unsupported obligations locally.</p></section></div>
          <div><span>2</span><section><b>Forecast and recommend</b><p>Project liquidity, rank deadlines and explain a safer date and funding source.</p></section></div>
          <div><span>3</span><section><b>Authorize with provider</b><p>You approve through the supported provider using its secure PIN, OTP or biometric flow.</p></section></div>
          <div><span>4</span><section><b>Monitor and reconcile</b><p>Track progress, retry notifications and verify the bill or subscription state after payment.</p></section></div>
        </div>
      </section>

      <section className="section trust" id="trust">
        <div className="trust-card"><span className="eyebrow">Trust is a product feature</span><h2>Your money never becomes an AI experiment.</h2><div className="trust-points"><p><b>Policy-controlled</b> SafePay respects your reserve and approval rules.</p><p><b>Provider-authorized</b> BillFlow never collects UPI PINs or bank passwords.</p><p><b>Operationally visible</b> Recommendations, payment states, retries and reconciliation stay auditable.</p></div><button className="button light" onClick={() => setAuthOpen(true)}>Open my private Home →</button></div>
      </section>

      <footer><Brand /><p>Public platform perspective. Private financial Home.</p><span>© 2026 BillFlow AI</span></footer>
      <AuthModal
        open={authOpen}
        onClose={() => { setAuthOpen(false); onAuthErrorDismissed?.() }}
        onAuthenticated={onAuthenticated}
        initialError={authError}
      />
    </div>
  )
}
