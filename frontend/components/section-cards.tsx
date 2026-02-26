"use client"

import { useState, useEffect } from "react"
import { authFetch } from "@/lib/ygb-api"
import { IconTrendingDown, IconTrendingUp } from "@tabler/icons-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface AdminStats {
  total_users: number
  total_targets: number
  total_bounties: number
  active_sessions: number
  activity_24h: number
}

export function SectionCards() {
  const [stats, setStats] = useState<AdminStats | null>(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await authFetch(`${API_BASE}/api/db/admin/stats`)
        if (res.ok) {
          const data = await res.json()
          setStats(data.stats || null)
        }
      } catch (e) {
        console.error("Failed to fetch admin stats:", e)
      }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
      <Card className="@container/card">
        <CardHeader>
          <CardDescription>Total Users</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {stats?.total_users ?? "—"}
          </CardTitle>
          <CardAction>
            <Badge variant="outline">
              <IconTrendingUp />
              HDD
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">
            Registered hunters <IconTrendingUp className="size-4" />
          </div>
          <div className="text-muted-foreground">
            Stored on HDD engine
          </div>
        </CardFooter>
      </Card>
      <Card className="@container/card">
        <CardHeader>
          <CardDescription>Active Targets</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {stats?.total_targets ?? "—"}
          </CardTitle>
          <CardAction>
            <Badge variant="outline">
              <IconTrendingUp />
              Live
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">
            Bug bounty programs <IconTrendingUp className="size-4" />
          </div>
          <div className="text-muted-foreground">Real-time from HDD</div>
        </CardFooter>
      </Card>
      <Card className="@container/card">
        <CardHeader>
          <CardDescription>Bounty Submissions</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {stats?.total_bounties ?? "—"}
          </CardTitle>
          <CardAction>
            <Badge variant="outline">
              <IconTrendingUp />
              Reports
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">
            Vulnerability reports <IconTrendingUp className="size-4" />
          </div>
          <div className="text-muted-foreground">All stored on HDD</div>
        </CardFooter>
      </Card>
      <Card className="@container/card">
        <CardHeader>
          <CardDescription>Active Sessions</CardDescription>
          <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
            {stats?.active_sessions ?? "—"}
          </CardTitle>
          <CardAction>
            <Badge variant="outline">
              {(stats?.active_sessions ?? 0) > 0 ? (
                <><IconTrendingUp /> Live</>
              ) : (
                <><IconTrendingDown /> Idle</>
              )}
            </Badge>
          </CardAction>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-1.5 text-sm">
          <div className="line-clamp-1 flex gap-2 font-medium">
            {(stats?.active_sessions ?? 0) > 0 ? "Sessions active" : "No active sessions"}
            {(stats?.active_sessions ?? 0) > 0 ? <IconTrendingUp className="size-4" /> : <IconTrendingDown className="size-4" />}
          </div>
          <div className="text-muted-foreground">
            {stats?.activity_24h ?? 0} audit events
          </div>
        </CardFooter>
      </Card>
    </div>
  )
}
