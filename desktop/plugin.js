// Homelab Watch — Desktop half. A status-bar chip (green / amber / red rollup) and a /homelab page that
// lists every target. Data comes from dashboard/plugin_api.py through ctx.rest; nothing here probes devices.
import { atom, Button, host, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'homelab-watch'
const PATH = '/homelab'
const POLL_MS = 30_000

// Disk plugins are not scanned by Tailwind, so layout lives here; colours are theme variables.
const CSS = `
.hlw-chip{display:flex;align-items:center;gap:5px;height:100%;padding:0 6px;font-size:11px;color:var(--ui-text-tertiary);background:none;border:0;cursor:pointer}
.hlw-chip:hover{color:var(--ui-text-secondary)}
.hlw-dot{display:inline-block;width:7px;height:7px;border-radius:50%;flex-shrink:0;background:var(--ui-text-quaternary)}
.hlw-dot[data-tone=up]{background:var(--ui-success)}
.hlw-dot[data-tone=degraded],.hlw-dot[data-tone=pending]{background:var(--ui-warning)}
.hlw-dot[data-tone=down]{background:var(--ui-danger)}
.hlw-page{display:flex;flex-direction:column;gap:16px;padding:24px 28px;max-width:980px;overflow:auto;height:100%;box-sizing:border-box}
.hlw-head{display:flex;align-items:center;gap:12px}
.hlw-title{font-size:18px;font-weight:600;color:var(--ui-text-primary)}
.hlw-sub{font-size:13px;color:var(--ui-text-secondary);line-height:1.5}
.hlw-muted{font-size:12px;color:var(--ui-text-tertiary)}
.hlw-grow{flex:1}
.hlw-incident{border:1px solid var(--ui-stroke-secondary);border-left:3px solid var(--ui-danger);border-radius:6px;padding:10px 12px;font-size:13px;color:var(--ui-text-secondary)}
.hlw-incident b{color:var(--ui-text-primary)}
.hlw-table{width:100%;border-collapse:collapse;font-size:12.5px}
.hlw-table th{text-align:left;font-weight:500;color:var(--ui-text-tertiary);padding:6px 8px;border-bottom:1px solid var(--ui-stroke-secondary)}
.hlw-table td{padding:7px 8px;border-bottom:1px solid var(--ui-stroke-secondary);color:var(--ui-text-secondary);vertical-align:top}
.hlw-table td.hlw-name{color:var(--ui-text-primary);white-space:nowrap}
.hlw-child{padding-left:16px}
.hlw-mono{font-family:var(--font-mono,monospace);font-size:11.5px}
.hlw-sep{color:var(--ui-text-quaternary)}
.hlw-card{border:1px solid var(--ui-stroke-secondary);border-radius:6px;padding:12px 14px;display:flex;flex-direction:column;gap:6px}
.hlw-card h3{margin:0;font-size:13px;font-weight:600;color:var(--ui-text-primary)}
.hlw-stats{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;color:var(--ui-text-secondary)}
.hlw-stats b{color:var(--ui-text-primary);font-weight:600}
.hlw-saved{color:var(--ui-success)}
`

const LABEL = { up: 'All good', degraded: 'Watching', down: 'Down', unconfigured: 'Set up', loading: 'Checking', error: 'Offline' }

const status = atom({ overall: 'loading', incidents: [], targets: [] })

function ago(since) {
  if (!since) return ''
  const mins = Math.floor((Date.now() / 1000 - since) / 60)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  return hours < 48 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`
}

function chipText(s) {
  if (s.overall === 'down') {
    const n = s.incidents.length
    return `Home: ${n} problem${n === 1 ? '' : 's'}`
  }
  return `Home: ${LABEL[s.overall] || s.overall}`
}

function shortTokens(n) {
  if (!n) return '0'
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
  if (n >= 1e3) return `${Math.round(n / 1e3)}k`
  return String(n)
}

const usd = n => `$${(n || 0).toFixed(2)}`

function usageChip(s) {
  const t = s.usage && s.usage.today
  if (!t || !t.tokens) return ''
  return ` · ${shortTokens(t.tokens)} tok${t.saved_total ? ` · saved ${usd(t.saved_total)}` : ''}`
}

function Dot({ tone }) {
  return jsx('span', { className: 'hlw-dot', 'data-tone': tone, 'aria-hidden': 'true' })
}

function Chip() {
  const s = useValue(status)
  return jsxs('button', {
    type: 'button',
    className: 'hlw-chip',
    title: s.summary || s.error || 'Homelab Watch',
    onClick: () => host.navigate(PATH),
    children: [jsx(Dot, { tone: s.overall }), chipText(s) + usageChip(s)]
  })
}

function metricsText(m) {
  if (!m || !Object.keys(m).length) return ''
  const parts = []
  if (m.hashrate_ghs != null) parts.push(`${m.hashrate_ghs} GH/s`)
  if (m.temp_c != null) parts.push(`${m.temp_c}°C`)
  if (m.vr_temp_c != null) parts.push(`VR ${m.vr_temp_c}°C`)
  if (m.efficiency_jth != null) parts.push(`${m.efficiency_jth} J/TH`)
  return parts.join(' · ')
}

function depth(t, byId) {
  let d = 0
  for (let p = t.parent; p && byId[p] && d < 8; p = byId[p].parent) d++
  return d
}

function TargetRow({ t, byId }) {
  const d = depth(t, byId)
  return jsxs('tr', {
    children: [
      jsx('td', { children: jsx(Dot, { tone: t.status }) }),
      jsx('td', { className: 'hlw-name', style: { paddingLeft: 8 + d * 16 }, children: t.name }),
      jsx('td', { className: 'hlw-mono', children: t.check }),
      jsx('td', { children: [t.detail, metricsText(t.metrics)].filter(Boolean).join(' — ') }),
      jsx('td', { className: 'hlw-mono', children: t.latency_ms != null ? `${t.latency_ms} ms` : '' }),
      jsx('td', { className: 'hlw-muted', children: `${t.status} ${ago(t.since)}` })
    ]
  })
}

function Stat({ label, value, saved }) {
  return jsxs('span', { children: [`${label} `, jsx('b', { className: saved ? 'hlw-saved' : undefined, children: value })] })
}

function UsagePeriod({ title, u }) {
  if (!u || !u.tokens) return null
  return jsxs('div', {
    className: 'hlw-stats',
    children: [
      jsx('b', { children: title }),
      jsx(Stat, { label: 'tokens', value: shortTokens(u.tokens) }),
      jsx(Stat, { label: 'requests', value: String(u.requests) }),
      jsx(Stat, { label: 'saved', value: usd(u.saved_total), saved: true }),
      jsx(Stat, { label: 'by subscription', value: usd(u.saved_by_subscription) }),
      jsx(Stat, { label: 'by cheaper models', value: usd(u.saved_by_cheaper_model) }),
      jsx(Stat, { label: 'by free models', value: usd(u.saved_by_free_model) }),
      jsx(Stat, { label: 'spent', value: usd(u.spent) }),
      u.judge_cost ? jsx(Stat, { label: 'router judge', value: `−${usd(u.judge_cost)}` }) : null,
      u.unpriced_tokens ? jsx(Stat, { label: 'unpriced', value: `${shortTokens(u.unpriced_tokens)} tok` }) : null
    ]
  })
}

function UsageCard({ usage }) {
  const today = usage && usage.today
  if (!today || !today.tokens) {
    return jsxs('div', { className: 'hlw-card', children: [jsx('h3', { children: 'Hermes' }), jsx('div', { className: 'hlw-muted', children: 'No model requests recorded yet today.' })] })
  }
  const models = Object.entries(today.by_model || {}).sort((a, b) => b[1].tokens - a[1].tokens)
  return jsxs('div', {
    className: 'hlw-card',
    children: [
      jsx('h3', { children: 'Hermes' }),
      jsx(UsagePeriod, { title: 'Today', u: today }),
      jsx(UsagePeriod, { title: 'This month', u: usage.month }),
      jsx('div', { className: 'hlw-muted', children: models.map(([m, v]) => `${m}: ${shortTokens(v.tokens)} tok (${v.requests})`).join('  ·  ') }),
      jsx('div', { className: 'hlw-muted', children: 'Saved = API-equivalent dollars at published list prices. Unpriced models are counted, never estimated.' })
    ]
  })
}

function Page({ refresh }) {
  const s = useValue(status)
  const byId = Object.fromEntries(s.targets.map(t => [t.id, t]))
  const nameOf = id => (byId[id] ? byId[id].name : id)
  return jsxs('div', {
    className: 'hlw-page',
    children: [
      jsxs('div', {
        className: 'hlw-head',
        children: [
          jsx(Dot, { tone: s.overall }),
          jsx('div', { className: 'hlw-title', children: `Homelab — ${LABEL[s.overall] || s.overall}` }),
          jsx('div', { className: 'hlw-grow' }),
          jsx(Button, { size: 'sm', variant: 'outline', onClick: () => refresh(true), children: 'Check now' })
        ]
      }),
      jsx('div', { className: 'hlw-sub', children: s.error || s.summary || 'Checking…' }),
      s.overall === 'unconfigured'
        ? jsx('div', { className: 'hlw-muted', children: 'Run `hermes homelab init`, then edit targets.yaml.' })
        : null,
      jsx(UsageCard, { usage: s.usage }),
      ...s.incidents.map(i =>
        jsxs('div', {
          key: i.root,
          className: 'hlw-incident',
          children: [
            jsx('b', { children: i.name }),
            ` is down ${ago(i.since)} (${i.detail})`,
            i.affected.length ? ` — also affects ${i.affected.map(nameOf).join(', ')}` : ''
          ]
        })
      ),
      s.targets.length
        ? jsxs('table', {
            className: 'hlw-table',
            children: [
              jsx('thead', {
                children: jsxs('tr', {
                  children: ['', 'Target', 'Check', 'Detail', 'Latency', 'Status'].map((h, n) => jsx('th', { children: h }, n))
                })
              }),
              jsx('tbody', { children: s.targets.map(t => jsx(TargetRow, { t, byId }, t.id)) })
            ]
          })
        : null,
      jsx('div', { className: 'hlw-muted', children: 'Read-only checks. Alerts: /homelab alerts on' })
    ]
  })
}

export default {
  id: ID,
  name: 'Homelab Watch',
  register(ctx) {
    const style = document.createElement('style')
    style.textContent = CSS
    document.head.appendChild(style)
    ctx.onDispose(() => style.remove())

    let inFlight = false
    const refresh = async (force = false) => {
      if (inFlight) return
      inFlight = true
      try {
        const next = await ctx.rest(force ? '/check' : '/status', force ? { method: 'POST', timeoutMs: 30_000 } : {})
        status.set({ incidents: [], targets: [], ...next })
      } catch (err) {
        status.set({ ...status.get(), overall: 'error', error: `Homelab Watch backend unavailable: ${err && err.message ? err.message : err}` })
      } finally {
        inFlight = false
      }
    }

    refresh()
    ctx.setInterval(() => refresh(), POLL_MS)

    ctx.registerMany([
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 115, render: () => jsx(Chip, {}) },
      { id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => jsx(Page, { refresh }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Homelab', codicon: 'pulse' } }
    ])
  }
}
