'use client';

import React, { useEffect, useState } from 'react';

/**
 * FieldMasteryDashboard — Field Mastery Dashboard (Phase H)
 *
 * - Field stability meter per field
 * - Hallucination rate graph
 * - Duplicate risk score
 * - Verified exploit badge
 * - Shadow mode indicator
 * - Sequential field progress
 */

interface FieldStatus {
    name: string;
    status: 'QUEUED' | 'ACTIVE' | 'MASTERED' | 'FROZEN';
    accuracy: number;
    fpr: number;
    hallucination: number;
    stability: number;
    dup_risk: number;
    exploit_verified: boolean;
    shadow_stable: boolean;
    cycles: number;
}

interface DashboardData {
    fields: FieldStatus[];
    active_field: string;
    mastered_count: number;
    total_fields: number;
    system_healthy: boolean;
}

function FieldCard({ field }: { field: FieldStatus }) {
    const statusColor: Record<string, string> = {
        QUEUED: '#6b7280', ACTIVE: '#3b82f6', MASTERED: '#10b981', FROZEN: '#ef4444',
    };
    const color = statusColor[field.status] || '#6b7280';
    const bar = (val: number, max: number, col: string) => {
        const pct = Math.min((val / max) * 100, 100);
        return (
            <div style={{ height: '4px', background: '#1e293b', borderRadius: '2px', overflow: 'hidden' }}>
                <div style={{ width: `${pct}%`, height: '100%', background: col, transition: 'width 0.5s' }} />
            </div>
        );
    };

    return (
        <div style={{
            background: '#111827', border: `1px solid ${field.status === 'ACTIVE' ? '#3b82f6' : '#1e293b'}`,
            borderRadius: '10px', padding: '12px', display: 'flex', flexDirection: 'column', gap: '6px',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '13px', fontWeight: 700, color: '#e2e8f0' }}>{field.name}</span>
                <span style={{
                    fontSize: '9px', fontWeight: 700, padding: '2px 8px', borderRadius: '10px',
                    background: color + '22', color,
                }}>{field.status}</span>
            </div>

            {/* Metrics */}
            <div style={{ fontSize: '10px', color: '#9ca3af', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Accuracy</span>
                    <span style={{ color: field.accuracy >= 0.92 ? '#10b981' : '#f59e0b', fontWeight: 700 }}>
                        {(field.accuracy * 100).toFixed(1)}%
                    </span>
                </div>
                {bar(field.accuracy, 1.0, field.accuracy >= 0.92 ? '#10b981' : '#f59e0b')}

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>FPR</span>
                    <span style={{ color: field.fpr < 0.01 ? '#10b981' : '#ef4444', fontWeight: 700 }}>
                        {(field.fpr * 100).toFixed(2)}%
                    </span>
                </div>
                {bar(field.fpr, 0.05, field.fpr < 0.01 ? '#10b981' : '#ef4444')}

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Halluc</span>
                    <span style={{ color: field.hallucination < 0.005 ? '#10b981' : '#f97316', fontWeight: 700 }}>
                        {(field.hallucination * 100).toFixed(2)}%
                    </span>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span>Dup Risk</span>
                    <span style={{ color: field.dup_risk < 0.3 ? '#10b981' : '#f59e0b', fontWeight: 700 }}>
                        {(field.dup_risk * 100).toFixed(0)}%
                    </span>
                </div>
            </div>

            {/* Badges */}
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                {field.exploit_verified && (
                    <span style={{ fontSize: '8px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', background: '#064e3b', color: '#10b981' }}>
                        ✓ VERIFIED
                    </span>
                )}
                {field.shadow_stable && (
                    <span style={{ fontSize: '8px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', background: '#312e81', color: '#a78bfa' }}>
                        ✓ SHADOW
                    </span>
                )}
                <span style={{ fontSize: '8px', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', background: '#1e293b', color: '#9ca3af' }}>
                    {field.cycles}/5 cycles
                </span>
            </div>
        </div>
    );
}

export default function FieldMasteryDashboard() {
    const [data, setData] = useState<DashboardData>({
        fields: [], active_field: '', mastered_count: 0, total_fields: 23, system_healthy: true,
    });
    const [connected, setConnected] = useState(false);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = new WebSocket(process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8765/mastery');
                ws.onopen = () => setConnected(true);
                ws.onmessage = (e) => { try { setData(JSON.parse(e.data)); } catch { } };
                ws.onclose = () => { setConnected(false); setTimeout(connect, 3000); };
                ws.onerror = () => ws?.close();
            } catch { setTimeout(connect, 3000); }
        }
        connect();
        return () => ws?.close();
    }, []);

    return (
        <div style={{
            background: '#0a0e14', border: '1px solid #1e293b', borderRadius: '14px',
            padding: '20px', fontFamily: 'Inter, system-ui, sans-serif', color: '#e2e8f0',
            maxWidth: '800px',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                    <h2 style={{ fontSize: '18px', fontWeight: 800, margin: 0 }}>
                        Field Mastery
                        <span style={{ fontSize: '10px', marginLeft: '8px', color: connected ? '#10b981' : '#ef4444' }}>
                            {connected ? '● Live' : '○ Offline'}
                        </span>
                    </h2>
                    <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '2px' }}>
                        Sequential Training · {data.mastered_count}/{data.total_fields} fields mastered
                    </div>
                </div>
                <div style={{
                    fontSize: '12px', fontWeight: 700, padding: '4px 12px', borderRadius: '8px',
                    background: data.system_healthy ? '#064e3b' : '#7f1d1d',
                    color: data.system_healthy ? '#10b981' : '#ef4444',
                }}>
                    {data.system_healthy ? '✓ HEALTHY' : '✗ RISK'}
                </div>
            </div>

            {/* Progress bar */}
            <div style={{ marginBottom: '16px' }}>
                <div style={{ height: '8px', background: '#1e293b', borderRadius: '4px', overflow: 'hidden' }}>
                    <div style={{
                        width: `${(data.mastered_count / Math.max(data.total_fields, 1)) * 100}%`,
                        height: '100%', background: 'linear-gradient(90deg, #10b981, #3b82f6)',
                        borderRadius: '4px', transition: 'width 0.5s',
                    }} />
                </div>
            </div>

            {/* Field grid */}
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))',
                gap: '10px',
            }}>
                {data.fields.map((f) => <FieldCard key={f.name} field={f} />)}
            </div>
        </div>
    );
}
