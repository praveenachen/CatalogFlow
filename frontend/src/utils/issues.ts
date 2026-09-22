function canonicalIssueKey(issue: string) {
  const normalized = issue.trim().toLowerCase().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
  if (/\bduplicate\b/.test(normalized)) return 'duplicate candidate'
  const invalidCode = normalized.match(/^invalid (.+)$/)
  if (invalidCode) return `${invalidCode[1]}: invalid value`
  return normalized
}

function readableIssue(issue: string) {
  const normalized = issue.trim().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ')
  const invalidCode = normalized.match(/^invalid (.+)$/i)
  if (invalidCode) return `${invalidCode[1]}: invalid value`
  return normalized
}

export function uniqueIssueReasons(issues: string[]) {
  const seen = new Set<string>()
  return issues.reduce<string[]>((result, issue) => {
    const key = canonicalIssueKey(issue)
    if (!key || seen.has(key)) return result
    seen.add(key)
    result.push(key === 'duplicate candidate' ? 'Possible duplicate requires review' : readableIssue(issue))
    return result
  }, [])
}
