import { z } from 'zod';

// ─── Leaf schemas ────────────────────────────────────────────

export const WeatherInfoSchema = z.object({
    temperature: z.number(),
    description: z.string(),
    humidity: z.number().optional(),
    wind_speed: z.number().optional(),
    city: z.string().optional(),
    country: z.string().optional(),
    icon: z.string().optional(),
});

export const BreachDataSchema = z.object({
    _type: z.undefined().optional(),
    Name: z.string(),
    Title: z.string(),
    Domain: z.string(),
    BreachDate: z.string(),
    PwnCount: z.number().optional(),
    DataClasses: z.array(z.string()),
    IsVerified: z.boolean(),
    IsSensitive: z.boolean().optional(),
    IsSpamList: z.boolean().optional(),
    IsFabricated: z.boolean().optional(),
    Description: z.string().optional(),
    TargetEmail: z.string(),
});

export const PasteDataSchema = z.object({
    _type: z.literal('paste'),
    Source: z.string(),
    Id: z.string(),
    Title: z.string(),
    Date: z.string(),
    EmailCount: z.number(),
    TargetEmail: z.string(),
});

export const LeakRecordSchema = z.union([BreachDataSchema, PasteDataSchema]);

export const ScoreBreakdownSchema = z.object({
    platform_presence: z.number(),
    follower_impact: z.number(),
    activity_intensity: z.number(),
    web_visibility: z.number(),
    digital_diversity: z.number(),
});

export const GeoLocationDataSchema = z.object({
    lat: z.number(),
    lng: z.number(),
    label: z.string(),
    type: z.enum(['primary', 'company', 'exif', 'ip']),
    source: z.string(),
    confidence: z.number(),
    timestamp: z.string().optional(),
});

export const SocialEngineeringVectorSchema = z.object({
    vector: z.string(),
    approach: z.string(),
    risk_level: z.enum(['low', 'medium', 'high']),
});

export const PsychologicalAnalysisSchema = z.object({
    psychological_profile: z.string(),
    strengths: z.array(z.string()),
    weaknesses: z.array(z.string()),
    tactical_recommendations: z.array(z.string()),
    social_engineering_vectors: z.array(SocialEngineeringVectorSchema),
    manipulation_resistance_score: z.number(),
    confidence_level: z.number(),
});

export const PredictionEntrySchema = z.object({
    category: z.enum(['activity', 'behavioral', 'security', 'financial']),
    prediction: z.string(),
    probability: z.number(),
    timeframe: z.enum(['24h', '7d', '30d', '90d']),
    supporting_evidence: z.array(z.string()),
});

export const PredictiveAnalysisSchema = z.object({
    predictions: z.array(PredictionEntrySchema),
    activity_pattern: z.object({
        most_active_hours: z.array(z.number()),
        most_active_days: z.array(z.string()),
        posting_frequency: z.string(),
    }).optional(),
    trend_direction: z.enum(['increasing', 'stable', 'decreasing', 'erratic']),
    data_sufficiency: z.number(),
});

export const CompanyRecordSchema = z.object({
    company_name: z.string(),
    company_type: z.string(),
    role: z.string(),
    role_category: z.enum(['founder', 'executive', 'board_member', 'shareholder', 'unknown']),
    status: z.enum(['active', 'passive', 'liquidated', 'unknown']),
    source_url: z.string(),
    source_name: z.string(),
    country: z.string().optional(),
    confidence: z.number(),
    registry_id: z.string().optional(),
    city: z.string().optional(),
    sector: z.string().optional(),
    risk_flags: z.array(z.string()),
    snippet: z.string(),
});

export const FieldChangeSchema = z.object({
    field: z.string(),
    field_label: z.string(),
    old_value: z.string().nullable(),
    new_value: z.string().nullable(),
});

export const ChangeReportSchema = z.object({
    query_name: z.string(),
    previous_captured_at: z.string().nullable(),
    current_captured_at: z.string(),
    changes: z.array(FieldChangeSchema),
    snapshot_count: z.number(),
    has_changes: z.boolean(),
});

