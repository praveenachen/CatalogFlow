import { useMemo, useState } from 'react'
import type { RecordItem } from '../types'
import { Icon } from './Icon'
import { ReviewStatusBadge, StatusBadge } from './StatusBadge'
import { uniqueIssueReasons } from '../utils/issues'

export function RecordsGrid({ records, onSelect, compact = false }: { records: RecordItem[]; onSelect?: (record: RecordItem) => void; compact?: boolean }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('All')
  const [attentionOnly, setAttentionOnly] = useState(false)
  const filtered = useMemo(() => records.filter((record) => {
    const text = [record.cleaned_product_name, record.sku, record.cleaned_category].join(' ').toLowerCase()
    const needsAttention = !record.exportable && record.review_status !== 'rejected'
    return text.includes(query.toLowerCase()) && (status === 'All' || record.status === status) && (!attentionOnly || needsAttention)
  }), [records, query, status, attentionOnly])

  return <section className="overflow-hidden rounded-xl border border-[#e3e3e5] bg-white">
    <div className="flex flex-col gap-3 border-b border-[#ececee] p-4 md:flex-row md:items-center md:justify-between">
      <p className="text-sm text-[#777]"><span className="font-medium text-[#333]">{filtered.length}</span> of {records.length} processed records</p>
      <div className="flex flex-wrap gap-2">
        <label className="flex h-9 min-w-64 items-center gap-2 rounded-lg border border-[#dedee1] bg-white px-3 text-sm focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/10"><Icon name="search" className="h-4 w-4 text-[#999]" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search products, SKUs, categories" className="min-w-0 flex-1 bg-transparent outline-none" /></label>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="h-9 rounded-lg border border-[#dedee1] bg-white px-3 text-sm outline-none focus:border-blue-500" aria-label="Automation status filter"><option>All</option><option>Auto-approved</option><option>Needs Review</option><option>Duplicate</option><option>Invalid</option></select>
        <button onClick={() => setAttentionOnly((current) => !current)} className={`flex h-9 items-center gap-2 rounded-lg border px-3 text-sm font-medium ${attentionOnly ? 'border-amber-200 bg-amber-50 text-amber-800' : 'border-[#dedee1] bg-white text-[#666] hover:bg-[#f7f7f8]'}`}><Icon name="filter" className="h-4 w-4" />Attention</button>
      </div>
    </div>
    <div className={`overflow-auto ${compact ? 'max-h-[360px]' : 'max-h-[calc(100vh-250px)] min-h-[440px]'}`}>
      <table className="w-full min-w-[1040px] border-collapse text-left text-sm">
        <thead className="sticky top-0 z-10 bg-[#fafafa] text-xs font-medium text-[#777]"><tr><th className="px-5 py-3">Product</th><th className="px-4 py-3">Category</th><th className="px-4 py-3">Price</th><th className="px-4 py-3">Stock</th><th className="px-4 py-3">Confidence</th><th className="px-4 py-3">Automation</th><th className="px-4 py-3">Review</th><th className="px-5 py-3 text-right">Issues</th></tr></thead>
        <tbody className="divide-y divide-[#eeeeef]">{filtered.map((record) => { const issueCount = uniqueIssueReasons(record.issue_reasons).length; return <tr key={record.id} onClick={() => onSelect?.(record)} className={`${onSelect ? 'cursor-pointer' : ''} h-16 transition hover:bg-[#fafafa]`}><td className="max-w-[260px] px-5 py-3"><p className="truncate font-medium text-[#222]">{record.cleaned_product_name || 'Unnamed product'}</p><p className="mt-1 font-mono text-[11px] text-[#999]">{record.sku || 'NO-SKU'}</p></td><td className="px-4 py-3 text-[#666]">{record.cleaned_category || '—'}</td><td className="px-4 py-3 font-medium">{record.cleaned_price != null ? `${record.cleaned_currency ?? ''} ${record.cleaned_price.toFixed(2)}` : '—'}</td><td className="px-4 py-3 text-[#666]">{record.cleaned_inventory ?? '—'}</td><td className="px-4 py-3"><div className="flex items-center gap-2"><div className="h-1.5 w-16 overflow-hidden rounded-full bg-[#e9e9eb]"><div className="h-full rounded-full bg-blue-500" style={{ width: `${record.confidence_score}%` }} /></div><span className="text-xs font-medium">{record.confidence_score.toFixed(0)}%</span></div></td><td className="px-4 py-3"><StatusBadge status={record.status} /></td><td className="px-4 py-3"><ReviewStatusBadge record={record} /></td><td className="px-5 py-3 text-right"><span className={issueCount ? 'font-medium text-red-600' : 'text-[#aaa]'}>{issueCount}</span></td></tr> })}</tbody>
      </table>
      {!filtered.length ? <div className="grid h-44 place-items-center text-sm text-[#777]">No records match the current filters.</div> : null}
    </div>
  </section>
}
