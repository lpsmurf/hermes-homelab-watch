// Homelab Watch — Desktop half. A status-bar chip (green / amber / red rollup) and a /homelab page that
// lists every target. Data comes from dashboard/plugin_api.py through ctx.rest; nothing here probes devices.
import { atom, host, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, useValue } from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'homelab-watch'
const PATH = '/homelab'
const POLL_MS = 30_000

// Disk plugins are not scanned by Tailwind, so layout lives here. The chip sits in Hermes' own chrome and uses
// its theme variables; the /homelab page is an AX Control Room "room" (ax/dashboard/web/DESIGN.md, "The
// Curator's Study"): deep teal ground, cream ink, serif display, mono numerals, 3px corners, flat cards, and the
// AX ordered-dither background. Fonts are named, never fetched: installed ones are used, otherwise the fallbacks.
const CSS = `
.hlw-chip{display:flex;align-items:center;gap:5px;height:100%;padding:0 6px;font-size:11px;color:var(--ui-text-tertiary);background:none;border:0;cursor:pointer}
.hlw-chip:hover{color:var(--ui-text-secondary)}
.hlw-chip .hlw-dot{width:7px;height:7px}
.hlw-chip .hlw-dot[data-tone=up]{background:var(--ui-success)}
.hlw-chip .hlw-dot[data-tone=degraded],.hlw-chip .hlw-dot[data-tone=pending]{background:var(--ui-warning)}
.hlw-chip .hlw-dot[data-tone=down]{background:var(--ui-danger)}
.hlw-dot{display:inline-block;width:6px;height:6px;border-radius:50%;flex-shrink:0;background:var(--muted,#7d9691)}

.hlw-room{
  --ground:#041c1c;--surface:#0a2624;--sunk:#06201f;--line:#14403c;--line-soft:#0e322f;
  --ink:#ffe6cb;--ink-dim:#cdbba6;--muted:#7d9691;--accent:#43b6aa;--accent-soft:#0f3330;
  --good:#5fbf80;--warn:#e0a548;--crit:#f0786e;--info:#86a6e0;
  --sans:"Schibsted Grotesk",ui-sans-serif,system-ui,-apple-system,sans-serif;
  --serif:"Cormorant Garamond",Georgia,"Times New Roman",serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  --r:3px;--glow:var(--accent);
  position:relative;height:100%;overflow:auto;background:var(--ground);color:var(--ink);
  font:14px/1.5 var(--sans);-webkit-font-smoothing:antialiased;
}
.hlw-room[data-tone=up]{--glow:var(--good)}
.hlw-room[data-tone=degraded],.hlw-room[data-tone=pending]{--glow:var(--warn)}
.hlw-room[data-tone=down]{--glow:var(--crit)}

/* AX backdrop: a status-tinted light falling across the room, masked off to the right, broken into dots by the
   same 4px ordered-dither screen AX lays over its classical art. */
.hlw-backdrop{position:absolute;inset:0;min-height:100%;pointer-events:none;overflow:hidden;mix-blend-mode:screen;opacity:.85;
  -webkit-mask-image:linear-gradient(100deg,#000 0%,#000 38%,transparent 86%);mask-image:linear-gradient(100deg,#000 0%,#000 38%,transparent 86%)}
.hlw-backdrop::before{content:"";position:absolute;inset:-10% -10% auto -10%;height:120%;
  background:radial-gradient(ellipse 72% 56% at 14% 4%,color-mix(in srgb,var(--glow) 62%,transparent),transparent 72%),
             radial-gradient(ellipse 50% 60% at 4% 70%,color-mix(in srgb,var(--accent) 16%,transparent),transparent 72%),
             linear-gradient(160deg,var(--surface),var(--ground) 62%)}
.hlw-backdrop::after{content:"";position:absolute;inset:0;
  background-image:radial-gradient(circle at 25% 25%,rgba(4,28,28,.92) 1px,transparent 1.4px),
                   radial-gradient(circle at 75% 75%,rgba(4,28,28,.92) 1px,transparent 1.4px);
  background-size:4px 4px,4px 4px;background-position:0 0,2px 2px}
.hlw-room[data-tone=down] .hlw-backdrop{animation:hlw-breathe 3.2s cubic-bezier(.22,.61,.36,1) infinite alternate}
@keyframes hlw-breathe{from{opacity:.62}to{opacity:1}}
@media (prefers-reduced-motion:reduce){.hlw-room[data-tone=down] .hlw-backdrop{animation:none}}

.hlw-inner{position:relative;display:flex;flex-direction:column;gap:18px;padding:30px 34px 40px;max-width:1080px}
.hlw-kicker{display:flex;align-items:center;gap:8px;font:600 11px/1 var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--muted)}
.hlw-kicker .hlw-dot{background:var(--glow)}
.hlw-head{display:flex;align-items:flex-end;gap:18px;flex-wrap:wrap}
.hlw-head-text{flex:1;min-width:260px}
.hlw-room h1{font:400 34px/1.1 var(--serif);letter-spacing:.01em;margin:10px 0 6px;color:var(--ink)}
.hlw-summary{color:var(--ink-dim);font-size:13.5px;max-width:70ch}
.hlw-btn{font:600 12px/1 var(--sans);padding:9px 14px;border-radius:var(--r);border:0;background:var(--accent);color:#04211f;cursor:pointer}
.hlw-btn:hover{filter:brightness(1.08)}
.hlw-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hlw-btn[disabled]{opacity:.6;cursor:default}

.hlw-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:18px}
.hlw-card{border:1px solid var(--line);background:var(--surface);border-radius:var(--r);padding:14px 16px;position:relative;overflow:hidden;min-width:0}
.hlw-label{font:600 11px/1.6 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.hlw-big{font:400 32px/1.15 var(--serif);color:var(--ink);margin-top:4px}
.hlw-big.good{color:var(--good)}
.hlw-sub{color:var(--muted);font-size:12.5px}
.hlw-card h2{font:400 20px/1.2 var(--serif);margin:0 0 10px;color:var(--ink)}

.hlw-pill{display:inline-block;font:600 11px/1.6 var(--mono);letter-spacing:.08em;text-transform:uppercase;padding:1px 7px;border-radius:999px;border:1px solid var(--line);color:var(--ink-dim);white-space:nowrap}
.hlw-pill.good{color:var(--good);border-color:#2c5c3f}
.hlw-pill.warn{color:var(--warn);border-color:#5c4a23}
.hlw-pill.crit{color:var(--crit);border-color:#6b3330}
.hlw-pill.info{color:var(--info);border-color:#33456b}

.hlw-incident{display:flex;gap:12px;align-items:baseline}
.hlw-incident + .hlw-incident{margin-top:10px;padding-top:10px;border-top:1px solid var(--line-soft)}
.hlw-incident b{color:var(--ink);font-weight:600}
.hlw-incident span{color:var(--ink-dim)}

.hlw-table{width:100%;border-collapse:collapse;font-size:13px}
.hlw-table th{text-align:left;font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted);padding:0 10px 8px 0}
.hlw-table td{padding:8px 10px 8px 0;border-top:1px solid var(--line-soft);color:var(--ink-dim);vertical-align:top}
.hlw-table td.name{color:var(--ink);white-space:nowrap}
.hlw-table td.name i{font-style:normal;color:var(--muted);margin-right:6px;font-family:var(--mono)}
.hlw-table .num{text-align:right;font-family:var(--mono);font-size:12.5px;white-space:nowrap}
.hlw-table th.num{font:600 11px/1 var(--mono)}
.hlw-table td.mono{font-family:var(--mono);font-size:12px;color:var(--muted)}
.hlw-btn.ghost{background:var(--sunk);color:var(--ink);border:1px solid var(--line)}
.hlw-btns{display:flex;gap:10px;flex-wrap:wrap}
.hlw-scan{display:flex;flex-direction:column;gap:12px}
.hlw-scan p{margin:0;font-size:13.5px;color:var(--ink-dim);max-width:70ch}
.hlw-scan input[type=text]{background:var(--sunk);border:1px solid var(--line);border-radius:3px;color:var(--ink);font:13px var(--sans);padding:6px 8px;width:100%;min-width:0}
.hlw-scan input[type=checkbox]{accent-color:var(--accent);width:16px;height:16px}
.hlw-err{color:var(--crit);font-size:13px}
.hlw-foot{font:400 12px/1.7 var(--mono);color:var(--muted)}
`

