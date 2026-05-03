import { QueryClientProvider } from "@tanstack/react-query"
import React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider } from "react-router-dom"

import { queryClient } from "@/lib/queryClient"
import { router } from "@/router"
import { AppRoot } from "@/App"

import "./index.css"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppRoot>
        <RouterProvider router={router} />
      </AppRoot>
    </QueryClientProvider>
  </React.StrictMode>,
)
