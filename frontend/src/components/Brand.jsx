export default function Brand({ compact = false }) {
  return (
    <div className="brand" aria-label="BillFlow AI">
      <span className="brand-mark">B</span>
      {!compact && <span>BillFlow <b>AI</b></span>}
    </div>
  )
}

