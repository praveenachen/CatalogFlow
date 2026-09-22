import axios from 'axios'
import type { BatchSummary, ProcessingRun, RecordItem, ReviewPatch } from '../types'

const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE ?? 'http://localhost:8000' })

export function errorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return 'An unexpected error occurred.'
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.validation_errors?.length) return detail.validation_errors.join(' · ')
  if (typeof detail?.message === 'string') return detail.message
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      const field = Array.isArray(item?.loc) ? item.loc.at(-1) : null
      const label = typeof field === 'string' ? field.replace(/^cleaned_/, '').replace(/_/g, ' ') : 'Value'
      return typeof item?.msg === 'string' ? `${label}: ${item.msg}` : null
    }).filter((message): message is string => Boolean(message))
    if (messages.length) return messages.join(' · ')
  }
  return error.message || 'The request could not be completed.'
}

export async function loadWorkspace() {
  try {
    const summary = (await http.get<BatchSummary>('/latest-batch')).data
    const [records, reviewQueue, run] = await Promise.all([
      http.get<RecordItem[]>('/processed-records', { params: { batch_id: summary.batch_id } }),
      http.get<RecordItem[]>('/review-queue', { params: { batch_id: summary.batch_id } }),
      summary.run_id ? http.get<ProcessingRun>(`/processing-runs/${summary.run_id}`) : Promise.resolve({ data: null }),
    ])
    return { summary, records: records.data, reviewQueue: reviewQueue.data, run: run.data }
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) return null
    throw error
  }
}

export async function uploadCatalog(file: File, defaultCurrency?: string) {
  const form = new FormData()
  form.append('file', file)
  return (await http.post<BatchSummary>('/batches', form, { params: defaultCurrency ? { default_currency: defaultCurrency } : undefined })).data
}

export async function saveReview(recordId: number, patch: ReviewPatch) {
  return (await http.put<RecordItem>(`/review-queue/${recordId}`, patch)).data
}

export async function refreshRun(runId: number) {
  return (await http.post<ProcessingRun>(`/processing-runs/${runId}/refresh`)).data
}

export async function downloadExport(path: string, filename: string, batchId?: number) {
  const response = await http.get(path, { responseType: 'blob', params: batchId ? { batch_id: batchId } : undefined })
  const url = URL.createObjectURL(new Blob([response.data], { type: 'text/csv' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
