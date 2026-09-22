import type { RecordItem } from '../types'
import { formatConfidence } from '../utils/format'
import { uniqueIssueReasons } from '../utils/issues'
import { Icon } from './Icon'
import { RecordStatus } from './StatusBadge'

function value(input: unknown) { return input == null || input === '' ? 'Not provided' : String(input) }

export function RecordDrawer({ record, onClose, onReview }: { record: RecordItem | null; onClose: () => void; onReview: (record: RecordItem) => void }) {
  if (!record) return null
  const issues = uniqueIssueReasons(record.issue_reasons)
  const pairs = [
    ['Product', record.original_product_name, record.cleaned_product_name],
    ['Category', record.original_category, record.cleaned_category],
    ['Price', record.original_price, record.cleaned_price != null ? `${record.cleaned_currency ?? ''} ${record.cleaned_price.toFixed(2)}` : null],
    ['Inventory', record.original_inventory, record.cleaned_inventory],
    ['Tags', record.original_tags, record.cleaned_tags],
  ]
  return <div className="fixed inset-0 z-[70]" role="dialog" aria-modal="true" aria-label="Record details">
    <button className="absolute inset-0 bg-black/20 backdrop-blur-[1px]" onClick={onClose} aria-label="Close record details" />
    <aside className="absolute inset-y-0 right-0 flex w-full max-w-[520px] flex-col border-l border-[#dedee1] bg-white shadow-2xl">
      <header className="flex items-start justify-between border-b border-[#ececee] px-6 py-5"><div className="min-w-0 pr-4"><p className="font-mono text-xs text-[#999]">{record.sku ?? 'NO-SKU'} · Record {record.id}</p><h2 className="mt-1.5 truncate text-xl font-semibold tracking-[-0.02em]">{record.cleaned_product_name || 'Unnamed product'}</h2><div className="mt-3"><RecordStatus record={record} /></div></div><button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-[#777] hover:bg-[#f2f2f3]" aria-label="Close"><Icon name="x" className="h-4 w-4" /></button></header>
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <section><h3 className="section-label">Overview</h3><dl className="mt-3 grid grid-cols-2 gap-3"><Fact label="Automation confidence" value={formatConfidence(record.automation_confidence, 1)} /><Fact label="Review decision" value={record.review_status.replace(/_/g, ' ')} /><Fact label="Category" value={value(record.cleaned_category)} /><Fact label="Price" value={record.cleaned_price != null ? `${record.cleaned_currency ?? ''} ${record.cleaned_price.toFixed(2)}` : 'Not provided'} /><Fact label="Inventory" value={value(record.cleaned_inventory)} /><Fact label="Export policy" value={record.exportable ? 'Publishable' : 'Excluded'} /></dl></section>
        <section className="mt-7"><h3 className="section-label">Source and normalized values</h3><div className="mt-3 overflow-hidden rounded-xl border border-[#e7e7e9]"><div className="grid grid-cols-[90px_1fr_1fr] bg-[#fafafa] px-3 py-2 text-[11px] font-medium text-[#888]"><span>Field</span><span>Original</span><span>Normalized</span></div>{pairs.map(([label, original, normalized]) => <div key={String(label)} className="grid grid-cols-[90px_1fr_1fr] gap-2 border-t border-[#eeeeef] px-3 py-3 text-xs"><span className="font-medium text-[#777]">{label}</span><span className="break-words text-[#777]">{value(original)}</span><span className="break-words font-medium text-[#222]">{value(normalized)}</span></div>)}</div></section>
        <section className="mt-7"><h3 className="section-label">Issues</h3><div className="mt-3 space-y-2">{issues.length ? issues.map((issue) => <div key={issue} className="rounded-lg bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">{issue}</div>) : <p className="text-sm text-[#777]">No unresolved issues.</p>}</div></section>
        <details className="mt-7 border-t border-[#ececee] pt-4"><summary className="cursor-pointer text-sm font-medium">Confidence breakdown</summary><div className="mt-4 space-y-4">{Object.entries(record.quality_components).map(([name, item]) => <div key={name}><div className="flex justify-between text-xs"><span className="capitalize text-[#666]">{name.replace(/_/g, ' ')}</span><span className="font-medium">{Math.round(item.score * 100)}%</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#ececee]"><div className="h-full rounded-full bg-blue-500" style={{ width: `${item.score * 100}%` }} /></div></div>)}</div></details>
        <details className="mt-4 border-t border-[#ececee] pt-4"><summary className="cursor-pointer text-sm font-medium">Source metadata and transformations</summary><div className="mt-3 space-y-2">{record.normalization_trace.map((trace) => <div key={`${trace.field}-${trace.rule}`} className="rounded-lg bg-[#f7f7f8] p-3 text-xs"><div className="flex justify-between"><span className="font-medium capitalize">{trace.field}</span><span className="text-[#888]">{Math.round(trace.certainty * 100)}%</span></div><p className="mt-1 text-[#777]">{trace.rule.replace(/_/g, ' ')}</p></div>)}</div></details>
      </div>
      {!record.exportable && record.review_status !== 'rejected' ? <footer className="border-t border-[#e7e7e9] p-5"><button onClick={() => onReview(record)} className="action-primary w-full">Open in review</button></footer> : null}
    </aside>
  </div>
}

function Fact({ label, value: factValue }: { label: string; value: string }) { return <div className="rounded-lg bg-[#f7f7f8] p-3"><dt className="text-[11px] text-[#888]">{label}</dt><dd className="mt-1 text-sm font-medium">{factValue}</dd></div> }