const LABEL = { up: 'All good', degraded: 'Watching', down: 'Down', unconfigured: 'Set up', loading: 'Checking', error: 'Offline' }
const HEADLINE = {
  up: 'Your homelab is calm.',
  degraded: 'Something just flickered.',
  unconfigured: 'Nothing to watch yet.',
  loading: 'Looking around…',
  error: 'The watch is offline.'
}
const PILL = { up: 'good', pending: 'warn', degraded: 'warn', down: 'crit' }

const status = atom({ overall: 'loading', incidents: [], targets: [] })
const busy = atom(false)

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

function Pill({ tone, children }) {
  return jsx('span', { className: `hlw-pill ${PILL[tone] || ''}`, children })
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
  if (m.hashrate_ghs != null) parts.push(`${Math.round(m.hashrate_ghs)} GH/s`)
  if (m.temp_c != null) parts.push(`${Math.round(m.temp_c)}°C`)
  if (m.vr_temp_c) parts.push(`VR ${Math.round(m.vr_temp_c)}°C`)  // 0 = no sensor on this board
  if (m.power_w != null) parts.push(`${m.power_w.toFixed(1)} W`)
  if (m.efficiency_jth != null) parts.push(`${m.efficiency_jth.toFixed(1)} J/TH`)
  return parts.join(' · ')
}

