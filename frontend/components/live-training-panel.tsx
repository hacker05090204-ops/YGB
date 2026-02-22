'use client';

import React, { useEffect, useRef, useState } from 'react';

/**
 * LiveTrainingPanel — WebSocket-based Real-Time Training Dashboard (Phase 3)
 *
 * Features:
 * - Live SPS display
 * - ETA countdown
 * - GPU utilization meter
 * - Loss/Accuracy graph (canvas)
 * - Epoch progress bar
 * - 10s stall detection
 */

interface TelemetryFrame {
    epoch: number;
    batch: number;
    total_batches: number;
    samples_processed: number;
    total_samples: number;
    samples_per_sec: number;
    gpu_utilization: number;
    gpu_memory_mb: number;
    gpu_temp: number;
    loss: number;
    running_accuracy: number;
    learning_rate: number;
    eta_seconds: number;
    stalled: boolean;
    timestamp: string;
}

function formatETA(seconds: number): string {
    if (seconds <= 0) return '00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function formatSPS(sps: number): string {
    if (sps >= 1000000) return `${(sps / 1000000).toFixed(1)}M`;
    if (sps >= 1000) return `${(sps / 1000).toFixed(1)}K`;
    return sps.toFixed(0);
}

function LossCanvas({ history }: { history: { loss: number; accuracy: number }[] }) {
    const ref = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        const c = ref.current;
        if (!c || history.length < 2) return;
        const ctx = c.getContext('2d');
        if (!ctx) return;

        const w = c.width, h = c.height;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#0a0e14';
        ctx.fillRect(0, 0, w, h);

        const pts = history.slice(-100);
        const maxL = Math.max(...pts.map(p => p.loss), 0.01);
        const step = w / Math.max(pts.length - 1, 1);

        // Loss (cyan)
        ctx.strokeStyle = '#00e5ff'; ctx.lineWidth = 2;
        ctx.beginPath();
        pts.forEach((p, i) => {
            const x = i * step, y = h - (p.loss / maxL) * h * 0.9;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();

        // Accuracy (green)
        ctx.strokeStyle = '#10b981'; ctx.lineWidth = 2;
        ctx.beginPath();
        pts.forEach((p, i) => {
            const x = i * step, y = h - p.accuracy * h * 0.9;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.stroke();

        ctx.fillStyle = '#6b7280'; ctx.font = '10px Inter, sans-serif';
        ctx.fillText(`Loss: ${pts[pts.length - 1].loss.toFixed(4)}`, 4, 14);
        ctx.fillStyle = '#10b981';
        ctx.fillText(`Acc: ${(pts[pts.length - 1].accuracy * 100).toFixed(1)}%`, 4, 26);
    }, [history]);

    return <canvas ref={ref} width={400} height={120}
        style={{ width: '100%', height: '120px', borderRadius: '8px', border: '1px solid #1e293b' }} />;
}

export default function LiveTrainingPanel() {
    const [frame, setFrame] = useState<TelemetryFrame | null>(null);
    const [history, setHistory] = useState<{ loss: number; accuracy: number }[]>([]);
    const [connected, setConnected] = useState(false);
    const [stalled, setStalled] = useState(false);
    const timer = useRef<NodeJS.Timeout | null>(null);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = new WebSocket(process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765/training/stream');
                ws.onopen = () => { setConnected(true); setStalled(false); };
                ws.onmessage = (e) => {
                    try {
                        const d: TelemetryFrame = JSON.parse(e.data);
                        setFrame(d);
                        setHistory(p => [...p.slice(-200), { loss: d.loss, accuracy: d.running_accuracy }]);
                        setStalled(d.stalled);
                        if (timer.current) clearTimeout(timer.current);
                        timer.current = setTimeout(() => setStalled(true), 10000);
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
        padding: '20px', fontFamily: 'Inter, system-ui, sans-serif', color: '#e2e8f0', maxWidth: '480px',
    };
    const stat: React.CSSProperties = {
        background: '#1a1f2e', borderRadius: '8px', padding: '12px', textAlign: 'center',
    };

    if (!frame) {
        return (
            <div style={box}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px' }}>Live Training</h3>
                    <span style={{ fontSize: '12px', color: connected ? '#10b981' : '#ef4444' }}>
                        {connected ? '● Connected' : '○ Disconnected'}
                    </span>
                </div>
                <p style={{ color: '#6b7280', textAlign: 'center', padding: '40px 0' }}>Waiting for telemetry...</p>
            </div>
        );
    }

    const gpuPct = Math.min(frame.gpu_utilization * 100, 100);
    const gpuColor = gpuPct > 90 ? '#ef4444' : gpuPct > 70 ? '#f59e0b' : '#10b981';
    const batchPct = frame.total_batches > 0 ? (frame.batch / frame.total_batches) * 100 : 0;

    return (
        <div style={box}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '16px' }}>
                    Live Training {stalled && <span style={{ marginLeft: '8px', fontSize: '12px', color: '#ef4444' }}>⚠ STALLED</span>}
                </h3>
                <span style={{ fontSize: '12px', color: connected ? '#10b981' : '#ef4444' }}>
                    {connected ? '● Live' : '○ Offline'}
                </span>
            </div>

            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '16px' }}>
                <div style={stat}>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#00e5ff' }}>{formatSPS(frame.samples_per_sec)}</div>
                    <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '4px' }}>Samples/sec</div>
                </div>
                <div style={stat}>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#f59e0b' }}>{formatETA(frame.eta_seconds)}</div>
                    <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '4px' }}>ETA</div>
                </div>
                <div style={stat}>
                    <div style={{ fontSize: '20px', fontWeight: 700, color: '#10b981' }}>{(frame.running_accuracy * 100).toFixed(1)}%</div>
                    <div style={{ fontSize: '10px', color: '#6b7280', marginTop: '4px' }}>Accuracy</div>
                </div>
            </div>

            {/* Epoch bar */}
            <div style={{ marginBottom: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#9ca3af' }}>
                    <span>Epoch {frame.epoch}</span>
                    <span>{frame.batch}/{frame.total_batches} ({batchPct.toFixed(0)}%)</span>
                </div>
                <div style={{ width: '100%', height: '8px', background: '#1e293b', borderRadius: '4px', overflow: 'hidden', marginTop: '4px' }}>
                    <div style={{ width: `${batchPct}%`, height: '100%', background: 'linear-gradient(90deg,#6366f1,#8b5cf6)', borderRadius: '4px', transition: 'width 0.3s' }} />
                </div>
            </div>

            {/* GPU */}
            <div style={{ marginBottom: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#9ca3af' }}>
                    <span>GPU</span>
                    <span>{gpuPct.toFixed(0)}% | {frame.gpu_temp.toFixed(0)}°C | {frame.gpu_memory_mb.toFixed(0)}MB</span>
                </div>
                <div style={{ width: '100%', height: '6px', background: '#1e293b', borderRadius: '3px', overflow: 'hidden', marginTop: '4px' }}>
                    <div style={{ width: `${gpuPct}%`, height: '100%', background: gpuColor, borderRadius: '3px', transition: 'width 0.5s' }} />
                </div>
            </div>

            {/* Loss graph */}
            <LossCanvas history={history} />

            {/* Footer */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#6b7280', marginTop: '8px' }}>
                <span>LR: {frame.learning_rate.toExponential(2)}</span>
                <span>Loss: {frame.loss.toFixed(4)}</span>
                <span>{frame.samples_processed.toLocaleString()} / {frame.total_samples.toLocaleString()}</span>
            </div>
        </div>
    );
}

export type { TelemetryFrame };
