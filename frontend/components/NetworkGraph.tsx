'use client';

import React, { useEffect, useRef, useState, useMemo } from 'react';
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

interface NetworkGraphProps {
    targetName: string;
    connections: NetworkConnection[];
    platforms?: PlatformNode[];
}

export default function NetworkGraph({ targetName, connections, platforms }: NetworkGraphProps) {
    const fgRef = useRef<any>(null);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
    const containerRef = useRef<HTMLDivElement>(null);

    // Parse nodes and links
    const graphData = useMemo(() => {
        const validConnections = connections.filter(
            conn => conn.name && conn.name.trim() !== ''
        );

        const nodes: GraphNode[] = [
            { id: 'target', name: targetName, group: 1, val: 20 }
        ];

        // Explicit typing for links array
        const links: Array<{ source: string, target: string, name: string }> = [];

        validConnections.forEach((conn, index) => {
            const nodeId = `node_${index}`;
            nodes.push({
                id: nodeId,
                name: conn.name,
                group: 2,
                val: 10,
                relation: conn.relation
            });

            links.push({
                source: 'target',
                target: nodeId,
                name: conn.relation
            });
        });

        platforms?.forEach((platform, index) => {
            const nodeId = `platform_${index}`;
            const firstUrl = platform.url ? platform.url.split(',')[0].trim() : undefined;
            nodes.push({
                id: nodeId,
                name: platform.name,
                group: 3,
                val: platform.activity ? 6 + (platform.activity / 100) * 8 : 8,
                url: firstUrl,
            });
            links.push({ source: 'target', target: nodeId, name: platform.name });
        });

        return { nodes, links, validCount: validConnections.length };
    }, [targetName, connections, platforms]);

    useEffect(() => {
        const updateDimensions = () => {
            if (containerRef.current) {
                setDimensions({
                    width: containerRef.current.clientWidth,
                    height: 350
                });
            }
        };

        updateDimensions();
        window.addEventListener('resize', updateDimensions);
        return () => window.removeEventListener('resize', updateDimensions);
    }, []);

    // Set distance forces when graph loads
    useEffect(() => {
        if (fgRef.current && graphData.nodes.length > 0) {
            fgRef.current.d3Force('link')?.distance(100);
            fgRef.current.d3Force('charge')?.strength(-300);
            fgRef.current.zoom(0.8, 1000);
        }
    }, [graphData]);

    if ((!connections || graphData.validCount === 0) && (!platforms || platforms.length === 0)) {
        return null;
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
                        graphData={graphData}
                        nodeLabel={(node: GraphNode) => {
                            if (node.id === 'target') return node.name ?? '';
                            const rel = node.relation ? `<br/><i>${node.relation}</i>` : '';
                            return `${node.name ?? ''}${rel}`;
                        }}
                        nodeColor={(node: GraphNode) =>
                            node.group === 1 ? '#00f3ff' :
                            node.group === 3 ? '#bf00ff' :
                            '#00ffd0'
                        }
                        nodeRelSize={4}
                        linkColor={() => 'rgba(0, 243, 255, 0.3)'}
                        linkWidth={1}
                        linkDirectionalParticles={2}
                        linkDirectionalParticleSpeed={0.005}
                        linkDirectionalParticleWidth={2}
                        backgroundColor="#00050a"
                        onNodeClick={(node: GraphNode) => {
                            if (node.group === 3 && node.url) {
                                window.open(node.url, '_blank', 'noopener,noreferrer');
                            } else {
                                fgRef.current?.centerAt(node.x, node.y, 1000);
                                fgRef.current?.zoom(1.5, 2000);
                            }
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
                </div>
            </div>
        </div>
    );
}
