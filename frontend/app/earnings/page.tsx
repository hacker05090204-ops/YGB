"use client"

import { useState, useEffect, useRef } from "react"
import { authFetch } from "@/lib/ygb-api"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { DollarSign, TrendingUp, CheckCircle, CreditCard, ArrowUpRight, RefreshCw, AlertCircle } from "lucide-react"
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, CartesianGrid } from "recharts"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface Bounty {
    id: string
    title: string
    severity: string
    reward: number
    status: string
    submitted_at: string
    user_name: string
}

const SEVERITY_COLORS: Record<string, string> = {
    Critical: "#a855f7",
    CRITICAL: "#a855f7",
    High: "#3b82f6",
    HIGH: "#3b82f6",
    Medium: "#06b6d4",
    MEDIUM: "#06b6d4",
    Low: "#94a3b8",
    LOW: "#94a3b8",
}

export default function EarningsPage() {
    const containerRef = useRef(null)
    const [bounties, setBounties] = useState<Bounty[]>([])
    const [apiStatus, setApiStatus] = useState<"online" | "offline" | "loading">("loading")

    const fetchData = async () => {
        try {
            setApiStatus("loading")
            const res = await authFetch(`${API_BASE}/api/db/bounties`)
            if (res.ok) {
                const data = await res.json()
                setBounties(data.bounties || [])
                setApiStatus("online")
            } else {
                setApiStatus("offline")
            }
        } catch (e) {
            console.error("Failed to fetch earnings data:", e)
            setApiStatus("offline")
        }
    }

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 30000)
        return () => clearInterval(interval)
    }, [])

    useGSAP(() => {
        gsap.from(".animate-item", {
            y: 20,
            opacity: 0,
            stagger: 0.1,
            duration: 0.6,
            ease: "power2.out",
            delay: 0.2
        })
    }, { scope: containerRef, dependencies: [bounties] })

    // Compute stats from real bounty data
    const paidBounties = bounties.filter(b => b.status === "PAID" || b.status === "Paid" || b.status === "Resolved")
    const totalEarnings = paidBounties.reduce((sum, b) => sum + (b.reward || 0), 0)
    const avgPerBug = paidBounties.length > 0 ? Math.round(totalEarnings / paidBounties.length) : 0

    // Build monthly earnings from real data
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const monthCounts: Record<string, number> = {}
    for (const b of paidBounties) {
        if (b.submitted_at) {
            const month = monthNames[new Date(b.submitted_at).getMonth()]
            monthCounts[month] = (monthCounts[month] || 0) + (b.reward || 0)
        }
    }
    const earningsByMonth = monthNames.map(m => ({ name: m, total: monthCounts[m] || 0 }))

    // Build severity distribution from real data
    const severityTotals: Record<string, number> = {}
    for (const b of paidBounties) {
        const sev = b.severity || "Unknown"
        severityTotals[sev] = (severityTotals[sev] || 0) + (b.reward || 0)
    }
    const distributionData = Object.entries(severityTotals).map(([name, value]) => ({
        name,
        value,
        color: SEVERITY_COLORS[name] || "#94a3b8"
    }))

    // Recent payouts from real data
    const recentPayouts = paidBounties
        .sort((a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime())
        .slice(0, 5)

    return (
        <SidebarProvider
            style={
                {
                    "--sidebar-width": "calc(var(--spacing) * 64)",
                    "--header-height": "calc(var(--spacing) * 12)",
                } as React.CSSProperties
            }
        >
            <AppSidebar variant="inset" />
            <SidebarInset>
                <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border/40 px-4 bg-background/50 backdrop-blur-md sticky top-0 z-10">
                    <div className="flex items-center gap-2 px-4">
                        <SidebarTrigger className="-ml-1" />
                    </div>
                    <div className="flex items-center gap-3">
                        <button onClick={fetchData} className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors">
                            <RefreshCw className={`w-4 h-4 text-muted-foreground ${apiStatus === "loading" ? "animate-spin" : ""}`} />
                        </button>
                        <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${apiStatus === "online" ? "bg-green-500/10 border-green-500/20 text-green-400"
                            : apiStatus === "loading" ? "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
                                : "bg-red-500/10 border-red-500/20 text-red-400"
                            }`}>
                            <div className={`w-1.5 h-1.5 rounded-full ${apiStatus === "online" ? "bg-green-400" : apiStatus === "loading" ? "bg-yellow-400 animate-pulse" : "bg-red-400"
                                }`} />
                            {apiStatus === "online" ? "Live Data" : apiStatus === "loading" ? "Loading..." : "Backend Offline"}
                        </div>
                    </div>
                </header>

                <div className="flex flex-1 flex-col p-4 md:p-8 pt-6 gap-8 max-w-7xl mx-auto w-full" ref={containerRef}>

                    <div className="space-y-1">
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Earnings</h1>
                        <p className="text-muted-foreground text-lg">Track your bug bounty rewards and payouts</p>
                    </div>

                    {apiStatus === "offline" && (
                        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-3">
                            <AlertCircle className="w-5 h-5 shrink-0" />
                            <span>Backend offline — cannot load earnings data. Connect to the API server.</span>
                        </div>
                    )}

                    <div className="grid gap-4 md:grid-cols-4">
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Total Earnings</CardTitle>
                                <DollarSign className="size-4 text-emerald-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-emerald-400">${totalEarnings.toLocaleString()}</div>
                                <p className="text-xs text-muted-foreground mt-1">Lifetime total</p>
                            </CardContent>
                        </Card>
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Reports Submitted</CardTitle>
                                <TrendingUp className="size-4 text-primary" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{bounties.length}</div>
                                <p className="text-xs text-muted-foreground mt-1">Total submissions</p>
                            </CardContent>
                        </Card>
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Fully Paid</CardTitle>
                                <CheckCircle className="size-4 text-blue-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{paidBounties.length}</div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {bounties.length > 0 ? `${Math.round(paidBounties.length / bounties.length * 100)}% success` : "No data yet"}
                                </p>
                            </CardContent>
                        </Card>
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Avg per Bug</CardTitle>
                                <CreditCard className="size-4 text-orange-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">${avgPerBug.toLocaleString()}</div>
                                <p className="text-xs text-muted-foreground mt-1">Based on paid reports</p>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="grid gap-4 md:grid-cols-7">
                        <Card className="animate-item md:col-span-4 bg-card/40 border-border/50">
                            <CardHeader>
                                <CardTitle>Earnings History</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[300px] w-full">
                                    {earningsByMonth.some(m => m.total > 0) ? (
                                        <ResponsiveContainer width="100%" height="100%">
                                            <BarChart data={earningsByMonth}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                                <XAxis dataKey="name" stroke="#666" fontSize={12} tickLine={false} axisLine={false} />
                                                <YAxis stroke="#666" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                                                <Tooltip
                                                    cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                                                    contentStyle={{ backgroundColor: '#171717', border: '1px solid #333', borderRadius: '8px' }}
                                                />
                                                <Bar dataKey="total" fill="#a855f7" radius={[4, 4, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    ) : (
                                        <div className="flex items-center justify-center h-full text-muted-foreground">
                                            <p>No earnings data yet</p>
                                        </div>
                                    )}
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="animate-item md:col-span-3 bg-card/40 border-border/50">
                            <CardHeader>
                                <CardTitle>Income Source</CardTitle>
                                <CardDescription>By severity level</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[300px] w-full">
                                    {distributionData.length > 0 ? (
                                        <ResponsiveContainer width="100%" height="100%">
                                            <PieChart>
                                                <Pie
                                                    data={distributionData}
                                                    cx="50%"
                                                    cy="50%"
                                                    innerRadius={70}
                                                    outerRadius={90}
                                                    paddingAngle={5}
                                                    dataKey="value"
                                                >
                                                    {distributionData.map((entry, index) => (
                                                        <Cell key={`cell-${index}`} fill={entry.color} stroke="rgba(0,0,0,0)" />
                                                    ))}
                                                </Pie>
                                                <Tooltip
                                                    contentStyle={{ backgroundColor: '#171717', border: '1px solid #333', borderRadius: '8px' }}
                                                    itemStyle={{ color: '#e5e5e5' }}
                                                />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    ) : (
                                        <div className="flex items-center justify-center h-full text-muted-foreground">
                                            <p>No severity distribution data</p>
                                        </div>
                                    )}
                                </div>
                                <div className="flex justify-center gap-4 text-xs text-muted-foreground">
                                    {distributionData.map(d => (
                                        <div key={d.name} className="flex items-center gap-1">
                                            <div className="size-2 rounded-full" style={{ backgroundColor: d.color }}></div>
                                            {d.name}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    <Card className="animate-item bg-card/40 border-border/50">
                        <CardHeader>
                            <CardTitle>Recent Payouts</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {recentPayouts.length > 0 ? recentPayouts.map((payout, i) => (
                                    <div key={payout.id || i} className="flex items-center justify-between border-b border-border/40 pb-4 last:border-0 last:pb-0">
                                        <div>
                                            <div className="font-medium text-lg">{payout.title}</div>
                                            <div className="text-sm text-muted-foreground">
                                                {payout.submitted_at ? new Date(payout.submitted_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : "Unknown date"}
                                            </div>
                                        </div>
                                        <div className="text-right">
                                            <div className="font-bold text-green-500">${(payout.reward || 0).toLocaleString()}</div>
                                            <div className="text-xs text-muted-foreground">{payout.status}</div>
                                        </div>
                                    </div>
                                )) : (
                                    <div className="text-center py-8 text-muted-foreground">
                                        <p>{apiStatus === "online" ? "No payouts yet" : "Waiting for backend connection..."}</p>
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
