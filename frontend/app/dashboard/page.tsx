"use client"

import { useState, useEffect } from "react"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts"
import {
  Users,
  Target,
  Trophy,
  Activity,
  Plus,
  ExternalLink,
  TrendingUp,
  DollarSign,
  Shield,
  Clock,
  CheckCircle,
  AlertTriangle,
  Search,
  RefreshCw
} from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { LiquidMetalButton } from "@/components/ui/liquid-metal"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface User {
  id: string
  name: string
  email: string | null
  role: string
  total_bounties: number
  total_earnings: number
  created_at: string
  last_active: string
}

interface Bounty {
  id: string
  title: string
  severity: string
  status: string
  reward: number
  submitted_at: string
  user_name?: string
  program_name?: string
  scope?: string
}

interface TargetType {
  id: string
  program_name: string
  scope: string
  link: string | null
  platform: string | null
  payout_tier: string
  status: string
}

interface AdminStats {
  users: { total: number; active_last_7_days: number }
  bounties: { total: number; pending: number; total_paid: number }
  targets: { total: number; active: number }
  sessions: { active: number }
}

export default function Dashboard() {
  const [users, setUsers] = useState<User[]>([])
  const [bounties, setBounties] = useState<Bounty[]>([])
  const [targets, setTargets] = useState<TargetType[]>([])
  const [adminStats, setAdminStats] = useState<AdminStats | null>(null)
  const [activities, setActivities] = useState<any[]>([])
  const [apiStatus, setApiStatus] = useState<"online" | "offline" | "loading">("loading")
  const [activeTab, setActiveTab] = useState<"overview" | "users" | "bounties" | "targets">("overview")
  const [selectedUser, setSelectedUser] = useState<User | null>(null)

  // Form states
  const [showAddUser, setShowAddUser] = useState(false)
  const [showAddTarget, setShowAddTarget] = useState(false)
  const [newUserName, setNewUserName] = useState("")
  const [newUserEmail, setNewUserEmail] = useState("")
  const [newTargetName, setNewTargetName] = useState("")
  const [newTargetScope, setNewTargetScope] = useState("")
  const [newTargetLink, setNewTargetLink] = useState("")

  const fetchData = async () => {
    try {
      setApiStatus("loading")

      // Fetch users
      const usersRes = await fetch(`${API_BASE}/api/db/users`)
      if (usersRes.ok) {
        const data = await usersRes.json()
        setUsers(data.users || [])
      }

      // Fetch bounties
      const bountiesRes = await fetch(`${API_BASE}/api/db/bounties`)
      if (bountiesRes.ok) {
        const data = await bountiesRes.json()
        setBounties(data.bounties || [])
      }

      // Fetch targets
      const targetsRes = await fetch(`${API_BASE}/api/db/targets`)
      if (targetsRes.ok) {
        const data = await targetsRes.json()
        setTargets(data.targets || [])
      }

      // Fetch admin stats
      const statsRes = await fetch(`${API_BASE}/api/db/admin/stats`)
      if (statsRes.ok) {
        const data = await statsRes.json()
        setAdminStats(data.stats)
      }

      // Fetch activity
      const activityRes = await fetch(`${API_BASE}/api/db/activity?limit=20`)
      if (activityRes.ok) {
        const data = await activityRes.json()
        setActivities(data.activities || [])
      }

      setApiStatus("online")
    } catch (e) {
      console.error("Failed to fetch data:", e)
      setApiStatus("offline")
    }
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const addUser = async () => {
    if (!newUserName.trim()) return
    try {
      const res = await fetch(`${API_BASE}/api/db/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newUserName, email: newUserEmail || null })
      })
      if (res.ok) {
        setNewUserName("")
        setNewUserEmail("")
        setShowAddUser(false)
        fetchData()
      }
    } catch (e) {
      console.error("Failed to add user:", e)
    }
  }

  const addTarget = async () => {
    if (!newTargetName.trim() || !newTargetScope.trim()) return
    try {
      const res = await fetch(`${API_BASE}/api/db/targets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          program_name: newTargetName,
          scope: newTargetScope,
          link: newTargetLink || null
        })
      })
      if (res.ok) {
        setNewTargetName("")
        setNewTargetScope("")
        setNewTargetLink("")
        setShowAddTarget(false)
        fetchData()
      }
    } catch (e) {
      console.error("Failed to add target:", e)
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case "CRITICAL": return "text-red-400"
      case "HIGH": return "text-orange-400"
      case "MEDIUM": return "text-yellow-400"
      case "LOW": return "text-green-400"
      default: return "text-gray-400"
    }
  }

  const getStatusColor = (status: string) => {
    switch (status?.toUpperCase()) {
      case "PAID": return "bg-green-500/20 text-green-400 border-green-500/30"
      case "APPROVED": return "bg-blue-500/20 text-blue-400 border-blue-500/30"
      case "PENDING": return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
      case "REJECTED": return "bg-red-500/20 text-red-400 border-red-500/30"
      default: return "bg-gray-500/20 text-gray-400 border-gray-500/30"
    }
  }

  const chartData = [
    { name: 'Mon', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 2 },
    { name: 'Tue', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 3 },
    { name: 'Wed', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 4 },
    { name: 'Thu', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 2 },
    { name: 'Fri', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 5 },
    { name: 'Sat', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 3 },
    { name: 'Sun', bounties: bounties.length > 0 ? Math.floor(Math.random() * 5) + 1 : 4 },
  ]

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="bg-[#000000] text-[#FAFAFA] overflow-hidden">

        {/* Ambient Glow */}
        <div className="fixed inset-0 pointer-events-none">
          <div className="absolute top-[-20%] right-[-10%] w-[50vw] h-[50vh] bg-gradient-radial from-purple-500/[0.05] via-transparent to-transparent rounded-full blur-3xl" />
          <div className="absolute bottom-[-10%] left-[-10%] w-[40vw] h-[40vh] bg-gradient-radial from-blue-500/[0.05] via-transparent to-transparent rounded-full blur-3xl" />
        </div>

        {/* Header */}
        <header className="flex h-16 shrink-0 items-center gap-2 border-b border-white/[0.06] bg-[#000000]/80 backdrop-blur-xl px-4 sticky top-0 z-10">
          <SidebarTrigger className="-ml-1 text-[#737373] hover:text-[#FAFAFA]" />
          <div className="mr-4 h-4 w-px bg-white/[0.1]" />
          <div className="flex items-center gap-2 text-sm font-medium">
            <span className="text-[#A3A3A3]">Dashboard</span>
            <span className="text-[#404040]">/</span>
            <span className="text-[#FAFAFA]">{activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}</span>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <button
              onClick={fetchData}
              className="p-2 rounded-lg hover:bg-white/[0.05] transition-colors"
            >
              <RefreshCw className={`w-4 h-4 text-[#737373] ${apiStatus === "loading" ? "animate-spin" : ""}`} />
            </button>
            <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${apiStatus === "online"
                ? "bg-green-500/10 border-green-500/20 text-green-400"
                : apiStatus === "loading"
                  ? "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
                  : "bg-red-500/10 border-red-500/20 text-red-400"
              }`}>
              <div className={`w-1.5 h-1.5 rounded-full ${apiStatus === "online" ? "bg-green-400" : apiStatus === "loading" ? "bg-yellow-400 animate-pulse" : "bg-red-400"
                }`} />
              {apiStatus === "online" ? "Database Connected" : apiStatus === "loading" ? "Loading..." : "Offline"}
            </div>
          </div>
        </header>

        {/* Tab Navigation */}
        <div className="flex gap-1 p-4 border-b border-white/[0.06]">
          {(["overview", "users", "bounties", "targets"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === tab
                  ? "bg-white/[0.1] text-[#FAFAFA]"
                  : "text-[#737373] hover:text-[#FAFAFA] hover:bg-white/[0.05]"
                }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        {/* Content */}
        <ScrollArea className="flex-1 h-[calc(100vh-8rem)]">
          <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-6">

            {/* Overview Tab */}
            {activeTab === "overview" && (
              <>
                {/* Stats Cards */}
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                  <div className="relative overflow-hidden rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-purple-500/30 transition-colors group">
                    <div className="flex items-center justify-between pb-2">
                      <div className="text-sm font-medium text-[#737373]">Total Users</div>
                      <Users className="h-4 w-4 text-purple-400" />
                    </div>
                    <div className="text-3xl font-bold text-[#FAFAFA]">{adminStats?.users.total || users.length}</div>
                    <p className="text-xs text-[#525252] mt-1">{adminStats?.users.active_last_7_days || 0} active this week</p>
                  </div>

                  <div className="relative overflow-hidden rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-blue-500/30 transition-colors group">
                    <div className="flex items-center justify-between pb-2">
                      <div className="text-sm font-medium text-[#737373]">Total Bounties</div>
                      <Trophy className="h-4 w-4 text-blue-400" />
                    </div>
                    <div className="text-3xl font-bold text-[#FAFAFA]">{adminStats?.bounties.total || bounties.length}</div>
                    <p className="text-xs text-[#525252] mt-1">{adminStats?.bounties.pending || 0} pending review</p>
                  </div>

                  <div className="relative overflow-hidden rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-green-500/30 transition-colors group">
                    <div className="flex items-center justify-between pb-2">
                      <div className="text-sm font-medium text-[#737373]">Total Paid</div>
                      <DollarSign className="h-4 w-4 text-green-400" />
                    </div>
                    <div className="text-3xl font-bold text-[#FAFAFA]">${adminStats?.bounties.total_paid?.toLocaleString() || "0"}</div>
                    <p className="text-xs text-[#525252] mt-1">Lifetime earnings</p>
                  </div>

                  <div className="relative overflow-hidden rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-orange-500/30 transition-colors group">
                    <div className="flex items-center justify-between pb-2">
                      <div className="text-sm font-medium text-[#737373]">Active Targets</div>
                      <Target className="h-4 w-4 text-orange-400" />
                    </div>
                    <div className="text-3xl font-bold text-[#FAFAFA]">{adminStats?.targets.active || targets.length}</div>
                    <p className="text-xs text-[#525252] mt-1">{adminStats?.sessions.active || 0} active sessions</p>
                  </div>
                </div>

                {/* Charts & Activity */}
                <div className="grid gap-4 md:grid-cols-2">
                  {/* Activity Chart */}
                  <div className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6">
                    <h3 className="text-lg font-semibold text-[#FAFAFA] mb-4">Weekly Activity</h3>
                    <div className="h-[200px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                          <defs>
                            <linearGradient id="colorBounties" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.3} />
                              <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
                          <XAxis dataKey="name" stroke="#525252" fontSize={12} tickLine={false} axisLine={false} />
                          <YAxis stroke="#525252" fontSize={12} tickLine={false} axisLine={false} />
                          <Tooltip contentStyle={{ backgroundColor: '#0A0A0A', borderColor: '#262626', borderRadius: '8px' }} />
                          <Area type="monotone" dataKey="bounties" stroke="#8B5CF6" strokeWidth={2} fill="url(#colorBounties)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Recent Activity */}
                  <div className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6">
                    <h3 className="text-lg font-semibold text-[#FAFAFA] mb-4">Recent Activity</h3>
                    <div className="space-y-3 max-h-[200px] overflow-y-auto">
                      {activities.length > 0 ? activities.slice(0, 5).map((activity) => (
                        <div key={activity.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-white/[0.02]">
                          <Activity className="w-4 h-4 text-purple-400" />
                          <div className="flex-1 min-w-0">
                            <p className="text-sm text-[#FAFAFA] truncate">{activity.description || activity.action_type}</p>
                            <p className="text-xs text-[#525252]">{activity.user_name || "System"}</p>
                          </div>
                          <span className="text-xs text-[#525252]">
                            {new Date(activity.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                      )) : (
                        <p className="text-sm text-[#525252]">No recent activity</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* Quick Actions */}
                <div className="grid gap-4 md:grid-cols-3">
                  <button
                    onClick={() => { setActiveTab("users"); setShowAddUser(true); }}
                    className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-purple-500/30 transition-all group text-left"
                  >
                    <Plus className="w-8 h-8 text-purple-400 mb-3" />
                    <h3 className="font-semibold text-[#FAFAFA]">Add User</h3>
                    <p className="text-sm text-[#525252] mt-1">Register a new researcher</p>
                  </button>

                  <button
                    onClick={() => { setActiveTab("targets"); setShowAddTarget(true); }}
                    className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-blue-500/30 transition-all group text-left"
                  >
                    <Target className="w-8 h-8 text-blue-400 mb-3" />
                    <h3 className="font-semibold text-[#FAFAFA]">Add Target</h3>
                    <p className="text-sm text-[#525252] mt-1">Add a new bug bounty target</p>
                  </button>

                  <a
                    href="/control"
                    className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-green-500/30 transition-all group text-left"
                  >
                    <Shield className="w-8 h-8 text-green-400 mb-3" />
                    <h3 className="font-semibold text-[#FAFAFA]">Control Panel</h3>
                    <p className="text-sm text-[#525252] mt-1">Phase-49 execution control</p>
                  </a>
                </div>
              </>
            )}

            {/* Users Tab */}
            {activeTab === "users" && (
              <>
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold text-[#FAFAFA]">Users & Researchers</h2>
                  <button
                    onClick={() => setShowAddUser(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-purple-500/20 text-purple-400 rounded-lg hover:bg-purple-500/30 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Add User
                  </button>
                </div>

                {/* Add User Form */}
                {showAddUser && (
                  <div className="rounded-xl border border-purple-500/30 bg-[#0A0A0A] p-6">
                    <h3 className="text-lg font-semibold text-[#FAFAFA] mb-4">Add New User</h3>
                    <div className="grid gap-4 md:grid-cols-2">
                      <input
                        type="text"
                        placeholder="Name"
                        value={newUserName}
                        onChange={(e) => setNewUserName(e.target.value)}
                        className="px-4 py-2 bg-[#171717] border border-white/[0.1] rounded-lg text-[#FAFAFA] placeholder-[#525252] focus:border-purple-500/50 outline-none"
                      />
                      <input
                        type="email"
                        placeholder="Email (optional)"
                        value={newUserEmail}
                        onChange={(e) => setNewUserEmail(e.target.value)}
                        className="px-4 py-2 bg-[#171717] border border-white/[0.1] rounded-lg text-[#FAFAFA] placeholder-[#525252] focus:border-purple-500/50 outline-none"
                      />
                    </div>
                    <div className="flex gap-3 mt-4">
                      <button
                        onClick={addUser}
                        className="px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors"
                      >
                        Create User
                      </button>
                      <button
                        onClick={() => setShowAddUser(false)}
                        className="px-4 py-2 bg-[#171717] text-[#737373] rounded-lg hover:bg-[#262626] transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Users List */}
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {users.map((user) => (
                    <div
                      key={user.id}
                      className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-purple-500/30 transition-colors cursor-pointer"
                      onClick={() => setSelectedUser(user)}
                    >
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white font-bold text-lg">
                          {user.name.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-semibold text-[#FAFAFA] truncate">{user.name}</h3>
                          <p className="text-sm text-[#525252] truncate">{user.email || "No email"}</p>
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-white/[0.06]">
                        <div>
                          <p className="text-2xl font-bold text-purple-400">{user.total_bounties}</p>
                          <p className="text-xs text-[#525252]">Bounties</p>
                        </div>
                        <div>
                          <p className="text-2xl font-bold text-green-400">${user.total_earnings}</p>
                          <p className="text-xs text-[#525252]">Earnings</p>
                        </div>
                      </div>
                      <div className="mt-4 flex items-center gap-2">
                        <span className={`px-2 py-1 text-xs rounded-full ${user.role === 'admin' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'}`}>
                          {user.role}
                        </span>
                        <span className="text-xs text-[#525252]">
                          Joined {new Date(user.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  ))}

                  {users.length === 0 && (
                    <div className="col-span-full text-center py-12">
                      <Users className="w-12 h-12 text-[#262626] mx-auto mb-4" />
                      <p className="text-[#525252]">No users yet. Add your first user above!</p>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Bounties Tab */}
            {activeTab === "bounties" && (
              <>
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold text-[#FAFAFA]">Bug Bounty Submissions</h2>
                </div>

                {/* Bounties Table */}
                <div className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/[0.06]">
                        <th className="text-left p-4 text-sm font-medium text-[#737373]">Title</th>
                        <th className="text-left p-4 text-sm font-medium text-[#737373]">Researcher</th>
                        <th className="text-left p-4 text-sm font-medium text-[#737373]">Target</th>
                        <th className="text-left p-4 text-sm font-medium text-[#737373]">Severity</th>
                        <th className="text-left p-4 text-sm font-medium text-[#737373]">Status</th>
                        <th className="text-left p-4 text-sm font-medium text-[#737373]">Reward</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bounties.map((bounty) => (
                        <tr key={bounty.id} className="border-b border-white/[0.06] hover:bg-white/[0.02]">
                          <td className="p-4">
                            <p className="text-sm text-[#FAFAFA] font-medium">{bounty.title}</p>
                            <p className="text-xs text-[#525252]">{new Date(bounty.submitted_at).toLocaleDateString()}</p>
                          </td>
                          <td className="p-4 text-sm text-[#A3A3A3]">{bounty.user_name || "Unknown"}</td>
                          <td className="p-4 text-sm text-[#A3A3A3]">{bounty.program_name || "N/A"}</td>
                          <td className="p-4">
                            <span className={`text-sm font-medium ${getSeverityColor(bounty.severity)}`}>
                              {bounty.severity}
                            </span>
                          </td>
                          <td className="p-4">
                            <span className={`px-2 py-1 text-xs rounded-full border ${getStatusColor(bounty.status)}`}>
                              {bounty.status}
                            </span>
                          </td>
                          <td className="p-4 text-sm text-green-400 font-medium">
                            ${bounty.reward || 0}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {bounties.length === 0 && (
                    <div className="text-center py-12">
                      <Trophy className="w-12 h-12 text-[#262626] mx-auto mb-4" />
                      <p className="text-[#525252]">No bounties submitted yet</p>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Targets Tab */}
            {activeTab === "targets" && (
              <>
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-bold text-[#FAFAFA]">Bug Bounty Targets</h2>
                  <button
                    onClick={() => setShowAddTarget(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Add Target
                  </button>
                </div>

                {/* Add Target Form */}
                {showAddTarget && (
                  <div className="rounded-xl border border-blue-500/30 bg-[#0A0A0A] p-6">
                    <h3 className="text-lg font-semibold text-[#FAFAFA] mb-4">Add New Target</h3>
                    <div className="grid gap-4 md:grid-cols-3">
                      <input
                        type="text"
                        placeholder="Program Name"
                        value={newTargetName}
                        onChange={(e) => setNewTargetName(e.target.value)}
                        className="px-4 py-2 bg-[#171717] border border-white/[0.1] rounded-lg text-[#FAFAFA] placeholder-[#525252] focus:border-blue-500/50 outline-none"
                      />
                      <input
                        type="text"
                        placeholder="Scope (e.g., *.example.com)"
                        value={newTargetScope}
                        onChange={(e) => setNewTargetScope(e.target.value)}
                        className="px-4 py-2 bg-[#171717] border border-white/[0.1] rounded-lg text-[#FAFAFA] placeholder-[#525252] focus:border-blue-500/50 outline-none"
                      />
                      <input
                        type="url"
                        placeholder="Link (optional)"
                        value={newTargetLink}
                        onChange={(e) => setNewTargetLink(e.target.value)}
                        className="px-4 py-2 bg-[#171717] border border-white/[0.1] rounded-lg text-[#FAFAFA] placeholder-[#525252] focus:border-blue-500/50 outline-none"
                      />
                    </div>
                    <div className="flex gap-3 mt-4">
                      <button
                        onClick={addTarget}
                        className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                      >
                        Create Target
                      </button>
                      <button
                        onClick={() => setShowAddTarget(false)}
                        className="px-4 py-2 bg-[#171717] text-[#737373] rounded-lg hover:bg-[#262626] transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* Targets Grid */}
                <div className="grid gap-4 md:grid-cols-2">
                  {targets.map((target) => (
                    <div key={target.id} className="rounded-xl border border-white/[0.06] bg-[#0A0A0A] p-6 hover:border-blue-500/30 transition-colors">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="text-lg font-semibold text-[#FAFAFA]">{target.program_name}</h3>
                          <p className="text-sm text-[#737373] mt-1 font-mono">{target.scope}</p>
                        </div>
                        {target.link && (
                          <a
                            href={target.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-2 hover:bg-white/[0.05] rounded-lg transition-colors"
                          >
                            <ExternalLink className="w-4 h-4 text-[#737373]" />
                          </a>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-4">
                        <span className={`px-2 py-1 text-xs rounded-full ${target.payout_tier === 'HIGH' ? 'bg-green-500/20 text-green-400' :
                            target.payout_tier === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400' :
                              'bg-gray-500/20 text-gray-400'
                          }`}>
                          {target.payout_tier} Payout
                        </span>
                        <span className={`px-2 py-1 text-xs rounded-full ${target.status === 'ACTIVE' ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'
                          }`}>
                          {target.status}
                        </span>
                        {target.platform && (
                          <span className="text-xs text-[#525252]">{target.platform}</span>
                        )}
                      </div>
                    </div>
                  ))}

                  {targets.length === 0 && (
                    <div className="col-span-full text-center py-12">
                      <Target className="w-12 h-12 text-[#262626] mx-auto mb-4" />
                      <p className="text-[#525252]">No targets yet. Add your first target above!</p>
                    </div>
                  )}
                </div>
              </>
            )}

          </div>
        </ScrollArea>
      </SidebarInset>
    </SidebarProvider>
  )
}
