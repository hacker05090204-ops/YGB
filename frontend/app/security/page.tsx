"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { ShieldAlert, CheckCircle, AlertTriangle, XCircle, Search, FileText } from "lucide-react"

import { API_BASE } from "@/lib/api-base"
import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

type AdminStats = {
    total_users?: number
    total_targets?: number
    total_bounties?: number
    total_reward?: number
    average_reward?: number
    recent_activity_count?: number
}

export default function SecurityPage() {
    const containerRef = useRef(null)
    const [stats, setStats] = useState<AdminStats | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useGSAP(() => {
        gsap.from(".animate-item", {
            y: 20,
            opacity: 0,
            stagger: 0.1,
            duration: 0.6,
            ease: "power2.out",
            delay: 0.2,
        })
    }, { scope: containerRef, dependencies: [stats, loading, error] })

    useEffect(() => {
        let cancelled = false

        const loadStats = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/db/admin/stats`, { cache: "no-store" })
                if (!response.ok) {
                    throw new Error(`Request failed: ${response.status}`)
                }
                const payload = await response.json()
                if (!cancelled) {
                    setStats(payload.stats ?? null)
                    setError(null)
                }
            } catch (err) {
                if (!cancelled) {
                    setStats(null)
                    setError(err instanceof Error ? err.message : "Failed to load security status")
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        void loadStats()
        return () => {
            cancelled = true
        }
    }, [])

    const riskScore = useMemo(() => {
        if (!stats) {
            return null
        }
        const totalBounties = Number(stats.total_bounties || 0)
        const recentActivity = Number(stats.recent_activity_count || 0)
        if (totalBounties === 0 && recentActivity === 0) {
            return 0
        }
        return Math.min(100, Math.round(((recentActivity + totalBounties) / Math.max(totalBounties || 1, 1)) * 15))
    }, [stats])

    return (
        <SidebarProvider
            style={{
                "--sidebar-width": "calc(var(--spacing) * 64)",
                "--header-height": "calc(var(--spacing) * 12)",
            } as React.CSSProperties}
        >
            <AppSidebar variant="inset" />
            <SidebarInset>
                <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border/40 px-4 bg-background/50 backdrop-blur-md sticky top-0 z-10">
                    <div className="flex items-center gap-2 px-4">
                        <SidebarTrigger className="-ml-1" />
                    </div>
                </header>

                <div className="flex flex-1 flex-col p-4 md:p-8 pt-6 gap-8 max-w-7xl mx-auto w-full" ref={containerRef}>
                    <div className="space-y-1">
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Security Status</h1>
                        <p className="text-muted-foreground text-lg">Operational security summary backed by live admin stats</p>
                    </div>

                    {error && (
                        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
                            {error}
                        </div>
                    )}

                    <div className="grid gap-6 md:grid-cols-2">
                        <Card className="animate-item bg-red-950/20 border-red-900/50">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className="p-3 bg-red-900/30 rounded-full text-red-500">
                                        <ShieldAlert className="size-8" />
                                    </div>
                                    <div>
                                        <CardTitle className="text-2xl text-red-500">Live Security Posture</CardTitle>
                                        <CardDescription className="text-red-400/70">
                                            Derived from backend targets, bounties, and recent activity
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="flex items-center justify-between">
                                <div className="space-y-4">
                                    <div className="flex items-center gap-2 text-muted-foreground">
                                        <div className="size-2 rounded-full bg-red-500" /> {stats ? `${stats.total_bounties || 0} tracked bounty records` : "No stats available"}
                                    </div>
                                    <div className="flex items-center gap-2 text-muted-foreground">
                                        <div className="size-2 rounded-full bg-orange-500" /> {stats ? `${stats.recent_activity_count || 0} recent activity events` : "Telemetry unavailable"}
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className="text-5xl font-bold text-red-500">{riskScore === null ? "--" : `${riskScore}%`}</div>
                                    <div className="text-sm text-red-400 opacity-80">Operational Risk Index</div>
                                </div>
                            </CardContent>
                            <CardFooter>
                                <Button variant="destructive" className="w-full" disabled>
                                    Live issue triage is backend-driven
                                </Button>
                            </CardFooter>
                        </Card>

                        <div className="grid gap-4 grid-cols-2">
                            <StatCard icon={<CheckCircle className="size-3" />} value={`${stats?.total_users ?? 0}`} label="Registered Users" tone="text-green-500" />
                            <StatCard icon={<XCircle className="size-3" />} value={`${stats?.total_targets ?? 0}`} label="Tracked Targets" tone="text-red-500" />
                            <StatCard icon={<AlertTriangle className="size-3" />} value={`${stats?.total_bounties ?? 0}`} label="Bounty Records" tone="text-orange-500" />
                            <StatCard icon={<Search className="size-3" />} value={`${stats?.recent_activity_count ?? 0}`} label="Recent Activity" tone="text-foreground" />
                        </div>
                    </div>

                    <Card className="animate-item bg-card/40 border-border/50">
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <CardTitle>Security Controls</CardTitle>
                                <span className="text-xs text-muted-foreground">Live data only - no demo metrics</span>
                            </div>
                        </CardHeader>
                        <CardContent className="grid gap-4 md:grid-cols-4">
                            <Button variant="outline" className="h-24 flex flex-col gap-2" disabled>
                                <Search className="size-6" /> Vulnerability Scan
                            </Button>
                            <Button variant="outline" className="h-24 flex flex-col gap-2" disabled>
                                <ShieldAlert className="size-6" /> Risk Review
                            </Button>
                            <Button variant="outline" className="h-24 flex flex-col gap-2" disabled>
                                <FileText className="size-6" /> Compliance Evidence
                            </Button>
                            <Button variant="outline" className="h-24 flex flex-col gap-2" disabled>
                                <AlertTriangle className="size-6" /> Manual Escalation
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}

function StatCard({ icon, value, label, tone }: { icon: React.ReactNode; value: string; label: string; tone: string }) {
    return (
        <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
            <div className={`text-3xl font-bold ${tone}`}>{value}</div>
            <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                {icon} {label}
            </div>
        </Card>
    )
}
