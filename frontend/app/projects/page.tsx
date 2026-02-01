"use client"

import { useRef } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { FolderOpen, Calendar, Clock, Plus } from "lucide-react"

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

const projects = [
    { title: "User Authentication Overhaul", desc: "Implementing OAuth2 and 2FA support.", progress: 78, status: "In Progress", due: "Feb 15" },
    { title: "Database Optimization", desc: "Sharding user tables for scalability.", progress: 45, status: "Review", due: "Mar 01" },
    { title: "API v2 Migration", desc: "Moving legacy endpoints to GraphQL.", progress: 92, status: "Testing", due: "Jan 30" },
    { title: "Mobile App Development", desc: "React Native specific implementations.", progress: 24, status: "Planning", due: "Apr 20" },
    { title: "Payment Gateway Integration", desc: "Stripe and Crypto payment support.", progress: 60, status: "In Progress", due: "Mar 10" },
    { title: "Q4 Security Audit", desc: "Internal penetration testing and reports.", progress: 100, status: "Completed", due: "Dec 31" },
    { title: "Security Audit 2024", desc: "External audit preparation.", progress: 10, status: "Planning", due: "Jun 15" },
]

export default function ProjectsPage() {
    const containerRef = useRef(null)

    useGSAP(() => {
        gsap.from(".animate-card", {
            y: 30,
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

                    <div className="flex items-center justify-between">
                        <div className="space-y-1">
                            <h1 className="text-3xl font-bold tracking-tight text-foreground">Projects</h1>
                            <p className="text-muted-foreground text-lg">Track development progress and milestones</p>
                        </div>
                        <Button className="bg-green-600 hover:bg-green-700 text-white gap-2">
                            <Plus className="size-4" /> New Development
                        </Button>
                    </div>

                    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                        {projects.map((project, i) => (
                            <Card key={i} className="animate-card bg-card/40 border-border/50 hover:border-primary/50 transition-all hover:-translate-y-1 duration-300">
                                <CardHeader>
                                    <div className="flex justify-between items-start mb-2">
                                        <Badge variant="outline" className={`${project.status === "Completed" ? "border-green-500 text-green-500" :
                                                project.status === "In Progress" ? "border-blue-500 text-blue-500" :
                                                    project.status === "Review" ? "border-orange-500 text-orange-500" :
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
                        ))}
                    </div>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
