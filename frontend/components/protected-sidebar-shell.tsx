"use client"

import { type CSSProperties } from "react"

import { AppSidebar } from "@/components/app-sidebar"
import { AuthGuard } from "@/components/auth-guard"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

interface ProtectedSidebarShellProps {
  children: React.ReactNode
  insetClassName?: string
  sidebarVariant?: "sidebar" | "floating" | "inset"
  providerStyle?: CSSProperties
}

export function ProtectedSidebarShell({
  children,
  insetClassName,
  sidebarVariant = "inset",
  providerStyle,
}: ProtectedSidebarShellProps) {
  return (
    <AuthGuard>
      <SidebarProvider style={providerStyle}>
        <AppSidebar variant={sidebarVariant} />
        <SidebarInset className={insetClassName}>{children}</SidebarInset>
      </SidebarProvider>
    </AuthGuard>
  )
}
