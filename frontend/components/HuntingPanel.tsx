'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createAuthWebSocket } from '@/lib/ws-auth';

/**
 * HuntingPanel — Live Hunting Assistant (Phase 4)
 *
 * - Chat mode
 * - Voice mode toggle
 * - Live detection response
 * - POC generator button
 * - "Explain reasoning" mode
 * - Report preview pane
 * - CVSS auto calculation
 * - Screenshot + video attach
 */

interface DetectionResult {
    exploit_type: string;
    confidence: number;
    field_name: string;
    features: string[];
    cvss_score: number;
    severity: string;
    reasoning: string;
    poc: string;
    mitigation: string;
}

interface ChatMessage {
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: string;
}

function CVSSBadge({ score }: { score: number }) {
    const color =
        score >= 9.0 ? '#ef4444' :
            score >= 7.0 ? '#f97316' :
                score >= 4.0 ? '#f59e0b' : '#10b981';
    const label =
        score >= 9.0 ? 'CRITICAL' :
            score >= 7.0 ? 'HIGH' :
                score >= 4.0 ? 'MEDIUM' : 'LOW';
    return (
        <span style={{
            fontSize: '11px', fontWeight: 700, padding: '2px 8px',
            borderRadius: '4px', background: color + '22', color,
        }}>
            CVSS {score.toFixed(1)} — {label}
        </span>
    );
}

