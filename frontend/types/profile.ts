export interface RagMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface BreachData {
  _type?: undefined;
  Name: string;
  Title: string;
  Domain: string;
  BreachDate: string;
  PwnCount?: number;
  DataClasses: string[];
  IsVerified: boolean;
  IsSensitive?: boolean;
  IsSpamList?: boolean;
  IsFabricated?: boolean;
  Description?: string;
  TargetEmail: string;
}

export interface PasteData {
  _type: 'paste';
  Source: string;
  Id: string;
  Title: string;
  Date: string;
  EmailCount: number;
  TargetEmail: string;
}

export type LeakRecord = BreachData | PasteData;

export interface WeatherInfo {
  temperature: number;
  description: string;
  humidity?: number;
  wind_speed?: number;
  city?: string;
  country?: string;
  icon?: string;
}

export interface DataBreach {
  name: string;
  breach_date?: string;
  description?: string;
  data_classes?: string[];
  is_verified?: boolean;
  pwn_count?: number;
}

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
  confidence: number;
  registry_id?: string;
  city?: string;
  sector?: string;
  risk_flags: string[];
  snippet: string;
}

export interface ScoreBreakdown {
  platform_presence: number;
  follower_impact: number;
  activity_intensity: number;
  web_visibility: number;
  digital_diversity: number;
}

/**
 * Shared fields between ProfileData and SearchResponse.
 * Single source of truth — add new social platforms here.
 */
interface SharedProfileFields {
  name: string;
  github_url?: string;
  instagram_url?: string;
  twitter_url?: string;
  linkedin_url?: string;
  spotify_url?: string;
  tiktok_url?: string;
  snapchat_url?: string;
  tumblr_url?: string;
  youtube_url?: string;
  reddit_url?: string;
  facebook_url?: string;
  pinterest_url?: string;
  medium_url?: string;
  threads_url?: string;
  steam_url?: string;
  tinder_mention?: string;
  bumble_mention?: string;
  discord_mention?: string;
  phone_numbers?: string[];
  location_country?: string;
  location_city?: string;
  weather_info?: WeatherInfo;
  social_media_score?: number;
  social_media_score_breakdown?: ScoreBreakdown;
  last_activity_summary?: string;
  platform_activity?: Record<string, number>;
  description?: string;
  additional_info?: Record<string, unknown>;
  similar_profiles?: string[];
  cross_validation_issues?: string[];
  network_connections?: { name: string; role: string; relation: string }[];
  email_addresses?: string[];
  data_breaches?: LeakRecord[];
  company_records?: CompanyRecord[];
}

export interface ProfileData extends SharedProfileFields {
  id?: number;
  created_at?: string;
  updated_at?: string;
}

export interface GeoLocationData {
  lat: number;
  lng: number;
  label: string;
  type: 'primary' | 'company' | 'exif' | 'ip';
  source: string;
  confidence: number;
  timestamp?: string;
}

export interface TimezoneAnalysis {
  inferred_timezone: string;
  peak_hours: number[];
  activity_pattern: string;
  hourly_distribution: Record<string, number>;
}

// ─── Psychological Analysis Types ───────────────────────────

export interface SocialEngineeringVector {
  vector: string;
  approach: string;
  risk_level: 'low' | 'medium' | 'high';
}

export interface PsychologicalAnalysis {
  psychological_profile: string;
  strengths: string[];
  weaknesses: string[];
  tactical_recommendations: string[];
  social_engineering_vectors: SocialEngineeringVector[];
  manipulation_resistance_score: number;
  confidence_level: number;
}

// ─── Predictive Analysis Types ──────────────────────────────

export interface PredictionEntry {
  category: 'activity' | 'behavioral' | 'security' | 'financial';
  prediction: string;
  probability: number;
  timeframe: '24h' | '7d' | '30d' | '90d';
  supporting_evidence: string[];
}

export interface PredictiveAnalysis {
  predictions: PredictionEntry[];
  activity_pattern?: {
    most_active_hours: number[];
    most_active_days: string[];
    posting_frequency: string;
  };
  trend_direction: 'increasing' | 'stable' | 'decreasing' | 'erratic';
  data_sufficiency: number;
}

export interface SearchResponse extends SharedProfileFields {
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
  geoint_data?: GeoLocationData[];
  timezone_analysis?: TimezoneAnalysis;
  psychological_analysis?: PsychologicalAnalysis;
  prediction_data?: PredictiveAnalysis;
  search_depth?: number;
  search_tier?: string;
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
  id: string;
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

// ─── Agent Types ────────────────────────────────────────────

export interface AgentMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
}

export interface AgentToolInfo {
  type: string;
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

// ─── Vision Types ───────────────────────────────────────────

export interface VisionAnalysisResponse {
  analysis: string | Record<string, unknown>;
  image_url: string;
}

export interface VisionScreenshotResponse {
  text: string;
  image_url: string;
}

// ─── Memory Types ───────────────────────────────────────────

export interface UserMemory {
  id: number;
  category: string;
  key: string;
  value: string;
  context: string | null;
  importance: number;
  created_at: string;
  updated_at: string;
}

// ─── Watch Types ────────────────────────────────────────────

export interface WatchTarget {
  query: string;
  interval_minutes: number;
  is_active: boolean;
  last_checked: string | null;
  changes_detected: number;
  last_diff: Record<string, { old: unknown; new: unknown }> | null;
}

// ─── Plugin Types ───────────────────────────────────────────

export interface PluginInfo {
  name: string;
  version: string;
  description: string;
  author: string;
  enabled: boolean;
}

// ─── System Types ───────────────────────────────────────────

export type ActionStatus = 'pending' | 'approved' | 'denied' | 'executed' | 'failed';

export interface SystemAction {
  action_id: string;
  action_type: string;
  description: string;
  status: ActionStatus;
  result: string | null;
  requested_at: string;
  resolved_at: string | null;
}
