import { useEffect, useState } from 'react'
import Brand from '../components/Brand'
import AuthModal from '../components/AuthModal'

const features = [
  { number: '01', title: 'One bill universe', text: 'See utilities, subscriptions, EMIs, insurance, rent and recharges in one calm timeline.' },
  { number: '02', title: 'SafePay intelligence', text: 'Forecast cash flow and choose a safer date and funding source—before a payment causes stress.' },
  { number: '03', title: 'Explainable alerts', text: 'Review unusual spending and payment risks with evidence, confidence and a reason you can understand.' },
  { number: '04', title: 'You stay in control', text: 'Automation follows your reserve policy. UPI PIN, OTP and final authorization remain with you.' },
]

export default function Landing({ onAuthenticated }) {
  const [authOpen, setAuthOpen] = useState(false)
  const [prompted, setPrompted] = useState(false)

  useEffect(() => {
    const showAtDepth = () => {
      const depth = window.scrollY / Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
      if (!prompted && depth > 0.58) {
        setPrompted(true)
        setAuthOpen(true)
      }
    }
    window.addEventListener('scroll', showAtDepth, { passive: true })
    return () => window.removeEventListener('scroll', showAtDepth)
  }, [prompted])

  return (
    <div className="landing">
      <nav className="landing-nav">
        <Brand />
        <div className="nav-links"><a href="#intelligence">Intelligence</a><a href="#workflow">How it works</a><a href="#trust">Trust</a></div>
        <button className="button nav-button" onClick={() => setAuthOpen(true)}>Open your workspace</button>
      </nav>

      <section className="hero">
        <div className="hero-copy">
          <div className="hero-pill"><span /> Intelligent finance, with human permission</div>
          <h1>Every bill.<br /><em>One clear decision.</em></h1>
          <p>BillFlow AI looks ahead across your money, detects what needs attention and creates a safe, explainable payment plan—all from one place.</p>
          <div className="hero-actions">
            <button className="button primary large" onClick={() => setAuthOpen(true)}>Start with your first bill <span>→</span></button>
            <a className="text-link" href="#workflow">See how it works ↓</a>
          </div>
          <div className="trust-row"><span>✓ No raw bank passwords</span><span>✓ No silent payments</span><span>✓ Audit-ready</span></div>
        </div>
        <div className="hero-visual" aria-label="BillFlow AI product preview">
          <div className="orb orb-one" /><div className="orb orb-two" />
          <div className="preview-window">
            <div className="preview-top"><div className="mini-brand">B</div><div className="preview-dots"><i /><i /><i /></div></div>
            <div className="preview-heading"><span>September outlook</span><b>Financial health <strong>82</strong></b></div>
            <div className="preview-balance"><small>Available across accounts</small><strong>₹90,450</strong><span>Stable through next 30 days</span></div>
            <div className="preview-grid">
              <div className="preview-chart"><small>Cash-flow forecast</small><svg viewBox="0 0 240 72"><path d="M0 54 C28 48 36 58 62 42 S100 48 120 30 S163 37 180 22 S217 26 240 8" fill="none" stroke="#77e6bb" strokeWidth="3" /><path d="M0 54 C28 48 36 58 62 42 S100 48 120 30 S163 37 180 22 S217 26 240 8 L240 72 L0 72Z" fill="url(#heroGradient)" /><defs><linearGradient id="heroGradient" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#77e6bb" stopOpacity=".25"/><stop offset="1" stopColor="#77e6bb" stopOpacity="0"/></linearGradient></defs></svg></div>
              <div className="preview-safe"><span>✦</span><small>SafePay plan</small><b>4 safe</b><em>1 needs review</em></div>
            </div>
            <div className="floating-card bill-card"><span className="icon-box">⚡</span><div><small>Electricity</small><b>Pay by Friday</b></div><strong>₹1,840</strong></div>
            <div className="floating-card ai-card"><span>✦</span><div><b>AI found a safer route</b><small>Keep ₹10,000 in reserve</small></div></div>
          </div>
        </div>
      </section>

      <section className="proof-strip"><span>One intelligent layer above</span><b>Banks</b><b>UPI</b><b>Cards</b><b>Utilities</b><b>Subscriptions</b></section>

      <section className="section features" id="intelligence">
        <div className="section-heading"><div><span className="eyebrow">Beyond an expense tracker</span><h2>A finance operating system<br />that thinks before it acts.</h2></div><p>Most apps tell you what already happened. BillFlow AI models what may happen next and turns that outlook into a permission-based plan.</p></div>
        <div className="feature-grid">{features.map((feature) => <article key={feature.number}><span>{feature.number}</span><h3>{feature.title}</h3><p>{feature.text}</p></article>)}</div>
      </section>

      <section className="section workflow" id="workflow">
        <div className="workflow-copy"><span className="eyebrow">SafePay Intelligence Engine</span><h2>Forecast. Protect. Explain. Then ask.</h2><p>Our novel decision layer balances due dates, projected cash, safety reserves and configured rewards. Its output is a recommendation—not an invisible command.</p><button className="button primary" onClick={() => setAuthOpen(true)}>Build my safe plan</button></div>
        <div className="workflow-steps">
          <div><span>1</span><section><b>Observe</b><p>Bring bills, balances and transaction history into one normalized view.</p></section></div>
          <div><span>2</span><section><b>Simulate</b><p>Project daily liquidity and test each obligation against your reserve policy.</p></section></div>
          <div><span>3</span><section><b>Recommend</b><p>Rank safer dates and funding sources with confidence and plain-language reasons.</p></section></div>
          <div><span>4</span><section><b>Authorize</b><p>You approve through the connected provider using its secure PIN, OTP or biometric flow.</p></section></div>
        </div>
      </section>

      <section className="section trust" id="trust">
        <div className="trust-card"><span className="eyebrow">Trust is a product feature</span><h2>Your money never becomes an AI experiment.</h2><div className="trust-points"><p><b>Policy-controlled</b> Set a reserve that SafePay must respect.</p><p><b>Provider-authorized</b> We never collect UPI PINs or bank passwords.</p><p><b>Auditable</b> Every recommendation and payment-state change is recorded.</p></div><button className="button light" onClick={() => setAuthOpen(true)}>Create my workspace →</button></div>
      </section>

      <footer><Brand /><p>Explainable finance intelligence. Human-authorized payments.</p><span>© 2026 BillFlow AI</span></footer>
      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} onAuthenticated={onAuthenticated} />
    </div>
  )
}