// Parents first, each followed by its own children, so the indent always sits under the right parent.
function treeOrder(targets, byId) {
  const kids = {}
  const roots = []
  for (const t of targets) (t.parent && byId[t.parent] ? (kids[t.parent] ||= []) : roots).push(t)
  const out = []
  const walk = t => { out.push(t); (kids[t.id] || []).forEach(walk) }
  roots.forEach(walk)
  return out
}

function depth(t, byId) {
  let d = 0
  for (let p = t.parent; p && byId[p] && d < 8; p = byId[p].parent) d++
  return d
}

// A healthy device with metrics shows the readable numbers; anything else shows the probe's own detail.
function detailText(t) {
  const m = metricsText(t.metrics)
  return t.status === 'up' && m ? m : [t.detail, m].filter(Boolean).join(' — ')
}

function TargetRow({ t, byId }) {
  const d = depth(t, byId)
  return jsxs('tr', {
    children: [
      jsx('td', { children: jsx(Pill, { tone: t.status, children: t.status }) }),
      jsxs('td', { className: 'name', style: { paddingLeft: d * 18 }, children: [d ? jsx('i', { children: '└' }) : null, t.name] }),
      jsx('td', { className: 'mono', children: t.check }),
      jsx('td', { children: detailText(t) }),
      jsx('td', { className: 'num', children: t.latency_ms != null ? `${Math.round(t.latency_ms)} ms` : '—' }),
      jsx('td', { className: 'num', style: { color: 'var(--muted)' }, children: ago(t.since) })
    ]
  })
}

function StatCard({ label, value, sub, good }) {
  return jsxs('div', {
    className: 'hlw-card',
    children: [
      jsx('div', { className: 'hlw-label', children: label }),
      jsx('div', { className: `hlw-big${good ? ' good' : ''}`, children: value }),
      sub ? jsx('div', { className: 'hlw-sub', children: sub }) : null
    ]
  })
}

function StatGrid({ s }) {
  const up = s.targets.filter(t => t.status === 'up').length
  const today = (s.usage && s.usage.today) || {}
  const route = (s.usage && s.usage.route) || {}
  return jsxs('div', {
    className: 'hlw-grid',
    children: [
      jsx(StatCard, { label: 'Targets up', value: `${up} / ${s.targets.length}`, sub: s.incidents.length ? `${s.incidents.length} root cause${s.incidents.length === 1 ? '' : 's'}` : 'no incidents' }),
      jsx(StatCard, { label: 'Hermes tokens today', value: shortTokens(today.tokens), sub: `${today.requests || 0} requests` }),
      jsx(StatCard, { label: 'Saved today', value: usd(today.saved_total), sub: 'API-equivalent', good: !!today.saved_total }),
      jsx(StatCard, { label: 'Cost router', value: `${route.would_move || 0} / ${route.decisions || 0}`, sub: route.decisions ? `could run cheaper · ${route.moved || 0} moved` : 'no subagent tasks judged yet' })
    ]
  })
}

function Incidents({ s, nameOf }) {
  if (!s.incidents.length) return null
  return jsxs('div', {
    className: 'hlw-card',
    children: [
      jsx('h2', { children: 'Incidents' }),
      ...s.incidents.map(i => jsxs('div', {
        key: i.root,
        className: 'hlw-incident',
        children: [
          jsx(Pill, { tone: 'down', children: 'down' }),
          jsxs('div', {
            children: [
              jsx('b', { children: i.name }),
              jsx('span', { children: ` since ${ago(i.since)} — ${i.detail}` }),
              i.affected.length ? jsx('div', { className: 'hlw-sub', children: `Also affects ${i.affected.map(nameOf).join(', ')}` }) : null
            ]
          })
        ]
      }))
    ]
  })
}

