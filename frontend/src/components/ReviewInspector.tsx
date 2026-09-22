import { useEffect, useMemo, useState } from 'react'
import type { RecordItem, ReviewDecision, ReviewPatch } from '../types'
import { confidencePercent, formatConfidence } from '../utils/format'
import { uniqueIssueReasons } from '../utils/issues'
import { DiffViewer } from './DiffViewer'
import { StatusBadge } from './StatusBadge'

type FormState = Record<'cleaned_product_name' | 'cleaned_description' | 'cleaned_category' | 'cleaned_price' | 'cleaned_currency' | 'cleaned_inventory' | 'cleaned_tags', string>

export function ReviewInspector({ record, records, busy, error, onSave }: { record: RecordItem | null; records: RecordItem[]; busy: boolean; error: string | null; onSave: (record: RecordItem, patch: ReviewPatch) => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>({ cleaned_product_name: '', cleaned_description: '', cleaned_category: '', cleaned_price: '', cleaned_currency: '', cleaned_inventory: '', cleaned_tags: '' })
  useEffect(() => { if (record) { setForm({ cleaned_product_name: record.cleaned_product_name ?? '', cleaned_description: record.cleaned_description ?? '', cleaned_category: record.cleaned_category ?? '', cleaned_price: record.cleaned_price?.toString() ?? '', cleaned_currency: record.cleaned_currency ?? '', cleaned_inventory: record.cleaned_inventory?.toString() ?? '', cleaned_tags: record.cleaned_tags ?? '' }); setEditing(false); setFormError(null) } }, [record])
  const duplicate = useMemo(() => record?.duplicate_of_record_id ? records.find((item) => item.id === record.duplicate_of_record_id) : null, [record, records])
  if (!record) return <div className="grid min-h-[620px] place-items-center rounded-xl border border-[#e3e3e5] bg-white p-8 text-center"><div><p className="text-base font-medium">Select a record</p><p className="mt-2 text-sm text-[#777]">Choose a flagged row to inspect its transformations and quality evidence.</p></div></div>
  const submit = async (decision: ReviewDecision) => {
    setFormError(null)
    const patch: ReviewPatch = { decision }
    if (editing) {
      const price = Number(form.cleaned_price)
      const inventory = Number(form.cleaned_inventory)
      const currency = form.cleaned_currency.trim().toUpperCase()
      if (form.cleaned_price !== '' && (!Number.isFinite(price) || price < 0)) { setFormError('Price must be 0 or greater.'); return }
      if (form.cleaned_inventory !== '' && (!Number.isInteger(inventory) || inventory < 0)) { setFormError('Inventory must be a whole number of 0 or greater.'); return }
      if (currency && !/^[A-Z]{3}$/.test(currency)) { setFormError('Currency must be a three-letter code such as USD.'); return }
      Object.assign(patch, { cleaned_product_name: form.cleaned_product_name, cleaned_description: form.cleaned_description, cleaned_category: form.cleaned_category, cleaned_currency: currency, cleaned_tags: form.cleaned_tags, ...(form.cleaned_price !== '' ? { cleaned_price: price } : {}), ...(form.cleaned_inventory !== '' ? { cleaned_inventory: inventory } : {}) })
    }
    await onSave(record, patch)
  }
  const issues = uniqueIssueReasons(record.issue_reasons)
  return <article className="overflow-hidden rounded-xl border border-[#e3e3e5] bg-white">
    <header className="flex items-start justify-between gap-3 border-b border-[#ececee] p-5"><div className="min-w-0"><p className="font-mono text-xs text-[#999]">{record.sku ?? 'NO-SKU'} · Record {record.id}</p><h2 className="mt-1.5 truncate text-xl font-semibold tracking-[-0.02em]">{record.cleaned_product_name || 'Unnamed product'}</h2></div><div className="flex flex-col items-end gap-2"><StatusBadge status={record.status} /><span className="text-xs font-medium text-[#777]">{formatConfidence(record.automation_confidence, 1)} confidence</span></div></header>
    <div className="space-y-6 p-5">
      <section><h3 className="section-label">Why this needs attention</h3><div className="mt-3 space-y-2">{issues.map((issue) => <p key={issue} className="rounded-lg bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-900">{issue}</p>)}{!issues.length ? <p className="text-sm text-[#777]">No unresolved issues.</p> : null}</div></section>
      <section><h3 className="section-label">Original and normalized</h3><div className="mt-3"><DiffViewer record={record} /></div></section>
      {editing ? <section><h3 className="section-label">Correction editor</h3><div className="mt-3 grid gap-3 sm:grid-cols-2">{Object.entries(form).map(([key, inputValue]) => <label key={key} className={key === 'cleaned_description' || key === 'cleaned_tags' ? 'sm:col-span-2' : ''}><span className="text-xs font-medium capitalize text-[#666]">{key.replace('cleaned_', '').replace('_', ' ')}</span><input value={inputValue} onChange={(event) => { setForm({ ...form, [key]: event.target.value }); setFormError(null) }} type={key === 'cleaned_price' || key === 'cleaned_inventory' ? 'number' : 'text'} min={key === 'cleaned_price' || key === 'cleaned_inventory' ? 0 : undefined} step={key === 'cleaned_inventory' ? 1 : key === 'cleaned_price' ? 0.01 : undefined} className="mt-1.5 h-10 w-full rounded-lg border border-[#dedee1] bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10" /></label>)}</div></section> : null}
      {duplicate ? <section><h3 className="section-label">Duplicate comparison</h3><div className="mt-3 grid overflow-hidden rounded-xl border border-indigo-100 bg-indigo-50/40 sm:grid-cols-2"><div className="border-b border-indigo-100 p-4 sm:border-b-0 sm:border-r"><p className="text-xs text-indigo-600">Existing candidate</p><p className="mt-1 font-medium">{duplicate.cleaned_product_name}</p><p className="mt-1 font-mono text-xs text-[#777]">{duplicate.sku}</p></div><div className="p-4"><p className="text-xs text-indigo-600">Current record</p><p className="mt-1 font-medium">{record.cleaned_product_name}</p><p className="mt-1 font-mono text-xs text-[#777]">{record.sku}</p></div><div className="border-t border-indigo-100 px-4 py-3 text-xs text-indigo-800 sm:col-span-2">{record.duplicate_method?.replace(/_/g, ' ')} · {Math.round((record.duplicate_confidence ?? 0) * 100)}% similarity</div></div></section> : null}
      <details className="border-t border-[#ececee] pt-4"><summary className="cursor-pointer text-sm font-medium">Confidence breakdown · {formatConfidence(record.automation_confidence, 1)}</summary><div className="mt-4 space-y-4">{Object.entries(record.quality_components).map(([name, item]) => <div key={name}><div className="flex justify-between text-xs"><span className="capitalize text-[#666]">{name.replace(/_/g, ' ')}</span><span className="font-medium">{formatConfidence(item.score)}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#ececee]"><div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, confidencePercent(item.score))}%` }} /></div>{item.reasons.length ? <p className="mt-1.5 text-xs text-[#888]">{item.reasons.join(' · ')}</p> : null}</div>)}</div></details>
      <details className="border-t border-[#ececee] pt-4"><summary className="cursor-pointer text-sm font-medium">Source metadata and transformation trace</summary><div className="mt-3 grid gap-2 sm:grid-cols-2">{record.normalization_trace.map((trace) => <div key={`${trace.field}-${trace.rule}`} className="rounded-lg bg-[#f7f7f8] p-3 text-xs"><div className="flex justify-between"><span className="font-medium capitalize">{trace.field}</span><span className="text-[#888]">{Math.round(trace.certainty * 100)}%</span></div><p className="mt-1 text-[#777]">{trace.rule.replace(/_/g, ' ')}</p></div>)}</div></details>
      {formError || error ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800"><strong>Cannot complete review:</strong> {formError ?? error}</div> : null}
      <div className="flex flex-wrap gap-2 border-t border-[#ececee] pt-5"><button disabled={busy} onClick={() => submit(editing ? 'edited' : 'approved')} className="action-primary">{busy ? 'Saving…' : editing ? 'Save correction' : record.status === 'Duplicate' ? 'Keep separate' : 'Approve'}</button><button disabled={busy} onClick={() => { setEditing((current) => !current); setFormError(null) }} className="action-secondary">{editing ? 'Cancel edit' : 'Edit values'}</button><button disabled={busy} onClick={() => submit('rejected')} className="action-danger">Reject</button></div>
    </div>
  </article>
}
