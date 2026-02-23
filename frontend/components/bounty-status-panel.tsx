'use client';

import React, { useEffect, useState } from 'react';

/**
 * BountyStatusPanel — Bounty Readiness Dashboard (Phase 8)
 *
 * - Verified badge for exploit-confirmed findings
 * - Hallucination rate display
 * - Field stability meter
 * - Promotion readiness indicator
 * - FPR gauge
 * - Live cycle count
 */

interface BountyStatus {
    exploit_verified: boolean;
    hallucination_rate: number;
    fpr: number;
    field_stability: number;
    promotion_ready: boolean;
    stable_cycles: number;
    required_cycles: number;
    mode: 'A' | 'B';
    live_ready: boolean;
}

function Gauge({ value, max, label, color, unit }: {
    value: number; max: number; label: string; color: string; unit?: string;
}) {
    const pct = Math.min((value / max) * 100, 100);
    const good = value <= max * 0.5;
    return (
        <div style={{ marginBottom: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                <span style={{ color: '#9ca3af' }}>{label}</span>
                <span style={{ color: good ? '#10b981' : color, fontWeight: 700 }}>
                    {unit === '%' ? `${(value * 100).toFixed(2)}%` : value.toFixed(4)}
                </span>
            </div>
            <div style={{ height: '6px', background: '#1e293b', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: good ? '#10b981' : color, borderRadius: '3px', transition: 'width 0.5s' }} />
            </div>
        </div>
    );
}

function Badge({ verified }: { verified: boolean }) {
    return (
        <span style={{
            fontSize: '10px', fontWeight: 800, padding: '3px 10px', borderRadius: '20px',
            background: verified ? '#064e3b' : '#422006',
            color: verified ? '#10b981' : '#f59e0b',
        }}>
            {verified ? '✓ EXPLOIT VERIFIED' : '○ UNVERIFIED'}
        </span>
    );
}

function StabilityMeter({ value }: { value: number }) {
    const bars = 10;
    const filled = Math.round(value * bars);
    return (
        <div style={{ display: 'flex', gap: '2px', alignItems: 'center' }}>
            {Array.from({ length: bars }).map((_, i) => (
                <div key={i} style={{
                    width: '8px', height: '16px', borderRadius: '2px',
                    background: i < filled
                        ? (value >= 0.8 ? '#10b981' : value >= 0.5 ? '#f59e0b' : '#ef4444')
                        : '#1e293b',
                }} />
            ))}
            <span style={{ fontSize: '11px', color: '#9ca3af', marginLeft: '6px' }}>
                {(value * 100).toFixed(0)}%
            </span>
        </div>
    );
}

export default function BountyStatusPanel() {
    const [status, setStatus] = useState<BountyStatus>({
        exploit_verified: false,
        hallucination_rate: 0,
        fpr: 0,
        field_stability: 0,
        promotion_ready: false,
        stable_cycles: 0,
        required_cycles: 5,
        mode: 'A',
        live_ready: false,
    });
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = new WebSocket(process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765/bounty');
                ws.onopen = () => setConnected(true);
                ws.onmessage = (e) => {
                    try { setStatus(JSON.parse(e.data)); } catch { }
                };
                ws.onclose = () => { setConnected(false); setTimeout(connect, 3000); };
                ws.onerror = () => ws?.close();
            } catch { setTimeout(connect, 3000); }
        }
        connect();
        return () => ws?.close();
    }, []);

    const box: React.CSSProperties = {
        background: '#0f1117', border: '1px solid #1e293b', borderRadius: '12px',
        padding: '16px', fontFamily: 'Inter, system-ui, sans-serif', color: '#e2e8f0',
        maxWidth: '420px', display: 'flex', flexDirection: 'column', gap: '12px',
    };

    return (
        <div style={box}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 800, margin: 0 }}>
                    Bounty Readiness
                    <span style={{ fontSize: '10px', marginLeft: '6px', color: connected ? '#10b981' : '#ef4444' }}>
                        {connected ? '● Live' : '○ Offline'}
                    </span>
                </h3>
                <Badge verified={status.exploit_verified} />
            </div>

            {/* Mode + LIVE_READY */}
            <div style={{ display: 'flex', gap: '8px' }}>
                <span style={{
                    fontSize: '11px', fontWeight: 700, padding: '3px 10px', borderRadius: '6px',
                    background: status.mode === 'B' ? '#312e81' : '#1e293b',
                    color: status.mode === 'B' ? '#a78bfa' : '#6b7280',
                }}>
                    MODE {status.mode}
                </span>
                {status.live_ready && (
                    <span style={{
                        fontSize: '11px', fontWeight: 700, padding: '3px 10px', borderRadius: '6px',
                        background: '#064e3b', color: '#10b981',
                    }}>
                        LIVE_READY
                    </span>
                )}
                <span style={{
                    fontSize: '11px', fontWeight: 700, padding: '3px 10px', borderRadius: '6px',
                    background: status.promotion_ready ? '#064e3b' : '#422006',
                    color: status.promotion_ready ? '#10b981' : '#f59e0b',
                }}>
                    {status.promotion_ready ? '✓ PROMOTION READY' : '○ NOT READY'}
                </span>
            </div>

            {/* Gauges */}
            <div>
                <Gauge value={status.fpr} max={0.01} label="False Positive Rate" color="#ef4444" unit="%" />
                <Gauge value={status.hallucination_rate} max={0.005} label="Hallucination Rate" color="#f97316" unit="%" />
            </div>

            {/* Stability */}
            <div>
                <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '4px' }}>Field Stability</div>
                <StabilityMeter value={status.field_stability} />
            </div>

            {/* Stable cycles */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                <span style={{ color: '#6b7280' }}>Stable Cycles</span>
                <span style={{ fontWeight: 700, color: status.stable_cycles >= status.required_cycles ? '#10b981' : '#f59e0b' }}>
                    {status.stable_cycles} / {status.required_cycles}
                </span>
            </div>
        </div>
    );
}