const SAVINGS_ROWS = [
  ['Saved by subscription', 'saved_by_subscription'],
  ['Saved by cheaper models', 'saved_by_cheaper_model'],
  ['Saved by free models', 'saved_by_free_model'],
  ['Spent (metered)', 'spent'],
  ['Router judge', 'judge_cost']
]

function UsageCard({ usage }) {
  const today = (usage && usage.today) || {}
  const month = (usage && usage.month) || {}
  if (!month.tokens) {
    return jsxs('div', { className: 'hlw-card', children: [jsx('h2', { children: 'Hermes' }), jsx('div', { className: 'hlw-sub', children: 'No model requests recorded yet.' })] })
  }
  const models = Object.entries(today.by_model || {}).sort((a, b) => b[1].tokens - a[1].tokens)
  return jsxs('div', {
    className: 'hlw-card',
    children: [
      jsx('h2', { children: 'Hermes' }),
      jsxs('table', {
        className: 'hlw-table',
        children: [
          jsx('thead', { children: jsxs('tr', { children: [jsx('th', { children: 'Model spend' }), jsx('th', { className: 'num', children: 'Today' }), jsx('th', { className: 'num', children: 'Month' })] }) }),
          jsxs('tbody', {
            children: [
              jsxs('tr', { children: [jsx('td', { className: 'name', children: 'Tokens' }), jsx('td', { className: 'num', children: shortTokens(today.tokens) }), jsx('td', { className: 'num', children: shortTokens(month.tokens) })] }),
              ...SAVINGS_ROWS.map(([label, key]) => jsxs('tr', {
                key,
                children: [jsx('td', { children: label }), jsx('td', { className: 'num', children: usd(today[key]) }), jsx('td', { className: 'num', children: usd(month[key]) })]
              })),
              jsxs('tr', { children: [jsx('td', { className: 'name', children: 'Saved, net' }), jsx('td', { className: 'num', style: { color: 'var(--good)' }, children: usd(today.saved_total) }), jsx('td', { className: 'num', style: { color: 'var(--good)' }, children: usd(month.saved_total) })] }),
              month.unpriced_tokens
                ? jsxs('tr', { children: [jsx('td', { children: 'Unpriced tokens' }), jsx('td', { className: 'num', children: shortTokens(today.unpriced_tokens) }), jsx('td', { className: 'num', children: shortTokens(month.unpriced_tokens) })] })
                : null
            ]
          })
        ]
      }),
      models.length ? jsx('div', { className: 'hlw-foot', style: { marginTop: 10 }, children: models.map(([m, v]) => `${m} ${shortTokens(v.tokens)}`).join('  ·  ') }) : null,
      jsx('div', { className: 'hlw-sub', style: { marginTop: 6 }, children: 'API-equivalent dollars at published list prices. Unpriced models are counted, never estimated.' })
    ]
  })
}

function Targets({ s, byId }) {
  if (!s.targets.length) return null
  return jsxs('div', {
    className: 'hlw-card',
    children: [
      jsx('h2', { children: 'Targets' }),
      jsxs('table', {
        className: 'hlw-table',
        children: [
          jsx('thead', {
            children: jsxs('tr', {
              children: ['Status', 'Target', 'Check', 'Detail', 'Latency', 'Since'].map((h, n) =>
                jsx('th', { className: n >= 4 ? 'num' : undefined, children: h }, n))
            })
          }),
          jsx('tbody', { children: treeOrder(s.targets, byId).map(t => jsx(TargetRow, { t, byId }, t.id)) })
        ]
      })
    ]
  })
}


// Desktop occasionally fails to get a login ticket from the local gateway ("Gateway ticket bootstrap failed")
// and succeeds a moment later, so every call to this plugin's backend retries once before giving up.
async function call(ctx, path, opts) {
  try {
    return await ctx.rest(path, opts)
  } catch (err) {
    if (!/ticket|bootstrap|Gateway/i.test(String((err && err.message) || err))) throw err
    await new Promise(r => setTimeout(r, 1500))
    return ctx.rest(path, opts)
  }
}

const KIND = { http: 'web page', tcp: 'port 22', ping: 'ping only' }

