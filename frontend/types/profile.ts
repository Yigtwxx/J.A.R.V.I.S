import { z } from 'zod';
import {
    BreachDataSchema, PasteDataSchema, LeakRecordSchema,
    ScoreBreakdownSchema, GeoLocationDataSchema,
    PsychologicalAnalysisSchema, PredictiveAnalysisSchema,
    CompanyRecordSchema, ChangeReportSchema, FaceMatchReportSchema,
    ProfileDataSchema, SearchResponseSchema, SearchHistoryItemSchema,
} from '@/lib/schemas';

export interface RagMessage {
    role: 'user' | 'assistant';
    content: string;
}

// ─── Zod-derived types ───────────────────────────────────────

export type BreachData = z.infer<typeof BreachDataSchema>;
export type PasteData = z.infer<typeof PasteDataSchema>;
export type LeakRecord = z.infer<typeof LeakRecordSchema>;
export type ScoreBreakdown = z.infer<typeof ScoreBreakdownSchema>;
export type GeoLocationData = z.infer<typeof GeoLocationDataSchema>;
export type PsychologicalAnalysis = z.infer<typeof PsychologicalAnalysisSchema>;
export type PredictiveAnalysis = z.infer<typeof PredictiveAnalysisSchema>;
export type CompanyRecord = z.infer<typeof CompanyRecordSchema>;
export type ChangeReport = z.infer<typeof ChangeReportSchema>;
export type FaceMatchReport = z.infer<typeof FaceMatchReportSchema>;
export type ProfileData = z.infer<typeof ProfileDataSchema>;
export type SearchResponse = z.infer<typeof SearchResponseSchema>;
export type SearchHistoryItem = z.infer<typeof SearchHistoryItemSchema>;

// Convenience aliases for union members of CompanyRecord
export type CompanyRoleCategory = CompanyRecord['role_category'];
export type CompanyStatus = CompanyRecord['status'];

// ─── DataBreach (simple, not in API responses) ───────────────

export interface DataBreach {
    name: string;
    breach_date?: string;
    description?: string;
    data_classes?: string[];
    is_verified?: boolean;
    pwn_count?: number;
}

// ─── Sub-types derived from SearchResponse ───────────────────

export type WeatherInfo = NonNullable<SearchResponse['weather_info']>;
export type TimezoneAnalysis = NonNullable<SearchResponse['timezone_analysis']>;
export type SocialEngineeringVector = PsychologicalAnalysis['social_engineering_vectors'][number];
export type PredictionEntry = PredictiveAnalysis['predictions'][number];
export type FieldChange = ChangeReport['changes'][number];
export type FacePairResult = FaceMatchReport['pairs'][number];

// ─── Manual types (simple / not in API schemas) ──────────────

export interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    profileData?: SearchResponse;
    isSaved?: boolean;
}

// ─── Agent Types ─────────────────────────────────────────────

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

// ─── Vision Types ────────────────────────────────────────────

export interface VisionAnalysisResponse {
    analysis: string | Record<string, unknown>;
    image_url: string;
}

export interface VisionScreenshotResponse {
    text: string;
    image_url: string;
}

// ─── Memory Types ────────────────────────────────────────────

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

// ─── Watch Types ─────────────────────────────────────────────

export interface WatchTarget {
    query: string;
    interval_minutes: number;
    is_active: boolean;
    last_checked: string | null;
    changes_detected: number;
    last_diff: Record<string, { old: unknown; new: unknown }> | null;
}

// ─── Plugin Types ────────────────────────────────────────────

export interface PluginInfo {
    name: string;
    version: string;
    description: string;
    author: string;
    enabled: boolean;
}

// ─── System Types ────────────────────────────────────────────

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
