"use client"

import { useState, useEffect, useRef } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { FolderOpen, Calendar, Clock, Plus, RefreshCw, AlertCircle } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface Project {
    id: string
    title: string
    desc: string
    progress: number
    status: string
    due: string
}

export default function ProjectsPage() {
    const containerRef = useRef(null)
    const [projects, setProjects] = useState<Project[]>([])
    const [apiStatus, setApiStatus] = useState<"online" | "offline" | "loading">("loading")

    const fetchProjects = async () => {
        try {
            setApiStatus("loading")
            const res = await fetch(`${API_BASE}/api/db/targets`)
            if (res.ok) {
                const data = await res.json()
                const targets = data.targets || []
                const mapped = targets.map((t: any) => ({
                    id: t.id || crypto.randomUUID(),
                    title: t.program_name || "Untitled Project",
                    desc: t.scope || "No scope defined",
                    progress: t.status === "COMPLETED" ? 100 : t.status === "IN_PROGRESS" ? 60 : t.status === "ACTIVE" ? 30 : 10,
                    status: t.status === "COMPLETED" ? "Completed" : t.status === "IN_PROGRESS" ? "In Progress" : t.status === "ACTIVE" ? "Active" : "Planning",
                    due: t.created_at ? new Date(t.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : "TBD",
                }))
                setProjects(mapped)
                setApiStatus("online")
            } else {
                setApiStatus("offline")
            }
        } catch (e) {
            console.error("Failed to fetch projects:", e)
            setApiStatus("offline")
        }
    }

    useEffect(() => {
        fetchProjects()
        const interval = setInterval(fetchProjects, 30000)
        return () => clearInterval(interval)
    }, [])

    useGSAP(() => {
        gsap.from(".animate-card", {
            y: 30,
            opacity: 0,
            stagger: 0.1,
            duration: 0.6,
            ease: "power2.out",
            delay: 0.2
        })
    }, { scope: containerRef, dependencies: [projects] })

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
                        <button onClick={fetchProjects} className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors">
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
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">Projects</h1>
                            <p className="text-muted-foreground text-lg">Track development progress and milestones</p>
                        </div>
                        <Button className="bg-green-600 hover:bg-green-700 text-white gap-2">
                            <Plus className="size-4" /> New Development
                        </Button>
                    </div>

                    {apiStatus === "offline" && (
                        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-3">
                            <AlertCircle className="w-5 h-5 shrink-0" />
                            <span>Backend offline — cannot load project data.</span>
                        </div>
                    )}

                    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                        {projects.length > 0 ? projects.map((project) => (
                            <Card key={project.id} className="animate-card bg-card/40 border-border/50 hover:border-primary/50 transition-all hover:-translate-y-1 duration-300">
                                <CardHeader>
                                    <div className="flex justify-between items-start mb-2">
                                        <Badge variant="outline" className={`${project.status === "Completed" ? "border-green-500 text-green-500" :
                                            project.status === "In Progress" ? "border-blue-500 text-blue-500" :
                                                project.status === "Active" ? "border-orange-500 text-orange-500" :
                                                    "border-muted-foreground text-muted-foreground"
                                            }`}>{project.status}</Badge>
                                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                                            <Calendar className="size-3" /> {project.due}
                                        </span>
                                    </div>
                                    <CardTitle className="text-xl">{project.title}</CardTitle>
                                    <CardDescription className="line-clamp-2">{project.desc}</CardDescription>
                                </CardHeader>
                                <CardContent className="space-y-4">
                                    <div className="flex justify-between items-end">
                                        <span className="text-sm font-medium">{project.progress}% Complete</span>
                                    </div>
                                    <Progress value={project.progress} className={`h-2 ${project.status === "Completed" ? "bg-green-950" : "bg-primary/20"}`} />
                                </CardContent>
                                <CardFooter className="pt-0">
                                    <Button variant="ghost" className="w-full text-muted-foreground hover:text-foreground">View Details</Button>
                                </CardFooter>
                            </Card>
                        )) : (
                            <div className="col-span-full text-center py-16">
                                <FolderOpen className="w-12 h-12 text-muted-foreground/30 mx-auto mb-4" />
                                <p className="text-muted-foreground">
                                    {apiStatus === "online" ? "No projects yet. Add targets to get started!" : "Waiting for backend connection..."}
                                </p>
                            </div>
                        )}
                    </div>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
