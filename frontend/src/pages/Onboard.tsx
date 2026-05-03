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

    // 1. Create the tenant. RLS allows authenticated users to insert.
    const { data: tenant, error: tenantError } = await supabase
      .from("tenants")
      .insert({
        firm_name: values.firmName,
        email: user.email!,
      })
      .select()
      .single()

    if (tenantError) {
      setSubmitting(false)
      toast.error(`Could not create firm: ${tenantError.message}`)
      return
    }

    // 2. Create the user_profile linking auth.user → tenant
    const { error: profileError } = await supabase
      .from("user_profiles")
      .insert({
        id: user.id,
        tenant_id: tenant.id,
        full_name: values.fullName,
        role: "firm_admin",
      })

    setSubmitting(false)

    if (profileError) {
      toast.error(`Could not create profile: ${profileError.message}`)
      return
    }

    toast.success(`Welcome, ${values.fullName}!`)
    queryClient.invalidateQueries({ queryKey: ["user_profile"] })
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
            {errors.firmName && <p className="text-sm text-red-600">{errors.firmName.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="fullName">Your full name</Label>
            <Input
              id="fullName"
              placeholder="e.g. Anwar Rahman"
              {...register("fullName")}
            />
            {errors.fullName && <p className="text-sm text-red-600">{errors.fullName.message}</p>}
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Setting up…" : "Continue to dashboard"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
