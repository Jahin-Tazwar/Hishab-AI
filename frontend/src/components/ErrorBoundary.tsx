import { Component, type ErrorInfo, type ReactNode } from "react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  /** Set to true when the user clicks "Try again"; cleared once new children arrive. */
  pendingReset: boolean
  /** Snapshot of children at the time the error was caught, used for change detection. */
  erroredChildren: ReactNode
}

/**
 * Catches render-time errors in its subtree and renders a fallback card.
 * Async errors (in fetch / mutation callbacks) are NOT caught here — those are
 * handled by per-hook `error` states from TanStack Query.
 *
 * Recovery pattern for React 19: clicking "Try again" sets pendingReset=true.
 * getDerivedStateFromProps detects when the parent re-renders with new children
 * (different reference from the children that caused the error) and then clears
 * the error state, allowing the subtree to render again.
 *
 * Mount one at the root (in main.tsx) and one per authenticated route
 * (via <RouteBoundary> in router.tsx) so a crash in one page slot doesn't
 * blank out the AppShell.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, pendingReset: false, erroredChildren: null }

  static getDerivedStateFromError(): Partial<State> {
    return { hasError: true, pendingReset: false }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Store the children that caused the error so we can detect when the parent
    // re-renders with new children (the signal that recovery is safe).
    this.setState({ erroredChildren: this.props.children })

    if (import.meta.env.DEV) {
      console.error("ErrorBoundary caught:", error, info.componentStack)
    }
  }

  /**
   * Clears the error state once both conditions hold:
   * - A reset has been requested (pendingReset=true)
   * - The parent has re-rendered with new children (different reference)
   *
   * This two-step approach prevents the boundary from immediately re-catching
   * an error when the children in props are still stale (React 19 behaviour).
   */
  static getDerivedStateFromProps(
    props: Props,
    state: State,
  ): Partial<State> | null {
    if (
      state.pendingReset &&
      state.hasError &&
      props.children !== state.erroredChildren
    ) {
      return { hasError: false, pendingReset: false, erroredChildren: null }
    }
    return null
  }

  reset = (): void => {
    this.setState({ pendingReset: true })
  }

  render(): ReactNode {
    if (this.state.hasError || this.state.pendingReset) {
      return (
        <div className="flex min-h-[40vh] items-center justify-center p-6">
          <Card className="max-w-md w-full">
            <CardContent className="space-y-3 pt-6">
              <h2 className="text-lg font-semibold text-foreground">
                Something went wrong
              </h2>
              <p className="text-sm text-muted-foreground">
                The page hit an unexpected error. You can try again, or head
                back to the dashboard.
              </p>
              <div className="flex gap-2 pt-1">
                <Button onClick={this.reset}>Try again</Button>
                <Link
                  to="/dashboard"
                  className="inline-flex items-center justify-center rounded-md border border-input px-3 py-1.5 text-sm hover:bg-muted"
                >
                  Go to dashboard
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      )
    }
    return this.props.children
  }
}

/**
 * Convenience wrapper for use inside <Route element={...}> entries — keeps
 * router.tsx readable.
 */
export function RouteBoundary({ children }: { children: ReactNode }) {
  return <ErrorBoundary>{children}</ErrorBoundary>
}
