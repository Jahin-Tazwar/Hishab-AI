import type { ReactNode } from "react"

interface Props {
  children: ReactNode
}

export function AuthLayout({ children }: Props) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md">
        <h1 className="text-2xl font-bold text-center mb-6 text-slate-900">HishabAI</h1>
        {children}
      </div>
    </div>
  )
}
