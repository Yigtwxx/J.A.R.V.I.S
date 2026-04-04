import axios from 'axios';
import { SearchResponse, ProfileData, SearchHistoryItem, ChangeReport } from '@/types/profile';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE_URL,
    timeout: 300_000,
    headers: {
        'Content-Type': 'application/json',
    },
});

export const searchPerson = async (query: string): Promise<SearchResponse> => {
    const response = await api.post<SearchResponse>('/api/search/', { query });
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

export default api;