function ScanPanel({ ctx, onDone }) {
  const [st, setSt] = useState({ phase: 'plan' })
  const [rows, setRows] = useState([])
  const go = async (phase, run) => {
    setSt({ phase })
    try { return await run() } catch (e) { setSt({ phase: 'error', msg: String((e && e.message) || e) }) }
  }
  const plan = () => go('planning', async () => {
    const r = await call(ctx, '/scan/plan')
    setSt(r.error ? { phase: 'error', msg: r.error } : { phase: 'confirm', nets: r.networks })
  })
  const scan = plan_ => go('scanning', async () => {
    const r = await call(ctx, '/scan', { method: 'POST', body: { range: plan_.range }, timeoutMs: 120000 })
    if (r.error) return setSt({ phase: 'error', msg: r.error })
    setRows(r.devices.map(d => ({ ...d, pick: !d.known, name: d.name || (d.gateway ? 'Router' : '') })))
    setSt({ phase: 'results', plan: plan_, found: r })
  })
  const add = () => go('adding', async () => {
    const picked = rows.filter(r => r.pick && !r.known).map(r => ({ ip: r.ip, name: r.name || r.ip, check: r.check, url: r.url, port: r.port, gateway: r.gateway }))
    const r = await call(ctx, '/scan/add', { method: 'POST', body: { devices: picked, gateway: st.found.gateway }, timeoutMs: 60000 })
    if (r.error) return setSt({ phase: 'error', msg: r.error })
    setSt({ phase: 'done', added: r.added }); onDone()
  })
  const upd = (i, patch) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)))
  const close = jsx('button', { type: 'button', className: 'hlw-btn ghost', onClick: onDone, children: 'Close' })

  if (st.phase === 'plan') {
    return jsxs('div', { className: 'hlw-card hlw-scan', children: [
      jsx('h2', { children: 'Scan my network' }),
      jsx('p', { children: 'Looks for devices on the network this computer is on, so you can pick which ones to watch. It only looks: a ping, a knock on a few common ports, and the list of devices this computer already knows. It never logs in or changes anything.' }),
      jsxs('div', { className: 'hlw-btns', children: [jsx('button', { type: 'button', className: 'hlw-btn', onClick: plan, children: 'Continue' }), close] })] })
  }
  if (st.phase === 'planning' || st.phase === 'scanning' || st.phase === 'adding') {
    const msg = { planning: 'Checking your network…', scanning: 'Scanning. This takes about 15 seconds.', adding: 'Adding and checking…' }[st.phase]
    return jsxs('div', { className: 'hlw-card hlw-scan', children: [jsx('h2', { children: 'Scan my network' }), jsx('p', { children: msg })] })
  }
  if (st.phase === 'confirm') {
    return jsxs('div', { className: 'hlw-card hlw-scan', children: [
      jsx('h2', { children: st.nets.length > 1 ? 'Which network?' : 'Ready to scan' }),
      jsx('p', { children: 'Only your own home or office network is ever scanned, one at a time, and VPN tunnels are skipped. Each scan pings the addresses in that range and knocks on a few common ports.' }),
      jsxs('div', { className: 'hlw-btns', children: [...st.nets.map(n => jsx('button', { type: 'button', className: 'hlw-btn', onClick: () => scan(n), children: `Scan ${n.range} (${n.iface})` }, n.range)), close] })] })
  }
  if (st.phase === 'error') {
    return jsxs('div', { className: 'hlw-card hlw-scan', children: [jsx('h2', { children: 'Scan my network' }), jsx('p', { className: 'hlw-err', children: st.msg }), jsx('div', { className: 'hlw-btns', children: close })] })
  }
  if (st.phase === 'done') {
    return jsxs('div', { className: 'hlw-card hlw-scan', children: [jsx('h2', { children: 'Added' }), jsx('p', { children: `${st.added} device${st.added === 1 ? '' : 's'} added and checked. They now appear in the table and in your alerts.` }), jsx('div', { className: 'hlw-btns', children: close })] })
  }
  const f = st.found
  const chosen = rows.filter(r => r.pick && !r.known).length
  return jsxs('div', { className: 'hlw-card hlw-scan', children: [
    jsx('h2', { children: `Found ${rows.length} device${rows.length === 1 ? '' : 's'} in ${f.range}` }),
    jsx('p', { children: 'Tick what you want watched and give each a name you will recognise. Anything switched off, behind a firewall, or on another network will not show up here; you can add it by asking Hermes, or by using the add-targets skill.' }),
    jsx('div', { className: 'scroll', children: jsxs('table', { className: 'hlw-table', children: [
      jsx('thead', { children: jsxs('tr', { children: ['', 'Name', 'Address', 'Looks like', 'Will check'].map((h, n) => jsx('th', { children: h }, n)) }) }),
      jsx('tbody', { children: rows.map((r, i) => jsxs('tr', { key: r.ip, children: [
        jsx('td', { children: r.known ? jsx(Pill, { tone: 'up', children: 'watched' }) : jsx('input', { type: 'checkbox', checked: r.pick, onChange: e => upd(i, { pick: e.target.checked }), 'aria-label': `Watch ${r.ip}` }) }),
        jsx('td', { children: r.known ? r.name || r.ip : jsx('input', { type: 'text', value: r.name, placeholder: r.ip, onChange: e => upd(i, { name: e.target.value }), 'aria-label': `Name for ${r.ip}` }) }),
        jsx('td', { className: 'mono', children: r.ip + (r.gateway ? ' (router)' : '') }),
        jsx('td', { children: r.label }),
        jsx('td', { className: 'mono', children: KIND[r.check] || r.check })] })) })] }) }),
    jsxs('div', { className: 'hlw-btns', children: [
      jsx('button', { type: 'button', className: 'hlw-btn', disabled: !chosen, onClick: add, children: chosen ? `Add ${chosen} selected` : 'Select something to add' }), close] })] })
}

