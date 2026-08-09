import axios from 'axios';
import {
    SearchResponse,
    ProfileData,
    SearchHistoryItem,
    ChangeReport,
    AgentToolInfo,
    AgentMessage,
    VisionAnalysisResponse,
    VisionScreenshotResponse,
    UserMemory,
    WatchTarget,
    PluginInfo,
    SystemAction,
} from '@/types/profile';
import {
    SearchResponseSchema,
    ProfileDataSchema,
    SearchHistoryItemSchema,
    ChangeReportSchema,
    VisionAnalysisResponseSchema,
    VisionScreenshotResponseSchema,
    MemoryListResponseSchema,
    WatchListResponseSchema,
    PluginListResponseSchema,
    ServiceStatusResponseSchema,
    HealthLogListResponseSchema,
} from '@/lib/schemas';
import { validateResponse } from '@/lib/validateApi';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

/** Build headers for raw fetch() calls — includes API key if configured. */
export const getApiHeaders = (): Record<string, string> => ({
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

/**
 * Stream the live-status SSE feed via ``fetch`` so the API key travels in the
 * ``X-API-Key`` header instead of the URL (the native ``EventSource`` API cannot
 * set headers, which would force the key into access logs / history / Referer).
 *
 * ``onMessage`` is invoked once per SSE event with its concatenated ``data``
 * payload, mirroring ``EventSource.onmessage``. Resolves when the stream ends;
 * abort via ``signal`` to close it.
 */
export const streamStatus = async (onMessage: (data: string) => void, signal?: AbortSignal): Promise<void> => {
    const response = await fetch(`${API_BASE_URL}/api/status/stream`, {
        method: 'GET',
        headers: getApiHeaders(),
        signal,
    });
    if (!response.ok || !response.body) {
        throw new Error(`Status stream failed (HTTP ${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by a blank line; join each event's data lines.
        let sep: number;
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
            const rawEvent = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const data = rawEvent
                .split('\n')
                .filter((line) => line.startsWith('data:'))
                .map((line) => line.replace(/^data: ?/, ''))
                .join('\n');
            if (data) onMessage(data);
        }
    }
};

const api = axios.create({
    baseURL: API_BASE_URL,
    // 0 disables the client-side timeout: deep OSINT sweeps and local LLM
    // streams can run far longer than any fixed budget. Callers pass an
    // AbortSignal when the user needs to cancel.
    timeout: 0,
    headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    },
});

export const searchPerson = async (query: string, depth: number = 5, signal?: AbortSignal): Promise<SearchResponse> => {
    const response = await api.post<SearchResponse>('/api/search/', { query, depth }, { signal });
    return validateResponse(SearchResponseSchema, response.data, 'searchPerson');
};

export const saveProfile = async (profileData: ProfileData): Promise<ProfileData> => {
    const response = await api.post<ProfileData>('/api/profiles/', profileData);
    return validateResponse(ProfileDataSchema, response.data, 'saveProfile');
};

export const getAllProfiles = async (): Promise<ProfileData[]> => {
    const response = await api.get<ProfileData[]>('/api/profiles/');
    return (response.data as unknown[]).map((item, i) =>
        validateResponse(ProfileDataSchema, item, `getAllProfiles[${i}]`)
    );
};

export const getProfile = async (id: number): Promise<ProfileData> => {
    const response = await api.get<ProfileData>(`/api/profiles/${id}`);
    return validateResponse(ProfileDataSchema, response.data, 'getProfile');
};

export const deleteProfile = async (id: number): Promise<void> => {
    await api.delete(`/api/profiles/${id}`);
};

export const searchProfiles = async (name: string): Promise<ProfileData[]> => {
    const response = await api.get<ProfileData[]>(`/api/profiles/search/${name}`);
    return (response.data as unknown[]).map((item, i) =>
        validateResponse(ProfileDataSchema, item, `searchProfiles[${i}]`)
    );
};

export const getSearchHistory = async (): Promise<SearchHistoryItem[]> => {
    const response = await api.get<SearchHistoryItem[]>('/api/history/');
    return (response.data as unknown[]).map((item, i) =>
        validateResponse(SearchHistoryItemSchema, item, `getSearchHistory[${i}]`)
    );
};

export const deleteHistoryItem = async (id: number): Promise<void> => {
    await api.delete(`/api/history/${id}`);
};

export const getVersionHistory = async (queryName: string): Promise<ChangeReport> => {
    const response = await api.get(`/api/version-history/${encodeURIComponent(queryName)}/report`);
    return validateResponse(ChangeReportSchema, response.data, 'getVersionHistory');
};

// --- Export endpoints ---

export const exportPdfFromData = async (profileData: SearchResponse): Promise<Blob> => {
    const response = await api.post('/api/export/pdf', profileData, { responseType: 'blob' });
    return response.data;
};

export const exportJsonFromData = async (profileData: SearchResponse): Promise<Blob> => {
    const response = await api.post('/api/export/json', profileData, { responseType: 'blob' });
    return response.data;
};

export const exportCsvFromData = async (profileData: SearchResponse): Promise<Blob> => {
    const response = await api.post('/api/export/csv', profileData, { responseType: 'blob' });
    return response.data;
};

export const exportPdf = async (profileId: number): Promise<Blob> => {
    const response = await api.get(`/api/export/pdf/${profileId}`, { responseType: 'blob' });
    return response.data;
};

export const exportJson = async (profileId: number): Promise<Blob> => {
    const response = await api.get(`/api/export/json/${profileId}`, { responseType: 'blob' });
    return response.data;
};

export const exportCsv = async (profileId: number): Promise<Blob> => {
    const response = await api.get(`/api/export/csv/${profileId}`, { responseType: 'blob' });
    return response.data;
};

// ─── Agent API ──────────��───────────────────────���───────────

export const agentChat = async (
    message: string,
    history: AgentMessage[] = [],
    signal?: AbortSignal
): Promise<string> => {
    const response = await api.post<{ response: string }>(
        '/api/agent/chat',
        {
            message,
            history,
            stream: false,
        },
        { signal }
    );
    return response.data.response;
};

export const agentChatStream = async (
    message: string,
    history: AgentMessage[] = [],
    signal?: AbortSignal
): Promise<Response> => {
    return fetch(`${API_BASE_URL}/api/agent/chat`, {
        method: 'POST',
        headers: getApiHeaders(),
        body: JSON.stringify({ message, history, stream: true }),
        signal,
    });
};

export const getAgentTools = async (): Promise<AgentToolInfo[]> => {
    const response = await api.get<{ tools: AgentToolInfo[] }>('/api/agent/tools');
    return response.data.tools;
};

// ─── Vision API ────��────────────────────────────────────────

export const analyzeImage = async (
    imageUrl: string,
    prompt?: string,
    signal?: AbortSignal
): Promise<VisionAnalysisResponse> => {
    const response = await api.post<VisionAnalysisResponse>(
        '/api/vision/analyze',
        { image_url: imageUrl, prompt },
        { signal }
    );
    return validateResponse(VisionAnalysisResponseSchema, response.data, 'analyzeImage');
};

export const analyzeSocialPhoto = async (imageUrl: string, signal?: AbortSignal): Promise<VisionAnalysisResponse> => {
    const response = await api.post<VisionAnalysisResponse>(
        '/api/vision/social-photo',
        { image_url: imageUrl },
        { signal }
    );
    return validateResponse(VisionAnalysisResponseSchema, response.data, 'analyzeSocialPhoto');
};

export const readScreenshot = async (imageUrl: string, signal?: AbortSignal): Promise<VisionScreenshotResponse> => {
    const response = await api.post<VisionScreenshotResponse>(
        '/api/vision/screenshot',
        { image_url: imageUrl },
        { signal }
    );
    return validateResponse(VisionScreenshotResponseSchema, response.data, 'readScreenshot');
};

export const compareFacesVisual = async (imageUrlA: string, imageUrlB: string, signal?: AbortSignal) => {
    const response = await api.post(
        '/api/vision/compare-faces',
        { image_url_a: imageUrlA, image_url_b: imageUrlB },
        { signal }
    );
    return response.data;
};

// ─── Visual Intelligence API (public webcams + latest images) ───────────────

export interface WebcamItem {
    title: string;
    lat: number | null;
    lng: number | null;
    image_current: string;
    image_daylight: string;
    page_url: string;
    source: string;
}

export interface LocationCamerasResponse {
    place: string;
    coords: { lat: number; lng: number; display_name: string } | null;
    source: string;
    webcams: WebcamItem[];
}

export interface ImageItem {
    image_url: string;
    thumbnail: string;
    source_url: string;
    title: string;
}

export interface LatestImagesResponse {
    images: ImageItem[];
    query: string;
}

export const getLocationCameras = async (query: string, signal?: AbortSignal): Promise<LocationCamerasResponse> => {
    const response = await api.post<LocationCamerasResponse>('/api/visual-intel/cameras', { query }, { signal });
    return response.data;
};

export const getLatestImages = async (query: string, signal?: AbortSignal): Promise<LatestImagesResponse> => {
    const response = await api.post<LatestImagesResponse>('/api/visual-intel/images', { query }, { signal });
    return response.data;
};

// ─── Memory API ─────────────────────────────────────────────

export const createMemory = async (
    category: string,
    key: string,
    value: string,
    context?: string,
    importance = 5
): Promise<{ status: string; id: number; key: string }> => {
    const response = await api.post('/api/memory/', { category, key, value, context, importance });
    return response.data;
};

export const getMemories = async (category?: string): Promise<{ memories: UserMemory[]; count: number }> => {
    const params = category ? { category } : {};
    const response = await api.get('/api/memory/', { params });
    return validateResponse(MemoryListResponseSchema, response.data, 'getMemories');
};

export const deleteMemory = async (id: number): Promise<void> => {
    await api.delete(`/api/memory/${id}`);
};

export const deleteMemoryCategory = async (category: string): Promise<void> => {
    await api.delete(`/api/memory/category/${category}`);
};

export const searchMemories = async (query: string, nResults = 5) => {
    const response = await api.post('/api/memory/search', { query, n_results: nResults });
    return response.data;
};

export const getUserContext = async (): Promise<{ context: string; has_memories: boolean }> => {
    const response = await api.get('/api/memory/context');
    return response.data;
};

// ─── Watch API ─────────��────────────────────────────────────

export const startWatch = async (query: string, intervalMinutes = 60) => {
    const response = await api.post('/api/watch/start', { query, interval_minutes: intervalMinutes });
    return response.data;
};

export const stopWatch = async (query: string) => {
    const response = await api.post('/api/watch/stop', { query });
    return response.data;
};

export const stopAllWatches = async () => {
    const response = await api.post('/api/watch/stop-all');
    return response.data;
};

export const getActiveWatches = async (): Promise<{ watches: WatchTarget[]; count: number }> => {
    const response = await api.get('/api/watch/');
    return validateResponse(WatchListResponseSchema, response.data, 'getActiveWatches');
};

export const getWatchStatus = async (query: string): Promise<WatchTarget> => {
    const response = await api.get(`/api/watch/${encodeURIComponent(query)}`);
    return response.data;
};

// ─── Plugins API ─────��──────────────────────────────────────

export const getPlugins = async (): Promise<{ plugins: PluginInfo[] }> => {
    const response = await api.get('/api/plugins/');
    return validateResponse(PluginListResponseSchema, response.data, 'getPlugins');
};

export const togglePlugin = async (name: string): Promise<{ name: string; enabled: boolean }> => {
    const response = await api.post(`/api/plugins/${encodeURIComponent(name)}/toggle`);
    return response.data;
};

export const runPlugin = async (name: string, query: string) => {
    const response = await api.post(`/api/plugins/${encodeURIComponent(name)}/run`, null, { params: { query } });
    return response.data;
};

// ─── System API ─────────────────────────────────────────────

export const requestCommand = async (command: string, timeout = 30): Promise<SystemAction> => {
    const response = await api.post('/api/system/execute/command', { command, timeout });
    return response.data;
};

export const requestAppOpen = async (appName: string): Promise<SystemAction> => {
    const response = await api.post('/api/system/execute/app', { app_name: appName });
    return response.data;
};

export const requestUrlOpen = async (url: string): Promise<SystemAction> => {
    const response = await api.post('/api/system/execute/url', { url });
    return response.data;
};

export const approveAction = async (actionId: string) => {
    const response = await api.post('/api/system/approve', { action_id: actionId });
    return response.data;
};

export const denyAction = async (actionId: string) => {
    const response = await api.post('/api/system/deny', { action_id: actionId });
    return response.data;
};

export const getPendingActions = async (): Promise<{ pending_actions: SystemAction[] }> => {
    const response = await api.get('/api/system/pending');
    return response.data;
};

export const getActionHistory = async (limit = 50): Promise<{ history: SystemAction[] }> => {
    const response = await api.get('/api/system/history', { params: { limit } });
    return response.data;
};

export interface ServiceStatusResponse {
    services: Record<string, { status: string; error?: string; [key: string]: unknown }>;
    uptime_seconds: number;
    is_monitoring: boolean;
    recovery_attempts: Record<string, number>;
}

export interface HealthLogEntry {
    timestamp: string;
    service: string;
    type: string;
    message: string;
}

export const getServiceStatus = async (): Promise<ServiceStatusResponse> => {
    const response = await api.get('/api/system/service-status');
    return validateResponse(ServiceStatusResponseSchema, response.data, 'getServiceStatus');
};

export const getHealthLog = async (limit = 50): Promise<{ log: HealthLogEntry[] }> => {
    const response = await api.get('/api/system/health-log', { params: { limit } });
    return validateResponse(HealthLogListResponseSchema, response.data, 'getHealthLog');
};

// ─── Health API ─────────────────────────────────────────────

export interface HealthCategory {
    id: string;
    label: string;
}

export interface HealthRecord {
    id: number;
    category: string;
    key: string;
    value: string;
    context: string | null;
    importance: number;
    created_at: string | null;
    updated_at: string | null;
}

export interface HealthSuggestions {
    assessment: string;
    suggestions: string[];
    warnings: string[];
    follow_up_questions: string[];
    user_report: string;
}

export interface HealthPattern {
    description: string;
    category: string;
    severity: 'low' | 'medium' | 'high';
    recommendation: string;
}

export interface HealthPatterns {
    patterns: HealthPattern[];
    summary: string;
    data_points: number;
}

export const getHealthCategories = async (): Promise<HealthCategory[]> => {
    const response = await api.get('/api/health/categories');
    return response.data;
};

export const recordHealthData = async (
    category: string,
    key: string,
    value: string,
    context?: string
): Promise<HealthRecord> => {
    const response = await api.post('/api/health/record', { category, key, value, context });
    return response.data;
};

export const getHealthHistory = async (category?: string, limit = 50): Promise<HealthRecord[]> => {
    const params: Record<string, string | number> = { limit };
    if (category) params.category = category;
    const response = await api.get('/api/health/history', { params });
    return response.data;
};

export const getHealthSuggestions = async (report: string): Promise<HealthSuggestions> => {
    const response = await api.post('/api/health/suggestions', { report });
    return response.data;
};

export const getHealthPatterns = async (): Promise<HealthPatterns> => {
    const response = await api.get('/api/health/patterns');
    return response.data;
};

export default api;
