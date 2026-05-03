import { z } from "zod"

const envSchema = z.object({
  VITE_SUPABASE_URL: z.string().url(),
  VITE_SUPABASE_ANON_KEY: z.string().min(1),
  VITE_API_URL: z.string().url(),
})

const parsed = envSchema.safeParse(import.meta.env)

if (!parsed.success) {
  console.error("Invalid environment variables:", parsed.error.flatten().fieldErrors)
  throw new Error("Missing or invalid environment variables. See .env.example.")
}

export const env = parsed.data
