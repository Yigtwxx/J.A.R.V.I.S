import axios from 'axios';
import {
    SearchResponse, ProfileData, SearchHistoryItem, ChangeReport,
    AgentToolInfo, AgentMessage, VisionAnalysisResponse, VisionScreenshotResponse,
    UserMemory, WatchTarget, PluginInfo, SystemAction,
} from '@/types/profile';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

/** Build headers for raw fetch() calls — includes API key if configured. */
export const getApiHeaders = (): Record<string, string> => ({
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
});

const api = axios.create({
    baseURL: API_BASE_URL,
    timeout: 120_000,
    headers: {
        'Content-Type': 'application/json',
        ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    },
});

export const searchPerson = async (query: string, depth: number = 5): Promise<SearchResponse> => {
    const response = await api.post<SearchResponse>('/api/search/', { query, depth }, {
        timeout: 300_000, // 5 minutes — search pipeline has multiple sequential AI steps
    });
    return response.data;
};

export const saveProfile = async (profileData: ProfileData): Promise<ProfileData> => {
    const response = await api.post<ProfileData>('/api/profiles/', profileData);
    return response.data;
};

export const getAllProfiles = async (): Promise<ProfileData[]> => {
    const response = await api.get<ProfileData[]>('/api/profiles/');
    return response.data;
};

export const getProfile = async (id: number): Promise<ProfileData> => {
    const response = await api.get<ProfileData>(`/api/profiles/${id}`);
    return response.data;
};

export const deleteProfile = async (id: number): Promise<void> => {
    await api.delete(`/api/profiles/${id}`);
};

export const searchProfiles = async (name: string): Promise<ProfileData[]> => {
    const response = await api.get<ProfileData[]>(`/api/profiles/search/${name}`);
    return response.data;
};

export const getSearchHistory = async (): Promise<SearchHistoryItem[]> => {
    const response = await api.get<SearchHistoryItem[]>('/api/history/');
    return response.data;
};

export const deleteHistoryItem = async (id: number): Promise<void> => {
    await api.delete(`/api/history/${id}`);
};

export const getVersionHistory = async (queryName: string): Promise<ChangeReport> => {
    const response = await api.get(`/api/version-history/${encodeURIComponent(queryName)}/report`);
    return response.data;
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
    stream = false,
): Promise<string> => {
    if (stream) {
        const response = await fetch(`${API_BASE_URL}/api/agent/chat`, {
            method: 'POST',
            headers: getApiHeaders(),
            body: JSON.stringify({ message, history, stream: true }),
        });
        return response.text();
    }
    const response = await api.post<{ response: string }>('/api/agent/chat', {
        message, history, stream: false,
    });
    return response.data.response;
};

export const agentChatStream = async (
    message: string,
    history: AgentMessage[] = [],
): Promise<Response> => {
    return fetch(`${API_BASE_URL}/api/agent/chat`, {
        method: 'POST',
        headers: getApiHeaders(),
        body: JSON.stringify({ message, history, stream: true }),
    });
};

export const getAgentTools = async (): Promise<AgentToolInfo[]> => {
    const response = await api.get<{ tools: AgentToolInfo[] }>('/api/agent/tools');
    return response.data.tools;
};

// ─── Vision API ────��────────────────────────────────────────

export const analyzeImage = async (imageUrl: string, prompt?: string): Promise<VisionAnalysisResponse> => {
    const response = await api.post<VisionAnalysisResponse>('/api/vision/analyze', { image_url: imageUrl, prompt });
    return response.data;
};

export const analyzeSocialPhoto = async (imageUrl: string): Promise<VisionAnalysisResponse> => {
    const response = await api.post<VisionAnalysisResponse>('/api/vision/social-photo', { image_url: imageUrl });
    return response.data;
};

export const readScreenshot = async (imageUrl: string): Promise<VisionScreenshotResponse> => {
    const response = await api.post<VisionScreenshotResponse>('/api/vision/screenshot', { image_url: imageUrl });
    return response.data;
};

export const compareFacesVisual = async (imageUrlA: string, imageUrlB: string) => {
    const response = await api.post('/api/vision/compare-faces', { image_url_a: imageUrlA, image_url_b: imageUrlB });
    return response.data;
};

// ─── Memory API ─────────────────────────────────────────────

export const createMemory = async (
    category: string, key: string, value: string, context?: string, importance = 5,
): Promise<{ status: string; id: number; key: string }> => {
    const response = await api.post('/api/memory/', { category, key, value, context, importance });
    return response.data;
};

export const getMemories = async (category?: string): Promise<{ memories: UserMemory[]; count: number }> => {
    const params = category ? { category } : {};
    const response = await api.get('/api/memory/', { params });
    return response.data;
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
    return response.data;
};

export const getWatchStatus = async (query: string): Promise<WatchTarget> => {
    const response = await api.get(`/api/watch/${encodeURIComponent(query)}`);
    return response.data;
};

// ─── Plugins API ─────��──────────────────────────────────────

export const getPlugins = async (): Promise<{ plugins: PluginInfo[] }> => {
    const response = await api.get('/api/plugins/');
    return response.data;
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
    return response.data;
};

export const getHealthLog = async (limit = 50): Promise<{ log: HealthLogEntry[] }> => {
    const response = await api.get('/api/system/health-log', { params: { limit } });
    return response.data;
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
    category: string, key: string, value: string, context?: string,
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
