"use client"

import { useState, useEffect, useRef } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { Bug, Filter, Plus, AlertCircle, CheckCircle, XCircle, RefreshCw } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface BugReport {
    id: string
    title: string
    severity: string
    reporter: string
    bounty: string
    status: string
}

export default function BugReportsPage() {
    const containerRef = useRef(null)
    const [bugs, setBugs] = useState<BugReport[]>([])
    const [apiStatus, setApiStatus] = useState<"online" | "offline" | "loading">("loading")

    const fetchBugs = async () => {
        try {
            setApiStatus("loading")
            const res = await fetch(`${API_BASE}/api/db/bounties`)
            if (res.ok) {
                const data = await res.json()
                const mapped = (data.bounties || []).map((b: any) => ({
                    id: b.id || `BUG-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
                    title: b.title || "Untitled Report",
                    severity: b.severity || "Medium",
                    reporter: b.user_name || "Unknown",
                    bounty: b.reward ? `$${b.reward.toLocaleString()}` : "$0",
                    status: b.status || "Open",
                }))
                setBugs(mapped)
                setApiStatus("online")
            } else {
                setApiStatus("offline")
            }
        } catch (e) {
            console.error("Failed to fetch bug reports:", e)
            setApiStatus("offline")
        }
    }

    useEffect(() => {
        fetchBugs()
        const interval = setInterval(fetchBugs, 30000)
        return () => clearInterval(interval)
    }, [])

    useGSAP(() => {
        gsap.from(".animate-item", {
            y: 20,
            opacity: 0,
            stagger: 0.05,
            duration: 0.5,
            ease: "power2.out",
            delay: 0.2
        })
    }, { scope: containerRef, dependencies: [bugs] })

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
                        <button onClick={fetchBugs} className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors">
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

                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">Bug Reports</h1>
                            <p className="text-muted-foreground text-lg">Track and manage vulnerability reports</p>
                        </div>
                        <Button className="bg-red-600 hover:bg-red-700 text-white gap-2">
                            <Plus className="size-4" /> New Hunt
                        </Button>
                    </div>

                    {apiStatus === "offline" && (
                        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-3">
                            <AlertCircle className="w-5 h-5 shrink-0" />
                            <span>Backend offline — cannot load real bug reports. Connect to the API server.</span>
                        </div>
                    )}

                    <Tabs defaultValue="all" className="w-full">
                        <div className="flex items-center justify-between mb-4">
                            <TabsList className="bg-card/50">
                                <TabsTrigger value="all">All Bugs ({bugs.length})</TabsTrigger>
                                <TabsTrigger value="open">Open ({bugs.filter(b => b.status === "Open" || b.status === "PENDING").length})</TabsTrigger>
                                <TabsTrigger value="progress">In Progress ({bugs.filter(b => b.status === "In Progress" || b.status === "APPROVED").length})</TabsTrigger>
                                <TabsTrigger value="resolved">Resolved ({bugs.filter(b => b.status === "Resolved" || b.status === "PAID").length})</TabsTrigger>
                            </TabsList>
                            <Button variant="outline" size="sm" className="gap-2">
                                <Filter className="size-3" /> Filter
                            </Button>
                        </div>

                        <TabsContent value="all" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.length > 0 ? bugs.map((bug, i) => (
                                    <BugCard key={bug.id} bug={bug} />
                                )) : (
                                    <div className="col-span-full text-center py-12">
                                        <Bug className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                                        <p className="text-muted-foreground">
                                            {apiStatus === "online" ? "No bug reports yet. Submit your first report!" : "Waiting for backend connection..."}
                                        </p>
                                    </div>
                                )}
                            </div>
                        </TabsContent>

                        <TabsContent value="open" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.filter(b => b.status === "Open" || b.status === "PENDING").map((bug, i) => (
                                    <BugCard key={bug.id} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                        <TabsContent value="progress" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.filter(b => b.status === "In Progress" || b.status === "APPROVED").map((bug, i) => (
                                    <BugCard key={bug.id} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                        <TabsContent value="resolved" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.filter(b => b.status === "Resolved" || b.status === "PAID").map((bug, i) => (
                                    <BugCard key={bug.id} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                    </Tabs>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}

function BugCard({ bug }: { bug: BugReport }) {
    return (
        <Card className="animate-item bg-card/40 border-border/50 hover:bg-card/60 transition-colors">
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start mb-1">
                    <Badge variant="outline" className={`
                        ${bug.severity === 'Critical' || bug.severity === 'CRITICAL' ? 'border-red-500/50 text-red-500 bg-red-500/10' :
                            bug.severity === 'High' || bug.severity === 'HIGH' ? 'border-orange-500/50 text-orange-500 bg-orange-500/10' :
                                bug.severity === 'Medium' || bug.severity === 'MEDIUM' ? 'border-yellow-500/50 text-yellow-500 bg-yellow-500/10' :
                                    'border-blue-500/50 text-blue-500 bg-blue-500/10'}
                    `}>{bug.severity}</Badge>
                    <span className="text-xs font-mono text-muted-foreground">{bug.id}</span>
                </div>
                <CardTitle className="text-lg leading-tight">{bug.title}</CardTitle>
                <CardDescription>Reported by <span className="text-foreground font-medium">{bug.reporter}</span></CardDescription>
            </CardHeader>
            <CardFooter className="pt-0 flex justify-between items-center">
                <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="bg-secondary/50">{bug.status}</Badge>
                </div>
                <div className="font-bold text-green-500">{bug.bounty}</div>
            </CardFooter>
        </Card>
    )
}
