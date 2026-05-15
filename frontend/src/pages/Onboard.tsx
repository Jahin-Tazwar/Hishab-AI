import { zodResolver } from "@hookform/resolvers/zod"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"

const onboardSchema = z.object({
  firmName: z.string().min(2, "Firm name is required"),
  fullName: z.string().min(2, "Your full name is required"),
})

type OnboardInput = z.infer<typeof onboardSchema>

export function Onboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const [submitting, setSubmitting] = useState(false)
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<OnboardInput>({ resolver: zodResolver(onboardSchema) })

  async function onSubmit(values: OnboardInput) {
    if (!user) {
      toast.error("Not signed in.")
      return
    }
    setSubmitting(true)

    // Atomic onboarding via SECURITY DEFINER RPC.
    // Creates the tenant AND the user_profile in a single transaction,
    // sidestepping the chicken-and-egg RLS situation (no tenant_id on user_profile yet)
    // and avoiding orphan tenants if the second insert fails.
    const { data: tenant, error } = await supabase.rpc("create_tenant_for_user", {
      p_firm_name: values.firmName,
      p_full_name: values.fullName,
    })

    if (error || !tenant) {
      setSubmitting(false)
      toast.error(`Could not create firm: ${error?.message ?? "no tenant returned"}`)
      return
    }

    // Seed the user_profile cache BEFORE navigating so RequireTenant doesn't
    // see the stale `null` profile and bounce us back to /onboard.
    queryClient.setQueryData(["user_profile", user.id], {
      id: user.id,
      tenant_id: tenant.id,
      full_name: values.fullName,
      role: "firm_admin",
      created_at: tenant.created_at ?? new Date().toISOString(),
    })

    setSubmitting(false)
    toast.success(`Welcome, ${values.fullName}!`)
    navigate("/dashboard")
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set up your firm</CardTitle>
        <CardDescription>
          Tell us about your CA firm. You can change these details later.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="firmName">Firm name</Label>
            <Input
              id="firmName"
              placeholder="e.g. Rahman & Associates"
              {...register("firmName")}
            />
            {errors.firmName && <p className="text-sm text-destructive">{errors.firmName.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="fullName">Your full name</Label>
            <Input
              id="fullName"
              placeholder="e.g. Anwar Rahman"
              {...register("fullName")}
            />
            {errors.fullName && <p className="text-sm text-destructive">{errors.fullName.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Setting up…" : "Continue to dashboard"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
