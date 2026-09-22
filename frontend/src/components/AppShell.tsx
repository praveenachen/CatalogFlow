import { useEffect, useState, type ReactNode } from 'react'
import type { BatchSummary, ViewId } from '../types'
import { Icon, type IconName } from './Icon'
import { StatusBadge } from './StatusBadge'

const navigation: Array<{ id: ViewId; label: string; icon: IconName }> = [
  { id: 'overview', label: 'Overview', icon: 'overview' },
  { id: 'batches', label: 'Batches', icon: 'batches' },
  { id: 'schema', label: 'Schema', icon: 'schema' },
  { id: 'records', label: 'Records', icon: 'records' },
  { id: 'review', label: 'Review', icon: 'review' },
  { id: 'publish', label: 'Publish', icon: 'publish' },
]

export function AppShell({ active, onNavigate, onUpload, summary, children }: { active: ViewId; onNavigate: (view: ViewId) => void; onUpload: () => void; summary: BatchSummary | null; children: ReactNode }) {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => localStorage.getItem('catalogflow-theme') === 'dark' ? 'dark' : 'light')
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem('catalogflow-theme', theme)
  }, [theme])
  const toggleTheme = () => setTheme((current) => current === 'light' ? 'dark' : 'light')
  return <div className="min-h-screen bg-[#f7f7f8] text-[#171717]">
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-[216px] flex-col border-r border-[#e7e7e8] bg-white lg:flex">
      <div className="flex h-16 items-center gap-2.5 px-5"><div className="grid h-8 w-8 place-items-center rounded-[9px] bg-[#171717] text-[11px] font-bold text-white dark:bg-[#f5f5f5] dark:text-[#111]">CF</div><span className="text-[15px] font-semibold tracking-[-0.01em]">CatalogFlow</span></div>
      <nav className="flex-1 space-y-1 px-3 py-3" aria-label="Primary navigation">{navigation.map((item) => <button key={item.id} onClick={() => onNavigate(item.id)} aria-current={active === item.id ? 'page' : undefined} className={`relative flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[14px] transition focus:outline-none focus:ring-2 focus:ring-blue-500/30 ${active === item.id ? 'bg-[#f1f1f2] font-medium text-[#171717]' : 'text-[#666] hover:bg-[#f6f6f7] hover:text-[#171717]'}`}><Icon name={item.icon} className="h-[17px] w-[17px]" /><span>{item.label}</span>{item.id === 'review' && (summary?.attention_count ?? 0) > 0 ? <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">{summary?.attention_count}</span> : null}{active === item.id ? <span className="absolute left-0 h-5 w-0.5 rounded-r bg-[#171717]" /> : null}</button>)}</nav>
      <div className="border-t border-[#eeeeef] p-4"><button onClick={toggleTheme} className="mb-3 flex h-9 w-full items-center gap-2 rounded-lg px-3 text-sm text-[#666] transition hover:bg-[#f6f6f7] hover:text-[#171717]"><Icon name={theme === 'dark' ? 'sun' : 'moon'} className="h-4 w-4" />{theme === 'dark' ? 'Light mode' : 'Dark mode'}</button><div className="rounded-lg bg-[#f7f7f8] p-3"><p className="text-xs font-medium text-[#333]">Default Merchant</p><p className="mt-1 truncate text-[11px] text-[#8a8a8a]">{summary?.filename ?? 'No catalog loaded'}</p></div><p className="mt-3 px-1 text-[11px] text-[#a0a0a0]">Catalog quality workspace</p></div>
    </aside>
    <div className="min-h-screen lg:ml-[216px]">
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[#e7e7e8] bg-white/95 px-7 backdrop-blur">
        <div className="min-w-0"><div className="flex items-center gap-2 text-sm"><span className="font-medium text-[#333] lg:hidden">CatalogFlow</span><span className="hidden font-medium text-[#333] lg:inline">Default Merchant</span><span className="text-[#b2b2b2]">/</span><span className="font-mono text-[13px] text-[#666]">{summary ? `CF-${String(summary.batch_id).padStart(4, '0')}` : 'No batch'}</span></div>{summary ? <div className="mt-1 flex items-center gap-2 text-xs text-[#8a8a8a]"><span className="max-w-[200px] truncate sm:max-w-[420px]">{summary.filename}</span><span>·</span><StatusBadge status={summary.processing_status ?? summary.status} /></div> : null}</div>
        <div className="flex items-center gap-2"><button onClick={toggleTheme} className="grid h-9 w-9 place-items-center rounded-lg border border-[#e7e7e8] text-[#666] lg:hidden" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}><Icon name={theme === 'dark' ? 'sun' : 'moon'} className="h-4 w-4" /></button><button onClick={onUpload} className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#171717] px-4 text-[13px] font-medium text-white shadow-sm transition hover:bg-black focus:outline-none focus:ring-2 focus:ring-blue-500/30 dark:bg-[#f5f5f5] dark:text-[#111] dark:hover:bg-white"><Icon name="upload" className="h-4 w-4" />Upload catalog</button></div>
      </header>
      <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7 sm:py-8">{children}</main>
    </div>
  </div>
}
