import { describe, expect, it } from "vitest"

import { clientFormSchema, ENTITY_TYPES, type ClientFormInput } from "../client"

describe("clientFormSchema", () => {
  const validBase: ClientFormInput = {
    name: "Acme Ltd",
    entity_type: "company",
    fiscal_year_end: "06-30",
    is_vat_registered: false,
  }

  it("accepts a minimal valid client", () => {
    expect(clientFormSchema.safeParse(validBase).success).toBe(true)
  })

  it("rejects empty name", () => {
    const result = clientFormSchema.safeParse({ ...validBase, name: "" })
    expect(result.success).toBe(false)
  })

  it("accepts a 12-digit TIN", () => {
    const result = clientFormSchema.safeParse({ ...validBase, tin: "123456789012" })
    expect(result.success).toBe(true)
  })

  it("rejects an 11-digit TIN", () => {
    const result = clientFormSchema.safeParse({ ...validBase, tin: "12345678901" })
    expect(result.success).toBe(false)
  })

  it("rejects non-numeric TIN", () => {
    const result = clientFormSchema.safeParse({ ...validBase, tin: "abcdefghijkl" })
    expect(result.success).toBe(false)
  })

  it("treats empty TIN as valid (optional)", () => {
    expect(clientFormSchema.safeParse({ ...validBase, tin: "" }).success).toBe(true)
  })

  it("accepts a 9-digit BIN", () => {
    expect(clientFormSchema.safeParse({ ...validBase, bin: "123456789" }).success).toBe(true)
  })

  it("rejects an 8-digit BIN", () => {
    expect(clientFormSchema.safeParse({ ...validBase, bin: "12345678" }).success).toBe(false)
  })

  it("rejects invalid email", () => {
    expect(
      clientFormSchema.safeParse({ ...validBase, contact_email: "not-an-email" }).success,
    ).toBe(false)
  })

  it("treats empty email as valid", () => {
    expect(clientFormSchema.safeParse({ ...validBase, contact_email: "" }).success).toBe(true)
  })

  it("rejects an unknown entity_type", () => {
    const result = clientFormSchema.safeParse({ ...validBase, entity_type: "alien" as never })
    expect(result.success).toBe(false)
  })

  it("rejects bad fiscal_year_end format", () => {
    const result = clientFormSchema.safeParse({ ...validBase, fiscal_year_end: "June 30" })
    expect(result.success).toBe(false)
  })

  it("ENTITY_TYPES contains the expected 5 values", () => {
    expect(ENTITY_TYPES).toEqual(["company", "individual", "partnership", "ngo", "bank"])
  })
})