export const FacePairResultSchema = z.object({
    image_a_label: z.string(),
    image_b_label: z.string(),
    verified: z.boolean(),
    confidence: z.number(),
    distance: z.number(),
});

export const FaceMatchReportSchema = z.object({
    overall_confidence: z.number(),
    total_comparisons: z.number(),
    successful_comparisons: z.number(),
    pairs: z.array(FacePairResultSchema),
    face_detected_count: z.number(),
    total_images: z.number(),
});

// ─── Shared base (no passthrough — keeps z.infer types clean) ─

const SharedProfileFieldsSchema = z.object({
    name: z.string(),
    github_url: z.string().optional(),
    instagram_url: z.string().optional(),
    twitter_url: z.string().optional(),
    linkedin_url: z.string().optional(),
    spotify_url: z.string().optional(),
    tiktok_url: z.string().optional(),
    snapchat_url: z.string().optional(),
    tumblr_url: z.string().optional(),
    youtube_url: z.string().optional(),
    reddit_url: z.string().optional(),
    facebook_url: z.string().optional(),
    pinterest_url: z.string().optional(),
    medium_url: z.string().optional(),
    threads_url: z.string().optional(),
    steam_url: z.string().optional(),
    tinder_mention: z.string().optional(),
    bumble_mention: z.string().optional(),
    discord_mention: z.string().optional(),
    phone_numbers: z.array(z.string()).optional(),
    location_country: z.string().optional(),
    location_city: z.string().optional(),
    weather_info: WeatherInfoSchema.optional(),
    social_media_score: z.number().optional(),
    social_media_score_breakdown: ScoreBreakdownSchema.optional(),
    last_activity_summary: z.string().optional(),
    platform_activity: z.record(z.string(), z.number()).optional(),
    description: z.string().optional(),
    additional_info: z.record(z.string(), z.unknown()).optional(),
    similar_profiles: z.array(z.string()).optional(),
    cross_validation_issues: z.array(z.string()).optional(),
    network_connections: z.array(z.object({
        name: z.string(),
        role: z.string(),
        relation: z.string(),
    })).optional(),
    email_addresses: z.array(z.string()).optional(),
    data_breaches: z.array(LeakRecordSchema).optional(),
    company_records: z.array(CompanyRecordSchema).optional(),
});

// ─── Top-level schemas ───────────────────────────────────────

export const ProfileDataSchema = SharedProfileFieldsSchema.extend({
    id: z.number().optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional(),
});

export const SearchResponseSchema = SharedProfileFieldsSchema.extend({
    sources: z.array(z.object({
        title: z.string(),
        url: z.string(),
        snippet: z.string(),
    })).optional(),
    ai_response: z.string(),
    version_history: ChangeReportSchema.optional(),
    face_match_results: FaceMatchReportSchema.optional(),
    sentiment_analysis: z.object({
        positive: z.number(),
        neutral: z.number(),
        negative: z.number(),
        dominant_emotion: z.string(),
        summary: z.string(),
    }).optional(),
    geoint_data: z.array(GeoLocationDataSchema).optional(),
    timezone_analysis: z.object({
        inferred_timezone: z.string(),
        peak_hours: z.array(z.number()),
        activity_pattern: z.string(),
        hourly_distribution: z.record(z.string(), z.number()),
    }).optional(),
    psychological_analysis: PsychologicalAnalysisSchema.optional(),
    prediction_data: PredictiveAnalysisSchema.optional(),
    search_depth: z.number().optional(),
    search_tier: z.string().optional(),
});

export const SearchHistoryItemSchema = z.object({
    id: z.number(),
    query_name: z.string(),
    searched_at: z.string(),
});

// ─── api.ts inline schemas ───────────────────────────────────

export const ServiceStatusResponseSchema = z.object({
    services: z.record(z.string(), z.object({ status: z.string(), error: z.string().optional() })),
    uptime_seconds: z.number(),
    is_monitoring: z.boolean(),
    recovery_attempts: z.record(z.string(), z.number()),
});

export const HealthLogEntrySchema = z.object({
    timestamp: z.string(),
    service: z.string(),
    type: z.string(),
    message: z.string(),
});
