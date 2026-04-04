'use client';

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { MapPin, Globe, Crosshair, Camera, Wifi } from 'lucide-react';
import type { GeoLocationData, TimezoneAnalysis } from '@/types/profile';

interface GeoLocation {
    lat: number;
    lng: number;
    label: string;
    type: 'primary' | 'ip' | 'checkin' | 'company' | 'exif';
}

interface GeoIntMapProps {
    locationCountry?: string;
    locationCity?: string;
    companyRecords?: { company_name: string; city?: string; country?: string }[];
    geointData?: GeoLocationData[];
    timezoneAnalysis?: TimezoneAnalysis;
}

// Geocode city/country to lat/lng using Nominatim (free, no API key)
async function geocode(query: string): Promise<{ lat: number; lng: number } | null> {
    try {
        const res = await fetch(
            `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=1`,
            { headers: { 'User-Agent': 'JARVIS-OSINT/1.0' } }
        );
        const data = await res.json();
        if (data.length > 0) {
            return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
        }
    } catch {
        // Geocoding failed silently
    }
    return null;
}

function GeoIntMap({ locationCountry, locationCity, companyRecords, geointData, timezoneAnalysis }: GeoIntMapProps) {
    const [locations, setLocations] = useState<GeoLocation[]>([]);
    const [mapReady, setMapReady] = useState(false);
    const [MapContainer, setMapContainer] = useState<React.ComponentType<Record<string, unknown>> | null>(null);
    const [TileLayer, setTileLayer] = useState<React.ComponentType<Record<string, unknown>> | null>(null);
    const [Marker, setMarker] = useState<React.ComponentType<Record<string, unknown>> | null>(null);
    const [Popup, setPopup] = useState<React.ComponentType<Record<string, unknown>> | null>(null);

    // Dynamic import of Leaflet (SSR-safe)
    useEffect(() => {
        (async () => {
            const L = await import('leaflet');
            const RL = await import('react-leaflet');

            // Fix default marker icons
            delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
            L.Icon.Default.mergeOptions({
                iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
                iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
            });

            setMapContainer(() => RL.MapContainer as unknown as React.ComponentType<Record<string, unknown>>);
            setTileLayer(() => RL.TileLayer as unknown as React.ComponentType<Record<string, unknown>>);
            setMarker(() => RL.Marker as unknown as React.ComponentType<Record<string, unknown>>);
            setPopup(() => RL.Popup as unknown as React.ComponentType<Record<string, unknown>>);
            setMapReady(true);
        })();
    }, []);

    // Use backend geoint_data if available, otherwise fall back to client-side geocoding
    useEffect(() => {
        if (geointData && geointData.length > 0) {
            const locs: GeoLocation[] = geointData.map(g => ({
                lat: g.lat,
                lng: g.lng,
                label: g.label,
                type: g.type as GeoLocation['type'],
            }));
            setLocations(locs);
            return;
        }

        // Fallback: client-side geocoding
        const fetchLocations = async () => {
            const locs: GeoLocation[] = [];

            if (locationCity || locationCountry) {
                const query = [locationCity, locationCountry].filter(Boolean).join(', ');
                const coords = await geocode(query);
                if (coords) {
                    locs.push({ ...coords, label: query, type: 'primary' });
                }
            }

            if (companyRecords) {
                for (const company of companyRecords.slice(0, 5)) {
                    const companyQuery = [company.city, company.country].filter(Boolean).join(', ');
                    if (companyQuery) {
                        const coords = await geocode(companyQuery);
                        if (coords) {
                            locs.push({
                                ...coords,
                                label: `${company.company_name} (${companyQuery})`,
                                type: 'company',
                            });
                        }
                    }
                }
            }

            setLocations(locs);
        };

        fetchLocations();
    }, [locationCountry, locationCity, companyRecords, geointData]);

    if (locations.length === 0 && !locationCountry && !locationCity) {
        return null; // No geo data available
    }

    const center = locations.length > 0
        ? { lat: locations[0].lat, lng: locations[0].lng }
        : { lat: 39.9, lng: 32.8 }; // Default: Ankara

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mt-6"
        >
            {/* Header */}
            <div className="flex items-center gap-2 mb-4">
                <Globe className="w-5 h-5 text-cyan-400 glow-cyan" />
                <h4 className="text-white font-orbitron font-bold text-sm tracking-[0.15em] uppercase glow-cyan">
                    GEOINT — Geographic Intelligence
                </h4>
            </div>

            {/* Location Tags */}
            <div className="flex flex-wrap gap-2 mb-3">
                {locations.map((loc, i) => {
                    const styles = {
                        primary: 'bg-cyan-400/10 border-cyan-400/30 text-cyan-300',
                        company: 'bg-blue-500/10 border-blue-400/30 text-blue-300',
                        exif: 'bg-amber-500/10 border-amber-400/30 text-amber-300',
                        ip: 'bg-purple-500/10 border-purple-400/30 text-purple-300',
                        checkin: 'bg-green-500/10 border-green-400/30 text-green-300',
                    };
                    const icons = {
                        primary: <Crosshair className="w-3 h-3" />,
                        company: <MapPin className="w-3 h-3" />,
                        exif: <Camera className="w-3 h-3" />,
                        ip: <Wifi className="w-3 h-3" />,
                        checkin: <MapPin className="w-3 h-3" />,
                    };
                    return (
                        <span
                            key={i}
                            className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono tracking-wider border ${styles[loc.type] || styles.primary}`}
                        >
                            {icons[loc.type] || icons.primary}
                            {loc.label}
                        </span>
                    );
                })}
            </div>

            {/* Timezone Analysis */}
            {timezoneAnalysis && timezoneAnalysis.inferred_timezone !== 'UNKNOWN' && (
                <div className="flex flex-wrap gap-3 mb-3 text-xs font-mono">
                    <span className="px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-400/30 text-emerald-300">
                        TZ: {timezoneAnalysis.inferred_timezone}
                    </span>
                    <span className="px-3 py-1 rounded-lg bg-slate-500/10 border border-slate-400/30 text-slate-300">
                        Pattern: {timezoneAnalysis.activity_pattern}
                    </span>
                    {timezoneAnalysis.peak_hours.length > 0 && (
                        <span className="px-3 py-1 rounded-lg bg-slate-500/10 border border-slate-400/30 text-slate-300">
                            Peak: {timezoneAnalysis.peak_hours.map(h => `${h}:00`).join(', ')}
                        </span>
                    )}
                </div>
            )}

            {/* Map */}
            <div className="rounded-xl overflow-hidden border border-cyan-400/20 shadow-[0_0_20px_rgba(0,255,255,0.1)] relative">
                {/* Leaflet CSS */}
                <link
                    rel="stylesheet"
                    href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
                />

                {mapReady && MapContainer && TileLayer ? (
                    <MapContainer
                        center={[center.lat, center.lng]}
                        zoom={locations.length > 1 ? 4 : 6}
                        style={{ height: '300px', width: '100%', background: '#0a0a1a' }}
                        scrollWheelZoom={false}
                    >
                        <TileLayer
                            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
                        />
                        {Marker && Popup && locations.map((loc, i) => (
                            <Marker key={i} position={[loc.lat, loc.lng]}>
                                <Popup>
                                    <div className="text-sm font-mono">
                                        <strong>{loc.label}</strong>
                                        <br />
                                        <span className="text-gray-500">
                                            {loc.lat.toFixed(4)}, {loc.lng.toFixed(4)}
                                        </span>
                                    </div>
                                </Popup>
                            </Marker>
                        ))}
                    </MapContainer>
                ) : (
                    <div className="h-[300px] flex items-center justify-center bg-slate-900/50">
                        <div className="text-cyan-400/50 text-sm font-mono animate-pulse">
                            {locations.length === 0 ? 'Geocoding coordinates...' : 'Initializing map...'}
                        </div>
                    </div>
                )}

                {/* Overlay gradient */}
                <div className="absolute inset-0 pointer-events-none rounded-xl border border-cyan-400/10" />
            </div>
        </motion.div>
    );
}

export default GeoIntMap;
