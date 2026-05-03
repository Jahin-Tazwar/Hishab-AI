import { createBrowserRouter, Navigate } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthLayout } from "@/components/layout/AuthLayout"
import { RequireAuth } from "@/components/RequireAuth"
import { RequireTenant } from "@/components/RequireTenant"
import { Dashboard } from "@/pages/Dashboard"
import { Login } from "@/pages/Login"
import { Onboard } from "@/pages/Onboard"
import { Signup } from "@/pages/Signup"

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/login", element: <AuthLayout><Login /></AuthLayout> },
  { path: "/signup", element: <AuthLayout><Signup /></AuthLayout> },
  {
    path: "/onboard",
    element: (
      <RequireAuth>
        <AuthLayout><Onboard /></AuthLayout>
      </RequireAuth>
    ),
  },
  {
    path: "/dashboard",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><Dashboard /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  // /clients route added in Phase B
  { path: "*", element: <Navigate to="/login" replace /> },
])
