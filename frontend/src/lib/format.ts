// Money arrives from the API as decimal strings ("1020.00"); format for display only, never for arithmetic.
type Num = string | number | null | undefined

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

const toNumber = (v: Num): number | null => {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

export const money = (v: Num): string => {
  const n = toNumber(v)
  return n === null ? '—' : usd.format(n)
}

export const pct = (v: Num, digits = 1): string => {
  const n = toNumber(v)
  return n === null ? '—' : `${n.toFixed(digits)}%`
}

// Hashes and IDs: keep the head, which is what people compare by eye.
export const short = (v: string | null | undefined, n = 8): string => (!v ? '—' : v.length <= n ? v : `${v.slice(0, n)}…`)
