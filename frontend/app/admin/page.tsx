"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Shield, Lock, AlertTriangle, Eye, EyeOff } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

export default function AdminLogin() {
    const router = useRouter()
    const [email, setEmail] = useState("")
    const [totpCode, setTotpCode] = useState("")
    const [vaultPassword, setVaultPassword] = useState("")
    const [error, setError] = useState("")
    const [loading, setLoading] = useState(false)
    const [showCode, setShowCode] = useState(false)
    const [showVaultPass, setShowVaultPass] = useState(false)
    const [attemptsLeft, setAttemptsLeft] = useState(5)
    const [lockedUntil, setLockedUntil] = useState<number | null>(null)

    // Check existing session
    useEffect(() => {
        const token = localStorage.getItem("ygb_session")
        if (token) {
            fetch(`${API_BASE}/admin/verify`, {
                headers: { Authorization: `Bearer ${token}` },
            })
                .then((r) => r.json())
                .then((data) => {
                    if (data.status === "ok") router.push("/admin/panel")
                })
                .catch(() => { })
        }
    }, [router])

    // Lockout countdown
    useEffect(() => {
        if (!lockedUntil) return
        const interval = setInterval(() => {
            const remaining = Math.max(0, lockedUntil - Date.now() / 1000)
            if (remaining <= 0) {
                setLockedUntil(null)
                setError("")
            }
        }, 1000)
        return () => clearInterval(interval)
    }, [lockedUntil])

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault()
        if (lockedUntil) return

        setLoading(true)
        setError("")

        try {
            const res = await fetch(`${API_BASE}/admin/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, totp_code: totpCode }),
                credentials: "include",
            })

            const data = await res.json()

            if (data.status === "ok") {
                localStorage.setItem("ygb_session", data.session_token)
                if (data.jwt_token) {
                    localStorage.setItem("ygb_jwt", data.jwt_token)
                }

                // Unlock vault with password (server-side key derivation)
                if (vaultPassword) {
                    try {
                        await fetch(`${API_BASE}/admin/vault-unlock`, {
                            method: "POST",
                            headers: {
                                "Content-Type": "application/json",
                                Authorization: `Bearer ${data.session_token}`,
                            },
                            body: JSON.stringify({ vault_password: vaultPassword }),
                        })
                    } catch {
                        // Vault unlock is best-effort — login still succeeds
                    }
                }

                // Clear vault password from memory immediately
                setVaultPassword("")
                router.push("/admin/panel")
            } else if (data.status === "locked_out") {
                setLockedUntil(Date.now() / 1000 + 1800)
                setError(data.message)
            } else {
                setError(data.message || "Authentication failed")
                if (data.remaining !== undefined) setAttemptsLeft(data.remaining)
            }
        } catch {
            setError("Connection failed. Check server status.")
        } finally {
            setLoading(false)
            setTotpCode("")
            setVaultPassword("")  // Always clear vault password
        }
    }

    const lockoutRemaining = lockedUntil
        ? Math.max(0, Math.ceil(lockedUntil - Date.now() / 1000))
        : 0

    return (
        <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4">
            {/* Background gradient */}
            <div className="fixed inset-0 bg-gradient-to-br from-violet-950/20 via-transparent to-cyan-950/20" />

            <div className="relative w-full max-w-md">
                {/* Card */}
                <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-2xl p-8 shadow-2xl shadow-violet-950/20">
                    {/* Header */}
                    <div className="text-center mb-8">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-cyan-500 mb-4">
                            <Shield className="w-8 h-8 text-white" />
                        </div>
                        <h1 className="text-2xl font-bold text-white mb-1">
                            Admin Panel
                        </h1>
                        <p className="text-sm text-white/40">
                            Google OAuth + TOTP Authentication
                        </p>
                    </div>

                    {/* Error */}
                    {error && (
                        <div className="mb-6 p-3 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-3">
                            <AlertTriangle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
                            <p className="text-sm text-red-300">{error}</p>
                        </div>
                    )}

                    {/* Lockout warning */}
                    {lockedUntil && lockoutRemaining > 0 && (
                        <div className="mb-6 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
                            <p className="text-sm text-amber-300 text-center">
                                Account locked. Try again in {Math.floor(lockoutRemaining / 60)}:{String(lockoutRemaining % 60).padStart(2, "0")}
                            </p>
                        </div>
                    )}

                    {/* Form */}
                    <form onSubmit={handleLogin} className="space-y-5">
                        {/* Email */}
                        <div>
                            <label className="block text-sm font-medium text-white/60 mb-1.5">
                                Email
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="admin@example.com"
                                required
                                disabled={!!lockedUntil}
                                className="w-full px-4 py-3 rounded-lg bg-white/[0.04] border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/30 transition-all disabled:opacity-40"
                            />
                        </div>

                        {/* TOTP Code */}
                        <div>
                            <label className="block text-sm font-medium text-white/60 mb-1.5">
                                Authenticator Code
                            </label>
                            <div className="relative">
                                <input
                                    type={showCode ? "text" : "password"}
                                    value={totpCode}
                                    onChange={(e) => {
                                        const v = e.target.value.replace(/\D/g, "").slice(0, 6)
                                        setTotpCode(v)
                                    }}
                                    placeholder="000000"
                                    required
                                    maxLength={6}
                                    disabled={!!lockedUntil}
                                    className="w-full px-4 py-3 rounded-lg bg-white/[0.04] border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/30 transition-all font-mono text-lg tracking-widest disabled:opacity-40"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowCode(!showCode)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
                                >
                                    {showCode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </button>
                            </div>
                            <p className="mt-1 text-xs text-white/30">
                                {attemptsLeft < 5 && `${attemptsLeft} attempts remaining`}
                            </p>
                        </div>

                        {/* Vault Password */}
                        <div>
                            <label className="block text-sm font-medium text-white/60 mb-1.5">
                                Vault Password
                            </label>
                            <div className="relative">
                                <input
                                    type={showVaultPass ? "text" : "password"}
                                    value={vaultPassword}
                                    onChange={(e) => setVaultPassword(e.target.value)}
                                    placeholder="Vault encryption password"
                                    disabled={!!lockedUntil}
                                    className="w-full px-4 py-3 rounded-lg bg-white/[0.04] border border-white/10 text-white placeholder:text-white/20 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition-all disabled:opacity-40"
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowVaultPass(!showVaultPass)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
                                >
                                    {showVaultPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                </button>
                            </div>
                            <p className="mt-1 text-xs text-white/25">
                                Optional — unlocks encrypted vault on login
                            </p>
                        </div>

                        {/* Submit */}
                        <button
                            type="submit"
                            disabled={loading || !!lockedUntil || totpCode.length !== 6}
                            className="w-full py-3 rounded-lg bg-gradient-to-r from-violet-600 to-cyan-600 text-white font-semibold hover:from-violet-500 hover:to-cyan-500 focus:outline-none focus:ring-2 focus:ring-violet-500/50 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                        >
                            {loading ? (
                                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <>
                                    <Lock className="w-4 h-4" />
                                    Authenticate
                                </>
                            )}
                        </button>
                    </form>

                    {/* Footer */}
                    <div className="mt-6 pt-6 border-t border-white/5 text-center">
                        <p className="text-xs text-white/25">
                            Protected by TOTP MFA · 5-attempt lockout · Audit logged
                        </p>
                    </div>
                </div>
            </div>
        </div>
    )
}
