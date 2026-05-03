import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useUserProfile } from "@/hooks/useUserProfile"

export function Dashboard() {
  const { data: profile } = useUserProfile()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-600 mt-1">
          {profile?.full_name ? `Welcome back, ${profile.full_name}.` : "Welcome to HishabAI."}
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>You're all set</CardTitle>
          <CardDescription>
            Your firm is created. Next, add clients and run your first reconciliation.
            (Clients and Reconciliation modules ship in Phase B–C.)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-600">
            For now, this empty dashboard confirms that auth, tenant creation, and RLS
            isolation are all working.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
