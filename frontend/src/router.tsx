import { createBrowserRouter, Navigate } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthLayout } from "@/components/layout/AuthLayout"
import { RouteBoundary } from "@/components/ErrorBoundary"
import { RequireAuth } from "@/components/RequireAuth"
import { RequireTenant } from "@/components/RequireTenant"
import { ClientDetail } from "@/pages/ClientDetail"
import { Clients } from "@/pages/Clients"
import { Dashboard } from "@/pages/Dashboard"
import { Login } from "@/pages/Login"
import { NotFound } from "@/pages/NotFound"
import { Onboard } from "@/pages/Onboard"
import { ReconNew } from "@/pages/ReconNew"
import { ReconReport } from "@/pages/ReconReport"
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
          <AppShell>
            <RouteBoundary><Dashboard /></RouteBoundary>
          </AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  {
    path: "/clients",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell>
            <RouteBoundary><Clients /></RouteBoundary>
          </AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  {
    path: "/clients/:id",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell>
            <RouteBoundary><ClientDetail /></RouteBoundary>
          </AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  {
    path: "/clients/:id/recon/new",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell>
            <RouteBoundary><ReconNew /></RouteBoundary>
          </AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  {
    path: "/clients/:id/recon/:reconId",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell>
            <RouteBoundary><ReconReport /></RouteBoundary>
          </AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  { path: "*", element: <NotFound /> },
])
