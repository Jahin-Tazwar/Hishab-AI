import { useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { NoticeUploadDropzone } from "@/components/notices/NoticeUploadDropzone"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { useNoticeList, useUploadNotice } from "@/hooks/useNotices"
import { ApiError } from "@/lib/api"
import type { NoticeStatus } from "@/types/notices"

const STATUS_TONE: Record<NoticeStatus, string> = {
  pending:         "bg-slate-200 text-slate-700",
  parsing:         "bg-blue-100 text-blue-800",
  parsed:          "bg-blue-100 text-blue-800",
  awaiting_data:   "bg-amber-100 text-amber-900",
  ready_to_draft:  "bg-indigo-100 text-indigo-800",
  drafting:        "bg-blue-100 text-blue-800",
  drafted:         "bg-emerald-100 text-emerald-800",
  finalized:       "bg-emerald-200 text-emerald-900",
  failed:          "bg-red-100 text-red-800",
}

export function NoticeList() {
  const { id: clientId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const list = useNoticeList(clientId)
  const upload = useUploadNotice(clientId ?? "")

  async function handlePick(file: File) {
    try {
      const { notice_id } = await upload.mutateAsync(file)
      toast.success("Notice uploaded. Parsing…")
      navigate(`/clients/${clientId}/notices/${notice_id}`)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Upload an NBR notice</CardTitle></CardHeader>
        <CardContent>
          <NoticeUploadDropzone
            disabled={upload.isPending}
            onPicked={handlePick}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Notices</CardTitle></CardHeader>
        <CardContent>
          {list.isLoading && <p className="text-sm text-slate-500">Loading&hellip;</p>}
          {list.isSuccess && list.data.length === 0 && (
            <p className="text-sm text-slate-500">
              No notices yet. Drop an NBR notice above to start.
            </p>
          )}
          {list.isSuccess && list.data.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Notice no</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Shortfall</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.data.map((n) => (
                  <TableRow
                    key={n.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => navigate(`/clients/${clientId}/notices/${n.id}`)}
                  >
                    <TableCell className="font-mono">{n.notice_no || n.original_filename}</TableCell>
                    <TableCell>{n.notice_date || "—"}</TableCell>
                    <TableCell>{n.period_start && n.period_end ? `${n.period_start} → ${n.period_end}` : "—"}</TableCell>
                    <TableCell>{n.alleged_shortfall_bdt ?? "—"}</TableCell>
                    <TableCell>
                      <Badge className={STATUS_TONE[n.status]}>{n.status}</Badge>
                    </TableCell>
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
