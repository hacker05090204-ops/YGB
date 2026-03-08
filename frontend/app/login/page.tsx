"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"

import {
  credentialedFetch,
  notifyAuthStateChanged,
  purgeLegacyAuthStorage,
} from "@/lib/auth-token"
import { getApiBase } from "@/lib/ygb-api"

interface AuthProviderSnapshot {
  password: {
    enabled: boolean
  }
  github: {
    enabled: boolean
    missing: string[]
    redirect_uri: string | null
    frontend_url: string | null
    shared_candidates: string[]
  }
  google: {
    enabled: boolean
    missing: string[]
    redirect_uri: string | null
    frontend_url: string | null
    shared_candidates: string[]
  }
  checked_at: string
}

function LoginContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle")
  const [message, setMessage] = useState("")
  const [authProviders, setAuthProviders] = useState<AuthProviderSnapshot | null>(null)

  useEffect(() => {
    let cancelled = false

    const loadAuthProviders = async () => {
      try {
        const res = await credentialedFetch(`${getApiBase()}/api/auth/providers`)
        if (!res.ok) {
          return
        }
        const data = (await res.json()) as AuthProviderSnapshot
        if (!cancelled) {
          setAuthProviders(data)
        }
      } catch {
        if (!cancelled) {
          setAuthProviders(null)
        }
      }
    }

    void loadAuthProviders()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let redirectTimer: ReturnType<typeof setTimeout> | undefined

    const error = searchParams.get("error")
    const authMethod = searchParams.get("auth")
    const providerLabel = authMethod === "google" ? "Google" : "GitHub"
    const usedExternalProvider = authMethod === "github" || authMethod === "google"
    const fallbackUser = searchParams.get("user")

    purgeLegacyAuthStorage()

    if (error) {
      const errorMessages: Record<string, string> = {
        no_code: `${providerLabel} did not return an authorization code`,
        token_exchange_failed: "Failed to exchange code for token",
        server_error: "Server error during authentication",
        access_denied: `Access denied by ${providerLabel}`,
        state_mismatch: "OAuth state mismatch detected; please retry login",
        invalid_github_profile: "GitHub profile data was incomplete",
        invalid_google_profile: "Google profile data was incomplete",
      }
      queueMicrotask(() => {
        if (cancelled) {
          return
        }
        setStatus("error")
        setMessage(errorMessages[error] || `Authentication error: ${error}`)
      })
      return () => {
        if (redirectTimer) {
          clearTimeout(redirectTimer)
        }
      }
    }

    const verifySession = async () => {
      try {
        const res = await credentialedFetch(`${getApiBase()}/auth/me`)
        if (!res.ok) {
          if (usedExternalProvider && !cancelled) {
            setStatus("error")
            setMessage(`${providerLabel} sign-in did not create a valid session`)
          }
          return
        }

        const data = await res.json()
        if (cancelled) {
          return
        }

        notifyAuthStateChanged()
        setStatus("success")
        setMessage(
          `Welcome, ${data.github_login || data.name || fallbackUser || "user"}!`
        )
        redirectTimer = setTimeout(() => router.push("/control"), 1500)
      } catch {
        if (usedExternalProvider && !cancelled) {
          setStatus("error")
          setMessage("Network error - could not verify the new session")
        }
      }
    }

    void verifySession()

    return () => {
      cancelled = true
      if (redirectTimer) {
        clearTimeout(redirectTimer)
      }
    }
  }, [router, searchParams])

  const handleGitHubLogin = () => {
    if (authProviders && !authProviders.github.enabled) {
      const missing = authProviders.github.missing.join(", ")
      setStatus("error")
      setMessage(
        missing
          ? `GitHub sign-in is not ready on this server yet. Missing: ${missing}`
          : "GitHub sign-in is not ready on this server yet."
      )
      return
    }
    const origin = encodeURIComponent(window.location.origin)
    window.location.href = `${getApiBase()}/auth/github?frontend_origin=${origin}`
  }

  const handleGoogleLogin = () => {
    if (authProviders && !authProviders.google.enabled) {
      const missing = authProviders.google.missing.join(", ")
      setStatus("error")
      setMessage(
        missing
          ? `Google sign-in is not ready on this server yet. Missing: ${missing}`
          : "Google sign-in is not ready on this server yet."
      )
      return
    }
    const origin = encodeURIComponent(window.location.origin)
    window.location.href = `${getApiBase()}/auth/google?frontend_origin=${origin}`
  }

  const passwordEnabled = authProviders?.password.enabled ?? true
  const githubEnabled = authProviders?.github.enabled ?? true
  const githubMissing = authProviders?.github.missing ?? []
  const googleEnabled = authProviders?.google.enabled ?? true
  const googleMissing = authProviders?.google.missing ?? []
  const retryAuthMethod = searchParams.get("auth") === "google" ? "google" : "github"

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center p-4">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[600px] rounded-full bg-blue-500/5 blur-[120px]" />
        <div className="absolute bottom-1/4 left-1/3 w-[400px] h-[400px] rounded-full bg-purple-500/5 blur-[100px]" />
      </div>

      <div className="relative w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-cyan-400 mb-4 shadow-lg shadow-blue-500/20">
            <svg
              className="w-8 h-8 text-white"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">YGB Control</h1>
          <p className="text-sm text-gray-500 mt-1">Phase-49 Security Operations</p>
        </div>

        <div className="bg-[#12121a] border border-gray-800/60 rounded-2xl p-8 shadow-2xl shadow-black/40 backdrop-blur-sm">
          {status === "success" ? (
            <div className="text-center py-4">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-4">
                <svg
                  className="w-6 h-6 text-emerald-400"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-white mb-1">{message}</h2>
              <p className="text-sm text-gray-400">Redirecting to control panel...</p>
              <div className="mt-4 h-1 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full animate-[progress_1.5s_ease-in-out]"
                  style={{ width: "100%" }}
                />
              </div>
            </div>
          ) : status === "error" ? (
            <div className="text-center py-4">
              <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-500/10 border border-red-500/20 mb-4">
                <svg
                  className="w-6 h-6 text-red-400"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-white mb-1">
                Authentication Failed
              </h2>
              <p className="text-sm text-red-400/80 mb-6">{message}</p>
              <button
                onClick={retryAuthMethod === "google" ? handleGoogleLogin : handleGitHubLogin}
                disabled={retryAuthMethod === "google" ? !googleEnabled : !githubEnabled}
                className="w-full py-3 px-4 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white rounded-xl text-sm font-medium transition-all duration-200 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
              >
                {retryAuthMethod === "google" ? "Retry Google Sign-In" : "Retry GitHub Sign-In"}
              </button>
            </div>
          ) : (
            <div>
              <h2 className="text-lg font-semibold text-white mb-1 text-center">
                Sign in to continue
              </h2>
              <p className="text-sm text-gray-500 mb-6 text-center">
                Choose your authentication method
              </p>

              {passwordEnabled ? (
                <form
                  id="login-form"
                  onSubmit={async (e) => {
                    e.preventDefault()
                    const formData = new FormData(e.currentTarget)
                    const email = String(formData.get("email") || "")
                    const password = String(formData.get("password") || "")

                    if (!email || !password) {
                      setStatus("error")
                      setMessage("Please enter both email and password")
                      return
                    }

                    try {
                      const res = await credentialedFetch(`${getApiBase()}/auth/login`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ email, password }),
                      })
                      const data = await res.json()

                      if (!res.ok) {
                        setStatus("error")
                        setMessage(data.detail?.detail || data.detail || "Login failed")
                        return
                      }

                      notifyAuthStateChanged()
                      setStatus("success")
                      setMessage(`Welcome, ${data.user?.name || email}!`)
                      setTimeout(() => router.push("/control"), 1500)
                    } catch {
                      setStatus("error")
                      setMessage("Network error - is the backend running?")
                    }
                  }}
                  className="space-y-4"
                >
                  <div>
                    <label
                      htmlFor="email"
                      className="block text-xs font-medium text-gray-400 mb-1.5"
                    >
                      Email
                    </label>
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      placeholder="you@example.com"
                      className="w-full px-4 py-3 bg-[#0e0e18] border border-gray-700/60 rounded-xl text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/30 transition-all"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="password"
                      className="block text-xs font-medium text-gray-400 mb-1.5"
                    >
                      Password
                    </label>
                    <input
                      id="password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      placeholder="********"
                      className="w-full px-4 py-3 bg-[#0e0e18] border border-gray-700/60 rounded-xl text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/60 focus:ring-1 focus:ring-blue-500/30 transition-all"
                    />
                  </div>
                  <button
                    type="submit"
                    id="password-login-button"
                    className="w-full py-3.5 px-4 bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white rounded-xl text-sm font-semibold transition-all duration-200 cursor-pointer shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30"
                  >
                    Sign In
                  </button>
                </form>
              ) : (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
                  Password login is disabled on this server. Use a configured external provider.
                </div>
              )}

              <div className="flex items-center gap-3 my-6">
                <div className="flex-1 h-px bg-gray-800/60" />
                <span className="text-xs text-gray-600 uppercase tracking-wider">or</span>
                <div className="flex-1 h-px bg-gray-800/60" />
              </div>

              <button
                onClick={handleGitHubLogin}
                id="github-login-button"
                disabled={!githubEnabled}
                className="group w-full py-3.5 px-4 bg-[#1a1a2e] hover:bg-[#22223a] border border-gray-700/60 hover:border-gray-600 text-white rounded-xl text-sm font-medium transition-all duration-200 flex items-center justify-center gap-3 cursor-pointer hover:shadow-lg hover:shadow-purple-500/5 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg
                  className="w-5 h-5 text-gray-300 group-hover:text-white transition-colors"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.31.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                Continue with GitHub
              </button>
              {!githubEnabled && githubMissing.length > 0 && (
                <p className="mt-3 text-xs text-amber-300 text-center">
                  GitHub sign-in is waiting on server-side OAuth config:{" "}
                  {githubMissing.join(", ")}
                </p>
              )}

              <button
                onClick={handleGoogleLogin}
                id="google-login-button"
                disabled={!googleEnabled}
                className="group mt-3 w-full py-3.5 px-4 bg-[#1c231f] hover:bg-[#243026] border border-emerald-900/40 hover:border-emerald-700/50 text-white rounded-xl text-sm font-medium transition-all duration-200 flex items-center justify-center gap-3 cursor-pointer hover:shadow-lg hover:shadow-emerald-500/5 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg
                  className="w-5 h-5"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.5 3.9-5.5 3.9-3.3 0-6-2.8-6-6.2s2.7-6.2 6-6.2c1.9 0 3.2.8 3.9 1.5l2.7-2.7C16.9 2.7 14.7 1.8 12 1.8 6.5 1.8 2 6.4 2 12s4.5 10.2 10 10.2c5.8 0 9.6-4.1 9.6-9.8 0-.7-.1-1.3-.2-1.9H12z" />
                  <path fill="#34A853" d="M2 7.8l3.2 2.3C6 7.6 8.7 5.8 12 5.8c1.9 0 3.2.8 3.9 1.5l2.7-2.7C16.9 2.7 14.7 1.8 12 1.8 8.1 1.8 4.8 4 2.9 7.1L2 7.8z" />
                  <path fill="#FBBC05" d="M12 22.2c2.6 0 4.8-.9 6.4-2.4l-3-2.5c-.8.6-1.9 1-3.4 1-3.9 0-5.3-2.6-5.5-3.9l-3.1 2.4C5.2 20 8.3 22.2 12 22.2z" />
                  <path fill="#4285F4" d="M21.6 12.4c0-.7-.1-1.3-.2-1.9H12v3.9h5.5c-.3 1.5-1.2 2.7-2.5 3.6l3 2.5c1.8-1.7 3.6-4.8 3.6-8.1z" />
                </svg>
                Continue with Google
              </button>
              {!googleEnabled && googleMissing.length > 0 && (
                <p className="mt-3 text-xs text-amber-300 text-center">
                  Google sign-in is waiting on server-side OAuth config:{" "}
                  {googleMissing.join(", ")}
                </p>
              )}

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

        <p className="text-center text-xs text-gray-700 mt-6">
          YGB Security Operations Platform
        </p>
      </div>

      <style jsx>{`
        @keyframes progress {
          from {
            width: 0%;
          }
          to {
            width: 100%;
          }
        }
      `}</style>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
          <div className="text-gray-500 text-sm">Loading...</div>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  )
}
