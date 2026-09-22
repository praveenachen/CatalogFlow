import { useState } from 'react'
import { Icon } from './Icon'

export function UploadModal({ open, busy, onClose, onSubmit }: { open: boolean; busy: boolean; onClose: () => void; onSubmit: (file: File, currency?: string) => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null)
  const [currency, setCurrency] = useState('')
  if (!open) return null
  return <div className="fixed inset-0 z-[70] grid place-items-center bg-black/30 p-5 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-labelledby="upload-title">
    <div className="w-full max-w-[520px] overflow-hidden rounded-xl border border-[#dedee0] bg-white shadow-2xl">
      <header className="flex items-start justify-between border-b border-[#ececee] px-6 py-5"><div><h2 id="upload-title" className="text-lg font-semibold tracking-[-0.01em]">Upload merchant catalog</h2><p className="mt-1 text-sm text-[#777]">Start a new quality-processing batch.</p></div><button onClick={onClose} className="rounded-md p-1.5 text-[#888] hover:bg-[#f3f3f4] hover:text-[#222]" aria-label="Close upload dialog"><Icon name="x" /></button></header>
      <div className="space-y-5 p-6"><label className="grid min-h-36 cursor-pointer place-items-center rounded-xl border border-dashed border-[#cfcfd2] bg-[#fafafa] p-5 text-center transition hover:border-[#888] hover:bg-[#f7f7f8]"><div><div className="mx-auto grid h-9 w-9 place-items-center rounded-lg border border-[#e4e4e6] bg-white text-[#555]"><Icon name="upload" /></div><p className="mt-3 text-sm font-medium">{file ? file.name : 'Choose a CSV file'}</p><p className="mt-1 text-xs text-[#929292]">Click to browse merchant catalog files</p></div><input type="file" accept=".csv,text/csv" className="sr-only" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <div className="grid gap-4 sm:grid-cols-2"><label><span className="text-xs font-medium text-[#555]">Merchant</span><input value="Default Merchant" disabled className="mt-1.5 h-10 w-full rounded-lg border border-[#e2e2e3] bg-[#f7f7f8] px-3 text-sm text-[#777]" /></label><label><span className="text-xs font-medium text-[#555]">Default currency <span className="font-normal text-[#aaa]">optional</span></span><input value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))} placeholder="USD" className="mt-1.5 h-10 w-full rounded-lg border border-[#dedee0] px-3 text-sm uppercase outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" /></label></div>
      </div>
      <footer className="flex justify-end gap-2 border-t border-[#ececee] bg-[#fafafa] px-6 py-4"><button onClick={onClose} className="action-secondary">Cancel</button><button disabled={!file || busy || (currency.length > 0 && currency.length !== 3)} onClick={() => file && onSubmit(file, currency || undefined)} className="action-primary">{busy ? 'Ingesting…' : 'Ingest catalog'}</button></footer>
    </div>
  </div>
}
