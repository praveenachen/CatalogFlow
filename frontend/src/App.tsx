import { useEffect, useState } from 'react'
import { AppShell } from './components/AppShell'
import { Icon } from './components/Icon'
import { UploadModal } from './components/UploadModal'
import { downloadExport, errorMessage, loadWorkspace, refreshRun, saveReview, uploadCatalog } from './api/client'
import type { BatchSummary, ProcessingRun, RecordItem, ReviewPatch, ViewId } from './types'
import { OverviewView } from './views/OverviewView'
import { BatchesView } from './views/BatchesView'
import { PublishView } from './views/PublishView'
import { RecordsView } from './views/RecordsView'
import { ReviewView } from './views/ReviewView'
import { SchemaView } from './views/SchemaView'

type Notice = { type: 'success' | 'error'; message: string }

export default function App() {
  const [view, setView] = useState<ViewId>('overview')
  const [summary, setSummary] = useState<BatchSummary | null>(null)
  const [records, setRecords] = useState<RecordItem[]>([])
  const [reviewQueue, setReviewQueue] = useState<RecordItem[]>([])
  const [run, setRun] = useState<ProcessingRun | null>(null)
  const [selected, setSelected] = useState<RecordItem | null>(null)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [pageError, setPageError] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  const notify = (message: string, type: Notice['type'] = 'success') => {
    setNotice({ message, type })
    window.setTimeout(() => setNotice(null), 4500)
  }

  const reload = async (preferredRecordId?: number) => {
    const workspace = await loadWorkspace()
    if (!workspace) {
      setSummary(null); setRecords([]); setReviewQueue([]); setRun(null); setSelected(null)
      return
    }
    setSummary(workspace.summary)
    setRecords(workspace.records)
    setReviewQueue(workspace.reviewQueue)
    setRun(workspace.run)
    const desired = preferredRecordId ? workspace.reviewQueue.find((item) => item.id === preferredRecordId) : null
    setSelected(desired ?? workspace.reviewQueue[0] ?? null)
  }

  useEffect(() => {
    reload().catch((error) => setPageError(errorMessage(error))).finally(() => setLoading(false))
  }, [])

  const handleUpload = async (file: File, currency?: string) => {
    setBusy(true); setPageError(null)
    try {
      await uploadCatalog(file, currency)
      await reload()
      setView('overview'); setUploadOpen(false)
      notify('Batch ingested. Quality workspace refreshed.')
    } catch (error) { setPageError(errorMessage(error)) }
    finally { setBusy(false) }
  }

  const handleReview = async (record: RecordItem, patch: ReviewPatch) => {
    setBusy(true); setReviewError(null)
    try {
      await saveReview(record.id, patch)
      await reload(record.id)
      notify(patch.decision === 'rejected' ? 'Record rejected and held from publication.' : 'Review decision saved; publication metrics recalculated.')
    } catch (error) { setReviewError(errorMessage(error)) }
    finally { setBusy(false) }
  }

  const handleExport = async (path: string, filename: string) => {
    if (!summary) return
    try { await downloadExport(path, filename, summary.batch_id); notify(`${filename} generated.`) }
    catch (error) { notify(errorMessage(error), 'error') }
  }

  const handleRefreshRun = async () => {
    if (!summary?.run_id) return
    setBusy(true)
    try { setRun(await refreshRun(summary.run_id)); await reload(selected?.id); notify('Processing state refreshed.') }
    catch (error) { notify(errorMessage(error), 'error') }
    finally { setBusy(false) }
  }

  const openReview = (record: RecordItem) => { setSelected(record); setReviewError(null); setView('review') }

  return <AppShell active={view} onNavigate={(next) => { setView(next); setReviewError(null) }} onUpload={() => setUploadOpen(true)} summary={summary}>

    {pageError ? <div role="alert" className="mb-4 flex items-start justify-between gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900"><span><strong>Workspace error:</strong> {pageError}</span><button onClick={() => setPageError(null)} aria-label="Dismiss error"><Icon name="x" /></button></div> : null}

    {loading ? <StatePanel title="Loading workspace" detail="Reading the latest batch and processing state…" />
      : !summary ? <StatePanel title="No batch loaded" detail="Choose the included sample CSV or another merchant catalog, then ingest it to begin profiling and quality review." />
        : view === 'overview' ? <OverviewView summary={summary} records={records} run={run} onNavigate={setView} onUpload={() => setUploadOpen(true)} onRefreshRun={handleRefreshRun} />
          : view === 'batches' ? <BatchesView summary={summary} run={run} />
          : view === 'schema' ? <SchemaView summary={summary} />
            : view === 'records' ? <RecordsView records={records} onReview={openReview} />
              : view === 'review' ? <ReviewView queue={reviewQueue} records={records} selected={selected} busy={busy} error={reviewError} onSelect={(record) => { setSelected(record); setReviewError(null) }} onSave={handleReview} />
                : <PublishView summary={summary} onExport={handleExport} onReview={() => setView('review')} />}

    {notice ? <div role="status" className={`fixed bottom-5 right-5 z-50 max-w-sm rounded-lg px-4 py-3 text-xs font-medium text-white shadow-xl ${notice.type === 'success' ? 'bg-[#24653b]' : 'bg-[#9a382a]'}`}>{notice.message}</div> : null}
    <UploadModal open={uploadOpen} busy={busy} onClose={() => !busy && setUploadOpen(false)} onSubmit={handleUpload} />
  </AppShell>
}

function StatePanel({ title, detail }: { title: string; detail: string }) {
  return <div className="grid min-h-[520px] place-items-center rounded-xl border border-[#e3e3e5] bg-white p-8 text-center"><div className="max-w-md"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[#171717] text-sm font-bold text-white">CF</div><h1 className="mt-4 text-xl font-semibold">{title}</h1><p className="mt-2 text-sm leading-6 text-[#777]">{detail}</p></div></div>
}
