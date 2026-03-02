"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Zap, Home, Settings, RefreshCw, Play, Pause,
    Clock, List, ChevronRight, Activity, AlarmClock
} from "lucide-react";

interface Article { id: string; title: string; description: string; url: string; source_domain: string; status: string; created_at: string; }
interface AgentSettings { queue_batch_size: string; auto_trigger_enabled: string; auto_trigger_interval_minutes: string; last_trigger_at: string | null; }

const INTERVALS = [
    { label: "10 minutes", value: "10" },
    { label: "30 minutes", value: "30" },
    { label: "1 hour", value: "60" },
    { label: "2 hours", value: "120" },
    { label: "4 hours", value: "240" },
];
const BATCH_SIZES = ["2", "5", "10", "15", "20"];

function StatusBadge({ status }: { status: string }) {
    const color: Record<string, string> = {
        Pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
        Processing: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
        Done: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
        Error: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
    };
    return (
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${color[status] ?? "bg-muted text-muted-foreground"}`}>
            {status}
        </span>
    );
}

export default function AgentSettingsPage() {
    const [agentSettings, setAgentSettings] = useState<AgentSettings>({
        queue_batch_size: "2",
        auto_trigger_enabled: "false",
        auto_trigger_interval_minutes: "30",
        last_trigger_at: null,
    });
    const [queue, setQueue] = useState<Article[]>([]);
    const [allArticles, setAllArticles] = useState<Article[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [nextTriggerIn, setNextTriggerIn] = useState<string | null>(null);
    const autoTriggerRef = useRef<NodeJS.Timeout | null>(null);

    const batchSize = parseInt(agentSettings.queue_batch_size || "2", 10);

    const loadAll = useCallback(async () => {
        setLoading(true);
        try {
            const [settRes, pendRes, artRes] = await Promise.all([
                supabase.from("agent_settings").select("key,value"),
                supabase.from("feeder_articles").select("*").eq("status", "Pending").order("created_at", { ascending: true }).limit(batchSize),
                supabase.from("feeder_articles").select("id,title,description,url,source_domain,status,created_at").order("created_at", { ascending: false }).limit(30),
            ]);
            const sMap: Record<string, string | null> = {};
            for (const row of settRes.data ?? []) sMap[row.key] = row.value;
            setAgentSettings(prev => ({ ...prev, ...sMap } as AgentSettings));
            setQueue(pendRes.data ?? []);
            setAllArticles(artRes.data ?? []);
        } finally {
            setLoading(false);
        }
    }, [batchSize]);

    useEffect(() => { loadAll(); }, [loadAll]);

    // Auto-trigger countdown display
    useEffect(() => {
        if (agentSettings.auto_trigger_enabled !== "true" || !agentSettings.last_trigger_at) {
            setNextTriggerIn(null);
            return;
        }
        const intervalMs = parseInt(agentSettings.auto_trigger_interval_minutes || "30", 10) * 60 * 1000;
        const tick = () => {
            const last = new Date(agentSettings.last_trigger_at!).getTime();
            const nextAt = last + intervalMs;
            const remaining = nextAt - Date.now();
            if (remaining <= 0) {
                setNextTriggerIn("Now");
            } else {
                const m = Math.floor(remaining / 60000);
                const s = Math.floor((remaining % 60000) / 1000);
                setNextTriggerIn(`${m}m ${s}s`);
            }
        };
        tick();
        const id = setInterval(tick, 1000);
        return () => clearInterval(id);
    }, [agentSettings.auto_trigger_enabled, agentSettings.last_trigger_at, agentSettings.auto_trigger_interval_minutes]);

    const saveSettings = async () => {
        setSaving(true);
        await Promise.all(
            Object.entries(agentSettings)
                .filter(([, v]) => v !== null)
                .map(([key, value]) =>
                    supabase.from("agent_settings").upsert({ key, value: value as string, updated_at: new Date().toISOString() })
                )
        );
        setSaving(false);
        loadAll();
    };

    const toggleAutoTrigger = async () => {
        const next = agentSettings.auto_trigger_enabled === "true" ? "false" : "true";
        setAgentSettings(p => ({ ...p, auto_trigger_enabled: next }));
        await supabase.from("agent_settings").upsert({ key: "auto_trigger_enabled", value: next, updated_at: new Date().toISOString() });
    };

    // Reset all Processing articles back to Pending (for failed/interrupted runs)
    const resetStuckArticles = async () => {
        const { data, error } = await supabase
            .from("feeder_articles")
            .update({ status: "Pending" })
            .eq("status", "Processing");
        if (!error) {
            alert("All Processing articles reverted to Pending for retry.");
            loadAll();
        } else {
            alert("Reset failed: " + error.message);
        }
    };


    // Fire agent manually — for each article in queue, trigger one thread
    const fireAgent = async () => {
        const articles = queue.slice(0, batchSize);
        if (articles.length === 0) { alert("No pending articles in queue."); return; }
        // Update last_trigger_at
        await supabase.from("agent_settings").upsert({ key: "last_trigger_at", value: new Date().toISOString() });
        // Mark as Processing
        const ids = articles.map(a => a.id);
        await supabase.from("feeder_articles").update({ status: "Processing" }).in("id", ids);
        // Navigate to main agent page, state passed via URL
        const encoded = encodeURIComponent(JSON.stringify(articles));
        window.location.href = `/?queue=${encoded}`;
    };

    const PKT_TIME = new Date().toLocaleString("en-PK", {
        timeZone: "Asia/Karachi",
        hour12: false,
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
    });

    return (
        <div className="flex h-screen flex-col bg-background overflow-hidden">
            <header className="flex h-16 shrink-0 items-center justify-between border-b px-6">
                <div className="flex items-center gap-3">
                    <Zap className="h-5 w-5 text-primary" />
                    <h1 className="text-xl font-semibold">Agent Settings</h1>
                    <span className="text-xs text-muted-foreground ml-4 font-mono">{PKT_TIME} PKT</span>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={loadAll} disabled={loading}>
                        <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh
                    </Button>
                    <Link href="/feeder/settings"><Button variant="outline" size="sm"><Settings className="mr-2 h-4 w-4" />Feeder Settings</Button></Link>
                    <Link href="/"><Button variant="outline" size="sm"><Home className="mr-2 h-4 w-4" />Agent</Button></Link>
                </div>
            </header>

            <main className="flex-1 overflow-auto p-6 space-y-6">
                <div className="grid gap-6 lg:grid-cols-2">
                    {/* Queue Config */}
                    <section className="rounded-xl border bg-card shadow-sm">
                        <div className="p-4 border-b flex items-center gap-2">
                            <List className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Queue Configuration</h2>
                        </div>
                        <div className="p-5 space-y-4">
                            <div>
                                <label className="text-sm font-medium">Batch Size</label>
                                <p className="text-xs text-muted-foreground mb-2">
                                    Articles sent per trigger. Each article runs in its own thread (FIFO).
                                </p>
                                <div className="flex gap-2 flex-wrap">
                                    {BATCH_SIZES.map(n => (
                                        <button
                                            key={n}
                                            onClick={() => setAgentSettings(p => ({ ...p, queue_batch_size: n }))}
                                            className={`w-12 h-10 rounded-lg border text-sm font-semibold transition-all
                        ${agentSettings.queue_batch_size === n
                                                    ? "border-primary bg-primary text-primary-foreground shadow"
                                                    : "border-border bg-muted hover:bg-muted/80"
                                                }`}
                                        >{n}</button>
                                    ))}
                                    <div className="flex items-center gap-1">
                                        <Input
                                            type="number"
                                            min={1} max={30}
                                            className="h-10 w-20 text-sm"
                                            value={agentSettings.queue_batch_size}
                                            onChange={e => setAgentSettings(p => ({ ...p, queue_batch_size: e.target.value }))}
                                        />
                                        <span className="text-xs text-muted-foreground">custom</span>
                                    </div>
                                </div>
                            </div>

                            <div className="p-3 rounded-lg bg-muted/50 border text-sm text-muted-foreground">
                                <p className="font-medium text-foreground mb-1">How the Queue Works</p>
                                <ul className="space-y-1 list-none">
                                    <li><ChevronRight className="inline h-3 w-3 mr-1" />Fetches <strong>{batchSize}</strong> latest Pending articles (FIFO)</li>
                                    <li><ChevronRight className="inline h-3 w-3 mr-1" />Each article → one separate agent thread</li>
                                    <li><ChevronRight className="inline h-3 w-3 mr-1" />When batch completes → next batch ready on next trigger</li>
                                    <li><ChevronRight className="inline h-3 w-3 mr-1" />Queue is a bucket — waits for manual or auto trigger</li>
                                </ul>
                            </div>

                            <Button onClick={saveSettings} disabled={saving} className="w-full">
                                {saving ? "Saving…" : "Save Queue Settings"}
                            </Button>
                        </div>
                    </section>

                    {/* Auto Trigger */}
                    <section className="rounded-xl border bg-card shadow-sm">
                        <div className="p-4 border-b flex items-center gap-2">
                            <AlarmClock className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Auto-Trigger Schedule</h2>
                        </div>
                        <div className="p-5 space-y-4">
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={toggleAutoTrigger}
                                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors
                    ${agentSettings.auto_trigger_enabled === "true" ? "bg-primary" : "bg-muted"}`}
                                >
                                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform
                    ${agentSettings.auto_trigger_enabled === "true" ? "translate-x-6" : "translate-x-1"}`} />
                                </button>
                                <span className="text-sm font-medium">
                                    Auto-trigger {agentSettings.auto_trigger_enabled === "true" ? "ON" : "OFF"}
                                </span>
                            </div>

                            <div>
                                <label className="text-sm font-medium">Trigger Interval</label>
                                <p className="text-xs text-muted-foreground mb-2">Agent will run automatically every N minutes</p>
                                <div className="flex gap-2 flex-wrap">
                                    {INTERVALS.map(iv => (
                                        <button
                                            key={iv.value}
                                            onClick={() => setAgentSettings(p => ({ ...p, auto_trigger_interval_minutes: iv.value }))}
                                            className={`px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all
                        ${agentSettings.auto_trigger_interval_minutes === iv.value
                                                    ? "border-primary bg-primary text-primary-foreground"
                                                    : "border-border bg-muted hover:bg-muted/80"
                                                }`}
                                        >{iv.label}</button>
                                    ))}
                                </div>
                                <div className="flex items-center gap-2 mt-2">
                                    <Input
                                        type="number" min={1}
                                        className="h-8 w-24 text-sm"
                                        value={agentSettings.auto_trigger_interval_minutes}
                                        onChange={e => setAgentSettings(p => ({ ...p, auto_trigger_interval_minutes: e.target.value }))}
                                    />
                                    <span className="text-xs text-muted-foreground">minutes (custom)</span>
                                </div>
                            </div>

                            {/* PKT Clock */}
                            <div className="rounded-lg border bg-muted/40 p-3 flex items-center gap-3">
                                <Clock className="h-4 w-4 text-primary" />
                                <div>
                                    <p className="text-xs text-muted-foreground">Current Pakistan Time (PKT, UTC+5)</p>
                                    <p className="text-sm font-mono font-bold">{PKT_TIME}</p>
                                </div>
                            </div>

                            {agentSettings.auto_trigger_enabled === "true" && nextTriggerIn && (
                                <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
                                    <span className="text-muted-foreground">Next trigger in: </span>
                                    <span className="font-bold text-primary">{nextTriggerIn}</span>
                                </div>
                            )}

                            {agentSettings.last_trigger_at && (
                                <p className="text-xs text-muted-foreground">
                                    Last triggered:{" "}
                                    {new Date(agentSettings.last_trigger_at).toLocaleString("en-PK", {
                                        timeZone: "Asia/Karachi", hour12: false,
                                        year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
                                    })} PKT
                                </p>
                            )}

                            <Button onClick={saveSettings} disabled={saving} variant="outline" className="w-full">
                                {saving ? "Saving…" : "Save Trigger Settings"}
                            </Button>
                        </div>
                    </section>
                </div>

                {/* Queue Preview + Manual Trigger */}
                <section className="rounded-xl border bg-card shadow-sm">
                    <div className="p-4 border-b flex items-center gap-2">
                        <Activity className="h-4 w-4 text-primary" />
                        <h2 className="font-semibold">Current Queue</h2>
                        <span className="ml-auto text-xs text-muted-foreground">Next {batchSize} pending articles (FIFO)</span>
                        <Button
                            onClick={resetStuckArticles}
                            size="sm"
                            variant="outline"
                            className="ml-2 border-yellow-500 text-yellow-600 hover:bg-yellow-50"
                            title="Revert all Processing articles back to Pending (use when agent fails or is interrupted)"
                        >
                            Reset Stuck
                        </Button>
                        <Button
                            onClick={fireAgent}
                            size="sm"
                            className="ml-2"
                            disabled={queue.length === 0}
                        >
                            <Play className="mr-2 h-3.5 w-3.5" />
                            Start Agent ({Math.min(queue.length, batchSize)} articles)
                        </Button>
                    </div>
                    <div className="divide-y">
                        {queue.length === 0 && (
                            <div className="p-6 text-center text-muted-foreground text-sm">
                                No pending articles in the queue. Run the feeder to populate it.
                            </div>
                        )}
                        {queue.slice(0, batchSize).map((art, i) => (
                            <div key={art.id} className="p-4 flex items-start gap-3">
                                <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold shrink-0">
                                    {i + 1}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <p className="font-medium text-sm truncate">{art.title}</p>
                                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{art.description}</p>
                                    <div className="flex items-center gap-2 mt-1">
                                        <span className="text-xs text-muted-foreground">{art.source_domain}</span>
                                        <span className="text-xs text-muted-foreground">·</span>
                                        <span className="text-xs text-muted-foreground">
                                            {new Date(art.created_at).toLocaleString("en-PK", { timeZone: "Asia/Karachi", hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })} PKT
                                        </span>
                                    </div>
                                </div>
                                <StatusBadge status={art.status} />
                                <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                            </div>
                        ))}
                    </div>
                </section>

                {/* Recent Articles */}
                <section className="rounded-xl border bg-card shadow-sm">
                    <div className="p-4 border-b flex items-center gap-2">
                        <List className="h-4 w-4 text-muted-foreground" />
                        <h2 className="font-semibold">Recent Articles</h2>
                        <span className="ml-auto text-xs text-muted-foreground">Last 30 articles (all statuses)</span>
                    </div>
                    <div className="divide-y max-h-96 overflow-auto">
                        {allArticles.length === 0 && (
                            <div className="p-6 text-center text-muted-foreground text-sm">No articles yet.</div>
                        )}
                        {allArticles.map(art => (
                            <div key={art.id} className="p-3 flex items-center gap-3">
                                <StatusBadge status={art.status} />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate">{art.title}</p>
                                    <p className="text-xs text-muted-foreground">{art.source_domain} · {new Date(art.created_at).toLocaleString("en-PK", { timeZone: "Asia/Karachi", hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })} PKT</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </main>
        </div>
    );
}
