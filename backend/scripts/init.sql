-- J.A.R.V.I.S Database Initialization Script
-- This script is for PostgreSQL. SQLite tables are auto-created by SQLAlchemy.
-- Run with: psql -U postgres -f init.sql

-- Drop database if exists
DROP DATABASE IF EXISTS "J.A.R.V.I.S";

-- Create database
CREATE DATABASE "J.A.R.V.I.S"
    WITH 
    OWNER = postgres
    ENCODING = 'UTF8'
    CONNECTION LIMIT = -1;

-- Connect to the database
\c "J.A.R.V.I.S"

-- Create profiles table
CREATE TABLE IF NOT EXISTS profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    github_url TEXT,
    instagram_url TEXT,
    twitter_url TEXT,
    linkedin_url TEXT,
    spotify_url TEXT,
    tiktok_url TEXT,
    description TEXT,
    additional_info JSONB,
    similar_profiles JSONB,
    cross_validation_issues JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create search history table
CREATE TABLE IF NOT EXISTS search_history (
    id SERIAL PRIMARY KEY,
    query_name VARCHAR(500) NOT NULL,
    searched_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(name);
CREATE INDEX IF NOT EXISTS idx_search_history_searched_at ON search_history(searched_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for updated_at
DROP TRIGGER IF EXISTS update_profiles_updated_at ON profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Display table structures
\d profiles;
\d search_history;

-- Success message
SELECT 'J.A.R.V.I.S database initialized successfully!' AS status;
