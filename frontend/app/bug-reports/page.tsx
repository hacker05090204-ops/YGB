"use client"

import { useRef } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { Bug, Filter, Plus, AlertCircle, CheckCircle, XCircle } from "lucide-react"

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

const bugs = [
    { title: "Insecure Direct Object Reference", severity: "Critical", reporter: "bug_hunter_99", bounty: "$5,000", status: "Open", id: "BUG-101" },
    { title: "Path Traversal in File Download", severity: "High", reporter: "security_pro", bounty: "$2,500", status: "In Progress", id: "BUG-102" },
    { title: "Remote Code Execution via File Upload", severity: "Critical", reporter: "root_access", bounty: "$10,000", status: "Open", id: "BUG-103" },
    { title: "SSRF on Image Proxy", severity: "High", reporter: "net_ninja", bounty: "$3,000", status: "Resolved", id: "BUG-104" },
    { title: "Broken Access Control", severity: "Medium", reporter: "web_wizard", bounty: "$1,000", status: "Open", id: "BUG-105" },
    { title: "Sensitive Data Exposure in API", severity: "High", reporter: "data_leaker", bounty: "$2,800", status: "Draft", id: "BUG-106" },
    { title: "Authentication Bypass", severity: "Critical", reporter: "zero_day", bounty: "$7,500", status: "Rejected", id: "BUG-107" },
    { title: "CSRF Token Bypass", severity: "Medium", reporter: "form_breaker", bounty: "$800", status: "In Progress", id: "BUG-108" },
    { title: "SQL Injection in Login", severity: "Critical", reporter: "db_admin", bounty: "$6,000", status: "Resolved", id: "BUG-109" },
    { title: "XSS Vulnerability in Comments", severity: "Low", reporter: "script_middie", bounty: "$300", status: "Open", id: "BUG-110" },
]

export default function BugReportsPage() {
    const containerRef = useRef(null)

    useGSAP(() => {
        gsap.from(".animate-item", {
            y: 20,
            opacity: 0,
            stagger: 0.05,
            duration: 0.5,
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

                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">Bug Reports</h1>
                            <p className="text-muted-foreground text-lg">Track and manage vulnerability reports</p>
                        </div>
                        <Button className="bg-red-600 hover:bg-red-700 text-white gap-2">
                            <Plus className="size-4" /> New Hunt
                        </Button>
                    </div>

                    <Tabs defaultValue="all" className="w-full">
                        <div className="flex items-center justify-between mb-4">
                            <TabsList className="bg-card/50">
                                <TabsTrigger value="all">All Bugs</TabsTrigger>
                                <TabsTrigger value="open">Open</TabsTrigger>
                                <TabsTrigger value="progress">In Progress</TabsTrigger>
                                <TabsTrigger value="resolved">Resolved</TabsTrigger>
                            </TabsList>
                            <Button variant="outline" size="sm" className="gap-2">
                                <Filter className="size-3" /> Filter
                            </Button>
                        </div>

                        <TabsContent value="all" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.map((bug, i) => (
                                    <BugCard key={i} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                        {/* For brevity in this demo, showing 'all' content for other tabs or just filtered */}
                        <TabsContent value="open" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.filter(b => b.status === "Open").map((bug, i) => (
                                    <BugCard key={i} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                        <TabsContent value="progress" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.filter(b => b.status === "In Progress").map((bug, i) => (
                                    <BugCard key={i} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                        <TabsContent value="resolved" className="mt-0">
                            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {bugs.filter(b => b.status === "Resolved").map((bug, i) => (
                                    <BugCard key={i} bug={bug} />
                                ))}
                            </div>
                        </TabsContent>
                    </Tabs>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}

function BugCard({ bug }: { bug: any }) {
    return (
        <Card className="animate-item bg-card/40 border-border/50 hover:bg-card/60 transition-colors">
            <CardHeader className="pb-3">
                <div className="flex justify-between items-start mb-1">
                    <Badge variant="outline" className={`
                        ${bug.severity === 'Critical' ? 'border-red-500/50 text-red-500 bg-red-500/10' :
                            bug.severity === 'High' ? 'border-orange-500/50 text-orange-500 bg-orange-500/10' :
                                bug.severity === 'Medium' ? 'border-yellow-500/50 text-yellow-500 bg-yellow-500/10' :
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
