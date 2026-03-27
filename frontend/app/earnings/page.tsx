"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { DollarSign, TrendingUp, CheckCircle, CreditCard } from "lucide-react"
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, CartesianGrid } from "recharts"

import { API_BASE } from "@/lib/api-base"
import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type BountyRecord = {
    id: string
    title: string
    severity?: string
    reward?: number | null
    status?: string
    submitted_at?: string | null
}

const COLORS = {
    CRITICAL: "#ef4444",
    HIGH: "#f97316",
    MEDIUM: "#facc15",
    LOW: "#38bdf8",
    UNKNOWN: "#737373",
} as const

export default function EarningsPage() {
    const containerRef = useRef(null)
    const [bounties, setBounties] = useState<BountyRecord[]>([])
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
    }, { scope: containerRef, dependencies: [bounties.length, loading, error] })

    useEffect(() => {
        let cancelled = false
        const loadBounties = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/db/bounties?limit=200`, { cache: "no-store" })
                if (!response.ok) {
                    throw new Error(`Request failed: ${response.status}`)
                }
                const payload = await response.json()
                if (!cancelled) {
                    setBounties(Array.isArray(payload.bounties) ? payload.bounties : [])
                    setError(null)
                }
            } catch (err) {
                if (!cancelled) {
                    setBounties([])
                    setError(err instanceof Error ? err.message : "Failed to load earnings data")
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        void loadBounties()
        return () => {
            cancelled = true
        }
    }, [])

    const rewardBounties = useMemo(
        () => bounties.filter((bounty) => typeof bounty.reward === "number"),
        [bounties],
    )

    const totalEarnings = rewardBounties.reduce((sum, bounty) => sum + Number(bounty.reward || 0), 0)
    const paidCount = rewardBounties.filter((bounty) => (bounty.status || "").toUpperCase() === "PAID").length
    const averageReward = rewardBounties.length > 0 ? totalEarnings / rewardBounties.length : 0

    const earningsByMonth = useMemo(() => {
        const bucket = new Map<string, number>()
        rewardBounties.forEach((bounty) => {
            const rawDate = bounty.submitted_at ? new Date(bounty.submitted_at) : null
            if (!rawDate || Number.isNaN(rawDate.getTime())) {
                return
            }
            const key = rawDate.toLocaleString("en-US", { month: "short" })
            bucket.set(key, (bucket.get(key) || 0) + Number(bounty.reward || 0))
        })
        return Array.from(bucket.entries()).map(([name, total]) => ({ name, total }))
    }, [rewardBounties])

    const distributionData = useMemo(() => {
        const counts = new Map<string, number>()
        rewardBounties.forEach((bounty) => {
            const severity = (bounty.severity || "UNKNOWN").toUpperCase()
            counts.set(severity, (counts.get(severity) || 0) + Number(bounty.reward || 0))
        })
        return Array.from(counts.entries()).map(([name, value]) => ({
            name,
            value,
            color: COLORS[name as keyof typeof COLORS] || COLORS.UNKNOWN,
        }))
    }, [rewardBounties])

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
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Earnings</h1>
                        <p className="text-muted-foreground text-lg">Reward totals derived from live bounty records</p>
                    </div>

                    {error && (
                        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
                            {error}
                        </div>
                    )}

                    <div className="grid gap-4 md:grid-cols-4">
                        <MetricCard title="Total Earnings" value={`$${totalEarnings.toFixed(2)}`} caption="Rewards recorded in backend" icon={<DollarSign className="size-4 text-emerald-500" />} />
                        <MetricCard title="Reports Submitted" value={`${bounties.length}`} caption="Live bounty records" icon={<TrendingUp className="size-4 text-primary" />} />
                        <MetricCard title="Paid Reports" value={`${paidCount}`} caption="Status=PAID" icon={<CheckCircle className="size-4 text-blue-500" />} />
                        <MetricCard title="Avg per Rewarded Bug" value={`$${averageReward.toFixed(2)}`} caption="Only rewarded records" icon={<CreditCard className="size-4 text-orange-500" />} />
                    </div>

                    <div className="grid gap-4 md:grid-cols-7">
                        <Card className="animate-item md:col-span-4 bg-card/40 border-border/50">
                            <CardHeader>
                                <CardTitle>Earnings History</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[300px] w-full">
                                    {earningsByMonth.length === 0 ? (
                                        <div className="flex h-full items-center justify-center text-muted-foreground">No dated reward data available.</div>
                                    ) : (
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={earningsByMonth}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                                <XAxis dataKey="name" stroke="#666" fontSize={12} tickLine={false} axisLine={false} />
                                                <YAxis stroke="#666" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                                                <Tooltip cursor={{ fill: "rgba(255,255,255,0.05)" }} contentStyle={{ backgroundColor: "#171717", border: "1px solid #333", borderRadius: "8px" }} />
                                                <Bar dataKey="total" fill="#10b981" radius={[4, 4, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    )}
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="animate-item md:col-span-3 bg-card/40 border-border/50">
                            <CardHeader>
                                <CardTitle>Income Source</CardTitle>
                                <CardDescription>Reward totals grouped by severity</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[300px] w-full">
                                    {distributionData.length === 0 ? (
                                        <div className="flex h-full items-center justify-center text-muted-foreground">No severity-linked reward data available.</div>
                                    ) : (
                                        <ResponsiveContainer width="100%" height="100%">
                                            <PieChart>
                                                <Pie data={distributionData} cx="50%" cy="50%" innerRadius={70} outerRadius={90} paddingAngle={5} dataKey="value">
                                                    {distributionData.map((entry) => (
                                                        <Cell key={entry.name} fill={entry.color} stroke="rgba(0,0,0,0)" />
                                                    ))}
                                                </Pie>
                                                <Tooltip contentStyle={{ backgroundColor: "#171717", border: "1px solid #333", borderRadius: "8px" }} itemStyle={{ color: "#e5e5e5" }} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    )}
                                </div>
                                <div className="flex justify-center gap-4 text-xs text-muted-foreground">
                                    {distributionData.map((entry) => (
                                        <div key={entry.name} className="flex items-center gap-1">
                                            <div className="size-2 rounded-full" style={{ backgroundColor: entry.color }} />
                                            {entry.name}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    <Card className="animate-item bg-card/40 border-border/50">
                        <CardHeader>
                            <CardTitle>Recent Rewarded Reports</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {rewardBounties.length === 0 ? (
                                    <div className="text-muted-foreground">No rewarded reports are available.</div>
                                ) : rewardBounties.slice(0, 10).map((bounty) => (
                                    <div key={bounty.id} className="flex items-center justify-between border-b border-border/40 pb-4 last:border-0 last:pb-0">
                                        <div>
                                            <div className="font-medium text-lg">{bounty.title}</div>
                                            <div className="text-sm text-muted-foreground">{bounty.submitted_at || "Submission date unavailable"}</div>
                                        </div>
                                        <div className="text-right">
                                            <div className="font-bold text-green-500">${Number(bounty.reward || 0).toFixed(2)}</div>
                                            <div className="text-xs text-muted-foreground">{bounty.status || "Unknown"}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}

function MetricCard({ title, value, caption, icon }: { title: string; value: string; caption: string; icon: React.ReactNode }) {
    return (
        <Card className="animate-item bg-card/40 border-border/50">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
                {icon}
            </CardHeader>
            <CardContent>
                <div className="text-2xl font-bold">{value}</div>
                <p className="text-xs text-muted-foreground mt-1">{caption}</p>
            </CardContent>
        </Card>
    )
}
