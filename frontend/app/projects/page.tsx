"use client"

import { useEffect, useRef, useState } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { Calendar, Globe, Plus } from "lucide-react"

import { API_BASE } from "@/lib/api-base"
import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"

type TargetRecord = {
    id: string
    program_name: string
    scope?: string
    payout_tier?: string
    status?: string
    created_at?: string
}

function payoutToProgress(payoutTier?: string): number {
    switch ((payoutTier || "").toUpperCase()) {
        case "HIGH":
            return 90
        case "MEDIUM":
            return 60
        case "LOW":
            return 35
        default:
            return 10
    }
}

export default function ProjectsPage() {
    const containerRef = useRef(null)
    const [targets, setTargets] = useState<TargetRecord[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useGSAP(() => {
        gsap.from(".animate-card", {
            y: 30,
            opacity: 0,
            stagger: 0.1,
            duration: 0.6,
            ease: "power2.out",
            delay: 0.2,
        })
    }, { scope: containerRef, dependencies: [targets.length, loading, error] })

    useEffect(() => {
        let cancelled = false
        const loadTargets = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/db/targets?limit=100`, { cache: "no-store" })
                if (!response.ok) {
                    throw new Error(`Request failed: ${response.status}`)
                }
                const payload = await response.json()
                if (!cancelled) {
                    setTargets(Array.isArray(payload.targets) ? payload.targets : [])
                    setError(null)
                }
            } catch (err) {
                if (!cancelled) {
                    setTargets([])
                    setError(err instanceof Error ? err.message : "Failed to load target programs")
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        void loadTargets()
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
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">Projects</h1>
                            <p className="text-muted-foreground text-lg">Registered target programs and scopes from the live backend</p>
                        </div>
                        <Button className="bg-green-600 hover:bg-green-700 text-white gap-2" disabled>
                            <Plus className="size-4" /> Add Target
                        </Button>
                    </div>

                    {error && (
                        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-300">
                            {error}
                        </div>
                    )}

                    {loading ? (
                        <div className="rounded-2xl border border-border/50 bg-card/40 p-10 text-center text-muted-foreground">
                            Loading live target programs...
                        </div>
                    ) : targets.length === 0 ? (
                        <div className="rounded-2xl border border-border/50 bg-card/40 p-10 text-center text-muted-foreground">
                            No target programs are registered in the backend yet.
                        </div>
                    ) : (
                        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                            {targets.map((target) => {
                                const status = target.status || "ACTIVE"
                                const progress = payoutToProgress(target.payout_tier)
                                return (
                                    <Card key={target.id} className="animate-card bg-card/40 border-border/50 hover:border-primary/50 transition-all hover:-translate-y-1 duration-300">
                                        <CardHeader>
                                            <div className="flex justify-between items-start mb-2">
                                                <Badge variant="outline" className="border-primary/50 text-primary">
                                                    {status}
                                                </Badge>
                                                <span className="text-xs text-muted-foreground flex items-center gap-1">
                                                    <Calendar className="size-3" /> {target.created_at || "Unknown"}
                                                </span>
                                            </div>
                                            <CardTitle className="text-xl">{target.program_name}</CardTitle>
                                            <CardDescription className="line-clamp-2">{target.scope || "Scope unavailable"}</CardDescription>
                                        </CardHeader>
                                        <CardContent className="space-y-4">
                                            <div className="flex justify-between items-end">
                                                <span className="text-sm font-medium">Payout tier: {target.payout_tier || "UNKNOWN"}</span>
                                                <Globe className="size-4 text-muted-foreground" />
                                            </div>
                                            <Progress value={progress} className="h-2 bg-primary/20" />
                                        </CardContent>
                                        <CardFooter className="pt-0">
                                            <Button variant="ghost" className="w-full text-muted-foreground hover:text-foreground" disabled>
                                                Live target record
                                            </Button>
                                        </CardFooter>
                                    </Card>
                                )
                            })}
                        </div>
                    )}
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
