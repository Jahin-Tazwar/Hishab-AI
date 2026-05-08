/**
 * Centralised axios instance for the HishabAI backend API.
 *
 * - Base URL from VITE_API_URL.
 * - Request interceptor: pulls the current Supabase session and attaches
 *   the JWT as Authorization: Bearer <token>. If no session, the request
 *   is sent unauthenticated (the backend will return 401, which the UI
 *   surfaces as a redirect to /login).
 * - Response interceptor: normalises HishabError envelopes
 *   ({ success: false, error: { code, message, details } }) into a
 *   consistent ApiError thrown to callers.
 */
import axios, { AxiosError, type AxiosInstance } from "axios"

import { env } from "./env"
import { supabase } from "./supabase"

export interface ApiErrorShape {
  code: string
  message: string
  details?: Record<string, unknown>
}

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(code: string, message: string, status: number, details: Record<string, unknown> = {}) {
    super(message)
    this.name = "ApiError"
    this.code = code
    this.status = status
    this.details = details
  }
}

export const api: AxiosInstance = axios.create({
  baseURL: env.VITE_API_URL,
  headers: { "Content-Type": "application/json" },
  // 60s — synchronous reconciliation runs are CPU-bound but bounded.
  timeout: 60_000,
})

api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`)
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    const status = err.response?.status ?? 0
    const body = err.response?.data as { error?: ApiErrorShape } | undefined

    if (body?.error) {
      throw new ApiError(body.error.code, body.error.message, status, body.error.details ?? {})
    }
    // Non-HishabError responses (network errors, 502s without bodies, etc.)
    throw new ApiError("NETWORK_ERROR", err.message || "Request failed", status)
  },
)
