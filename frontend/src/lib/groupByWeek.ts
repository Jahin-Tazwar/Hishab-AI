/**
 * Group items by where their date falls in the next 30 days, using a
 * Monday-start week convention for the first two buckets.
 *
 * Buckets:
 *   thisWeek           — today through Sunday of this week
 *   nextWeek           — Monday–Sunday of the week after
 *   laterThisMonth     — everything after that, up to today + 30 days
 *
 * Anything before today (midnight) or beyond 30 days is dropped. The
 * 30-day cap matches the "next 30 days" promise made by the upstream
 * `useUpcomingEvents(30)` query — the previous 4-week cap silently
 * dropped events on days 24–30 when today wasn't a Sunday.
 */
export interface WeekBuckets<T> {
  thisWeek: T[]
  nextWeek: T[]
  laterThisMonth: T[]
}

function _toMidnight(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/** Sunday of the current week, treating Monday as the start. */
function _endOfThisWeek(today: Date): Date {
  const t = _toMidnight(today)
  // JS getDay(): Sun=0, Mon=1, ... Sat=6. Days until Sunday (Mon-start week):
  //   Mon=6, Tue=5, Wed=4, Thu=3, Fri=2, Sat=1, Sun=0
  const dow = t.getDay()
  const daysUntilSun = dow === 0 ? 0 : 7 - dow
  const out = new Date(t)
  out.setDate(t.getDate() + daysUntilSun)
  return out
}

export function groupByWeek<T>(
  items: T[],
  today: Date,
  getDate: (item: T) => string,
): WeekBuckets<T> {
  const start = _toMidnight(today).getTime()
  const endThis = _endOfThisWeek(today).getTime()
  const endNext = endThis + 7 * 86_400_000
  const end30 = start + 30 * 86_400_000

  const buckets: WeekBuckets<T> = {
    thisWeek: [],
    nextWeek: [],
    laterThisMonth: [],
  }
  for (const it of items) {
    const ts = _toMidnight(new Date(getDate(it))).getTime()
    if (ts < start) continue
    if (ts <= endThis) buckets.thisWeek.push(it)
    else if (ts <= endNext) buckets.nextWeek.push(it)
    else if (ts <= end30) buckets.laterThisMonth.push(it)
  }
  return buckets
}
