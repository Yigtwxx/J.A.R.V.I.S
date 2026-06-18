'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Video, Camera, ExternalLink, Image as ImageIcon, Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
    getLocationCameras,
    getLatestImages,
    type WebcamItem,
    type ImageItem,
} from '@/services/api';
import { showError } from '@/lib/toast';

interface LiveCamerasWidgetProps {
    /** A place/location string used to look up public webcams. */
    place?: string;
    /** A person or place string used to look up the latest public images. */
    query?: string;
}

/**
 * Live Visual Intelligence widget.
 *
 * Shows PUBLIC live webcams near a searched place (publisher-streamed cameras
 * only — traffic / tourism / weather / harbor cams) and the latest publicly
 * published images for a person or place. "Watch live" opens the stream's own
 * public page in a new tab; no private or proxied feeds are ever shown.
 */
const LiveCamerasWidget: React.FC<LiveCamerasWidgetProps> = ({ place, query }) => {
    const t = useTranslations('liveCameras');
    const [cameras, setCameras] = useState<WebcamItem[]>([]);
    const [images, setImages] = useState<ImageItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [loaded, setLoaded] = useState(false);

    const imageQuery = query || place;

    useEffect(() => {
        const controller = new AbortController();
        let cancelled = false;

        const run = async () => {
            if (!place && !imageQuery) return;
            setLoading(true);
            try {
                const [camRes, imgRes] = await Promise.allSettled([
                    place ? getLocationCameras(place, controller.signal) : Promise.resolve(null),
                    imageQuery ? getLatestImages(imageQuery, controller.signal) : Promise.resolve(null),
                ]);

                if (cancelled) return;

                if (camRes.status === 'fulfilled' && camRes.value) {
                    setCameras(camRes.value.webcams || []);
                } else if (camRes.status === 'rejected') {
                    console.error('Camera lookup failed:', camRes.reason);
                }

                if (imgRes.status === 'fulfilled' && imgRes.value) {
                    setImages(imgRes.value.images || []);
                } else if (imgRes.status === 'rejected') {
                    console.error('Image lookup failed:', imgRes.reason);
                }

                if (camRes.status === 'rejected' && imgRes.status === 'rejected') {
                    showError('Visual intelligence lookup failed.');
                }
            } finally {
                if (!cancelled) {
                    setLoading(false);
                    setLoaded(true);
                }
            }
        };

        run();
        return () => {
            cancelled = true;
            controller.abort();
        };
    }, [place, imageQuery]);

    // Nothing to query for, or finished with no results at all → render nothing.
    if (!place && !imageQuery) return null;
    if (loaded && !loading && cameras.length === 0 && images.length === 0) return null;

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mt-6"
        >
            {/* Header */}
            <div className="flex items-center gap-2 mb-1">
                <Video className="w-5 h-5 text-cyan-400 glow-cyan" />
                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase glow-cyan">
                    {t('title')}
                </h4>
            </div>
            <p className="text-[10px] font-mono text-cyan-500/40 mb-4 ml-7">{t('publicNote')}</p>

            {loading && (
                <div className="flex items-center gap-2 text-cyan-400/60 text-xs font-mono mb-4 ml-7">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    {t('loading')}
                </div>
            )}

            {/* Public Live Cameras */}
            {cameras.length > 0 && (
                <div className="mb-6">
                    <div className="flex items-center gap-2 mb-3">
                        <Camera className="w-4 h-4 text-cyan-400/80" />
                        <span className="text-xs font-mono tracking-wider text-cyan-300/80 uppercase">
                            {t('camerasHeader')}
                        </span>
                        <span className="text-[10px] font-mono text-cyan-500/40">({cameras.length})</span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {cameras.map((cam, i) => (
                            <div
                                key={i}
                                className="group rounded-xl overflow-hidden border border-cyan-400/20 bg-black/40 hover:border-cyan-400/50 transition-colors shadow-[0_0_15px_rgba(0,255,255,0.06)]"
                            >
                                {cam.image_current ? (
                                    <div className="relative h-36 w-full overflow-hidden bg-slate-900/60">
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img
                                            src={cam.image_current}
                                            alt={cam.title}
                                            className="w-full h-full object-cover transition-transform group-hover:scale-105"
                                            loading="lazy"
                                        />
                                        <span className="absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-md bg-red-600/80 text-white text-[9px] font-mono tracking-wider">
                                            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> LIVE
                                        </span>
                                    </div>
                                ) : (
                                    <div className="h-36 w-full flex items-center justify-center bg-slate-900/40 text-cyan-500/30">
                                        <Camera className="w-8 h-8" />
                                    </div>
                                )}
                                <div className="p-2.5">
                                    <p className="text-[11px] font-mono text-gray-300 truncate" title={cam.title}>
                                        {cam.title}
                                    </p>
                                    {cam.page_url && (
                                        <a
                                            href={cam.page_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="mt-1.5 inline-flex items-center gap-1 text-[10px] font-mono text-cyan-400 hover:text-cyan-300 transition-colors"
                                        >
                                            <ExternalLink className="w-3 h-3" />
                                            {t('watchLive')}
                                        </a>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Latest Public Images */}
            {images.length > 0 && (
                <div>
                    <div className="flex items-center gap-2 mb-3">
                        <ImageIcon className="w-4 h-4 text-purple-400/80" />
                        <span className="text-xs font-mono tracking-wider text-purple-300/80 uppercase">
                            {t('imagesHeader')}
                        </span>
                        <span className="text-[10px] font-mono text-purple-500/40">({images.length})</span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                        {images.map((img, i) => (
                            <a
                                key={i}
                                href={img.source_url || img.image_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="group relative block h-28 rounded-lg overflow-hidden border border-purple-400/20 bg-slate-900/60 hover:border-purple-400/50 transition-colors"
                                title={img.title}
                            >
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                    src={img.thumbnail || img.image_url}
                                    alt={img.title || imageQuery}
                                    className="w-full h-full object-cover transition-transform group-hover:scale-105"
                                    loading="lazy"
                                />
                                <span className="absolute inset-x-0 bottom-0 p-1 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                                    <ExternalLink className="w-3 h-3 text-white/80" />
                                </span>
                            </a>
                        ))}
                    </div>
                </div>
            )}

            {/* Empty states (only after a completed load) */}
            {loaded && !loading && (
                <div className="ml-7 space-y-1">
                    {place && cameras.length === 0 && (
                        <p className="text-[10px] font-mono text-cyan-500/30">{t('noCameras')}</p>
                    )}
                    {imageQuery && images.length === 0 && (
                        <p className="text-[10px] font-mono text-purple-500/30">{t('noImages')}</p>
                    )}
                </div>
            )}
        </motion.div>
    );
};

export default LiveCamerasWidget;
