/**
 * Read-only renderer for the audit_defense_pack composed payload.
 * Sections: notice summary, reconciled position (reuses AtRiskItcScheduleView),
 * override log, drafted reply + citations, evidence index.
 */
import { AtRiskItcScheduleView } from "@/components/working-papers/AtRiskItcScheduleView"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/formatBDT"
import type { AuditDefensePackPayload } from "@/types/workingPapers"

interface Props { payload: AuditDefensePackPayload }

export function AuditDefensePackView({ payload }: Props) {
  const n = payload.notice
  return (
    <div className="space-y-6">
      <div className="rounded-md border bg-white p-4">
        <p className="text-xs uppercase tracking-wide text-slate-500">In response to</p>
        <p className="text-base font-semibold text-slate-900">
          Notice {n.notice_no ?? "—"}{" "}
          <span className="text-sm font-normal text-slate-500">
            dated {n.notice_date ?? "—"}
          </span>
        </p>
        <p className="mt-1 text-sm text-slate-600">
          {payload.client_name}
          {payload.client_bin ? ` · BIN ${payload.client_bin}` : ""}
          {payload.client_tin ? ` · TIN ${payload.client_tin}` : ""}
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">1. Notice summary</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
            <Field label="Type" value={n.notice_type ?? "—"} />
            <Field label="Period" value={`${n.period_start ?? "?"} → ${n.period_end ?? "?"}`} />
            <Field label="Alleged claimed" value={formatBDT(n.alleged_itc_claimed_bdt ?? null)} />
            <Field label="Alleged allowed" value={formatBDT(n.alleged_itc_allowed_bdt ?? null)} />
            <Field label="Alleged shortfall"
                   value={formatBDT(n.alleged_shortfall_bdt ?? null)} tone="warn" />
          </dl>
        </CardContent>
      </Card>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">2. Reconciled position</h2>
        {payload.reconciled_position ? (
          <AtRiskItcScheduleView payload={payload.reconciled_position} />
        ) : (
          <Card><CardContent className="py-6 text-sm text-slate-500">
            No reconciliation linked to this notice.
          </CardContent></Card>
        )}
      </section>

      <Card>
        <CardHeader><CardTitle className="text-base">3. Decision &amp; override log</CardTitle></CardHeader>
        <CardContent>
          {payload.override_log.length === 0 ? (
            <p className="text-sm text-slate-500">No CA overrides recorded.</p>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Supplier</TableHead><TableHead>Invoice</TableHead>
                <TableHead>Decision</TableHead><TableHead>Note</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {payload.override_log.map((e, i) => (
                  <TableRow key={`${e.invoice_no ?? "?"}-${i}`}>
                    <TableCell>{e.supplier_name ?? "—"}</TableCell>
                    <TableCell className="font-medium">{e.invoice_no ?? "—"}</TableCell>
                    <TableCell><Badge variant="outline">{e.ca_override ?? "—"}</Badge></TableCell>
                    <TableCell className="text-slate-600">{e.ca_notes ?? ""}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">4. Drafted reply</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {payload.drafted_reply?.body_html ? (
            <>
              <div className="prose prose-sm max-w-none"
                   dangerouslySetInnerHTML={{ __html: payload.drafted_reply.body_html }} />
              {payload.drafted_reply.citations.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Citations</p>
                  <ul className="mt-1 list-disc pl-5 text-sm text-slate-600">
                    {payload.drafted_reply.citations.map((c, i) => (
                      <li key={i}>{String((c as Record<string, unknown>).source_ref ?? "citation")}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-slate-500">No reply drafted yet.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">5. Evidence index</CardTitle></CardHeader>
        <CardContent>
          {payload.evidence_index.length === 0 ? (
            <p className="text-sm text-slate-500">No evidence linked.</p>
          ) : (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Ref</TableHead><TableHead>Document</TableHead>
                <TableHead>Source type</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {payload.evidence_index.map((e) => (
                  <TableRow key={e.ref}>
                    <TableCell className="font-mono">{e.ref}</TableCell>
                    <TableCell>{e.filename}</TableCell>
                    <TableCell>{e.source_type.replace(/_/g, " ")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Field({ label, value, tone }: { label: string; value: string; tone?: "warn" }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={tone === "warn" ? "font-semibold text-amber-700" : "text-slate-900"}>
        {value}
      </dd>
    </div>
  )
}
