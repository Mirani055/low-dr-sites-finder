-- =============================================================
-- LINK LOOT - SUPABASE DATABASE SCHEMA
-- =============================================================
-- Copy and paste this entire script into your Supabase SQL Editor:
-- Supabase Dashboard -> SQL Editor -> New Query -> Run (Ctrl+Enter)

-- 1. Create the leads table
CREATE TABLE IF NOT EXISTS public.leads (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    niche TEXT,
    country TEXT,
    city TEXT,
    domain TEXT,
    url TEXT UNIQUE,
    title TEXT,
    dr_score NUMERIC,
    dr_source TEXT,
    emails TEXT,
    email_status TEXT,
    facebook TEXT,
    linkedin TEXT,
    instagram TEXT,
    twitter TEXT,
    phone TEXT,
    whatsapp TEXT,
    dr_status TEXT,
    scrape_status TEXT
);

-- 2. Create performance indexes for quick searching & filtering
CREATE INDEX IF NOT EXISTS idx_leads_domain ON public.leads (domain);
CREATE INDEX IF NOT EXISTS idx_leads_country ON public.leads (country);
CREATE INDEX IF NOT EXISTS idx_leads_niche ON public.leads (niche);
CREATE INDEX IF NOT EXISTS idx_leads_dr_score ON public.leads (dr_score);
CREATE INDEX IF NOT EXISTS idx_leads_created_at ON public.leads (created_at DESC);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;

-- 4. Create permissive policies for public / anon access
-- (Allows your Streamlit dashboard to read, insert, and update leads)
DROP POLICY IF EXISTS "Allow anon read" ON public.leads;
CREATE POLICY "Allow anon read" ON public.leads 
    FOR SELECT 
    USING (true);

DROP POLICY IF EXISTS "Allow anon insert" ON public.leads;
CREATE POLICY "Allow anon insert" ON public.leads 
    FOR INSERT 
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow anon update" ON public.leads;
CREATE POLICY "Allow anon update" ON public.leads 
    FOR UPDATE 
    USING (true);

DROP POLICY IF EXISTS "Allow anon delete" ON public.leads;
CREATE POLICY "Allow anon delete" ON public.leads 
    FOR DELETE 
    USING (true);

-- 5. Comments for documentation
COMMENT ON TABLE public.leads IS 'Stores low DR website leads collected by Link Loot';
