import type { BatchSummary, ViewId } from '../types'
import { Icon } from './Icon'

type Stage = { label: string; view: ViewId; signal: (summary: BatchSummary) => string; warning?: (summary: BatchSummary) => boolean }

const stages: Stage[] = [
  { label: 'Ingest', view: 'overview', signal: (s) => `${s.total_records} rows` },
  { label: 'Profile', view: 'schema', signal: (s) => `${s.schema_report.profiles.length} columns` },
  { label: 'Map', view: 'schema', signal: (s) => `${s.mappings.filter((m) => m.auto_applied).length} applied`, warning: (s) => s.mappings.some((m) => !m.auto_applied) },
  { label: 'Validate', view: 'records', signal: (s) => `${s.invalid_count} invalid`, warning: (s) => s.invalid_count > 0 },
  { label: 'Normalize', view: 'records', signal: (s) => `${s.total_records} shaped` },
  { label: 'Match', view: 'records', signal: (s) => `${s.duplicate_count} duplicate`, warning: (s) => s.duplicate_count > 0 },
  { label: 'Review', view: 'review', signal: (s) => `${s.attention_count} open`, warning: (s) => s.attention_count > 0 },
  { label: 'Publish', view: 'publish', signal: (s) => `${s.publishable_count} ready` },
]

export function PipelineRail({ summary, onNavigate }: { summary: BatchSummary; onNavigate: (view: ViewId) => void }) {
  const pending = !['COMPLETED', 'completed'].includes(summary.processing_status ?? summary.status)
  return <section className="overflow-x-auto rounded-xl border border-[#e3e3e5] bg-white" aria-label="Processing pipeline">
    <div className="flex min-w-[900px] px-3 py-5">
      {stages.map((stage, index) => {
        const warning = stage.warning?.(summary) ?? false
        return <button key={stage.label} onClick={() => onNavigate(stage.view)} className="group relative flex min-w-0 flex-1 flex-col items-center px-2 text-center focus:outline-none">
          {index < stages.length - 1 ? <span className="absolute left-[calc(50%+16px)] right-[calc(-50%+16px)] top-[15px] h-px bg-[#e2e2e4]" /> : null}
          <span className={`relative z-10 grid h-8 w-8 place-items-center rounded-full border text-xs font-semibold transition group-hover:scale-105 ${pending ? 'border-[#d9d9dc] bg-white text-[#888]' : warning ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
            {pending ? index + 1 : warning ? '!' : <Icon name="check" className="h-4 w-4" />}
          </span>
          <span className="mt-3 text-[13px] font-medium text-[#303030]">{stage.label}</span>
          <span className="mt-0.5 max-w-full truncate text-[11px] text-[#929292]">{pending ? 'Pending' : stage.signal(summary)}</span>
        </button>
      })}
    </div>
  </section>
}
