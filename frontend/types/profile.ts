export interface ProfileData {
  id?: number;
  name: string;
  github_url?: string;
  instagram_url?: string;
  twitter_url?: string;
  linkedin_url?: string;
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
  description?: string;
  additional_info?: Record<string, unknown>;
  similar_profiles?: string[];
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
