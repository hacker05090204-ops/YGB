"use client"

import { useEffect, useState, Suspense } from "react"
import { useSearchParams, useRouter } from "next/navigation"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

function LoginContent() {
    const searchParams = useSearchParams()
    const router = useRouter()
    const [status, setStatus] = useState<"idle" | "success" | "error">("idle")
    const [message, setMessage] = useState("")
    const [userName, setUserName] = useState("")

    useEffect(() => {
        const token = searchParams.get("token")
        const error = searchParams.get("error")
        const user = searchParams.get("user")

        if (token) {
            // Store token and redirect to control page
            sessionStorage.setItem("ygb_token", token)
            if (user) setUserName(user)
            setStatus("success")
            setMessage(`Welcome, ${user || "user"}!`)

            // Redirect after brief display
            const timer = setTimeout(() => router.push("/control"), 1500)
            return () => clearTimeout(timer)
        } else if (error) {
            setStatus("error")
            const errorMessages: Record<string, string> = {
                no_code: "GitHub did not return an authorization code",
                token_exchange_failed: "Failed to exchange code for token",
                server_error: "Server error during authentication",
                access_denied: "Access denied by GitHub",
            }
            setMessage(errorMessages[error] || `Authentication error: ${error}`)
        }
    }, [searchParams, router])

    const handleGitHubLogin = () => {
        window.location.href = `${API_BASE}/auth/github`
    }

    return (
        <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4">
            {/* Ambient glow */}
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full bg-blue-500/5 blur-[120px]" />
                <div className="absolute bottom-1/4 left-1/3 w-[400px] h-[400px] rounded-full bg-purple-500/5 blur-[100px]" />
            </div>

            <div className="relative w-full max-w-md">
                {/* Logo / Branding */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 mb-4 shadow-lg shadow-blue-500/20">
                        <svg className="w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        </svg>
                    </div>
                    <h1 className="text-2xl font-bold text-white tracking-tight">YGB Control</h1>
                    <p className="text-sm text-gray-500 mt-1">Phase-49 Security Operations</p>
                </div>

                {/* Card */}
                <div className="bg-[#12121a] border border-gray-800/60 rounded-2xl p-8 shadow-2xl shadow-black/40 backdrop-blur-sm">
                    {status === "success" ? (
                        <div className="text-center py-4">
                            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-4">
                                <svg className="w-6 h-6 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <polyline points="20 6 9 17 4 12" />
                                </svg>
                            </div>
                            <h2 className="text-lg font-semibold text-white mb-1">{message}</h2>
                            <p className="text-sm text-gray-400">Redirecting to control panel...</p>
                            <div className="mt-4 h-1 bg-gray-800 rounded-full overflow-hidden">
                                <div className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full animate-[progress_1.5s_ease-in-out]" style={{ width: "100%" }} />
                            </div>
                        </div>
                    ) : status === "error" ? (
                        <div className="text-center py-4">
                            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 mb-4">
                                <svg className="w-6 h-6 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <circle cx="12" cy="12" r="10" />
                                    <line x1="15" y1="9" x2="9" y2="15" />
                                    <line x1="9" y1="9" x2="15" y2="15" />
                                </svg>
                            </div>
                            <h2 className="text-lg font-semibold text-white mb-1">Authentication Failed</h2>
                            <p className="text-sm text-red-400/80 mb-6">{message}</p>
                            <button
                                onClick={handleGitHubLogin}
                                className="w-full py-3 px-4 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer"
                            >
                                Try Again
                            </button>
                        </div>
                    ) : (
                        <div>
                            <h2 className="text-lg font-semibold text-white mb-1 text-center">Sign in to continue</h2>
                            <p className="text-sm text-gray-500 mb-8 text-center">Authenticate with your GitHub account</p>

                            <button
                                onClick={handleGitHubLogin}
                                id="github-login-button"
                                className="group w-full py-3.5 px-4 bg-[#1a1a2e] hover:bg-[#22223a] border border-gray-700/60 hover:border-gray-600 text-white rounded-xl text-sm font-medium transition-all duration-200 flex items-center justify-center gap-3 cursor-pointer hover:shadow-lg hover:shadow-purple-500/5"
                            >
                                {/* GitHub Logo */}
                                <svg className="w-5 h-5 text-gray-300 group-hover:text-white transition-colors" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.31.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                                </svg>
                                Continue with GitHub
                            </button>

                            <div className="mt-6 pt-6 border-t border-gray-800/60">
                                <p className="text-xs text-gray-600 text-center leading-relaxed">
                                    By signing in, you agree to the terms of use.
                                    <br />
                                    Only authorized personnel may access this system.
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <p className="text-center text-xs text-gray-700 mt-6">
                    YGB Security Operations Platform
                </p>
            </div>

            <style jsx>{`
                @keyframes progress {
                    from { width: 0%; }
                    to { width: 100%; }
                }
            `}</style>
        </div>
    )
}

export default function LoginPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
                <div className="text-gray-500 text-sm">Loading...</div>
            </div>
        }>
            <LoginContent />
        </Suspense>
    )
}
