-- Migration: Add portal analytics tracking
-- Description: Adds lightweight analytics with UTC timestamps and event deduplication
-- Database: PostgreSQL (Cloud SQL)

-- ============================================
-- STEP 1: Add new columns to portals table
-- ============================================

ALTER TABLE portals
ADD COLUMN last_viewed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL,
ADD COLUMN last_copied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NULL;

COMMENT ON COLUMN portals.last_viewed_at IS 'UTC timestamp of most recent portal view';
COMMENT ON COLUMN portals.last_copied_at IS 'UTC timestamp of most recent successful copy from portal';


-- ============================================
-- STEP 2: Create portal_events table
-- ============================================

CREATE TABLE portal_events (
    id SERIAL PRIMARY KEY,
    portal_id INTEGER NOT NULL REFERENCES portals(id) ON DELETE CASCADE,
    event_type VARCHAR(20) NOT NULL,
    profile_id VARCHAR(100),
    copier_id VARCHAR(100),
    occurred_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    event_day DATE NOT NULL,

    CONSTRAINT chk_event_type CHECK (event_type IN ('view', 'copy_success'))
);

COMMENT ON TABLE portal_events IS 'Portal analytics events with UTC timestamps and daily deduplication';
COMMENT ON COLUMN portal_events.event_type IS 'Event type: view or copy_success';
COMMENT ON COLUMN portal_events.profile_id IS 'User profile ID (populated for both view and copy_success)';
COMMENT ON COLUMN portal_events.copier_id IS 'Copier account ID (only for copy_success events)';
COMMENT ON COLUMN portal_events.occurred_at IS 'UTC timestamp when event occurred';
COMMENT ON COLUMN portal_events.event_day IS 'UTC date for deduplication (computed from occurred_at)';


-- ============================================
-- STEP 3: Create unique constraint for deduplication
-- ============================================

CREATE UNIQUE INDEX uq_portal_profile_day_event
ON portal_events (portal_id, profile_id, event_day, event_type);

COMMENT ON INDEX uq_portal_profile_day_event IS 'Deduplicates views: one view event per profile per portal per UTC day';


-- ============================================
-- STEP 4: Create performance indexes
-- ============================================

CREATE INDEX idx_portal_occurred
ON portal_events (portal_id, occurred_at);

COMMENT ON INDEX idx_portal_occurred IS 'Query events by portal with time-based filtering';

CREATE INDEX idx_portal_event_occurred
ON portal_events (portal_id, event_type, occurred_at);

COMMENT ON INDEX idx_portal_event_occurred IS 'Query specific event types by portal with time-based filtering';

CREATE INDEX idx_portal_id_fk
ON portal_events (portal_id);

COMMENT ON INDEX idx_portal_id_fk IS 'Foreign key index for portal_id joins';


-- ============================================
-- VERIFICATION QUERIES
-- ============================================

-- Verify new columns exist
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'portals' AND column_name IN ('last_viewed_at', 'last_copied_at');

-- Verify portal_events table structure
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'portal_events'
-- ORDER BY ordinal_position;

-- Verify constraints and indexes
-- SELECT constraint_name, constraint_type
-- FROM information_schema.table_constraints
-- WHERE table_name = 'portal_events';

-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'portal_events';
