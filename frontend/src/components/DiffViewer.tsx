import type { RecordItem } from '../types'

function text(value: unknown) { return value == null || value === '' ? 'Not provided' : String(value) }

export function DiffViewer({ record }: { record: RecordItem }) {
  const rows = [
    ['Product', record.original_product_name, record.cleaned_product_name],
    ['Category', record.original_category, record.cleaned_category],
    ['Price', record.original_price, record.cleaned_price != null ? `${record.cleaned_currency ?? ''} ${record.cleaned_price.toFixed(2)}` : null],
    ['Inventory', record.original_inventory, record.cleaned_inventory],
    ['Tags', record.original_tags, record.cleaned_tags],
  ]
  return <div className="overflow-hidden rounded-xl border border-[#e6e6e8]"><div className="grid grid-cols-[100px_1fr_32px_1fr] bg-[#fafafa] px-4 py-2.5 text-[11px] font-medium text-[#888]"><span>Field</span><span>Original</span><span /><span>Normalized</span></div>{rows.map(([label, before, after]) => <div key={String(label)} className="grid grid-cols-[100px_1fr_32px_1fr] items-start border-t border-[#eeeeef] px-4 py-3 text-xs"><span className="font-medium text-[#777]">{label}</span><span className="break-words text-[#777]">{text(before)}</span><span className="text-[#bbb]">→</span><span className="break-words font-medium text-[#222]">{text(after)}</span></div>)}</div>
}
