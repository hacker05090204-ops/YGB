"use client"

import { useRef } from "react"
import gsap from "gsap"
import { useGSAP } from "@gsap/react"
import { DollarSign, TrendingUp, CheckCircle, CreditCard, ArrowUpRight } from "lucide-react"
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, CartesianGrid } from "recharts"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

const earningsByMonth = [
    { name: 'Jan', total: 4000 },
    { name: 'Feb', total: 3000 },
    { name: 'Mar', total: 9800 },
    { name: 'Apr', total: 3908 },
    { name: 'May', total: 4800 },
    { name: 'Jun', total: 3800 },
    { name: 'Jul', total: 4300 },
]

const distributionData = [
    { name: "Critical", value: 15000, color: "#a855f7" },
    { name: "High", value: 8000, color: "#3b82f6" },
    { name: "Medium", value: 3000, color: "#06b6d4" },
    { name: "Low", value: 500, color: "#94a3b8" },
]

const payouts = [
    { title: "Critical RCE in Payment Gateway", date: "Jan 12, 2024", amount: "$5,000", status: "Paid" },
    { title: "Stored XSS in User Profile", date: "Jan 08, 2024", amount: "$1,500", status: "Paid" },
    { title: "IDOR on Order History", date: "Dec 28, 2023", amount: "$2,000", status: "Paid" },
    { title: "Information Disclosure via API", date: "Dec 15, 2023", amount: "$800", status: "Paid" },
    { title: "Logic Flaw in Coupon System", date: "Nov 30, 2023", amount: "$3,500", status: "Paid" },
]

export default function EarningsPage() {
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
                        <h1 className="text-3xl font-bold tracking-tight text-foreground">Earnings</h1>
                        <p className="text-muted-foreground text-lg">Track your bug bounty rewards and payouts</p>
                    </div>

                    <div className="grid gap-4 md:grid-cols-4">
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Total Earnings</CardTitle>
                                <DollarSign className="size-4 text-emerald-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-emerald-400">$26,500</div>
                                <p className="text-xs text-muted-foreground mt-1">Lifetime total</p>
                            </CardContent>
                        </Card>
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Reports Submitted</CardTitle>
                                <TrendingUp className="size-4 text-primary" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">42</div>
                                <p className="text-xs text-muted-foreground mt-1">This year</p>
                            </CardContent>
                        </Card>
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Fully Paid</CardTitle>
                                <CheckCircle className="size-4 text-blue-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">38</div>
                                <p className="text-xs text-muted-foreground mt-1">90% success</p>
                            </CardContent>
                        </Card>
                        <Card className="animate-item bg-card/40 border-border/50">
                            <CardHeader className="flex flex-row items-center justify-between pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">Avg per Bug</CardTitle>
                                <CreditCard className="size-4 text-orange-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">$630</div>
                                <p className="text-xs text-muted-foreground mt-1">Estimated</p>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="grid gap-4 md:grid-cols-7">
                        <Card className="animate-item md:col-span-4 bg-card/40 border-border/50">
                            <CardHeader>
                                <CardTitle>Earnings History</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[300px] w-full">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <BarChart data={earningsByMonth}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#333" vertical={false} />
                                            <XAxis dataKey="name" stroke="#666" fontSize={12} tickLine={false} axisLine={false} />
                                            <YAxis stroke="#666" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                                            <Tooltip
                                                cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                                                contentStyle={{ backgroundColor: '#171717', border: '1px solid #333', borderRadius: '8px' }}
                                            />
                                            <Bar dataKey="total" fill="#a855f7" radius={[4, 4, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="animate-item md:col-span-3 bg-card/40 border-border/50">
                            <CardHeader>
                                <CardTitle>Income Source</CardTitle>
                                <CardDescription>By severity level</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="h-[300px] w-full">
                                    <ResponsiveContainer width="100%" height="100%">
                                        <PieChart>
                                            <Pie
                                                data={distributionData}
                                                cx="50%"
                                                cy="50%"
                                                innerRadius={70}
                                                outerRadius={90}
                                                paddingAngle={5}
                                                dataKey="value"
                                            >
                                                {distributionData.map((entry, index) => (
                                                    <Cell key={`cell-${index}`} fill={entry.color} stroke="rgba(0,0,0,0)" />
                                                ))}
                                            </Pie>
                                            <Tooltip
                                                contentStyle={{ backgroundColor: '#171717', border: '1px solid #333', borderRadius: '8px' }}
                                                itemStyle={{ color: '#e5e5e5' }}
                                            />
                                        </PieChart>
                                    </ResponsiveContainer>
                                </div>
                                <div className="flex justify-center gap-4 text-xs text-muted-foreground">
                                    {distributionData.map(d => (
                                        <div key={d.name} className="flex items-center gap-1">
                                            <div className="size-2 rounded-full" style={{ backgroundColor: d.color }}></div>
                                            {d.name}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    <Card className="animate-item bg-card/40 border-border/50">
                        <CardHeader>
                            <CardTitle>Recent Payouts</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-4">
                                {payouts.map((payout, i) => (
                                    <div key={i} className="flex items-center justify-between border-b border-border/40 pb-4 last:border-0 last:pb-0">
                                        <div>
                                            <div className="font-medium text-lg">{payout.title}</div>
                                            <div className="text-sm text-muted-foreground">{payout.date}</div>
                                        </div>
                                        <div className="text-right">
                                            <div className="font-bold text-green-500">{payout.amount}</div>
                                            <div className="text-xs text-muted-foreground">{payout.status}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>

                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
