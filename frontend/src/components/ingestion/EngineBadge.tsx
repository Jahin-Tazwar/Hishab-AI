import { Badge } from "@/components/ui/badge"

const LABELS: Record<string, string> = {
  pandas: "Excel",
  "pandas+llm-mapper": "Excel + AI columns",
  "pdfplumber+llm": "PDF + AI",
  "gemini-vision": "AI vision",
  "tesseract+llm": "OCR + AI",
}

export function EngineBadge({ engine }: { engine: string | null | undefined }) {
  if (!engine) return null
  return <Badge variant="outline" className="font-normal">{LABELS[engine] ?? engine}</Badge>
}
