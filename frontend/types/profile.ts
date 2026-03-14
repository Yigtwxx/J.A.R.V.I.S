export type CompanyRoleCategory = 'founder' | 'executive' | 'board_member' | 'shareholder' | 'unknown';
export type CompanyStatus = 'active' | 'passive' | 'liquidated' | 'unknown';

export interface CompanyRecord {
  company_name: string;
  company_type: string;
  role: string;
  role_category: CompanyRoleCategory;
  status: CompanyStatus;
  source_url: string;
  source_name: string;
  country?: string;
  confidence: number;           // 0.0–1.0
  registry_id?: string;         // MERSİS, CIK, Company No, HRB, vb.
  city?: string;
  sector?: string;
  risk_flags: string[];         // 'offshore' | 'shell_company' | 'liquidated' | 'pep_related' | 'sanction' | 'high_risk_sector' | 'rapid_change'
  snippet: string;
}

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
  network_connections?: { name: string, role: string, relation: string }[];
  email_addresses?: string[];
  data_breaches?: any[];
  company_records?: CompanyRecord[];
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
  network_connections?: { name: string, role: string, relation: string }[];
  email_addresses?: string[];
  data_breaches?: any[];
  company_records?: CompanyRecord[];
  sources?: { title: string; url: string; snippet: string }[];
  ai_response: string;
  version_history?: ChangeReport;
  face_match_results?: FaceMatchReport;
  sentiment_analysis?: {
    positive: number;
    neutral: number;
    negative: number;
    dominant_emotion: string;
    summary: string;
  };
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
