import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { toast } from "sonner"

import { CitationsPanel } from "@/components/notices/CitationsPanel"
import { ComputationAppendixTable } from "@/components/notices/ComputationAppendixTable"
import { DraftEditor } from "@/components/notices/DraftEditor"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import {
  exportDraftUrl, useFinalizeDraft, useGenerateDraft, useNotice,
  useNoticeDraft, useReopenDraft, useSaveDraft,
} from "@/hooks/useNotices"
import { ApiError } from "@/lib/api"
import type { AppendixJson } from "@/types/notices"

const EMPTY_APPENDIX: AppendixJson = { rows: [] }

export function NoticeDraft() {
  const { noticeId } = useParams<{ noticeId: string }>()
  const notice = useNotice(noticeId)
  const draft = useNoticeDraft(noticeId)
  const save = useSaveDraft(noticeId ?? "")
  const regenerate = useGenerateDraft(noticeId ?? "")
  const finalize = useFinalizeDraft(noticeId ?? "")
  const reopen = useReopenDraft(noticeId ?? "")

  const [bodyHtml, setBodyHtml] = useState<string>("")
  const [appendix, setAppendix] = useState<AppendixJson>(EMPTY_APPENDIX)

  // Hydrate from server on first load + on regenerate
  useEffect(() => {
    if (draft.data) {
      setBodyHtml(draft.data.body_html)
      setAppendix(draft.data.appendix_json as AppendixJson)
    }
  }, [draft.data?.id, draft.data?.updated_at])

  // Autosave (debounced 2s) only when the draft is editable
  const isFinalized = draft.data?.status === "finalized"
  const debouncedBody = useDebouncedValue(bodyHtml, 2000)
  const debouncedAppendix = useDebouncedValue(appendix, 2000)

  useEffect(() => {
    if (!draft.data || isFinalized) return
    if (debouncedBody === draft.data.body_html
        && JSON.stringify(debouncedAppendix) === JSON.stringify(draft.data.appendix_json)) {
      return
    }
    save.mutate({ body_html: debouncedBody, appendix_json: debouncedAppendix })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedBody, debouncedAppendix, isFinalized])

  if (notice.isLoading || draft.isLoading) {
    return <p className="text-sm text-slate-500">Loading draft…</p>
  }
  if (draft.isError || !draft.data) {
    return <p className="text-sm text-red-700">No draft yet for this notice.</p>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Reply draft</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="outline" disabled={regenerate.isPending}
            onClick={async () => {
              try {
                await regenerate.mutateAsync()
                toast.success("Regenerating…")
              } catch (e) {
                toast.error(e instanceof ApiError ? e.message : (e as Error).message)
              }
            }}
          >
            Regenerate
          </Button>
          <a
            href={exportDraftUrl(noticeId!, "docx")}
            download
            className={buttonVariants({ variant: "outline" })}
          >
            Export .docx
          </a>
          <a
            href={exportDraftUrl(noticeId!, "pdf")}
            download
            className={buttonVariants({ variant: "outline" })}
          >
            Export PDF
          </a>
          {isFinalized ? (
            <Button
              onClick={async () => {
                const reason = prompt("Reason to reopen (visible in history):") ?? ""
                if (reason.trim().length < 3) return
                await reopen.mutateAsync(reason)
                toast.success("Reopened for editing.")
              }}
            >
              Reopen for editing
            </Button>
          ) : (
            <Button
              onClick={async () => {
                await finalize.mutateAsync()
                toast.success("Draft finalized.")
              }}
            >
              Mark finalized
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader><CardTitle>Body (Bangla)</CardTitle></CardHeader>
          <CardContent>
            <DraftEditor value={bodyHtml} onChange={setBodyHtml} disabled={isFinalized} />
            <p className="mt-2 text-xs text-slate-500">
              {save.isPending ? "Saving…" : "Autosaves every 2 seconds."}
            </p>
          </CardContent>
        </Card>
        <div className="space-y-4">
          <CitationsPanel citations={draft.data.citations} />
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>Computation appendix (English)</CardTitle></CardHeader>
        <CardContent>
          <ComputationAppendixTable
            value={appendix} onChange={setAppendix} disabled={isFinalized}
          />
        </CardContent>
      </Card>
    </div>
  )
}
