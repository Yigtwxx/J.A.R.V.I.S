export interface ProfileData {
  id?: number;
  name: string;
  github_url?: string;
  instagram_url?: string;
  twitter_url?: string;
  linkedin_url?: string;
  spotify_url?: string;
  tiktok_url?: string;
  location_country?: string;
  location_city?: string;
  weather_info?: any;
  social_media_score?: number;
  last_activity_summary?: string;
  description?: string;
  additional_info?: Record<string, unknown>;
  similar_profiles?: string[];
  created_at?: string;
  updated_at?: string;
}

export interface SearchResponse {
  name: string;
  github_url?: string;
  instagram_url?: string;
  twitter_url?: string;
  linkedin_url?: string;
  spotify_url?: string;
  tiktok_url?: string;
  location_country?: string;
  location_city?: string;
  weather_info?: any;
  social_media_score?: number;
  last_activity_summary?: string;
  description?: string;
  additional_info?: Record<string, unknown>;
  similar_profiles?: string[];
  sources?: { title: string; url: string; snippet: string }[];
  ai_response: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  profileData?: SearchResponse;
  isSaved?: boolean;
}

export interface SearchHistoryItem {
  id: number;
  query_name: string;
  searched_at: string;
}
