import { useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { AwaitingDataPrompt } from "@/components/notices/AwaitingDataPrompt"
import { NoticeMetaCard } from "@/components/notices/NoticeMetaCard"
import { NoticeStatusBanner } from "@/components/notices/NoticeStatusBanner"
import { RelinkDialog } from "@/components/notices/RelinkDialog"
import { Button } from "@/components/ui/button"
import { useNotice } from "@/hooks/useNotices"
import { useComposeWorkingPaper } from "@/hooks/useWorkingPapers"
import { ApiError } from "@/lib/api"

export function NoticeDetail() {
  const { id: clientId, noticeId } = useParams<{ id: string; noticeId: string }>()
  const navigate = useNavigate()
  const q = useNotice(noticeId)
  const [relinkOpen, setRelinkOpen] = useState(false)
  const composePack = useComposeWorkingPaper()

  async function handleGeneratePack() {
    if (!noticeId || !clientId) return
    try {
      const out = await composePack.mutateAsync({
        kind: "audit_defense_pack", notice_id: noticeId,
      })
      toast.success("Audit defense pack generated.")
      navigate(`/clients/${clientId}/working-papers/${out.working_paper_id}`)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  if (q.isLoading) return <p className="text-sm text-slate-500">Loading notice…</p>
  if (q.isError || !q.data) {
    return <p className="text-sm text-red-700">Could not load notice.</p>
  }
  const n = q.data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">
          {n.notice_no || n.original_filename}
        </h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setRelinkOpen(true)}>
            Re-link notice
          </Button>
          <Button
            variant="outline"
            onClick={handleGeneratePack}
            disabled={composePack.isPending}
          >
            {composePack.isPending ? "Generating…" : "Generate Audit Defense Pack"}
          </Button>
          {(n.status === "drafted" || n.status === "finalized") && (
            <Button onClick={() => navigate(`/clients/${clientId}/notices/${n.id}/draft`)}>
              Open draft →
            </Button>
          )}
        </div>
      </div>

      <NoticeStatusBanner
        notice={n}
        onDraftStarted={() => navigate(`/clients/${clientId}/notices/${n.id}/draft`)}
      />

      {n.status === "awaiting_data" && clientId && (
        <AwaitingDataPrompt notice={n} clientId={clientId} />
      )}

      <NoticeMetaCard notice={n} />

      <RelinkDialog notice={n} open={relinkOpen} onOpenChange={setRelinkOpen} />
    </div>
  )
}
