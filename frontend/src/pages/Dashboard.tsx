import { OverdueClientsWidget } from "@/components/compliance/OverdueClientsWidget"
import { RecentReconciliationsWidget } from "@/components/compliance/RecentReconciliationsWidget"
import { UpcomingDeadlinesWidget } from "@/components/compliance/UpcomingDeadlinesWidget"
import { PageHeader } from "@/components/layout/PageHeader"
import { useUserProfile } from "@/hooks/useUserProfile"

export function Dashboard() {
  const { data: profile } = useUserProfile()
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle={profile?.full_name ? `Welcome back, ${profile.full_name}.` : "Welcome to HishabAI."}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><UpcomingDeadlinesWidget /></div>
        <div className="space-y-4">
          <OverdueClientsWidget />
          <RecentReconciliationsWidget />
        </div>
      </div>
    </div>
  )
}
