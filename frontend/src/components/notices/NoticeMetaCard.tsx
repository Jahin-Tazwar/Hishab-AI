import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Notice } from "@/types/notices"

export function NoticeMetaCard({ notice }: { notice: Notice }) {
  return (
    <Card>
      <CardHeader><CardTitle>Parsed notice metadata</CardTitle></CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <Field label="Notice no" value={notice.notice_no} mono />
          <Field label="Notice date" value={notice.notice_date} />
          <Field label="Taxpayer BIN" value={notice.taxpayer_bin} mono />
          <Field label="Taxpayer TIN" value={notice.taxpayer_tin} mono />
          <Field label="Period" value={
            notice.period_start && notice.period_end
              ? `${notice.period_start} → ${notice.period_end}`
              : null
          } />
          <Field label="Alleged claimed ITC" value={notice.alleged_itc_claimed_bdt} />
          <Field label="Alleged allowed ITC" value={notice.alleged_itc_allowed_bdt} />
          <Field label="Alleged shortfall" value={notice.alleged_shortfall_bdt} />
        </dl>
      </CardContent>
    </Card>
  )
}

function Field({
  label, value, mono,
}: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className={mono ? "font-mono" : ""}>{value || "—"}</dd>
    </>
  )
}
