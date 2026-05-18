import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Citation } from "@/types/notices"

export function CitationsPanel({ citations }: { citations: Citation[] }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Citations</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-sm">
        {citations.length === 0 && (
          <p className="text-slate-500">No citations in this draft yet.</p>
        )}
        {citations.map((c, i) => (
          <div key={`${c.corpus_chunk_id}-${i}`} className="rounded-md border p-2">
            <p className="font-medium">{c.source_ref}</p>
            <p className="mt-1 text-xs text-slate-600 line-clamp-3">{c.snippet}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
