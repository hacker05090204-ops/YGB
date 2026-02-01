"use client"

import * as React from "react"
import { useRef } from "react"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  Bug,
  FolderOpen,
  DollarSign,
  ShieldCheck,
  Settings,
  HelpCircle,
  Command,
  ShieldAlert,
  Play,
} from "lucide-react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"

import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarGroup,
  SidebarGroupContent,
} from "@/components/ui/sidebar"

// Data Structure
const data = {
  user: {
    name: "BugHunter_01",
    email: "hunter@bugbounty.com",
    avatar: "/avatars/agnish.jpg",
  },
  navMain: [
    {
      title: "Dashboard",
      url: "/",
      icon: LayoutDashboard,
    },
    {
      title: "Bug Reports",
      url: "/bug-reports",
      icon: Bug,
    },
    {
      title: "Projects",
      url: "/projects",
      icon: FolderOpen,
    },
    {
      title: "Earnings",
      url: "/earnings",
      icon: DollarSign,
    },
    {
      title: "Security",
      url: "/security",
      icon: ShieldCheck,
    },
    {
      title: "Runner",
      url: "/runner",
      icon: Play,
    },
  ],
  navSecondary: [
    {
      title: "Settings",
      url: "/settings",
      icon: Settings,
    },
    {
      title: "Help",
      url: "#",
      icon: HelpCircle,
    },
  ]
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const containerRef = useRef(null)
  const pathname = usePathname()

  useGSAP(() => {
    // Staggered entry for menu items
    gsap.from(".sidebar-item", {
      x: -20,
      opacity: 0,
      stagger: 0.05,
      duration: 0.6,
      ease: "power2.out",
      delay: 0.2
    })

    // Header animation
    gsap.from(".sidebar-header", {
      y: -10,
      opacity: 0,
      duration: 0.6,
      ease: "power2.out"
    })

  }, { scope: containerRef })

  return (
    <Sidebar collapsible="offcanvas" {...props} ref={containerRef} className="border-r border-sidebar-border bg-sidebar">
      <SidebarHeader className="sidebar-header pb-4 pt-5">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <a href="/" className="group">
                <div className="flex aspect-square size-10 items-center justify-center rounded-lg bg-primary/20 text-primary ring-1 ring-primary/50 group-hover:bg-primary/30 group-hover:shadow-[0_0_15px_rgba(168,85,247,0.5)] transition-all duration-300">
                  <ShieldAlert className="size-6" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight ml-2">
                  <span className="truncate text-xl font-bold tracking-tight text-foreground">BugBounty</span>
                  <span className="truncate text-xs text-muted-foreground font-mono">v2.0 Secure</span>
                </div>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="gap-2">
              {data.navMain.map((item) => {
                const isActive = pathname === item.url
                return (
                  <SidebarMenuItem key={item.title} className="sidebar-item">
                    <SidebarMenuButton
                      asChild
                      tooltip={item.title}
                      isActive={isActive}
                      className="h-10 data-[active=true]:bg-primary/15 data-[active=true]:text-primary data-[active=true]:shadow-[0_0_20px_rgba(168,85,247,0.15)] hover:bg-white/5 transition-all duration-200"
                    >
                      <a href={item.url} className="flex items-center gap-3">
                        <item.icon className="size-5" />
                        <span className="font-medium text-base">{item.title}</span>
                      </a>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup className="mt-auto">
          <SidebarGroupContent>
            <SidebarMenu>
              {data.navSecondary.map((item) => (
                <SidebarMenuItem key={item.title} className="sidebar-item">
                  <SidebarMenuButton asChild tooltip={item.title} className="h-10 hover:bg-white/5 text-muted-foreground hover:text-foreground">
                    <a href={item.url} className="flex items-center gap-3">
                      <item.icon className="size-5" />
                      <span className="font-medium">{item.title}</span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="sidebar-item p-4">
        <NavUser user={data.user} />
      </SidebarFooter>
    </Sidebar>
  )
}
