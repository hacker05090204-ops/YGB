'use client';

import React, { useEffect, useState } from 'react';
import { authFetch } from '@/lib/ygb-api';
import { createAuthWebSocket } from '@/lib/ws-auth';

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
    divergence_score: number;
    dup_risk: number;
    chaos_stability: number;
    eta_minutes: number;
    active_field: string;
}

interface DataSourceInfo {
    data_source: string;
    dataset_hash: string;
    sample_count: number;
    registry_status: string;
    strict_real_mode: boolean;
    ingestion_manifest_hash: string;
    bridge_hash: string;
    dll_integrity: string;
    integrity_guard: string;
    synthetic_status: string;
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
        divergence_score: 0,
        dup_risk: 0,
        chaos_stability: 0,
        eta_minutes: 0,
        active_field: '',
    });
    const [connected, setConnected] = useState(false);
    const [dataSource, setDataSource] = useState<DataSourceInfo>({
        data_source: 'LOADING',
        dataset_hash: '',
        sample_count: 0,
        registry_status: 'LOADING',
        strict_real_mode: true,
        ingestion_manifest_hash: '',
        bridge_hash: '',
        dll_integrity: 'LOADING',
        integrity_guard: 'LOADING',
        synthetic_status: 'BLOCKED',
    });

    // Fetch data source info
    useEffect(() => {
        const fetchDataSource = async () => {
            try {
                const res = await authFetch(
                    (process.env.NEXT_PUBLIC_YGB_API_URL || 'http://localhost:8000') + '/api/training/data-source'
                );
                if (res.ok) setDataSource(await res.json());
            } catch { /* backend offline */ }
        };
        fetchDataSource();
        const interval = setInterval(fetchDataSource, 10000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = createAuthWebSocket(
                    '/bounty',
                    (e) => {
                        try { setStatus(JSON.parse(e.data)); } catch { }
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

            {/* Divergence + Dup Risk + Chaos */}
            <div>
                <Gauge value={status.divergence_score} max={0.10} label="Divergence Score" color="#8b5cf6" />
                <Gauge value={status.dup_risk} max={1.0} label="Duplicate Risk" color="#f43f5e" unit="%" />
                <Gauge value={1 - status.chaos_stability} max={1.0} label="Chaos Variance" color="#06b6d4" unit="%" />
            </div>

            {/* Active Field + ETA */}
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                <span style={{ color: '#6b7280' }}>Active Field</span>
                <span style={{ fontWeight: 700, color: '#a78bfa', fontSize: '11px' }}>
                    {status.active_field || '—'}
                </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                <span style={{ color: '#6b7280' }}>ETA</span>
                <span style={{ fontWeight: 700, color: '#9ca3af' }}>
                    {status.eta_minutes > 0 ? `${Math.floor(status.eta_minutes / 60)}h ${status.eta_minutes % 60}m` : '—'}
                </span>
            </div>

            {/* Promotion Readiness Checklist */}
            <div style={{ borderTop: '1px solid #1e293b', paddingTop: '8px', marginTop: '4px' }}>
                <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '6px', fontWeight: 700 }}>Promotion Checklist</div>
                {[
                    { label: 'FPR < 1%', ok: status.fpr < 0.01 },
                    { label: 'Hallucination < 0.5%', ok: status.hallucination_rate < 0.005 },
                    { label: 'Exploit Verified', ok: status.exploit_verified },
                    { label: 'Chaos Stable ≥ 95%', ok: status.chaos_stability >= 0.95 },
                    { label: 'Dup Risk < 50%', ok: status.dup_risk < 0.5 },
                    { label: `${status.stable_cycles}/${status.required_cycles} Stable Cycles`, ok: status.stable_cycles >= status.required_cycles },
                ].map((item, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', marginBottom: '2px' }}>
                        <span style={{ color: item.ok ? '#10b981' : '#ef4444', fontWeight: 800 }}>
                            {item.ok ? '✓' : '✗'}
                        </span>
                        <span style={{ color: item.ok ? '#9ca3af' : '#6b7280' }}>{item.label}</span>
                    </div>
                ))}
            </div>

            {/* Data Source Transparency + Integrity */}
            <div style={{ borderTop: '1px solid #1e293b', paddingTop: '8px', marginTop: '4px' }}>
                <div style={{ fontSize: '11px', color: '#6b7280', marginBottom: '6px', fontWeight: 700 }}>Data Source &amp; Integrity</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>Source</span>
                    <span style={{
                        fontWeight: 700,
                        color: dataSource.data_source === 'INGESTION_PIPELINE' ? '#10b981'
                            : dataSource.data_source === 'NO_DATA' ? '#f59e0b'
                                : '#ef4444',
                    }}>
                        {dataSource.data_source === 'INGESTION_PIPELINE' ? 'REAL'
                            : dataSource.data_source === 'SYNTHETIC_GENERATOR' ? 'SYNTHETIC (blocked)'
                                : dataSource.data_source}
                    </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>Samples</span>
                    <span style={{ fontWeight: 700, color: '#9ca3af' }}>{dataSource.sample_count.toLocaleString()}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>Dataset Hash</span>
                    <span style={{ fontWeight: 600, color: '#525252', fontFamily: 'monospace', fontSize: '10px' }}>
                        {dataSource.dataset_hash ? dataSource.dataset_hash.slice(0, 16) + '…' : '—'}
                    </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>Bridge Hash</span>
                    <span style={{ fontWeight: 600, color: '#525252', fontFamily: 'monospace', fontSize: '10px' }}>
                        {dataSource.bridge_hash ? dataSource.bridge_hash.slice(0, 16) + '…' : '—'}
                    </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>DLL Integrity</span>
                    <span style={{
                        fontWeight: 700, fontSize: '10px', padding: '1px 6px', borderRadius: '4px',
                        background: dataSource.dll_integrity === 'VERIFIED' ? '#064e3b'
                            : dataSource.dll_integrity === 'LOADING' ? '#1e293b' : '#7f1d1d',
                        color: dataSource.dll_integrity === 'VERIFIED' ? '#10b981'
                            : dataSource.dll_integrity === 'LOADING' ? '#6b7280' : '#ef4444',
                    }}>
                        {dataSource.dll_integrity}
                    </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>Integrity Guard</span>
                    <span style={{
                        fontWeight: 700, fontSize: '10px', padding: '1px 6px', borderRadius: '4px',
                        background: dataSource.integrity_guard === 'ACTIVE' ? '#064e3b'
                            : dataSource.integrity_guard === 'LOADING' ? '#1e293b' : '#7f1d1d',
                        color: dataSource.integrity_guard === 'ACTIVE' ? '#10b981'
                            : dataSource.integrity_guard === 'LOADING' ? '#6b7280' : '#ef4444',
                    }}>
                        {dataSource.integrity_guard}
                    </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '3px' }}>
                    <span style={{ color: '#6b7280' }}>Synthetic Status</span>
                    <span style={{
                        fontWeight: 700, fontSize: '10px', padding: '1px 6px', borderRadius: '4px',
                        background: '#7f1d1d', color: '#ef4444',
                    }}>
                        {dataSource.synthetic_status || 'BLOCKED'}
                    </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                    <span style={{ color: '#6b7280' }}>Registry</span>
                    <span style={{
                        fontWeight: 700, fontSize: '10px', padding: '1px 6px', borderRadius: '4px',
                        background: dataSource.registry_status === 'VERIFIED' ? '#064e3b' : '#422006',
                        color: dataSource.registry_status === 'VERIFIED' ? '#10b981' : '#f59e0b',
                    }}>
                        {dataSource.registry_status}
                    </span>
                </div>
                {/* Red warning bar for critical failures */}
                {(dataSource.data_source === 'NO_DATA' || dataSource.data_source === 'ERROR'
                    || dataSource.dll_integrity === 'FAILED' || dataSource.dll_integrity === 'ERROR'
                    || dataSource.registry_status === 'NO_MANIFEST') && (
                        <div style={{
                            marginTop: '6px', padding: '6px 8px', borderRadius: '6px',
                            background: '#7f1d1d', border: '1px solid #ef4444',
                            fontSize: '10px', color: '#fca5a5', fontWeight: 700,
                        }}>
                            ⚠ INTEGRITY WARNING: {dataSource.data_source === 'NO_DATA' ? 'No training data available'
                                : dataSource.dll_integrity === 'FAILED' ? 'Bridge DLL hash mismatch'
                                    : dataSource.data_source === 'ERROR' ? 'Data source error'
                                        : 'Verification incomplete'}
                        </div>
                    )}
            </div>
        </div>
    );
}
