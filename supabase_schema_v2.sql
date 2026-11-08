-- =============================================================
-- LINK LOOT - SUPABASE SCHEMA v2 (User Accounts Update)
-- =============================================================
-- Run this ONCE in the Supabase SQL Editor:
-- Supabase Dashboard -> SQL Editor -> New Query -> Paste -> Run
--
-- What it does:
--  1. Adds user ownership to leads (user_id + user_email), so every
--     user only sees their own leads.
--  2. Changes the unique rule from "one row per URL for everyone"
--     to "one row per URL per user" — two different users can both
--     save the same website without overwriting each other.
--  3. Creates the profiles table (registered users list for Admin).

-- 1. Per-user ownership columns on leads
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS user_id UUID,
    ADD COLUMN IF NOT EXISTS user_email TEXT;

CREATE INDEX IF NOT EXISTS idx_leads_user_id ON public.leads (user_id);
CREATE INDEX IF NOT EXISTS idx_leads_user_email ON public.leads (user_email);

-- 2. Unique per user instead of global
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_url_key;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'leads_user_url_unique'
    ) THEN
        ALTER TABLE public.leads
            ADD CONSTRAINT leads_user_url_unique UNIQUE (user_id, url);
    END IF;
END $$;

-- 3. Registered users (profiles)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY,
    email TEXT,
    full_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow anon read profiles" ON public.profiles;
CREATE POLICY "Allow anon read profiles" ON public.profiles
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow anon insert profiles" ON public.profiles;
CREATE POLICY "Allow anon insert profiles" ON public.profiles
    FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "Allow anon update profiles" ON public.profiles;
CREATE POLICY "Allow anon update profiles" ON public.profiles
    FOR UPDATE USING (true);

COMMENT ON TABLE public.profiles IS 'Registered Link Loot users (mirrors Supabase Auth users)';
COMMENT ON COLUMN public.leads.user_id IS 'Owner of the lead (Supabase Auth user id). The app filters every query by this.';
COMMENT ON COLUMN public.leads.user_email IS 'Owner email, kept for admin reporting.';
