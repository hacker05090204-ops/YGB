"use client"

import { useState, useEffect, useRef } from "react"
import { authFetch } from "@/lib/ygb-api"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { ShieldAlert, CheckCircle, AlertTriangle, XCircle, Search, Play, FileText, RefreshCw, AlertCircle } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface SecurityData {
    critical: number
    high: number
    medium: number
    low: number
    passed: number
    failed: number
    warnings: number
    total: number
    riskScore: number
}

export default function SecurityPage() {
    const containerRef = useRef(null)
    const [secData, setSecData] = useState<SecurityData>({ critical: 0, high: 0, medium: 0, low: 0, passed: 0, failed: 0, warnings: 0, total: 0, riskScore: 0 })
    const [apiStatus, setApiStatus] = useState<"online" | "offline" | "loading">("loading")
    const [lastScan, setLastScan] = useState<string | null>(null)

    const fetchSecurityData = async () => {
        try {
            setApiStatus("loading")
            const res = await authFetch(`${API_BASE}/api/db/bounties`)
            if (res.ok) {
                const data = await res.json()
                const bounties = data.bounties || []

                // Compute security stats from real bounty data
                const critical = bounties.filter((b: any) => b.severity === "Critical" || b.severity === "CRITICAL").length
                const high = bounties.filter((b: any) => b.severity === "High" || b.severity === "HIGH").length
                const medium = bounties.filter((b: any) => b.severity === "Medium" || b.severity === "MEDIUM").length
                const low = bounties.filter((b: any) => b.severity === "Low" || b.severity === "LOW").length
                const resolved = bounties.filter((b: any) => b.status === "PAID" || b.status === "Resolved").length
                const rejected = bounties.filter((b: any) => b.status === "REJECTED" || b.status === "Rejected").length
                const pending = bounties.filter((b: any) => b.status === "PENDING" || b.status === "Open" || b.status === "In Progress").length
                const total = bounties.length

                // Risk score: higher with more unresolved critical/high
                const unresolvedCritical = bounties.filter((b: any) => (b.severity === "Critical" || b.severity === "CRITICAL") && b.status !== "PAID" && b.status !== "Resolved").length
                const unresolvedHigh = bounties.filter((b: any) => (b.severity === "High" || b.severity === "HIGH") && b.status !== "PAID" && b.status !== "Resolved").length
                const riskScore = total > 0 ? Math.min(100, Math.round((unresolvedCritical * 20 + unresolvedHigh * 10 + pending * 2) / Math.max(1, total) * 100)) : 0

                setSecData({
                    critical,
                    high,
                    medium,
                    low,
                    passed: resolved,
                    failed: rejected,
                    warnings: pending,
                    total,
                    riskScore,
                })
                setApiStatus("online")
            } else {
                setApiStatus("offline")
            }
        } catch (e) {
            console.error("Failed to fetch security data:", e)
            setApiStatus("offline")
        }
    }

    useEffect(() => {
        fetchSecurityData()
        const interval = setInterval(fetchSecurityData, 30000)
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
    }, { scope: containerRef, dependencies: [secData] })

    const hasIssues = secData.critical > 0 || secData.high > 0

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
                        <button onClick={fetchSecurityData} className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors">
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
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Security Status</h1>
                        <p className="text-muted-foreground text-lg">Monitor your system's security health</p>
                    </div>

                    {apiStatus === "offline" && (
                        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-3">
                            <AlertCircle className="w-5 h-5 shrink-0" />
                            <span>Backend offline — security data unavailable.</span>
                        </div>
                    )}

                    <div className="grid gap-6 md:grid-cols-2">

                        {/* Main Status Panel */}
                        <Card className={`animate-item ${hasIssues ? "bg-red-950/20 border-red-900/50" : "bg-green-950/20 border-green-900/50"}`}>
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className={`p-3 ${hasIssues ? "bg-red-900/30" : "bg-green-900/30"} rounded-full ${hasIssues ? "text-red-500" : "text-green-500"}`}>
                                        <ShieldAlert className="size-8" />
                                    </div>
                                    <div>
                                        <CardTitle className={`text-2xl ${hasIssues ? "text-red-500" : "text-green-500"}`}>
                                            {hasIssues ? "Security Issues Detected" : secData.total === 0 ? "No Data Yet" : "All Clear"}
                                        </CardTitle>
                                        <CardDescription className={hasIssues ? "text-red-400/70" : "text-green-400/70"}>
                                            {hasIssues ? "Attention required" : secData.total === 0 ? "Submit bounty reports to populate" : "No critical issues found"}
                                        </CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="flex items-center justify-between">
                                <div className="space-y-4">
                                    <div className="flex items-center gap-2 text-muted-foreground">
                                        <div className="size-2 rounded-full bg-red-500"></div> {secData.critical} Critical Vulnerabilities
                                    </div>
                                    <div className="flex items-center gap-2 text-muted-foreground">
                                        <div className="size-2 rounded-full bg-orange-500"></div> {secData.high} High Severity Issues
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className={`text-5xl font-bold ${secData.riskScore > 50 ? "text-red-500" : secData.riskScore > 20 ? "text-orange-500" : "text-green-500"}`}>
                                        {secData.riskScore}%
                                    </div>
                                    <div className={`text-sm opacity-80 ${secData.riskScore > 50 ? "text-red-400" : secData.riskScore > 20 ? "text-orange-400" : "text-green-400"}`}>
                                        Risk Score
                                    </div>
                                </div>
                            </CardContent>
                            {hasIssues && (
                                <CardFooter>
                                    <Button variant="destructive" className="w-full">View Critical Issues</Button>
                                </CardFooter>
                            )}
                        </Card>

                        {/* Scan Stats */}
                        <div className="grid gap-4 grid-cols-2">
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold text-green-500">{secData.passed}</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <CheckCircle className="size-3" /> Resolved
                                </div>
                            </Card>
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold text-red-500">{secData.failed}</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <XCircle className="size-3" /> Rejected
                                </div>
                            </Card>
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold text-orange-500">{secData.warnings}</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <AlertTriangle className="size-3" /> Pending
                                </div>
                            </Card>
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold">{secData.total}</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <Search className="size-3" /> Total Reports
                                </div>
                            </Card>
                        </div>
                    </div>

                    {/* Action Panel */}
                    <Card className="animate-item bg-card/40 border-border/50">
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <CardTitle>Run Security Scans</CardTitle>
                                <span className="text-xs text-muted-foreground">
                                    {apiStatus === "online" ? "Backend connected" : "Backend offline"}
                                </span>
                            </div>
                        </CardHeader>
                        <CardContent className="grid gap-4 md:grid-cols-4">
                            <Button variant="outline" className="h-24 flex flex-col gap-2 hover:border-primary hover:bg-primary/5 hover:text-primary">
                                <Search className="size-6" />
                                Vulnerability Scan
                            </Button>
                            <Button variant="outline" className="h-24 flex flex-col gap-2 hover:border-primary hover:bg-primary/5 hover:text-primary">
                                <ShieldAlert className="size-6" />
                                Malware Detection
                            </Button>
                            <Button variant="outline" className="h-24 flex flex-col gap-2 hover:border-primary hover:bg-primary/5 hover:text-primary">
                                <FileText className="size-6" />
                                Compliance Check
                            </Button>
                            <Button variant="outline" className="h-24 flex flex-col gap-2 hover:border-primary hover:bg-primary/5 hover:text-primary">
                                <Play className="size-6" />
                                Penetration Test
                            </Button>
                        </CardContent>
                    </Card>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