function Page({ refresh, ctx }) {
  const s = useValue(status)
  const checking = useValue(busy)
  const [scanning, setScanning] = useState(false)
  const byId = Object.fromEntries(s.targets.map(t => [t.id, t]))
  const nameOf = id => (byId[id] ? byId[id].name : id)
  const n = s.incidents.length
  const headline = s.overall === 'down' ? `${n} problem${n === 1 ? '' : 's'} at home.` : HEADLINE[s.overall] || LABEL[s.overall]
  return jsxs('div', {
    className: 'hlw-room',
    'data-tone': s.overall,
    children: [
      jsx('div', { className: 'hlw-backdrop', 'aria-hidden': 'true' }),
      jsxs('div', {
        className: 'hlw-inner',
        children: [
          jsxs('div', {
            className: 'hlw-head',
            children: [
              jsxs('div', {
                className: 'hlw-head-text',
                children: [
                  jsxs('div', { className: 'hlw-kicker', children: [jsx(Dot, { tone: s.overall }), `Homelab Watch · ${LABEL[s.overall] || s.overall}`] }),
                  jsx('h1', { children: headline }),
                  jsx('div', { className: 'hlw-summary', children: s.error || s.summary || 'Checking…' })
                ]
              }),
              jsxs('div', { className: 'hlw-btns', children: [jsx('button', { type: 'button', className: 'hlw-btn ghost', onClick: () => setScanning(true), children: 'Scan my network' }), jsx('button', { type: 'button', className: 'hlw-btn', disabled: checking, onClick: () => refresh(true), children: checking ? 'Checking…' : 'Check now' })] })
            ]
          }),
          s.overall === 'unconfigured' ? jsx('div', { className: 'hlw-sub', children: 'Run `hermes homelab init`, then edit targets.yaml.' }) : null,
          scanning ? jsx(ScanPanel, { ctx, onDone: () => { setScanning(false); refresh(true) } }) : null,
          jsx(StatGrid, { s }),
          jsx(Incidents, { s, nameOf }),
          jsx(Targets, { s, byId }),
          jsx(UsageCard, { usage: s.usage }),
          jsx('div', { className: 'hlw-foot', children: 'Read-only checks · alerts: /homelab alerts on · router: /homelab route' })
        ]
      })
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

    const refresh = async (force = false) => {
      if (busy.get()) return
      busy.set(true)
      try {
        const next = await call(ctx, force ? '/check' : '/status', force ? { method: 'POST', timeoutMs: 30_000 } : {})
        status.set({ incidents: [], targets: [], ...next })
      } catch (err) {
        status.set({ ...status.get(), overall: 'error', error: `Homelab Watch backend unavailable: ${err && err.message ? err.message : err}` })
      } finally {
        busy.set(false)
      }
    }

    refresh()
    ctx.setInterval(() => refresh(), POLL_MS)

    ctx.registerMany([
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 115, render: () => jsx(Chip, {}) },
      { id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => jsx(Page, { refresh, ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Homelab', codicon: 'pulse' } }
    ])
  }
}
