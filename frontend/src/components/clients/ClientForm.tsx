import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  clientFormSchema,
  ENTITY_TYPES,
  ENTITY_TYPE_LABELS,
  type ClientFormInput,
  type EntityType,
} from "@/types/client"

interface Props {
  defaultValues?: Partial<ClientFormInput>
  submitting?: boolean
  submitLabel?: string
  onSubmit: (values: ClientFormInput) => void
  onCancel: () => void
}

export function ClientForm({
  defaultValues,
  submitting,
  submitLabel = "Save",
  onSubmit,
  onCancel,
}: Props) {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ClientFormInput>({
    resolver: zodResolver(clientFormSchema),
    defaultValues: {
      entity_type: "company",
      fiscal_year_end: "06-30",
      is_vat_registered: false,
      ...defaultValues,
    },
  })

  const entityType = watch("entity_type")
  const isVatRegistered = watch("is_vat_registered")

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="name">Name *</Label>
          <Input id="name" {...register("name")} placeholder="e.g. Acme Industries Ltd" />
          {errors.name && <p className="text-sm text-red-600">{errors.name.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="name_bn">Name (Bangla)</Label>
          <Input id="name_bn" {...register("name_bn")} placeholder="e.g. অ্যাকমে ইন্ডাস্ট্রিজ" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="entity_type">Entity type *</Label>
          <Select
            value={entityType}
            onValueChange={(v) => setValue("entity_type", v as EntityType, { shouldValidate: true })}
          >
            <SelectTrigger id="entity_type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENTITY_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {ENTITY_TYPE_LABELS[t]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="industry">Industry</Label>
          <Input id="industry" {...register("industry")} placeholder="e.g. Manufacturing" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="tin">TIN (12 digits)</Label>
          <Input id="tin" {...register("tin")} placeholder="123456789012" maxLength={12} />
          {errors.tin && <p className="text-sm text-red-600">{errors.tin.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="bin">BIN (9 digits)</Label>
          <Input id="bin" {...register("bin")} placeholder="123456789" maxLength={9} />
          {errors.bin && <p className="text-sm text-red-600">{errors.bin.message}</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 items-end">
        <div className="space-y-1">
          <Label htmlFor="fiscal_year_end">Fiscal year end (MM-DD)</Label>
          <Input
            id="fiscal_year_end"
            {...register("fiscal_year_end")}
            placeholder="06-30"
            maxLength={5}
          />
          {errors.fiscal_year_end && (
            <p className="text-sm text-red-600">{errors.fiscal_year_end.message}</p>
          )}
        </div>
        <div className="flex items-center gap-2 pb-2">
          <Checkbox
            id="is_vat_registered"
            checked={isVatRegistered}
            onCheckedChange={(c) => setValue("is_vat_registered", Boolean(c))}
          />
          <Label htmlFor="is_vat_registered" className="cursor-pointer">
            VAT registered
          </Label>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="contact_email">Contact email</Label>
          <Input
            id="contact_email"
            type="email"
            {...register("contact_email")}
            placeholder="contact@client.com"
          />
          {errors.contact_email && (
            <p className="text-sm text-red-600">{errors.contact_email.message}</p>
          )}
        </div>
        <div className="space-y-1">
          <Label htmlFor="contact_phone">Contact phone</Label>
          <Input id="contact_phone" {...register("contact_phone")} placeholder="+8801XXXXXXXXX" />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" {...register("notes")} rows={3} />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  )
}
