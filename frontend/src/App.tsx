import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'

type RecordItem = {
  id: number
  batch_id: number
  original_product_name?: string
  original_category?: string
  original_price?: string
  original_inventory?: string
  original_tags?: string
  cleaned_product_name?: string
  cleaned_category?: string
  cleaned_price?: number
  cleaned_inventory?: number
  cleaned_tags?: string
  confidence_score: number
  automation_confidence: number
  status: string
  recommended_action: string
  issue_reasons: string[]
  severity: string
  review_status: string
  reviewer_decision?: string
  reviewed: boolean
  exportable: boolean
}

type UploadSummary = {
  upload_id: number
  batch_id: number
  filename: string
  total_records: number
  auto_approved_count: number
  needs_review_count: number
  duplicate_count: number
  invalid_count: number
  attention_count: number
  publishable_count: number
  average_confidence: number
  schema_drift_detected: boolean
  schema_report: {
    missing_columns: string[]
    unexpected_columns: string[]
    suggested_mappings: Record<string, string>
    auto_applied_mappings: Record<string, string>
    unresolved_mappings: Record<string, string>
    drift_severity: string
  }
}

type IconName =
  | 'alert'
  | 'archive'
  | 'barChart'
  | 'check'
  | 'chevronLeft'
  | 'download'
  | 'file'
  | 'filter'
  | 'layers'
  | 'menu'
  | 'package'
  | 'search'
  | 'shield'
  | 'spark'
  | 'upload'
  | 'x'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [summary, setSummary] = useState<UploadSummary | null>(null)
  const [catalog, setCatalog] = useState<RecordItem[]>([])
  const [reviewQueue, setReviewQueue] = useState<RecordItem[]>([])
  const [driftReport, setDriftReport] = useState<UploadSummary['schema_report'] | null>(null)
  const [statusFilter, setStatusFilter] = useState('All')
  const [searchText, setSearchText] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [editingRecord, setEditingRecord] = useState<RecordItem | null>(null)
  const [formState, setFormState] = useState({ cleaned_category: '', cleaned_price: '', cleaned_inventory: '', cleaned_tags: '' })

  const filteredCatalog = useMemo(() => {
    return catalog.filter((record) => {
      const statusMatch = statusFilter === 'All' || record.status === statusFilter
      const searchMatch = [record.cleaned_product_name, record.cleaned_category]
        .join(' ')
        .toLowerCase()
        .includes(searchText.toLowerCase())
      return statusMatch && searchMatch
    })
  }, [catalog, searchText, statusFilter])

  const exportableCount = summary?.publishable_count ?? catalog.filter((record) => record.exportable).length

  const fetchData = async () => {
    try {
      let latest: UploadSummary | null = null
      try {
        latest = (await axios.get<UploadSummary>(`${API_BASE}/latest-batch`)).data
      } catch (error) {
        if (!axios.isAxiosError(error) || error.response?.status !== 404) throw error
      }
      if (!latest) {
        setSummary(null)
        setCatalog([])
        setReviewQueue([])
        setDriftReport(null)
        return
      }
      const [catalogRes, reviewRes, driftRes] = await Promise.all([
        axios.get<RecordItem[]>(`${API_BASE}/processed-records`, { params: { batch_id: latest.batch_id } }),
        axios.get<RecordItem[]>(`${API_BASE}/review-queue`, { params: { batch_id: latest.batch_id } }),
        axios.get<UploadSummary['schema_report']>(`${API_BASE}/schema-drift-report`, { params: { batch_id: latest.batch_id } }),
      ])
      setSummary(latest)
      setCatalog(catalogRes.data)
      setReviewQueue(reviewRes.data)
      setDriftReport(driftRes.data)
    } catch (error) {
      console.error(error)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    setToast({ message, type })
    window.setTimeout(() => setToast(null), 4000)
  }

  const handleUpload = async () => {
    if (!file) return
    setLoading(true)
    const form = new FormData()
    form.append('file', file)

    try {
      const response = await axios.post<UploadSummary>(`${API_BASE}/upload-catalog`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setSummary(response.data)
      setDriftReport(response.data.schema_report)
      await fetchData()
      showToast('Catalog uploaded and normalized successfully.')
    } catch (error) {
      console.error(error)
      showToast('Upload failed. Please check the CSV and try again.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async (path: string, filename: string) => {
    try {
      const response = await axios.get(`${API_BASE}${path}`, {
        responseType: 'blob',
        params: summary?.batch_id ? { batch_id: summary.batch_id } : undefined,
      })
      const blob = new Blob([response.data], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.click()
      URL.revokeObjectURL(url)
      showToast(`${filename} generated.`)
    } catch (error) {
      console.error(error)
      showToast('Unable to export CSV.', 'error')
    }
  }

  const openEditor = (record: RecordItem) => {
    setEditingRecord(record)
    setFormState({
      cleaned_category: record.cleaned_category ?? '',
      cleaned_price: record.cleaned_price?.toString() ?? '',
      cleaned_inventory: record.cleaned_inventory?.toString() ?? '',
      cleaned_tags: record.cleaned_tags ?? '',
    })
  }

  const saveReview = async () => {
    if (!editingRecord) return
    setLoading(true)
    try {
      const payload: Record<string, unknown> = {
        cleaned_category: formState.cleaned_category,
        cleaned_tags: formState.cleaned_tags,
        mark_reviewed: true,
      }
      if (formState.cleaned_price !== '') {
        payload.cleaned_price = parseFloat(formState.cleaned_price)
      }
      if (formState.cleaned_inventory !== '') {
        payload.cleaned_inventory = parseInt(formState.cleaned_inventory, 10)
      }
      await axios.put(`${API_BASE}/review-queue/${editingRecord.id}`, payload)
      setEditingRecord(null)
      await fetchData()
      showToast('Record updated and moved toward export.')
    } catch (error) {
      console.error(error)
      showToast('Unable to save review updates.', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <div className="flex min-h-screen">
        <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen((value) => !value)} />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onToggleSidebar={() => setSidebarOpen((value) => !value)} attentionCount={summary?.attention_count ?? reviewQueue.length} />

          <main className="mx-auto w-full max-w-[1480px] flex-1 px-4 py-5 sm:px-6 lg:px-8">
            <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="space-y-5">
                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px] lg:items-center">
                    <div>
                      <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold uppercase text-emerald-800">
                        <Icon name="spark" className="h-3.5 w-3.5" />
                        CatalogFlow
                      </span>
                      <h1 className="mt-4 max-w-3xl text-3xl font-semibold text-slate-950 sm:text-4xl">
                        Catalog quality control, from upload to export.
                      </h1>
                      <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
                        Normalize supplier CSVs, identify schema drift, score record confidence, and move high-risk items into a focused review workflow.
                      </p>
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <label className="block">
                        <span className="mb-2 block text-sm font-semibold text-slate-800">Upload catalog CSV</span>
                        <input
                          type="file"
                          accept=".csv"
                          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                          className="block w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm outline-none transition file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100"
                        />
                      </label>
                      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
                        <button
                          onClick={handleUpload}
                          disabled={!file || loading}
                          className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-emerald-200/60 transition hover:from-emerald-600 hover:to-teal-700 disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-400"
                        >
                          <Icon name="upload" className="h-4 w-4" />
                          {loading ? 'Processing' : 'Normalize catalog'}
                        </button>
                        <a
                          href="/sample-messy-catalog.csv"
                          className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
                          download
                        >
                          <Icon name="download" className="h-4 w-4" />
                          Sample CSV
                        </a>
                      </div>
                    </div>
                  </div>
                </section>

                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  <StatCard icon="package" label="Total products" value={summary?.total_records ?? catalog.length} bgColor="from-blue-500 to-blue-700" />
                  <StatCard icon="check" label="Auto-approved" value={summary?.auto_approved_count ?? 0} bgColor="from-emerald-500 to-emerald-700" />
                  <StatCard icon="alert" label="Needs review (auto)" value={summary?.needs_review_count ?? 0} bgColor="from-amber-400 to-orange-500" />
                  <StatCard icon="shield" label="Confidence" value={summary?.average_confidence ?? 0} unit="%" bgColor="from-purple-500 to-violet-700" />
                </div>

                <div className="grid gap-4 lg:grid-cols-3">
                  <InsightCard label="Export-ready records" value={exportableCount} tone="teal" />
                  <InsightCard label="Duplicates found" value={summary?.duplicate_count ?? 0} tone="orange" />
                  <InsightCard label="Schema drift" value={summary?.schema_drift_detected ? 'Detected' : 'None'} tone={summary?.schema_drift_detected ? 'rose' : 'emerald'} />
                </div>

                <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
                  <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-lg font-semibold text-slate-950">Processed records</h2>
                      <p className="mt-1 text-sm text-slate-500">All normalized rows for this batch. Only publishable records are included in the cleaned export.</p>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <label className="relative block">
                        <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <input
                          value={searchText}
                          onChange={(event) => setSearchText(event.target.value)}
                          placeholder="Search products"
                          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-3 text-sm text-slate-900 outline-none transition focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-100 sm:w-56"
                        />
                      </label>
                      <label className="relative block">
                        <Icon name="filter" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <select
                          value={statusFilter}
                          onChange={(event) => setStatusFilter(event.target.value)}
                          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-9 pr-8 text-sm text-slate-900 outline-none transition focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-100 sm:w-44"
                        >
                          {['All', 'Auto-approved', 'Needs Review', 'Duplicate', 'Invalid'].map((option) => (
                            <option key={option} value={option}>{option}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                      <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                        <tr>
                          <th className="px-5 py-3 font-semibold">Product</th>
                          <th className="px-5 py-3 font-semibold">Category</th>
                          <th className="px-5 py-3 font-semibold">Price</th>
                          <th className="px-5 py-3 font-semibold">Stock</th>
                          <th className="px-5 py-3 font-semibold">Score</th>
                          <th className="px-5 py-3 font-semibold">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {filteredCatalog.slice(0, 12).map((record) => (
                          <tr key={record.id} className="transition hover:bg-emerald-50/40">
                            <td className="px-5 py-4 font-semibold text-slate-950">{record.cleaned_product_name || record.original_product_name || '-'}</td>
                            <td className="px-5 py-4 text-slate-600">{record.cleaned_category || '-'}</td>
                            <td className="px-5 py-4 font-medium text-slate-700">{record.cleaned_price != null ? `$${record.cleaned_price.toFixed(2)}` : '-'}</td>
                            <td className="px-5 py-4 text-slate-600">{record.cleaned_inventory ?? '-'}</td>
                            <td className="px-5 py-4">
                              <div className="flex items-center gap-2">
                                <div className="h-2 w-20 overflow-hidden rounded-full bg-slate-200">
                                  <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-500" style={{ width: `${record.confidence_score}%` }} />
                                </div>
                                <span className="min-w-10 text-sm font-semibold text-slate-700">{record.confidence_score}%</span>
                              </div>
                            </td>
                            <td className="px-5 py-4">
                              <RecordStatusBadge record={record} />
                            </td>
                          </tr>
                        ))}
                        {filteredCatalog.length === 0 && (
                          <tr>
                            <td colSpan={6} className="px-5 py-10 text-center text-sm text-slate-500">No records match the current filter or search.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  <div className="border-t border-slate-200 bg-slate-50/70 p-5">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                      <div>
                        <h2 className="text-lg font-semibold text-slate-950">Exports</h2>
                        <p className="mt-1 text-sm text-slate-500">Generate CSV outputs for downstream workflows.</p>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-3 lg:min-w-[560px]">
                        <ExportButton label="Cleaned catalog" icon="barChart" onClick={() => handleDownload('/export/cleaned-catalog', 'cleaned-catalog.csv')} bgColor="from-blue-500 to-blue-700" />
                        <ExportButton label="Review report" icon="file" onClick={() => handleDownload('/export/review-report', 'review-report.csv')} bgColor="from-purple-500 to-violet-700" />
                        <ExportButton label="Schema report" icon="layers" onClick={() => handleDownload('/export/schema-drift-report', 'schema-drift-report.csv')} bgColor="from-orange-400 to-orange-600" />
                      </div>
                    </div>
                  </div>
                </section>
              </div>

              <aside className="space-y-5">
                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-semibold text-slate-950">Review queue</h2>
                      <p className="mt-1 text-sm text-slate-500">Records that need attention before export.</p>
                    </div>
                    <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">{reviewQueue.length}</span>
                  </div>
                  <div className="mt-5 space-y-3">
                    {reviewQueue.slice(0, 5).map((record) => (
                      <div key={record.id} className="rounded-lg border border-slate-200 bg-slate-50 p-4 transition hover:border-emerald-300 hover:bg-white">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold text-slate-950">{record.cleaned_product_name || record.original_product_name}</p>
                            <p className="mt-1 text-xs leading-5 text-slate-500">{record.recommended_action}</p>
                          </div>
                          <StatusBadge status={record.status} size="sm" />
                        </div>
                        <div className="mt-3 grid gap-2 text-xs text-slate-600">
                          <p><span className="font-semibold text-slate-800">Issues:</span> {record.issue_reasons.length > 0 ? record.issue_reasons.join(', ') : 'None'}</p>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-800">Severity:</span>
                            <SeverityBadge severity={record.severity} />
                          </div>
                        </div>
                        <button
                          onClick={() => openEditor(record)}
                          className="mt-3 inline-flex w-full items-center justify-center rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 px-3 py-2 text-xs font-semibold text-white transition hover:from-emerald-600 hover:to-teal-700"
                        >
                          Review record
                        </button>
                      </div>
                    ))}
                    {reviewQueue.length === 0 && (
                      <div className="rounded-lg border border-dashed border-emerald-300 bg-emerald-50 p-4 text-center text-sm font-semibold text-emerald-800">
                        No flagged records. The current catalog is clear for export.
                      </div>
                    )}
                  </div>
                </section>

                <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                  <h2 className="text-lg font-semibold text-slate-950">Schema drift</h2>
                  <p className="mt-1 text-sm text-slate-500">Column-level changes detected during ingestion.</p>
                  {driftReport ? (
                    <div className="mt-5 space-y-3 text-sm">
                      {driftReport.unexpected_columns.length > 0 && (
                        <DriftBlock title="Unexpected columns" value={driftReport.unexpected_columns.join(', ')} tone="orange" />
                      )}
                      {driftReport.missing_columns.length > 0 && (
                        <DriftBlock title="Missing columns" value={driftReport.missing_columns.join(', ')} tone="rose" />
                      )}
                      {Object.keys(driftReport.auto_applied_mappings).length > 0 && (
                        <div className="rounded-lg border-l-4 border-emerald-500 bg-emerald-50 p-4">
                          <p className="text-sm font-semibold text-slate-950">Applied mappings</p>
                          <div className="mt-2 space-y-1 text-xs text-slate-700">
                            {Object.entries(driftReport.auto_applied_mappings).map(([src, dest]) => (
                              <div key={src}>{src} to {dest}</div>
                            ))}
                          </div>
                        </div>
                      )}
                      <DriftBlock title="Risk level" value={driftReport.drift_severity} tone={driftReport.drift_severity === 'High' ? 'rose' : driftReport.drift_severity === 'Medium' ? 'amber' : 'emerald'} />
                    </div>
                  ) : (
                    <p className="mt-5 rounded-lg bg-slate-50 p-4 text-sm text-slate-500">Upload a CSV to inspect schema drift.</p>
                  )}
                </section>

              </aside>
            </section>
          </main>
        </div>
      </div>

      {editingRecord ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 px-4 py-8">
          <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold text-slate-950">Review record</h3>
                <p className="mt-2 text-sm text-slate-600">Adjust the cleaned values before export.</p>
              </div>
              <button onClick={() => setEditingRecord(null)} className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-900" aria-label="Close review dialog">
                <Icon name="x" className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <RecordPanel title="Original values" record={editingRecord} mode="original" />
              <RecordPanel title="Cleaned preview" record={editingRecord} mode="cleaned" />
            </div>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <Field label="Category" value={formState.cleaned_category} onChange={(value) => setFormState({ ...formState, cleaned_category: value })} />
              <Field label="Price" value={formState.cleaned_price} onChange={(value) => setFormState({ ...formState, cleaned_price: value })} type="number" step="0.01" />
              <Field label="Inventory" value={formState.cleaned_inventory} onChange={(value) => setFormState({ ...formState, cleaned_inventory: value })} type="number" />
              <Field label="Tags" value={formState.cleaned_tags} onChange={(value) => setFormState({ ...formState, cleaned_tags: value })} className="sm:col-span-2" />
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <button onClick={saveReview} className="rounded-lg bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700">Save & approve</button>
              <button onClick={() => setEditingRecord(null)} className="rounded-lg border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 transition hover:bg-slate-50">Cancel</button>
            </div>
          </div>
        </div>
      ) : null}

      {toast ? (
        <div className={`fixed bottom-6 right-6 z-50 rounded-lg px-5 py-3 text-sm font-semibold shadow-lg ${toast.type === 'success' ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white'}`}>
          {toast.message}
        </div>
      ) : null}
    </div>
  )
}

function Sidebar({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const items: Array<{ label: string; icon: IconName; active?: boolean }> = [
    { label: 'Dashboard', icon: 'barChart', active: true },
    { label: 'Catalog review', icon: 'package' },
    { label: 'Schema drift', icon: 'layers' },
    { label: 'Exports', icon: 'download' },
    { label: 'Controls', icon: 'shield' },
  ]

  return (
    <aside className={`${open ? 'w-64' : 'w-[76px]'} hidden shrink-0 border-r border-slate-200 bg-white transition-all duration-300 lg:block`}>
      <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-teal-600 text-white shadow-sm">
            <Icon name="spark" className="h-5 w-5" />
          </div>
          {open ? <span className="text-sm font-bold text-slate-950">CatalogFlow</span> : null}
        </div>
        <button onClick={onToggle} className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900" aria-label="Collapse sidebar">
          <Icon name="chevronLeft" className={`h-4 w-4 transition ${open ? '' : 'rotate-180'}`} />
        </button>
      </div>
      <nav className="space-y-1 p-3">
        {items.map((item) => (
          <button
            key={item.label}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-semibold transition ${
              item.active ? 'bg-emerald-50 text-emerald-800' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
            } ${open ? '' : 'justify-center'}`}
            title={item.label}
          >
            <Icon name={item.icon} className="h-4 w-4 shrink-0" />
            {open ? <span>{item.label}</span> : null}
          </button>
        ))}
      </nav>
    </aside>
  )
}

function TopBar({ onToggleSidebar, attentionCount }: { onToggleSidebar: () => void; attentionCount: number }) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex h-16 items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <button onClick={onToggleSidebar} className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900" aria-label="Toggle sidebar">
            <Icon name="menu" className="h-5 w-5" />
          </button>
          <div>
            <p className="text-sm font-semibold text-slate-950">Operations dashboard</p>
            <p className="text-xs text-slate-500">Catalog ingestion and data quality workflow</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-amber-100 px-3 py-1.5 text-xs font-semibold text-amber-800">{attentionCount} need attention</span>
        </div>
      </div>
    </header>
  )
}

function StatCard({ icon, label, value, unit = '', bgColor }: { icon: IconName; label: string; value: string | number; unit?: string; bgColor: string }) {
  return (
    <div className={`rounded-xl bg-gradient-to-br ${bgColor} p-5 text-white shadow-sm`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-white/80">{label}</p>
          <p className="mt-2 text-3xl font-semibold">{value}{unit}</p>
        </div>
        <div className="grid h-10 w-10 place-items-center rounded-lg bg-white/15">
          <Icon name={icon} className="h-5 w-5" />
        </div>
      </div>
    </div>
  )
}

function InsightCard({ label, value, tone }: { label: string; value: string | number; tone: 'emerald' | 'orange' | 'rose' | 'teal' }) {
  const tones = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    orange: 'border-orange-200 bg-orange-50 text-orange-800',
    rose: 'border-rose-200 bg-rose-50 text-rose-800',
    teal: 'border-teal-200 bg-teal-50 text-teal-800',
  }
  return (
    <div className={`rounded-xl border p-4 ${tones[tone]}`}>
      <p className="text-xs font-semibold uppercase opacity-75">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  )
}

function RecordStatusBadge({ record }: { record: RecordItem }) {
  const reviewedStatus = record.review_status
  const isHumanResolved = record.exportable && (reviewedStatus === 'approved' || reviewedStatus === 'edited')
  const currentStatus =
    record.exportable && reviewedStatus === 'edited'
      ? 'Human-edited'
      : record.exportable && reviewedStatus === 'approved'
        ? 'Human-approved'
        : reviewedStatus === 'rejected'
          ? 'Rejected'
          : record.reviewed && !record.exportable
            ? 'Needs correction'
            : record.status

  return (
    <div className="flex flex-col items-start gap-1">
      <StatusBadge status={currentStatus} />
      {isHumanResolved ? (
        <span className="text-[11px] font-medium text-slate-500">Automated: {record.status}</span>
      ) : null}
    </div>
  )
}

function StatusBadge({ status, size = 'md' }: { status: string; size?: 'sm' | 'md' }) {
  const badges: Record<string, { bg: string; text: string; icon: IconName }> = {
    'Auto-approved': { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: 'check' },
    'Needs Review': { bg: 'bg-amber-100', text: 'text-amber-800', icon: 'alert' },
    Duplicate: { bg: 'bg-slate-100', text: 'text-slate-800', icon: 'file' },
    Invalid: { bg: 'bg-rose-100', text: 'text-rose-800', icon: 'x' },
    'Human-approved': { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: 'check' },
    'Human-edited': { bg: 'bg-amber-100', text: 'text-amber-800', icon: 'check' },
    'Needs correction': { bg: 'bg-rose-100', text: 'text-rose-800', icon: 'alert' },
    Rejected: { bg: 'bg-slate-200', text: 'text-slate-700', icon: 'x' },
  }
  const badge = badges[status] || badges['Needs Review']
  const isSmall = size === 'sm'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-semibold ${badge.bg} ${badge.text} ${isSmall ? 'text-xs' : 'text-sm'}`}>
      <Icon name={badge.icon} className="h-3.5 w-3.5" />
      {status}
    </span>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const severities: Record<string, string> = {
    Low: 'bg-emerald-100 text-emerald-800',
    Medium: 'bg-amber-100 text-amber-800',
    High: 'bg-rose-100 text-rose-800',
  }
  return (
    <span className={`inline-flex rounded-md px-2 py-1 text-xs font-semibold ${severities[severity] || severities.Low}`}>
      {severity}
    </span>
  )
}

function DriftBlock({ title, value, tone }: { title: string; value: string; tone: 'orange' | 'rose' | 'amber' | 'emerald' }) {
  const tones = {
    orange: 'border-orange-500 bg-orange-50',
    rose: 'border-rose-500 bg-rose-50',
    amber: 'border-amber-500 bg-amber-50',
    emerald: 'border-emerald-500 bg-emerald-50',
  }
  return (
    <div className={`rounded-lg border-l-4 p-4 ${tones[tone]}`}>
      <p className="text-sm font-semibold text-slate-950">{title}</p>
      <p className="mt-1 text-sm text-slate-700">{value}</p>
    </div>
  )
}

function ExportButton({ label, icon, onClick, bgColor }: { label: string; icon: IconName; onClick: () => void; bgColor: string }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r ${bgColor} px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:brightness-95`}
    >
      <Icon name={icon} className="h-4 w-4" />
      {label}
    </button>
  )
}

function RecordPanel({ title, record, mode }: { title: string; record: RecordItem; mode: 'original' | 'cleaned' }) {
  const values = mode === 'original'
    ? [
        ['Name', record.original_product_name],
        ['Category', record.original_category],
        ['Price', record.original_price],
        ['Inventory', record.original_inventory],
        ['Tags', record.original_tags],
      ]
    : [
        ['Name', record.cleaned_product_name],
        ['Category', record.cleaned_category],
        ['Price', record.cleaned_price != null ? `$${record.cleaned_price.toFixed(2)}` : '-'],
        ['Inventory', record.cleaned_inventory ?? '-'],
        ['Tags', record.cleaned_tags],
      ]

  return (
    <div className="rounded-lg bg-slate-50 p-4">
      <p className="text-sm font-semibold text-slate-950">{title}</p>
      <dl className="mt-4 space-y-3 text-sm text-slate-600">
        {values.map(([label, value]) => (
          <div key={label}>
            <span className="font-semibold text-slate-900">{label}:</span> {value || '-'}
          </div>
        ))}
      </dl>
    </div>
  )
}

function Field({ label, value, onChange, type = 'text', step, className = '' }: { label: string; value: string; onChange: (value: string) => void; type?: string; step?: string; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-sm font-semibold text-slate-800">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        type={type}
        step={step}
        className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-500 focus:ring-4 focus:ring-emerald-100"
      />
    </label>
  )
}

function Icon({ name, className = 'h-5 w-5' }: { name: IconName; className?: string }) {
  const paths: Record<IconName, JSX.Element> = {
    alert: <><path d="M12 9v4" /><path d="M12 17h.01" /><path d="M10.3 3.7 2.4 17.2A2 2 0 0 0 4.1 20h15.8a2 2 0 0 0 1.7-2.8L13.7 3.7a2 2 0 0 0-3.4 0Z" /></>,
    archive: <><path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8" /><path d="M10 12h4" /><path d="M2 3h20v5H2z" /></>,
    barChart: <><path d="M3 3v18h18" /><path d="M8 17V9" /><path d="M13 17V5" /><path d="M18 17v-6" /></>,
    check: <path d="m20 6-11 11-5-5" />,
    chevronLeft: <path d="m15 18-6-6 6-6" />,
    download: <><path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" /></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6" /></>,
    filter: <><path d="M22 3H2l8 9v7l4 2v-9l8-9Z" /></>,
    layers: <><path d="m12 2 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5" /><path d="m3 17 9 5 9-5" /></>,
    menu: <><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h16" /></>,
    package: <><path d="m16.5 9.4-9-5.2" /><path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" /></>,
    search: <><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" /><path d="m9 12 2 2 4-4" /></>,
    spark: <><path d="M12 2v6" /><path d="M12 16v6" /><path d="m4.9 4.9 4.2 4.2" /><path d="m14.9 14.9 4.2 4.2" /><path d="M2 12h6" /><path d="M16 12h6" /><path d="m4.9 19.1 4.2-4.2" /><path d="m14.9 9.1 4.2-4.2" /></>,
    upload: <><path d="M12 21V9" /><path d="m17 14-5-5-5 5" /><path d="M5 3h14" /></>,
    x: <><path d="M18 6 6 18" /><path d="m6 6 12 12" /></>,
  }

  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

export default App
