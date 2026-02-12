"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"

import { useIsMobile } from "@/hooks/use-mobile"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group"

export const description = "An interactive area chart with real data"

const chartConfig = {
  visitors: {
    label: "Visitors",
  },
  desktop: {
    label: "Desktop",
    color: "var(--primary)",
  },
  mobile: {
    label: "Mobile",
    color: "var(--primary)",
  },
} satisfies ChartConfig

interface ChartDataPoint {
  date: string
  desktop: number
  mobile: number
}

export function ChartAreaInteractive() {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState("90d")
  const [chartData, setChartData] = React.useState<ChartDataPoint[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d")
    }
  }, [isMobile])

  // Fetch real data from API
  React.useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const response = await fetch("http://localhost:8000/api/db/activity?limit=90")
        if (!response.ok) throw new Error("Backend unavailable")
        const data = await response.json()

        // Transform activity data into chart format
        const activityByDate: Record<string, { desktop: number; mobile: number }> = {}

        if (data.activities && Array.isArray(data.activities)) {
          data.activities.forEach((activity: { created_at?: string }) => {
            const dateStr = activity.created_at
              ? new Date(activity.created_at).toISOString().split("T")[0]
              : new Date().toISOString().split("T")[0]

            if (!activityByDate[dateStr]) {
              activityByDate[dateStr] = { desktop: 0, mobile: 0 }
            }
            activityByDate[dateStr].desktop += 1
          })
        }

        const transformed = Object.entries(activityByDate)
          .map(([date, counts]) => ({ date, ...counts }))
          .sort((a, b) => a.date.localeCompare(b.date))

        setChartData(transformed)
        setError(null)
      } catch {
        setError("Backend Offline")
        setChartData([])
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const filteredData = chartData.filter((item) => {
    const date = new Date(item.date)
    const now = new Date()
    let daysToSubtract = 90
    if (timeRange === "30d") daysToSubtract = 30
    else if (timeRange === "7d") daysToSubtract = 7
    const startDate = new Date(now)
    startDate.setDate(startDate.getDate() - daysToSubtract)
    return date >= startDate
  })

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>System Activity</CardTitle>
        <CardDescription>
          {error ? (
            <span className="text-red-500 font-medium">{error}</span>
          ) : loading ? (
            <span className="text-muted-foreground">Loading...</span>
          ) : (
            <>
              <span className="hidden @[540px]/card:block">
                Activity for the selected period
              </span>
              <span className="@[540px]/card:hidden">Activity</span>
            </>
          )}
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={timeRange}
            onValueChange={setTimeRange}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
          >
            <ToggleGroupItem value="90d">Last 3 months</ToggleGroupItem>
            <ToggleGroupItem value="30d">Last 30 days</ToggleGroupItem>
            <ToggleGroupItem value="7d">Last 7 days</ToggleGroupItem>
          </ToggleGroup>
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger
              className="flex w-40 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
              aria-label="Select a value"
            >
              <SelectValue placeholder="Last 3 months" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="90d" className="rounded-lg">Last 3 months</SelectItem>
              <SelectItem value="30d" className="rounded-lg">Last 30 days</SelectItem>
              <SelectItem value="7d" className="rounded-lg">Last 7 days</SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        {filteredData.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-[250px] text-muted-foreground">
            {error ? "Unable to load data" : "No activity data"}
          </div>
        ) : (
          <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
            <AreaChart data={filteredData}>
              <defs>
                <linearGradient id="fillDesktop" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-desktop)" stopOpacity={1.0} />
                  <stop offset="95%" stopColor="var(--color-desktop)" stopOpacity={0.1} />
                </linearGradient>
                <linearGradient id="fillMobile" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--color-mobile)" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="var(--color-mobile)" stopOpacity={0.1} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="date"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={32}
                tickFormatter={(value) => {
                  const date = new Date(value)
                  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
                }}
              />
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) =>
                      new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric" })
                    }
                    indicator="dot"
                  />
                }
              />
              <Area dataKey="mobile" type="natural" fill="url(#fillMobile)" stroke="var(--color-mobile)" stackId="a" />
              <Area dataKey="desktop" type="natural" fill="url(#fillDesktop)" stroke="var(--color-desktop)" stackId="a" />
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
