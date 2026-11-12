import { useState } from 'react'
import { formatDate, formatMinutes, formatShortDate } from '../utils/format'

const WIDTH = 760
const HEIGHT = 220
const PAD = { top: 20, right: 12, bottom: 28, left: 44 }
const PLOT_W = WIDTH - PAD.left - PAD.right
const PLOT_H = HEIGHT - PAD.top - PAD.bottom

// Clean, round y-axis ticks (0, 5, 10 / 0, 20, 40 ...), about 4 steps, top tick >= max.
function niceTicks(max) {
  if (max <= 0) return [0, 1]
  const rough = max / 4
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough))
  const ticks = []
  for (let value = 0; value < max + step; value += step) ticks.push(value)
  return ticks
}

// A column with a 4px rounded top and a square base on the baseline.
function columnPath(x, y, width, height) {
  const r = Math.min(4, width / 2, height)
  const base = y + height
  return `M${x},${base} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} ` +
         `Q${x + width},${y} ${x + width},${y + r} V${base} Z`
}

export default function DailyStatsChart({ days }) {
  const [hover, setHover] = useState(null)
  if (days.length === 0) return null

  const ticks = niceTicks(Math.max(...days.map((d) => d.breaks)))
  const top = ticks[ticks.length - 1]
  const band = PLOT_W / days.length
  const barWidth = Math.max(1, Math.min(24, band - 2)) // ≤24px, always ≥2px of air between bars
  const yOf = (value) => PAD.top + PLOT_H - (value / top) * PLOT_H
  const labelEvery = Math.ceil(days.length / 6) // ~6 date labels, never overlapping
  const peak = days.reduce((best, d, i) => (d.breaks > days[best].breaks ? i : best), 0)
  const centerX = (i) => PAD.left + i * band + band / 2
  const hovered = hover !== null ? days[hover] : null

  return (
    <div className="chart" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
           aria-label={`Approved breaks per day. Peak: ${days[peak].breaks} on ${formatDate(days[peak].date)}.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={WIDTH - PAD.right} y1={yOf(t)} y2={yOf(t)} />
            <text className="tick" x={PAD.left - 8} y={yOf(t)} textAnchor="end" dominantBaseline="middle">
              {t.toLocaleString()}
            </text>
          </g>
        ))}

        {days.map((d, i) => {
          const height = yOf(0) - yOf(d.breaks)
          return (
            <g key={d.date}>
              {height > 0 && (
                <path className={`bar${hover === i ? ' active' : ''}`}
                      d={columnPath(centerX(i) - barWidth / 2, yOf(d.breaks), barWidth, height)} />
              )}
              {/* Hit target = the whole column band, much bigger than the thin bar */}
              <rect x={PAD.left + i * band} y={PAD.top} width={band} height={PLOT_H} fill="transparent"
                    onMouseEnter={() => setHover(i)} onClick={() => setHover(i)} />
              {i % labelEvery === 0 && (
                <text className="tick" x={centerX(i)} y={HEIGHT - 8} textAnchor="middle">
                  {formatShortDate(d.date)}
                </text>
              )}
            </g>
          )
        })}

        {/* Selective direct label: only the peak day */}
        {days[peak].breaks > 0 && hover === null && (
          <text className="value-label" x={centerX(peak)} y={yOf(days[peak].breaks) - 6} textAnchor="middle">
            {days[peak].breaks.toLocaleString()}
          </text>
        )}
      </svg>

      {hovered && (
        <div className="tooltip"
             style={{ left: `${Math.min(88, Math.max(12, (centerX(hover) / WIDTH) * 100))}%` }}>
          <strong>{formatDate(hovered.date)}</strong>
          <div>{hovered.breaks.toLocaleString()} breaks · {formatMinutes(hovered.total_minutes)}</div>
          <div>{hovered.unique_employees.toLocaleString()} employees</div>
        </div>
      )}
    </div>
  )
}
