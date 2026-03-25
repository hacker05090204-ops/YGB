"use client"

import { LiveDataProvider } from "@/components/providers/live-data-provider"

export function AppProviders({ children }: { children: React.ReactNode }) {
  return <LiveDataProvider>{children}</LiveDataProvider>
}