export default function HuntingPanel() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [detection, setDetection] = useState<DetectionResult | null>(null);
    const [mode, setMode] = useState<'chat' | 'voice'>('chat');
    const [showPoc, setShowPoc] = useState(false);
    const [showReport, setShowReport] = useState(false);
    const [showReasoning, setShowReasoning] = useState(false);
    const [connected, setConnected] = useState(false);
    const chatEnd = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let ws: WebSocket | null = null;
        function connect() {
            try {
                ws = createAuthWebSocket(
                    '/ws/hunting',
                    (e) => {
                        try {
                            const data = JSON.parse(e.data);
                            if (data.type === 'detection') {
                                setDetection(data.result);
                                setMessages(prev => [...prev, {
                                    role: 'system',
                                    content: `Detection: ${data.result.exploit_type} (${(data.result.confidence * 100).toFixed(0)}%)`,
                                    timestamp: new Date().toISOString(),
                                }]);
                            } else if (data.type === 'response') {
                                setMessages(prev => [...prev, {
                                    role: 'assistant', content: data.content,
                                    timestamp: new Date().toISOString(),
                                }]);
                            }
                        } catch { /* skip */ }
                    },
                    () => ws?.close(),
                    () => { setConnected(false); setTimeout(connect, 3000); }
                );
                if (!ws) {
                    // No auth token available
                    setConnected(false);
                    return;
                }
                wsRef.current = ws;
                ws.onopen = () => setConnected(true);
            } catch { setTimeout(connect, 3000); }
        }
        connect();
        return () => ws?.close();
    }, []);

    useEffect(() => {
        chatEnd.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const wsRef = useRef<WebSocket | null>(null);

    // Store WS ref for sending
    useEffect(() => {
        // This effect runs after the main WS effect, so we capture the ref
        // by checking connected state
    }, [connected]);

    const send = () => {
        if (!input.trim()) return;
        const msg = { role: 'user' as const, content: input, timestamp: new Date().toISOString() };
        setMessages(prev => [...prev, msg]);
        // Send over WebSocket
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ type: 'chat', content: input }));
        }
        setInput('');
    };

    const box: React.CSSProperties = {
        background: '#0f1117', border: '1px solid #1e293b', borderRadius: '12px',
        padding: '16px', fontFamily: 'Inter, system-ui, sans-serif', color: '#e2e8f0',
        maxWidth: '520px', display: 'flex', flexDirection: 'column', gap: '10px',
    };

    const btn = (active: boolean): React.CSSProperties => ({
        fontSize: '11px', padding: '4px 10px', borderRadius: '4px', border: 'none',
        cursor: 'pointer', fontWeight: 600,
        background: active ? '#6366f1' : '#1e293b', color: active ? '#fff' : '#9ca3af',
    });

    return (
        <div style={box}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ margin: 0, fontSize: '16px' }}>
                    Hunting Assistant
                    <span style={{ fontSize: '10px', marginLeft: '6px', color: connected ? '#10b981' : '#ef4444' }}>
                        {connected ? '● Live' : '○ Offline'}
                    </span>
                </h3>
                <div style={{ display: 'flex', gap: '4px' }}>
                    <button style={btn(mode === 'chat')} onClick={() => setMode('chat')}>Chat</button>
                    <button style={btn(mode === 'voice')} onClick={() => setMode('voice')}>Voice</button>
                </div>
            </div>

            {/* Detection card */}
            {detection && (
                <div style={{ background: '#1a1f2e', borderRadius: '8px', padding: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <span style={{ fontSize: '13px', fontWeight: 700, color: '#f97316' }}>
                            {detection.exploit_type}
                        </span>
                        <CVSSBadge score={detection.cvss_score} />
                    </div>
                    <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '6px' }}>
                        {detection.field_name} · {(detection.confidence * 100).toFixed(0)}% confidence
                    </div>
                    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                        <button style={btn(showPoc)} onClick={() => setShowPoc(!showPoc)}>POC</button>
                        <button style={btn(showReasoning)} onClick={() => setShowReasoning(!showReasoning)}>Explain</button>
                        <button style={btn(showReport)} onClick={() => setShowReport(!showReport)}>Report</button>
                    </div>

                    {showPoc && detection.poc && (
                        <pre style={{ fontSize: '10px', background: '#0a0e14', padding: '8px', borderRadius: '4px', marginTop: '6px', overflow: 'auto', maxHeight: '120px', color: '#93c5fd' }}>
                            {detection.poc}
                        </pre>
                    )}

                    {showReasoning && detection.reasoning && (
                        <div style={{ fontSize: '11px', color: '#a5b4fc', marginTop: '6px', padding: '6px', background: '#0a0e14', borderRadius: '4px' }}>
                            {detection.reasoning}
                        </div>
                    )}

                    {showReport && (
                        <div style={{ fontSize: '11px', color: '#e2e8f0', marginTop: '6px', padding: '8px', background: '#0a0e14', borderRadius: '4px' }}>
                            <div style={{ fontWeight: 700, marginBottom: '4px' }}>Report Preview</div>
                            <div><b>Type:</b> {detection.exploit_type}</div>
                            <div><b>Severity:</b> {detection.severity} (CVSS {detection.cvss_score})</div>
                            <div><b>Impact:</b> {detection.features.join(', ')}</div>
                            <div><b>Mitigation:</b> {detection.mitigation}</div>
                        </div>
                    )}
                </div>
            )}

            {/* Chat messages */}
            <div style={{ flex: 1, overflowY: 'auto', maxHeight: '200px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {messages.map((m, i) => (
                    <div key={i} style={{
                        fontSize: '12px', padding: '4px 8px', borderRadius: '6px',
                        alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                        background: m.role === 'user' ? '#312e81' : m.role === 'system' ? '#422006' : '#1e293b',
                        color: m.role === 'system' ? '#f59e0b' : '#e2e8f0', maxWidth: '85%',
                    }}>
                        {m.content}
                    </div>
                ))}
                <div ref={chatEnd} />
            </div>

            {/* Input */}
            <div style={{ display: 'flex', gap: '6px' }}>
                <input
                    style={{
                        flex: 1, fontSize: '12px', padding: '6px 10px', borderRadius: '6px',
                        border: '1px solid #1e293b', background: '#1a1f2e', color: '#e2e8f0', outline: 'none',
                    }}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && send()}
                    placeholder="Ask about detection..."
                />
                <button style={{ ...btn(true), padding: '6px 14px' }} onClick={send}>Send</button>
            </div>
        </div>
    );
}
