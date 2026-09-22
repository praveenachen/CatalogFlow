import type { RecordItem } from '../types'

const styles: Record<string, string> = {
  'Auto-approved': 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
  'Needs Review': 'bg-amber-50 text-amber-800 ring-amber-600/15',
  Duplicate: 'bg-indigo-50 text-indigo-700 ring-indigo-600/15',
  Invalid: 'bg-red-50 text-red-700 ring-red-600/15',
  'Human-approved': 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
  'Human-edited': 'bg-blue-50 text-blue-700 ring-blue-600/15',
  Rejected: 'bg-[#f2f2f3] text-[#666] ring-black/10',
  'Needs correction': 'bg-red-50 text-red-700 ring-red-600/15',
  'Not required': 'bg-[#f4f4f5] text-[#777] ring-black/10',
  'Pending review': 'bg-amber-50 text-amber-800 ring-amber-600/15',
  COMPLETED: 'bg-emerald-50 text-emerald-700 ring-emerald-600/15',
  RUNNING: 'bg-blue-50 text-blue-700 ring-blue-600/15',
  SUBMITTED: 'bg-blue-50 text-blue-700 ring-blue-600/15',
  PENDING: 'bg-amber-50 text-amber-800 ring-amber-600/15',
  FAILED: 'bg-red-50 text-red-700 ring-red-600/15',
  CANCELLED: 'bg-[#f2f2f3] text-[#666] ring-black/10',
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ring-inset ${styles[status] ?? styles.PENDING}`}>{status.replace('_', ' ')}</span>
}

export function RecordStatus({ record }: { record: RecordItem }) {
  const label = record.review_status === 'edited' && record.exportable
    ? 'Human-edited'
    : record.review_status === 'approved' && record.exportable
      ? 'Human-approved'
      : record.review_status === 'rejected'
        ? 'Rejected'
        : record.reviewed && !record.exportable
          ? 'Needs correction'
          : record.status
  return <StatusBadge status={label} />
}

export function ReviewStatusBadge({ record }: { record: RecordItem }) {
  const label = record.review_status === 'not_required'
    ? 'Not required'
    : record.review_status === 'approved'
      ? 'Human-approved'
      : record.review_status === 'edited'
        ? record.exportable ? 'Human-edited' : 'Needs correction'
        : record.review_status === 'rejected'
          ? 'Rejected'
          : 'Pending review'
  return <StatusBadge status={label} />
}
