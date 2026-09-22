import type { BatchSummary } from '../types'
import { SchemaMappingTable } from '../components/SchemaMappingTable'

export function SchemaView({ summary }: { summary: BatchSummary }) {
  const unresolved = Object.keys(summary.schema_report.unresolved_mappings)
  return <div className="space-y-6"><header><h1 className="text-[30px] font-semibold tracking-[-0.03em]">Schema mapping</h1><p className="mt-1.5 text-sm text-[#777]">Review how merchant fields map into the canonical catalog.</p></header><div className="grid gap-4 sm:grid-cols-3"><Summary title="Source changes" value={summary.schema_drift_count} detail="Detected in this batch" tone="amber" /><Summary title="Unresolved" value={unresolved.length} detail={unresolved.length ? unresolved.join(', ') : 'All fields mapped'} tone={unresolved.length ? 'red' : 'green'} /><Summary title="Drift severity" value={summary.schema_drift_severity} detail={`${summary.schema_report.unexpected_columns.length} unexpected source fields`} tone="blue" /></div><div><div className="mb-3"><h2 className="text-lg font-semibold">Field mappings</h2><p className="mt-1 text-sm text-[#777]">Select any row to inspect its profile evidence.</p></div><SchemaMappingTable summary={summary} /></div></div>
}

function Summary({ title, value, detail, tone }: { title: string; value: string | number; detail: string; tone: 'red' | 'amber' | 'blue' | 'green' }) {
  const classes = tone === 'red' ? 'bg-red-50 text-red-700' : tone === 'amber' ? 'bg-amber-50 text-amber-800' : tone === 'green' ? 'bg-emerald-50 text-emerald-700' : 'bg-blue-50 text-blue-700'
  return <div className="rounded-xl border border-[#e3e3e5] bg-white p-4"><div className="flex items-center justify-between"><p className="text-sm font-medium">{title}</p><span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${classes}`}>{value}</span></div><p className="mt-3 truncate text-xs text-[#888]" title={detail}>{detail}</p></div>
}
