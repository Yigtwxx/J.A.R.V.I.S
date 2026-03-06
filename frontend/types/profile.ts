export interface ScoreBreakdown {
  platform_presence: number;
  follower_impact: number;
  activity_intensity: number;
  web_visibility: number;
  digital_diversity: number;
}

export interface ProfileData {
  id?: number;
  name: string;
  github_url?: string;
  instagram_url?: string;
  twitter_url?: string;
  linkedin_url?: string;
  spotify_url?: string;
  tiktok_url?: string;
  snapchat_url?: string;
  tumblr_url?: string;
  tinder_mention?: string;
  bumble_mention?: string;
  phone_numbers?: string[];
  location_country?: string;
  location_city?: string;
  weather_info?: any;
  social_media_score?: number;
  social_media_score_breakdown?: ScoreBreakdown;
  last_activity_summary?: string;
  platform_activity?: Record<string, number>;
  description?: string;
  additional_info?: Record<string, unknown>;
  similar_profiles?: string[];
  cross_validation_issues?: string[];
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
  snapchat_url?: string;
  tumblr_url?: string;
  tinder_mention?: string;
  bumble_mention?: string;
  phone_numbers?: string[];
  location_country?: string;
  location_city?: string;
  weather_info?: any;
  social_media_score?: number;
  social_media_score_breakdown?: ScoreBreakdown;
  last_activity_summary?: string;
  platform_activity?: Record<string, number>;
  description?: string;
  additional_info?: Record<string, unknown>;
  similar_profiles?: string[];
  cross_validation_issues?: string[];
  sources?: { title: string; url: string; snippet: string }[];
  ai_response: string;
  version_history?: ChangeReport;
  face_match_results?: FaceMatchReport;
}

export interface FieldChange {
  field: string;
  field_label: string;
  old_value: string | null;
  new_value: string | null;
}

export interface ChangeReport {
  query_name: string;
  previous_captured_at: string | null;
  current_captured_at: string;
  changes: FieldChange[];
  snapshot_count: number;
  has_changes: boolean;
}

export interface FacePairResult {
  image_a_label: string;
  image_b_label: string;
  verified: boolean;
  confidence: number;
  distance: number;
}

export interface FaceMatchReport {
  overall_confidence: number;
  total_comparisons: number;
  successful_comparisons: number;
  pairs: FacePairResult[];
  face_detected_count: number;
  total_images: number;
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
