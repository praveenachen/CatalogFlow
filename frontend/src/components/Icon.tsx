export type IconName = 'overview' | 'batches' | 'schema' | 'records' | 'review' | 'publish' | 'upload' | 'search' | 'filter' | 'check' | 'alert' | 'x' | 'arrow' | 'download' | 'refresh' | 'file' | 'chevron' | 'sun' | 'moon'

export function Icon({ name, className = 'h-4 w-4' }: { name: IconName; className?: string }) {
  const paths: Record<IconName, JSX.Element> = {
    overview: <><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" /></>,
    batches: <><path d="M4 5h16v4H4zM4 11h16v8H4zM8 14h4" /></>,
    schema: <><path d="M4 5h6v4H4zM14 15h6v4h-6zM10 7h4v10h-4M4 17h6" /></>,
    records: <><path d="M4 5h16M4 10h16M4 15h16M4 20h16M8 3v19" /></>,
    review: <><path d="M4 4h16v16H4zM8 9h8M8 13h5M16 16l1.5 1.5L21 14" /></>,
    publish: <><path d="M12 3v12m0-12 4 4m-4-4L8 7M5 15v5h14v-5" /></>,
    upload: <><path d="M12 19V7m-4 4 4-4 4 4M5 4h14" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    filter: <path d="M3 5h18l-7 8v6l-4 2v-8z" />,
    check: <path d="m5 12 4 4L19 6" />,
    alert: <><path d="M12 8v5m0 4h.01" /><path d="m12 3 10 18H2z" /></>,
    x: <><path d="m6 6 12 12M18 6 6 18" /></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5" /></>,
    download: <><path d="M12 3v13m-5-5 5 5 5-5M4 21h16" /></>,
    refresh: <><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6.1 8a7 7 0 0 1 11.5-1L20 12M4 12l2.4 5a7 7 0 0 0 11.5-1" /></>,
    file: <><path d="M6 2h8l4 4v16H6zM14 2v5h5" /></>,
    chevron: <path d="m9 6 6 6-6 6" />,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
    moon: <path d="M20 15.4A8.5 8.5 0 0 1 8.6 4a8.5 8.5 0 1 0 11.4 11.4Z" />,
  }
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
