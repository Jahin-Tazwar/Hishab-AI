import { QueryClientProvider } from "@tanstack/react-query"
import React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider } from "react-router-dom"

import { ErrorBoundary } from "@/components/ErrorBoundary"
import { queryClient } from "@/lib/queryClient"
import { router } from "@/router"
import { AppRoot } from "@/App"

import "./index.css"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppRoot>
          <RouterProvider router={router} />
        </AppRoot>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)
