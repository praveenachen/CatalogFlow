export function confidencePercent(value: number) {
  return value <= 1 ? value * 100 : value
}

export function formatConfidence(value: number, fractionDigits = 0) {
  return `${confidencePercent(value).toFixed(fractionDigits)}%`
}
