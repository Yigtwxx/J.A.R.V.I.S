'use client';

import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Network } from 'lucide-react';

interface NetworkConnection {
    name: string;
    role: string;
    relation: string;
}

interface PlatformNode {
    name: string;
    url: string;
    activity?: number;
}

interface GraphNode {
    id: string;
    name?: string;
    type?: string;
    color?: string;
    val?: number;
    group?: number;
    relation?: string;
    url?: string;
    x?: number;
    y?: number;
}

interface RelationshipEdge {
    from: string;
    to: string;
    type?: string;
    source_url?: string;
}

interface NetworkGraphProps {
    targetName: string;
    connections: NetworkConnection[];
    platforms?: PlatformNode[];
    relationships?: RelationshipEdge[];
}

function isValidUrl(url: string): boolean {
    try {
        const parsed = new URL(url);
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
        return false;
    }
}

export default function NetworkGraph({ targetName, connections, platforms, relationships }: NetworkGraphProps) {
    const fgRef = useRef<any>(null);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const containerRef = useRef<HTMLDivElement>(null);
    const engineConfigured = useRef(false);

    // Parse nodes and links
    const graphData = useMemo(() => {
        const validConnections = connections.filter(
            conn => conn.name && conn.name.trim() !== ''
        );

        const nodes: GraphNode[] = [
            { id: 'target', name: targetName, group: 1, val: 20 }
        ];

        // Explicit typing for links array (url carries an optional public source)
        const links: Array<{ source: string, target: string, name: string, url?: string }> = [];

        // name → node id, so relationships can de-dup against existing nodes
        const nameToId = new Map<string, string>();
        const norm = (s: string) => s.trim().toLowerCase();
        if (targetName) nameToId.set(norm(targetName), 'target');

        validConnections.forEach((conn, index) => {
            const nodeId = `node_${index}`;
            nodes.push({
                id: nodeId,
                name: conn.name,
                group: 2,
                val: 10,
                relation: conn.relation
            });
            nameToId.set(norm(conn.name), nodeId);

            links.push({
                source: 'target',
                target: nodeId,
                name: conn.relation
            });
        });

        platforms?.forEach((platform, index) => {
            const nodeId = `platform_${index}`;
            const validUrl = platform.url && isValidUrl(platform.url) ? platform.url : undefined;
            nodes.push({
                id: nodeId,
                name: platform.name,
                group: 3,
                val: platform.activity ? 6 + (platform.activity / 100) * 8 : 8,
                url: validUrl,
            });
            links.push({ source: 'target', target: nodeId, name: platform.name });
        });

        // Typed relationship edges (Faz 3.2) — each carries an optional public source
        (relationships ?? []).forEach((rel, index) => {
            const toName = (rel.to || '').trim();
            if (!toName) return;
            let toId = nameToId.get(norm(toName));
            if (!toId) {
                toId = `rel_${index}`;
                nodes.push({ id: toId, name: toName, group: 4, val: 9, relation: rel.type });
                nameToId.set(norm(toName), toId);
            }
            const fromId = nameToId.get(norm(rel.from || '')) ?? 'target';
            const validUrl = rel.source_url && isValidUrl(rel.source_url) ? rel.source_url : undefined;
            links.push({
                source: fromId,
                target: toId,
                name: rel.type || 'related',
                url: validUrl,
            });
        });

        return { nodes, links, validCount: validConnections.length };
    }, [targetName, connections, platforms, relationships]);

    // Reset engine config flag when graph data changes
    useEffect(() => {
        engineConfigured.current = false;
    }, [graphData]);

    useEffect(() => {
        const updateDimensions = () => {
            if (containerRef.current && containerRef.current.clientWidth > 0) {
                setDimensions({
                    width: containerRef.current.clientWidth,
                    height: 350
                });
            }
        };

        updateDimensions();
        // Retry after 50ms to handle React 19 Strict Mode double-mount timing
        const timeout = setTimeout(updateDimensions, 50);
        window.addEventListener('resize', updateDimensions);
        return () => {
            clearTimeout(timeout);
            window.removeEventListener('resize', updateDimensions);
        };
    }, []);

    // Configure force simulation via onEngineStop — fires from inside ForceGraph2D
    // so fgRef.current is guaranteed to be set at that point
    const handleEngineStop = useCallback(() => {
        if (fgRef.current && !engineConfigured.current) {
            engineConfigured.current = true;
            fgRef.current.d3Force('link')?.distance(100);
            fgRef.current.d3Force('charge')?.strength(-300);
            fgRef.current.zoom(0.8, 0);
        }
    }, []);

    if ((!connections || graphData.validCount === 0) && (!platforms || platforms.length === 0) && (!relationships || relationships.length === 0)) {
        return (
            <div className="border border-[#00f3ff]/10 rounded-xl p-4 mt-6 flex flex-col items-center gap-1 bg-black/20">
                <Network size={16} className="text-[#00f3ff]/30" />
                <p className="font-mono text-[10px] text-white/25 tracking-widest uppercase">No Relational Network Data Available</p>
            </div>
        );
    }

    return (
        <div className="bg-black/40 border border-[#00f3ff]/20 rounded-xl overflow-hidden shadow-[0_0_15px_rgba(0,243,255,0.05)] mt-6 animate-fade-in-up">
            {/* Header */}
            <div className="flex items-center gap-2 p-3 border-b border-[#00f3ff]/20 bg-[#001824]/80">
                <Network size={18} className="text-[#00f3ff] animate-pulse" />
                <h3 className="font-mono text-sm tracking-wider text-[#00f3ff] font-semibold">
                    KNOWLEDGE GRAPH / RELATIONAL NETWORK
                </h3>
            </div>

            {/* Graph Area */}
            <div ref={containerRef} className="w-full relative bg-[#00050a] h-[350px]">
                {dimensions.width > 0 && (
                    <ForceGraph2D
                        ref={fgRef}
                        width={dimensions.width}
                        height={dimensions.height}
                        graphData={{ nodes: graphData.nodes, links: graphData.links }}
                        nodeLabel={(node: any) => {
                            if (node.id === 'target') return node.name ?? '';
                            const rel = node.relation ? `<br/><i>${node.relation}</i>` : '';
                            return `${node.name ?? ''}${rel}`;
                        }}
                        nodeColor={(node: any) =>
                            node.group === 1 ? '#00f3ff' :
                            node.group === 3 ? '#bf00ff' :
                            node.group === 4 ? '#ffb020' :
                            '#00ffd0'
                        }
                        nodeRelSize={4}
                        linkColor={(link: any) =>
                            typeof link.name === 'string' && link.name.startsWith('sanctions:') ? 'rgba(255, 60, 60, 0.55)' :
                            link.url ? 'rgba(255, 176, 32, 0.45)' :
                            'rgba(0, 243, 255, 0.3)'
                        }
                        linkLabel={(link: any) => link.name ?? ''}
                        linkWidth={1}
                        linkDirectionalParticles={2}
                        linkDirectionalParticleSpeed={0.005}
                        linkDirectionalParticleWidth={2}
                        backgroundColor="#00050a"
                        showPointerCursor={(obj: any) => !!(obj && obj.url)}
                        onEngineStop={handleEngineStop}
                        onNodeClick={(node: any) => {
                            if (node.group === 3 && node.url) {
                                window.open(node.url, '_blank', 'noopener,noreferrer');
                            } else if (fgRef.current) {
                                fgRef.current.centerAt(node.x, node.y, 1000);
                                fgRef.current.zoom(1.5, 2000);
                            }
                        }}
                        onLinkClick={(link: any) => {
                            if (link.url) window.open(link.url, '_blank', 'noopener,noreferrer');
                        }}
                    />
                )}

                {/* Legend */}
                <div className="absolute bottom-4 left-4 flex flex-col gap-2 font-mono text-[10px] bg-black/80 p-2 rounded border border-[#00f3ff]/30 text-white/70">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-[#00f3ff] shadow-[0_0_5px_#00f3ff]"></div>
                        <span>Primary Target</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-[#00ffd0] shadow-[0_0_5px_#00ffd0]"></div>
                        <span>Network Node</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-[#bf00ff] shadow-[0_0_5px_#bf00ff]"></div>
                        <span>Platform Node</span>
                    </div>
                    {relationships && relationships.length > 0 && (
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-[#ffb020] shadow-[0_0_5px_#ffb020]"></div>
                            <span>Relationship (click edge → source)</span>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
