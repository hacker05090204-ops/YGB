"use client"

import { useEffect, useRef, useState } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { Filter, Plus } from "lucide-react"

import { API_BASE } from "@/lib/api-base"
import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

type BountyRecord = {
    id: string
    title: string
    severity?: string
    status?: string
    reward?: number | null
    user_name?: string | null
}

const FILTERS = ["all", "OPEN", "IN_PROGRESS", "RESOLVED", "REJECTED", "DRAFT"] as const

export default function BugReportsPage() {
    const containerRef = useRef(null)
    const [bugs, setBugs] = useState<BountyRecord[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useGSAP(() => {
        gsap.from(".animate-item", {
            y: 20,
            opacity: 0,
            stagger: 0.05,
            duration: 0.5,
            ease: "power2.out",
            delay: 0.2,
        })
    }, { scope: containerRef, dependencies: [bugs.length, loading, error] })

    useEffect(() => {
        let cancelled = false

        const loadBounties = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/db/bounties?limit=100`, { cache: "no-store" })
                if (!response.ok) {
                    throw new Error(`Request failed: ${response.status}`)
                }
                const payload = await response.json()
                if (!cancelled) {
                    setBugs(Array.isArray(payload.bounties) ? payload.bounties : [])
                    setError(null)
                }
            } catch (err) {
                if (!cancelled) {
                    setBugs([])
                    setError(err instanceof Error ? err.message : "Failed to load bug reports")
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
                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">Bug Reports</h1>
                            <p className="text-muted-foreground text-lg">Live bounty records from the backend data store</p>
                        </div>
                        <Button className="bg-red-600 hover:bg-red-700 text-white gap-2" disabled>
                            <Plus className="size-4" /> New Hunt
                        </Button>
                    </div>

                    {error && (
                        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
                            {error}
                        </div>
                    )}

                    <Tabs defaultValue="all" className="w-full">
                        <div className="flex items-center justify-between mb-4">
                            <TabsList className="bg-card/50">
                                {FILTERS.map((filter) => (
                                    <TabsTrigger key={filter} value={filter.toLowerCase()}>{filter === "all" ? "All Reports" : filter.replace("_", " ")}</TabsTrigger>
                                ))}
                            </TabsList>
                            <Button variant="outline" size="sm" className="gap-2" disabled>
                                <Filter className="size-3" /> Live Filter
                            </Button>
                        </div>

                        {FILTERS.map((filter) => {
                            const filtered = filter === "all"
                                ? bugs
                                : bugs.filter((bug) => (bug.status || "").toUpperCase() === filter)
                            return (
                                <TabsContent key={filter} value={filter.toLowerCase()} className="mt-0">
                                    {loading ? (
                                        <div className="rounded-2xl border border-border/50 bg-card/40 p-10 text-center text-muted-foreground">
                                            Loading live bug reports...
                                        </div>
                                    ) : filtered.length === 0 ? (
                                        <div className="rounded-2xl border border-border/50 bg-card/40 p-10 text-center text-muted-foreground">
                                            No live bug reports found for this filter.
                                        </div>
                                    ) : (
                                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                            {filtered.map((bug) => (
                                                <BugCard key={bug.id} bug={bug} />
                                            ))}
                                        </div>
                                    )}
                                </TabsContent>
                            )
                        })}
                    </Tabs>
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}

function BugCard({ bug }: { bug: BountyRecord }) {
    const severity = (bug.severity || "UNKNOWN").toUpperCase()
    const status = bug.status || "UNKNOWN"
    const reward = typeof bug.reward === "number" ? `$${bug.reward.toFixed(2)}` : "Unrewarded"

    return (
        <Card className="animate-item bg-card/40 border-border/50 hover:bg-card/60 transition-colors">
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start mb-1">
                    <Badge variant="outline" className={
                        severity === "CRITICAL"
                            ? "border-red-500/50 text-red-500 bg-red-500/10"
                            : severity === "HIGH"
                                ? "border-orange-500/50 text-orange-500 bg-orange-500/10"
                                : severity === "MEDIUM"
                                    ? "border-yellow-500/50 text-yellow-500 bg-yellow-500/10"
                                    : "border-blue-500/50 text-blue-500 bg-blue-500/10"
                    }>
                        {severity}
                    </Badge>
                    <span className="text-xs font-mono text-muted-foreground">{bug.id}</span>
                </div>
                <CardTitle className="text-lg leading-tight">{bug.title}</CardTitle>
                <CardDescription>
                    Reporter: <span className="text-foreground font-medium">{bug.user_name || "Unknown user"}</span>
                </CardDescription>
            </CardHeader>
            <CardFooter className="pt-0 flex justify-between items-center">
                <Badge variant="secondary" className="bg-secondary/50">{status}</Badge>
                <div className="font-bold text-green-500">{reward}</div>
            </CardFooter>
        </Card>
    )
}
