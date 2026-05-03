import { z } from "zod"

export const ENTITY_TYPES = [
  "company",
  "individual",
  "partnership",
  "ngo",
  "bank",
] as const

export type EntityType = (typeof ENTITY_TYPES)[number]

const optionalBdId = (digits: number, label: string) =>
  z
    .string()
    .optional()
    .refine(
      (val) => !val || new RegExp(`^\\d{${digits}}$`).test(val),
      `${label} must be exactly ${digits} digits`,
    )

const optionalEmail = z
  .string()
  .optional()
  .refine((val) => !val || z.string().email().safeParse(val).success, "Invalid email")

/**
 * The form input shape (what the user enters in the Add/Edit dialog).
 * Differs from the DB row shape — no id, tenant_id, created_at, etc.
 */
export const clientFormSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  name_bn: z.string().optional(),
  tin: optionalBdId(12, "TIN"),
  bin: optionalBdId(9, "BIN"),
  entity_type: z.enum(ENTITY_TYPES),
  industry: z.string().optional(),
  fiscal_year_end: z
    .string()
    .regex(/^\d{2}-\d{2}$/, "Format: MM-DD (e.g. 06-30)"),
  is_vat_registered: z.boolean(),
  contact_email: optionalEmail,
  contact_phone: z.string().optional(),
  notes: z.string().optional(),
})

export type ClientFormInput = z.infer<typeof clientFormSchema>

/**
 * The full client row shape as stored in Supabase.
 */
export interface Client extends ClientFormInput {
  id: string
  tenant_id: string
  deleted_at: string | null
  created_at: string
  updated_at: string
  created_by: string
}

export const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  company: "Company",
  individual: "Individual",
  partnership: "Partnership",
  ngo: "NGO",
  bank: "Bank",
}
