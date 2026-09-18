export default function ForecastChart({ points = [] }) {
  if (!points.length) return <div className="chart-empty">No forecast yet</div>
  const sample = points.filter((_, index) => index % Math.max(1, Math.floor(points.length / 14)) === 0)
  const values = sample.map((item) => item.projected_balance)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = Math.max(1, max - min)
  const coordinates = sample.map((item, index) => {
    const x = (index / Math.max(1, sample.length - 1)) * 100
    const y = 88 - ((item.projected_balance - min) / range) * 70
    return `${x},${y}`
  }).join(' ')
  const area = `0,100 ${coordinates} 100,100`

  return (
    <div className="forecast-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Projected balance chart">
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#77e6bb" stopOpacity=".36" />
            <stop offset="1" stopColor="#77e6bb" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" y1="88" x2="100" y2="88" className="chart-grid" />
        <polygon points={area} fill="url(#area)" />
        <polyline points={coordinates} fill="none" className="chart-line" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="chart-labels"><span>{sample[0]?.date.slice(5)}</span><span>{sample.at(-1)?.date.slice(5)}</span></div>
    </div>
  )
}

