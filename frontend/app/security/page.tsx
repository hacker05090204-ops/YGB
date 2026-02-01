"use client"

import { useRef } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { ShieldAlert, CheckCircle, AlertTriangle, XCircle, Search, Play, FileText } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export default function SecurityPage() {
    const containerRef = useRef(null)

    useGSAP(() => {
        gsap.from(".animate-item", {
            y: 20,
            opacity: 0,
            stagger: 0.1,
            duration: 0.6,
            ease: "power2.out",
            delay: 0.2
        })
    }, { scope: containerRef })

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
                </header>

                <div className="flex flex-1 flex-col p-4 md:p-8 pt-6 gap-8 max-w-7xl mx-auto w-full" ref={containerRef}>

                    <div className="space-y-1">
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Security Status</h1>
                        <p className="text-muted-foreground text-lg">Monitor your system’s security health</p>
                    </div>

                    <div className="grid gap-6 md:grid-cols-2">

                        {/* Main Status Panel */}
                        <Card className="animate-item bg-red-950/20 border-red-900/50">
                            <CardHeader>
                                <div className="flex items-center gap-3">
                                    <div className="p-3 bg-red-900/30 rounded-full text-red-500">
                                        <ShieldAlert className="size-8" />
                                    </div>
                                    <div>
                                        <CardTitle className="text-2xl text-red-500">Security Issues Detected</CardTitle>
                                        <CardDescription className="text-red-400/70">Immediate attention required</CardDescription>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="flex items-center justify-between">
                                <div className="space-y-4">
                                    <div className="flex items-center gap-2 text-muted-foreground">
                                        <div className="size-2 rounded-full bg-red-500"></div> 3 Critical Vulnerabilities
                                    </div>
                                    <div className="flex items-center gap-2 text-muted-foreground">
                                        <div className="size-2 rounded-full bg-orange-500"></div> 5 High Severity Issues
                                    </div>
                                </div>
                                <div className="text-center">
                                    <div className="text-5xl font-bold text-red-500">35%</div>
                                    <div className="text-sm text-red-400 opacity-80">Risk Score</div>
                                </div>
                            </CardContent>
                            <CardFooter>
                                <Button variant="destructive" className="w-full">View Critical Issues</Button>
                            </CardFooter>
                        </Card>

                        {/* Scan Stats */}
                        <div className="grid gap-4 grid-cols-2">
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold text-green-500">124</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <CheckCircle className="size-3" /> Passed
                                </div>
                            </Card>
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold text-red-500">18</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <XCircle className="size-3" /> Failed
                                </div>
                            </Card>
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold text-orange-500">5</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <AlertTriangle className="size-3" /> Warnings
                                </div>
                            </Card>
                            <Card className="animate-item bg-card/40 border-border/50 flex flex-col justify-center items-center py-6">
                                <div className="text-3xl font-bold">147</div>
                                <div className="text-sm text-muted-foreground flex items-center gap-1 mt-1">
                                    <Search className="size-3" /> Total Scans
                                </div>
                            </Card>
                        </div>
                    </div>

                    {/* Action Panel */}
                    <Card className="animate-item bg-card/40 border-border/50">
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <CardTitle>Run Security Scans</CardTitle>
                                <span className="text-xs text-muted-foreground">Last scan: 2 hours ago</span>
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
