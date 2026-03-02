"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
    Settings, Home, Activity, RefreshCw, Trash2,
    PlusCircle, Rss, Globe, ShieldCheck, X, BarChart3,
    AlertTriangle, Database, Zap
} from "lucide-react";

interface FeedSource { id: string; url: string; label: string; is_active: boolean; }
interface WhitelistDomain { id: string; domain: string; note: string; }

function StatCard({ label, value, icon: Icon, color = "text-primary", sub }: {
    label: string; value: number | string; icon: React.ElementType; color?: string; sub?: string;
}) {
    return (
        <div className="rounded-xl border bg-card shadow-sm p-4 flex items-center gap-4">
            <div className={`rounded-lg p-2.5 bg-muted ${color}`}><Icon className="h-5 w-5" /></div>
            <div>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="text-2xl font-bold">{value}</p>
                {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
            </div>
        </div>
    );
}

export default function FeederSettingsPage() {
    const [sources, setSources] = useState<FeedSource[]>([]);
    const [newUrl, setNewUrl] = useState("");
    const [newLabel, setNewLabel] = useState("");
    const [domains, setDomains] = useState<WhitelistDomain[]>([]);
    const [newDomain, setNewDomain] = useState("");
    const [newDomainNote, setNewDomainNote] = useState("");
    const [settings, setEditSettings] = useState<Record<string, string>>({});
    const [stats, setStats] = useState({ guids: 0, hashes: 0, fingerprints: 0, articles: 0, embeddings: 0, pending: 0, done: 0 });
    const [articlesByStatus, setArticlesByStatus] = useState<{ status: string; count: number }[]>([]);
    const [loading, setLoading] = useState(false);
    const [dangerConfirm, setDangerConfirm] = useState(false);
    const [nukeBusy, setNukeBusy] = useState(false);
    const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

    const loadAll = useCallback(async () => {
        setLoading(true);
        try {
            const [srcsRes, domsRes, settRes, guidRes, hashRes, fpRes, artRes] = await Promise.all([
                supabase.from("feeder_sources").select("*").order("created_at"),
                supabase.from("feeder_whitelisted_domains").select("*").order("domain"),
                supabase.from("feeder_settings").select("key,value"),
                supabase.from("feeder_seen_guids").select("id", { count: "exact", head: true }),
                supabase.from("feeder_seen_hashes").select("id", { count: "exact", head: true }),
                supabase.from("feeder_seen_fingerprints").select("id", { count: "exact", head: true }),
                supabase.from("feeder_articles").select("status"),
            ]);

            setSources(srcsRes.data ?? []);
            setDomains(domsRes.data ?? []);
            const sMap: Record<string, string> = {};
            for (const row of settRes.data ?? []) sMap[row.key] = row.value;
            setEditSettings(sMap);

            const statusCounts: Record<string, number> = {};
            for (const a of artRes.data ?? []) statusCounts[a.status] = (statusCounts[a.status] ?? 0) + 1;
            setArticlesByStatus(Object.entries(statusCounts).map(([status, count]) => ({ status, count })));

            setStats({
                guids: guidRes.count ?? 0,
                hashes: hashRes.count ?? 0,
                fingerprints: fpRes.count ?? 0,
                articles: artRes.data?.length ?? 0,
                embeddings: 0, // fetched separately via Pinecone API route
                pending: statusCounts["Pending"] ?? 0,
                done: statusCounts["Done"] ?? 0,
            });

            // Fetch Pinecone count via API
            try {
                const r = await fetch("/api/feeder/pinecone-stats");
                if (r.ok) {
                    const d = await r.json();
                    setStats(s => ({ ...s, embeddings: d.totalRecordCount ?? 0 }));
                }
            } catch { }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadAll(); }, [loadAll]);

    const addSource = async () => {
        if (!newUrl.trim()) return;
        await supabase.from("feeder_sources").insert({ url: newUrl.trim(), label: newLabel.trim() || newUrl.trim() });
        setNewUrl(""); setNewLabel(""); loadAll();
    };

    const deleteSource = async (id: string) => {
        await supabase.from("feeder_sources").delete().eq("id", id); loadAll();
    };

    const toggleSource = async (id: string, is_active: boolean) => {
        await supabase.from("feeder_sources").update({ is_active: !is_active }).eq("id", id); loadAll();
    };

    const addDomain = async () => {
        if (!newDomain.trim()) return;
        const domain = newDomain.trim().toLowerCase().replace(/^www\./, "");
        await supabase.from("feeder_whitelisted_domains").insert({ domain, note: newDomainNote.trim() });
        setNewDomain(""); setNewDomainNote(""); loadAll();
    };

    const deleteDomain = async (id: string) => {
        await supabase.from("feeder_whitelisted_domains").delete().eq("id", id); loadAll();
    };

    const saveSettings = async () => {
        setSaveStatus('saving');
        try {
            // upsert with onConflict:'key' so existing rows are UPDATED not silently skipped
            const results = await Promise.all(
                Object.entries(settings).map(([key, value]) =>
                    supabase
                        .from("feeder_settings")
                        .upsert(
                            { key, value, updated_at: new Date().toISOString() },
                            { onConflict: 'key' }
                        )
                )
            );
            const hasError = results.some(r => r.error);
            if (hasError) {
                console.error('Save errors:', results.filter(r => r.error).map(r => r.error));
                setSaveStatus('error');
            } else {
                setSaveStatus('saved');
            }
            // Reload to confirm what's actually in DB
            await loadAll();
        } catch (e) {
            console.error('saveSettings error:', e);
            setSaveStatus('error');
        } finally {
            // Reset status after 3s
            setTimeout(() => setSaveStatus('idle'), 3000);
        }
    };

    const clearTable = async (table: string, label: string) => {
        if (!confirm(`Clear all records from "${label}"?`)) return;
        await supabase.from(table).delete().neq("id", "00000000-0000-0000-0000-000000000000");
        loadAll();
    };

    // ── DANGER ZONE: Nuke Everything ─────────────────────────────────────────
    const nukeAll = async () => {
        setNukeBusy(true);
        try {
            // Clear Supabase tracking tables
            await Promise.all([
                supabase.from("feeder_seen_guids").delete().neq("id", "00000000-0000-0000-0000-000000000000"),
                supabase.from("feeder_seen_hashes").delete().neq("id", "00000000-0000-0000-0000-000000000000"),
                supabase.from("feeder_seen_fingerprints").delete().neq("id", "00000000-0000-0000-0000-000000000000"),
                supabase.from("feeder_articles").delete().neq("id", "00000000-0000-0000-0000-000000000000"),
                supabase.from("feeder_run_history").delete().neq("id", "00000000-0000-0000-0000-000000000000"),
            ]);
            // Clear Pinecone embeddings
            await fetch("/api/feeder/pinecone-clear", { method: "POST" });
        } finally {
            setNukeBusy(false);
            setDangerConfirm(false);
            loadAll();
        }
    };

    const settingFields = [
        { key: "batch_size", label: "Batch Size", hint: "Articles per feeder run (default: 30)" },
        { key: "max_age_hours", label: "Max Age (hours)", hint: "Layer -2: drop articles older than this" },
        { key: "cluster_threshold", label: "Cluster Threshold (0-100)", hint: "Layer 0: same-event grouping (70 = plan default)" },
        { key: "fuzzy_threshold", label: "Fuzzy Threshold (0-100)", hint: "Layer 3: duplicate title similarity (65 = recommended, 50 = original default)" },
        { key: "fuzzy_db_limit", label: "Fuzzy DB Limit", hint: "Layer 3: max DB titles to compare against (default: 500)" },
        { key: "semantic_threshold", label: "Semantic Threshold (0-1)", hint: "Layer 5: Pinecone cosine cutoff (0.70 = plan default)" },
        { key: "pinecone_top_k", label: "Pinecone Top-K", hint: "Layer 5: nearest vectors to query (default: 5)" },
        { key: "pinecone_model", label: "Pinecone Model", hint: "Layer 5: embedding model name" },
        { key: "run_interval_minutes", label: "Auto-Run Interval (min)", hint: "Feeder auto-run every X minutes" },
    ];


    return (
        <div className="flex h-screen flex-col bg-background overflow-hidden">
            <header className="flex h-16 shrink-0 items-center justify-between border-b px-6">
                <div className="flex items-center gap-3">
                    <Settings className="h-5 w-5 text-primary" />
                    <h1 className="text-xl font-semibold">Feeder Settings & Stats</h1>
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={loadAll} disabled={loading}>
                        <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh
                    </Button>
                    <Link href="/feeder"><Button variant="outline" size="sm"><Activity className="mr-2 h-4 w-4" />Dashboard</Button></Link>
                    <Link href="/agent-settings"><Button variant="outline" size="sm"><Zap className="mr-2 h-4 w-4" />Agent Settings</Button></Link>
                    <Link href="/"><Button variant="outline" size="sm"><Home className="mr-2 h-4 w-4" />Agent</Button></Link>
                </div>
            </header>

            <main className="flex-1 overflow-auto p-6 space-y-6">
                {/* Stats */}
                <section>
                    <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-3 flex items-center gap-2">
                        <BarChart3 className="h-4 w-4" />Database Statistics
                    </h2>
                    <div className="grid gap-3 grid-cols-2 md:grid-cols-4 lg:grid-cols-7">
                        <StatCard label="Seen GUIDs" value={stats.guids} icon={Database} color="text-blue-500" sub="Layer 1" />
                        <StatCard label="Seen Hashes" value={stats.hashes} icon={ShieldCheck} color="text-green-500" sub="Layer 2" />
                        <StatCard label="NER Fingerprints" value={stats.fingerprints} icon={ShieldCheck} color="text-orange-500" sub="Layer 4" />
                        <StatCard label="Pinecone Embeddings" value={stats.embeddings} icon={Globe} color="text-cyan-500" sub="Layer 5" />
                        <StatCard label="Articles Total" value={stats.articles} icon={Activity} color="text-purple-500" sub="All statuses" />
                        <StatCard label="Pending" value={stats.pending} icon={Activity} color="text-yellow-500" sub="In queue" />
                        <StatCard label="Done" value={stats.done} icon={Activity} color="text-emerald-500" sub="Processed" />
                    </div>
                    {articlesByStatus.length > 0 && (
                        <div className="mt-3 flex gap-2 flex-wrap">
                            {articlesByStatus.map(s => (
                                <div key={s.status} className="rounded-lg border bg-card px-3 py-1.5 text-sm">
                                    <span className="font-medium">{s.status}:</span> <span className="text-muted-foreground">{s.count}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </section>

                <div className="grid gap-6 lg:grid-cols-2">
                    {/* Feed Sources */}
                    <section className="rounded-xl border bg-card shadow-sm">
                        <div className="p-4 border-b flex items-center gap-2">
                            <Rss className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Feed Sources (RSS)</h2>
                            <span className="ml-auto text-xs text-muted-foreground">{sources.length} sources</span>
                        </div>
                        <div className="p-4 space-y-2 max-h-64 overflow-auto">
                            {sources.map(s => (
                                <div key={s.id} className="flex items-center gap-2 text-sm">
                                    <button onClick={() => toggleSource(s.id, s.is_active)} title={s.is_active ? "Active (click to pause)" : "Paused (click to activate)"}>
                                        <div className={`h-2.5 w-2.5 rounded-full ${s.is_active ? "bg-green-500" : "bg-muted"}`} />
                                    </button>
                                    <div className="flex-1 min-w-0">
                                        <p className="font-medium truncate">{s.label}</p>
                                        <p className="text-xs text-muted-foreground truncate">{s.url}</p>
                                    </div>
                                    <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive shrink-0" onClick={() => deleteSource(s.id)}>
                                        <X className="h-3 w-3" />
                                    </Button>
                                </div>
                            ))}
                        </div>
                        <div className="p-4 pt-0 flex flex-col gap-2 border-t">
                            <Input placeholder="RSS URL" value={newUrl} onChange={e => setNewUrl(e.target.value)} className="h-8 text-sm" />
                            <Input placeholder="Label (optional)" value={newLabel} onChange={e => setNewLabel(e.target.value)} className="h-8 text-sm" />
                            <Button size="sm" onClick={addSource}><PlusCircle className="mr-2 h-3.5 w-3.5" />Add Source</Button>
                        </div>
                    </section>

                    {/* Whitelisted Domains */}
                    <section className="rounded-xl border bg-card shadow-sm">
                        <div className="p-4 border-b flex items-center gap-2">
                            <Globe className="h-4 w-4 text-primary" />
                            <h2 className="font-semibold">Whitelisted Domains</h2>
                            <span className="ml-auto text-xs text-muted-foreground">{domains.length} domains · Empty = allow all</span>
                        </div>
                        <div className="p-4 space-y-2 max-h-64 overflow-auto">
                            {domains.length === 0 && <p className="text-sm text-muted-foreground">No domains — all sources pass Layer -1.</p>}
                            {domains.map(d => (
                                <div key={d.id} className="flex items-center gap-2 text-sm">
                                    <ShieldCheck className="h-3.5 w-3.5 text-green-500 shrink-0" />
                                    <div className="flex-1">
                                        <p className="font-medium">{d.domain}</p>
                                        {d.note && <p className="text-xs text-muted-foreground">{d.note}</p>}
                                    </div>
                                    <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive" onClick={() => deleteDomain(d.id)}>
                                        <X className="h-3 w-3" />
                                    </Button>
                                </div>
                            ))}
                        </div>
                        <div className="p-4 pt-0 flex flex-col gap-2 border-t">
                            <Input placeholder="e.g. dawn.com" value={newDomain} onChange={e => setNewDomain(e.target.value)} className="h-8 text-sm" />
                            <Input placeholder="Note (optional)" value={newDomainNote} onChange={e => setNewDomainNote(e.target.value)} className="h-8 text-sm" />
                            <Button size="sm" onClick={addDomain}><PlusCircle className="mr-2 h-3.5 w-3.5" />Add Domain</Button>
                        </div>
                    </section>
                </div>

                {/* Pipeline Settings */}
                <section className="rounded-xl border bg-card shadow-sm">
                    <div className="p-4 border-b flex items-center gap-2">
                        <Settings className="h-4 w-4 text-primary" /><h2 className="font-semibold">Pipeline Settings</h2>
                    </div>
                    <div className="p-4 grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
                        {settingFields.map(({ key, label, hint }) => (
                            <div key={key}>
                                <label className="text-xs font-medium">{label}</label>
                                <p className="text-xs text-muted-foreground mb-1.5">{hint}</p>
                                <Input
                                    value={settings[key] ?? ""}
                                    onChange={e => setEditSettings(p => ({ ...p, [key]: e.target.value }))}
                                    className="h-8 text-sm"
                                />
                            </div>
                        ))}
                    </div>
                    <div className="px-4 pb-4 flex items-center gap-3">
                        <Button onClick={saveSettings} size="sm" disabled={saveStatus === 'saving'}>
                            {saveStatus === 'saving' ? 'Saving…' : 'Save Settings'}
                        </Button>
                        {saveStatus === 'saved' && (
                            <span className="text-sm text-green-600 font-medium">✓ Saved successfully</span>
                        )}
                        {saveStatus === 'error' && (
                            <span className="text-sm text-red-600 font-medium">✗ Save failed — check console</span>
                        )}
                    </div>
                </section>

                {/* Individual table clears */}
                <section className="rounded-xl border bg-card shadow-sm">
                    <div className="p-4 border-b flex items-center gap-2">
                        <Trash2 className="h-4 w-4 text-muted-foreground" /><h2 className="font-semibold">Clear Individual Tables</h2>
                    </div>
                    <div className="p-4 flex gap-2 flex-wrap">
                        {[
                            { table: "feeder_seen_guids", label: "Clear GUIDs (L1)" },
                            { table: "feeder_seen_hashes", label: "Clear Hashes (L2)" },
                            { table: "feeder_seen_fingerprints", label: "Clear NER (L4)" },
                            { table: "feeder_articles", label: "Clear Articles" },
                            { table: "feeder_run_history", label: "Clear Run History" },
                        ].map(({ table, label }) => (
                            <Button key={table} variant="outline" size="sm" onClick={() => clearTable(table, label)}>
                                <Trash2 className="mr-1.5 h-3 w-3" />{label}
                            </Button>
                        ))}
                    </div>
                </section>

                {/* DANGER ZONE */}
                <section className="rounded-xl border-2 border-destructive/40 bg-destructive/5 shadow-sm">
                    <div className="p-4 border-b border-destructive/20 flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-destructive" />
                        <h2 className="font-semibold text-destructive">Danger Zone</h2>
                    </div>
                    <div className="p-6 flex flex-col items-start gap-4">
                        <div>
                            <p className="font-medium">Delete ALL Feeder Data</p>
                            <p className="text-sm text-muted-foreground mt-1">
                                This permanently deletes: all articles, all GUIDs, all hashes, all NER fingerprints, all Pinecone embeddings, and all run history. Your feed sources and whitelist domains are kept.
                            </p>
                        </div>
                        {!dangerConfirm ? (
                            <Button variant="destructive" onClick={() => setDangerConfirm(true)}>
                                <AlertTriangle className="mr-2 h-4 w-4" />Delete All Feeder Data
                            </Button>
                        ) : (
                            <div className="flex items-center gap-3 p-3 rounded-lg border border-destructive bg-destructive/10 w-full">
                                <AlertTriangle className="h-5 w-5 text-destructive shrink-0" />
                                <p className="text-sm font-medium flex-1">Are you absolutely sure? This cannot be undone.</p>
                                <Button variant="destructive" size="sm" onClick={nukeAll} disabled={nukeBusy}>
                                    {nukeBusy ? "Deleting…" : "Yes, Delete Everything"}
                                </Button>
                                <Button variant="outline" size="sm" onClick={() => setDangerConfirm(false)}>Cancel</Button>
                            </div>
                        )}
                    </div>
                </section>
            </main>
        </div>
    );
}
