'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createAuthWebSocket } from '@/lib/ws-auth';

/**
 * TrainingDashboardV2 — Live Training Dashboard (Phase 5)
 *
 * - Global Storage Usage Bar (110GB)
 * - Active Field Indicator
 * - Cluster world_size
 * - Mode (A / Lab)
 * - Live SPS graph
 * - ETA timer
 * - Training state: RUNNING / WAITING / LOCKED / ERROR
 * - Auto-start indicator
 */

interface DashboardV2Frame {
    // Training
    active_field: string;
    training_state: string;  // RUNNING / WAITING / LOCKED / ERROR
    auto_mode: boolean;
    auto_pending: boolean;
    epoch: number;
    total_epochs: number;
    samples_per_sec: number;
    eta_seconds: number;
    loss: number;
    accuracy: number;
    // Cluster
    world_size: number;
    mode: string;           // A / Lab
    // Storage
    storage_used_gb: number;
    storage_cap_gb: number;
    // GPU
    gpu_utilization: number;
    gpu_temp: number;
    // Meta
    stalled: boolean;
    timestamp: string;
}

function formatETA(s: number): string {
    if (s <= 0) return '--';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${Math.floor(s % 60)}s`;
}

function MiniGraph({ values, color, height = 50, max }: {
    values: number[]; color: string; height?: number; max?: number;
}) {
    const ref = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
        const c = ref.current;
        if (!c || values.length < 2) return;
        const ctx = c.getContext('2d');
        if (!ctx) return;
        const w = c.width;
        ctx.clearRect(0, 0, w, height);
        ctx.fillStyle = '#0a0e14';
        ctx.fillRect(0, 0, w, height);

        const pts = values.slice(-60);
        const mx = max ?? Math.max(...pts, 1);
        const step = w / Math.max(pts.length - 1, 1);
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        pts.forEach((v, i) => {
            const x = i * step, y = height - (v / mx) * height * 0.85;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();
    }, [values, color, height, max]);

    return <canvas ref={ref} width={240} height={height}
        style={{ width: '100%', height: `${height}px`, borderRadius: '4px', border: '1px solid #1e293b' }} />;
}

function StorageBar({ used, cap }: { used: number; cap: number }) {
    const pct = cap > 0 ? Math.min((used / cap) * 100, 100) : 0;
    const color = pct > 90 ? '#ef4444' : pct > 75 ? '#f59e0b' : '#10b981';
    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#9ca3af', marginBottom: '3px' }}>
                <span>Global Storage</span>
                <span>{used.toFixed(1)}GB / {cap}GB</span>
            </div>
            <div style={{ width: '100%', height: '8px', background: '#1e293b', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '4px', transition: 'width 0.5s' }} />
            </div>
        </div>
    );
}

function StateChip({ state }: { state: string }) {
    const colors: Record<string, { bg: string; text: string }> = {
        RUNNING: { bg: '#064e3b', text: '#10b981' },
        WAITING: { bg: '#422006', text: '#f59e0b' },
        LOCKED: { bg: '#450a0a', text: '#ef4444' },
        ERROR: { bg: '#450a0a', text: '#ef4444' },
    };
    const c = colors[state] || colors.WAITING;
    return (
        <span style={{
            fontSize: '11px', fontWeight: 600, padding: '2px 10px',
            borderRadius: '4px', background: c.bg, color: c.text,
        }}>{state}</span>
    );
}

export default function TrainingDashboardV2() {
    const [frame, setFrame] = useState<DashboardV2Frame | null>(null);
    const [spsHistory, setSpsHistory] = useState<number[]>([]);
    const [connected, setConnected] = useState(false);
    const timer = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = createAuthWebSocket(
                    '/training/v2',
                    (e) => {
                        try {
                            const d: DashboardV2Frame = JSON.parse(e.data);
                            setFrame(d);
                            setSpsHistory(p => [...p.slice(-100), d.samples_per_sec]);
                            if (timer.current) clearTimeout(timer.current);
                            timer.current = setTimeout(() => {
                                setFrame(prev => prev ? { ...prev, stalled: true } : null);
                            }, 10000);
                        } catch { /* skip */ }
                    },
                    () => ws?.close(),
                    () => { setConnected(false); setTimeout(connect, 3000); },
                );
                if (ws) {
                    ws.onopen = () => setConnected(true);
                } else {
                    setConnected(false);
                }
            } catch { setTimeout(connect, 3000); }
        }
        connect();
        return () => { ws?.close(); if (timer.current) clearTimeout(timer.current); };
    }, []);

    const box: React.CSSProperties = {
        background: '#0f1117', border: '1px solid #1e293b', borderRadius: '12px',
        padding: '20px', fontFamily: 'Inter, system-ui, sans-serif', color: '#e2e8f0', maxWidth: '480px',
    };

    if (!frame) {
        return (
            <div style={box}>
                <h3 style={{ margin: '0 0 12px', fontSize: '16px' }}>Training Dashboard</h3>
                <p style={{ color: '#6b7280', textAlign: 'center', padding: '30px 0' }}>
                    {connected ? 'Waiting...' : 'Connecting...'}
                </p>
            </div>
        );
    }

    return (
        <div style={box}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
                <div>
                    <h3 style={{ margin: 0, fontSize: '16px' }}>
                        Training
                        {frame.stalled && <span style={{ marginLeft: '6px', fontSize: '11px', color: '#ef4444' }}>⚠ STALLED</span>}
                    </h3>
                    <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '2px' }}>
                        Mode {frame.mode} · World {frame.world_size}
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <StateChip state={frame.training_state} />
                    {frame.auto_mode && (
                        <span style={{ fontSize: '10px', color: '#10b981' }}>AUTO</span>
                    )}
                </div>
            </div>

            {/* Active field bar */}
            <div style={{
                background: '#1a1f2e', borderRadius: '8px', padding: '10px 14px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px',
            }}>
                <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#a78bfa' }}>
                        {frame.active_field || 'No active field'}
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>
                        E{frame.epoch}/{frame.total_epochs} · Loss {frame.loss.toFixed(4)}
                    </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '18px', fontWeight: 700, color: '#10b981' }}>
                        {(frame.accuracy * 100).toFixed(1)}%
                    </div>
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>
                        ETA {formatETA(frame.eta_seconds)}
                    </div>
                </div>
            </div>

            {/* Stats row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                {[
                    { l: 'SPS', v: frame.samples_per_sec >= 1000 ? `${(frame.samples_per_sec / 1000).toFixed(1)}K` : `${frame.samples_per_sec.toFixed(0)}`, c: '#00e5ff' },
                    { l: 'GPU', v: `${(frame.gpu_utilization * 100).toFixed(0)}%`, c: frame.gpu_utilization > 0.85 ? '#ef4444' : '#f59e0b' },
                    { l: 'Temp', v: `${frame.gpu_temp.toFixed(0)}°C`, c: frame.gpu_temp > 80 ? '#ef4444' : '#9ca3af' },
                ].map(s => (
                    <div key={s.l} style={{ background: '#1a1f2e', borderRadius: '6px', padding: '6px', textAlign: 'center' }}>
                        <div style={{ fontSize: '15px', fontWeight: 700, color: s.c }}>{s.v}</div>
                        <div style={{ fontSize: '9px', color: '#6b7280' }}>{s.l}</div>
                    </div>
                ))}
            </div>

            {/* SPS graph */}
            <MiniGraph values={spsHistory} color="#00e5ff" height={45} />

            {/* Storage bar */}
            <div style={{ marginTop: '10px' }}>
                <StorageBar used={frame.storage_used_gb} cap={frame.storage_cap_gb} />
            </div>

            {/* Auto-start indicator */}
            {frame.auto_pending && frame.training_state === 'WAITING' && (
                <div style={{
                    marginTop: '8px', fontSize: '11px', color: '#f59e0b',
                    textAlign: 'center', padding: '4px', background: '#422006',
                    borderRadius: '4px',
                }}>
                    ⏳ Auto-start pending...
                </div>
            )}

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#6b7280', marginTop: '8px' }}>
                <span>{connected ? '● Live' : '○ Offline'}</span>
                <span>{frame.timestamp?.slice(11, 19) || ''}</span>
            </div>
        </div>
    );
}

export type { DashboardV2Frame };
