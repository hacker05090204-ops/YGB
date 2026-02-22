'use client';

import React, { useEffect, useRef, useState } from 'react';

/**
 * AutoTrainingDashboard — Live Multi-Field Training Dashboard (Phase 5)
 *
 * - Active Field Label
 * - Field Queue List
 * - GPU Utilization Live Graph
 * - SPS Live Graph
 * - ETA per field
 * - World Size
 * - Auto Mode indicator
 * - 10s stall detection
 */

interface FieldInfo {
    field_name: string;
    priority: number;
    status: string;
    best_accuracy: number;
    epochs_completed: number;
}

interface DashboardFrame {
    active_field: string;
    queue: FieldInfo[];
    gpu_utilization: number;
    gpu_temp: number;
    vram_used_mb: number;
    samples_per_sec: number;
    eta_seconds: number;
    epoch: number;
    total_epochs: number;
    world_size: number;
    auto_mode: boolean;
    loss: number;
    accuracy: number;
    stalled: boolean;
    mode: string;
    timestamp: string;
}

function formatETA(s: number): string {
    if (s <= 0) return '--';
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${Math.floor(s % 60)}s`;
}

function MiniGraph({ values, color, label, max }: {
    values: number[]; color: string; label: string; max?: number;
}) {
    const ref = useRef<HTMLCanvasElement>(null);
    useEffect(() => {
        const c = ref.current;
        if (!c || values.length < 2) return;
        const ctx = c.getContext('2d');
        if (!ctx) return;
        const w = c.width, h = c.height;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#0a0e14';
        ctx.fillRect(0, 0, w, h);

        const pts = values.slice(-80);
        const mx = max ?? Math.max(...pts, 1);
        const step = w / Math.max(pts.length - 1, 1);

        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        pts.forEach((v, i) => {
            const x = i * step, y = h - (v / mx) * h * 0.85;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();

        ctx.fillStyle = '#6b7280';
        ctx.font = '10px Inter, sans-serif';
        ctx.fillText(`${label}: ${pts[pts.length - 1].toFixed(1)}`, 4, 12);
    }, [values, color, label, max]);

    return <canvas ref={ref} width={300} height={60}
        style={{ width: '100%', height: '60px', borderRadius: '6px', border: '1px solid #1e293b' }} />;
}

export default function AutoTrainingDashboard() {
    const [frame, setFrame] = useState<DashboardFrame | null>(null);
    const [gpuHistory, setGpuHistory] = useState<number[]>([]);
    const [spsHistory, setSpsHistory] = useState<number[]>([]);
    const [connected, setConnected] = useState(false);
    const timer = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = new WebSocket(process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765/training/dashboard');
                ws.onopen = () => setConnected(true);
                ws.onmessage = (e) => {
                    try {
                        const d: DashboardFrame = JSON.parse(e.data);
                        setFrame(d);
                        setGpuHistory(p => [...p.slice(-100), d.gpu_utilization * 100]);
                        setSpsHistory(p => [...p.slice(-100), d.samples_per_sec]);
                        if (timer.current) clearTimeout(timer.current);
                        timer.current = setTimeout(() => {
                            setFrame(prev => prev ? { ...prev, stalled: true } : null);
                        }, 10000);
                    } catch { /* skip */ }
                };
                ws.onclose = () => { setConnected(false); setTimeout(connect, 3000); };
                ws.onerror = () => ws?.close();
            } catch { setTimeout(connect, 3000); }
        }
        connect();
        return () => { ws?.close(); if (timer.current) clearTimeout(timer.current); };
    }, []);

    const box: React.CSSProperties = {
        background: '#0f1117', border: '1px solid #1e293b', borderRadius: '12px',
        padding: '20px', fontFamily: 'Inter, system-ui, sans-serif', color: '#e2e8f0', maxWidth: '520px',
    };

    if (!frame) {
        return (
            <div style={box}>
                <h3 style={{ margin: '0 0 12px', fontSize: '16px' }}>Auto Training Dashboard</h3>
                <p style={{ color: '#6b7280', textAlign: 'center', padding: '30px 0' }}>
                    {connected ? 'Waiting for data...' : 'Connecting...'}
                </p>
            </div>
        );
    }

    const statusColor = frame.auto_mode ? '#10b981' : '#6b7280';
    const modeLabel = frame.mode === 'training' ? '🟢 Training' :
        frame.mode === 'monitoring' ? '🟡 Monitoring' : '⚪ Idle';

    return (
        <div style={box}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '16px' }}>
                    Auto Training
                    {frame.stalled && <span style={{ marginLeft: '8px', fontSize: '12px', color: '#ef4444' }}>⚠ STALLED</span>}
                </h3>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <span style={{
                        fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
                        background: frame.auto_mode ? '#064e3b' : '#1e293b', color: statusColor
                    }}>
                        {frame.auto_mode ? 'AUTO' : 'MANUAL'}
                    </span>
                    <span style={{ fontSize: '11px', color: '#9ca3af' }}>{modeLabel}</span>
                </div>
            </div>

            {/* Active field + stats */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                {[
                    { label: 'Field', value: frame.active_field || '—', color: '#a78bfa' },
                    { label: 'ETA', value: formatETA(frame.eta_seconds), color: '#f59e0b' },
                    { label: 'World', value: `${frame.world_size}`, color: '#00e5ff' },
                    { label: 'Acc', value: `${(frame.accuracy * 100).toFixed(1)}%`, color: '#10b981' },
                ].map(s => (
                    <div key={s.label} style={{ background: '#1a1f2e', borderRadius: '6px', padding: '8px', textAlign: 'center' }}>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: s.color }}>{s.value}</div>
                        <div style={{ fontSize: '9px', color: '#6b7280', marginTop: '2px' }}>{s.label}</div>
                    </div>
                ))}
            </div>

            {/* GPU + SPS graphs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px' }}>
                <MiniGraph values={gpuHistory} color="#f59e0b" label="GPU%" max={100} />
                <MiniGraph values={spsHistory} color="#00e5ff" label="SPS" />
            </div>

            {/* Queue */}
            <div style={{ marginBottom: '8px' }}>
                <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '4px' }}>Queue</div>
                {frame.queue.length === 0 ? (
                    <div style={{ fontSize: '12px', color: '#6b7280', padding: '4px 0' }}>Empty</div>
                ) : frame.queue.slice(0, 5).map(f => (
                    <div key={f.field_name} style={{
                        display: 'flex', justifyContent: 'space-between', fontSize: '12px',
                        padding: '3px 0', borderBottom: '1px solid #1e293b',
                    }}>
                        <span style={{ color: f.status === 'training' ? '#a78bfa' : '#9ca3af' }}>
                            {f.status === 'training' ? '▶ ' : ''}{f.field_name}
                        </span>
                        <span style={{ color: '#6b7280' }}>
                            {f.status === 'completed' ? `✓ ${(f.best_accuracy * 100).toFixed(1)}%` : f.status}
                        </span>
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#6b7280' }}>
                <span>Loss: {frame.loss.toFixed(4)}</span>
                <span>E{frame.epoch}/{frame.total_epochs}</span>
                <span>{connected ? '● Live' : '○'}</span>
            </div>
        </div>
    );
}

export type { DashboardFrame, FieldInfo };
