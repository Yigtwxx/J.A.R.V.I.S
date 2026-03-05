import axios from 'axios';
import { SearchResponse, ProfileData } from '@/types/profile';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
    baseURL: API_BASE_URL,
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

export const getSearchHistory = async (): Promise<import('@/types/profile').SearchHistoryItem[]> => {
    const response = await api.get<import('@/types/profile').SearchHistoryItem[]>('/api/history/');
    return response.data;
};

export const deleteHistoryItem = async (id: number): Promise<void> => {
    await api.delete(`/api/history/${id}`);
};

export const getVersionHistory = async (queryName: string): Promise<import('@/types/profile').ChangeReport> => {
    const response = await api.get(`/api/version-history/${encodeURIComponent(queryName)}/report`);
    return response.data;
};

export default api;
