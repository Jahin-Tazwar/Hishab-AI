import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react"
import type { ElementType, ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useGenerateDraft } from "@/hooks/useNotices"
import type { Notice } from "@/types/notices"

interface Props {
  notice: Notice
  onDraftStarted?: () => void
}

export function NoticeStatusBanner({ notice, onDraftStarted }: Props) {
  const generate = useGenerateDraft(notice.id)

  if (notice.status === "parsing" || notice.status === "pending") {
    return (
      <Banner tone="info" icon={Loader2} spin>
        <strong>Parsing notice&hellip;</strong> Extracting metadata via Gemini Vision.
      </Banner>
    )
  }
  if (notice.status === "failed") {
    return (
      <Banner tone="error" icon={AlertTriangle}>
        <strong>Failed:</strong> {notice.parse_error || "Unknown error"}
      </Banner>
    )
  }
  if (notice.status === "ready_to_draft") {
    return (
      <Banner tone="info" icon={Sparkles}>
        <div className="flex items-center gap-3">
          <span>Ready to draft. Linked to a reconciliation for this period.</span>
          <Button
            size="sm"
            disabled={generate.isPending}
            onClick={async () => {
              await generate.mutateAsync()
              onDraftStarted?.()
            }}
          >
            {generate.isPending ? "Starting…" : "Draft reply with HishabAI"}
          </Button>
        </div>
      </Banner>
    )
  }
  if (notice.status === "drafting") {
    return (
      <Banner tone="info" icon={Loader2} spin>
        <strong>Drafting reply&hellip;</strong> Retrieving relevant law and composing Bangla letter.
      </Banner>
    )
  }
  if (notice.status === "drafted" || notice.status === "finalized") {
    return (
      <Banner tone="success" icon={CheckCircle2}>
        <strong>Draft ready.</strong> Open the editor below to review and export.
      </Banner>
    )
  }
  return null
}

function Banner({
  tone, icon: Icon, spin, children,
}: {
  tone: "info" | "error" | "success"
  icon: ElementType
  spin?: boolean
  children: ReactNode
}) {
  const cls = {
    info: "border-blue-200 bg-blue-50 text-blue-900",
    error: "border-red-200 bg-red-50 text-red-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[tone]
  return (
    <Card className={`border ${cls}`}>
      <CardContent className="flex items-start gap-3 py-3 text-sm">
        <Icon className={`size-4 mt-0.5 ${spin ? "animate-spin" : ""}`} aria-hidden />
        <div className="flex-1">{children}</div>
      </CardContent>
    </Card>
  )
}
