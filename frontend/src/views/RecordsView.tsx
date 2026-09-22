import { useState } from 'react'
import type { RecordItem } from '../types'
import { RecordDrawer } from '../components/RecordDrawer'
import { RecordsGrid } from '../components/RecordsGrid'

export function RecordsView({ records, onReview }: { records: RecordItem[]; onReview: (record: RecordItem) => void }) {
  const [selected, setSelected] = useState<RecordItem | null>(null)
  return <div><header className="mb-6"><h1 className="text-[30px] font-semibold tracking-[-0.03em]">Processed records</h1><p className="mt-1.5 text-sm text-[#777]">Explore every normalized row and inspect its source, quality, and review state.</p></header><RecordsGrid records={records} onSelect={setSelected} /><RecordDrawer record={selected} onClose={() => setSelected(null)} onReview={(record) => { setSelected(null); onReview(record) }} /></div>
}
