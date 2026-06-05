/**
 * Wrapper combining the read-only schedule view with a TipTap notes editor
 * for CA commentary. Autosaves debounced 2s; locked when status=finalized.
 *
 * Mirrors the autosave pattern from NoticeDraft.tsx.
 */
import { useEffect, useState } from "react"

import { AtRiskItcScheduleView } from "@/components/working-papers/AtRiskItcScheduleView"
import { DraftEditor } from "@/components/notices/DraftEditor"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useUpdateWorkingPaperNotes } from "@/hooks/useWorkingPapers"
import type {
  AtRiskItcSchedulePayload, WorkingPaper,
} from "@/types/workingPapers"

interface Props {
  workingPaper: WorkingPaper
  payload: AtRiskItcSchedulePayload
}

export function AtRiskItcScheduleEditor({ workingPaper, payload }: Props) {
  const isFinalized = workingPaper.status === "finalized"
  const save = useUpdateWorkingPaperNotes(workingPaper.id)

  const [notesHtml, setNotesHtml] = useState<string>(workingPaper.notes_html)
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null)

  // Hydrate when the working paper id or server-side updated_at changes
  // (e.g. after a regenerate).
  useEffect(() => {
    setNotesHtml(workingPaper.notes_html)
  }, [workingPaper.id, workingPaper.updated_at])

  const debouncedNotes = useDebouncedValue(notesHtml, 2000)

  useEffect(() => {
    if (isFinalized) return
    if (debouncedNotes === workingPaper.notes_html) return
    save.mutate(debouncedNotes, {
      onSuccess: () => setLastSavedAt(new Date()),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedNotes, isFinalized])

  return (
    <div className="space-y-4">
      <AtRiskItcScheduleView payload={payload} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">CA commentary</CardTitle>
        </CardHeader>
        <CardContent>
          <DraftEditor
            value={notesHtml}
            onChange={setNotesHtml}
            disabled={isFinalized}
          />
          <p className="mt-2 text-xs text-slate-500">
            {isFinalized
              ? "Finalized — read only."
              : save.isPending
                ? "Saving…"
                : lastSavedAt
                  ? `Last saved at ${lastSavedAt.toLocaleTimeString()}.`
                  : "Autosaves every 2 seconds."}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
