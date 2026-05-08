import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

interface Props {
  start: string
  end: string
  onChange: (next: { start: string; end: string }) => void
  disabled?: boolean
  errorMessage?: string
}

/**
 * Reconciliation period picker — two date inputs (HTML5) for the
 * Bangladeshi VAT month/quarter range. Stores ISO YYYY-MM-DD strings
 * to match the backend Pydantic date type.
 */
export function PeriodPicker({
  start,
  end,
  onChange,
  disabled = false,
  errorMessage,
}: Props) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="period_start">Period start</Label>
          <Input
            id="period_start"
            type="date"
            value={start}
            onChange={(e) => onChange({ start: e.target.value, end })}
            disabled={disabled}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="period_end">Period end</Label>
          <Input
            id="period_end"
            type="date"
            value={end}
            onChange={(e) => onChange({ start, end: e.target.value })}
            disabled={disabled}
            min={start || undefined}
          />
        </div>
      </div>
      {errorMessage && (
        <p className="text-xs text-red-600">{errorMessage}</p>
      )}
    </div>
  )
}
