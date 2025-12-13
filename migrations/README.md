# Database Migrations

This directory contains SQL migration scripts for the PostgreSQL database.

## Running Migrations

### Prerequisites
- Access to your Cloud SQL PostgreSQL instance
- Database credentials (from `DATABASE_URL` environment variable)

### Option 1: Using psql (Recommended)

```bash
# Connect to your Cloud SQL Postgres instance
psql "$DATABASE_URL"

# Or if DATABASE_URL is not set, connect manually:
psql -h <HOST> -U <USERNAME> -d <DATABASE>

# Run the migration
\i migrations/001_add_portal_analytics.sql

# Verify the migration
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'portals'
  AND column_name IN ('last_viewed_at', 'last_copied_at');

SELECT table_name
FROM information_schema.tables
WHERE table_name = 'portal_events';
```

### Option 2: Using Cloud SQL Proxy

```bash
# Start Cloud SQL Proxy (in a separate terminal)
cloud_sql_proxy -instances=YOUR_INSTANCE_CONNECTION_NAME=tcp:5432

# In another terminal, connect via psql
psql -h localhost -U YOUR_USERNAME -d YOUR_DATABASE

# Run the migration
\i migrations/001_add_portal_analytics.sql
```

### Option 3: Via Python Script

```python
from app import create_app
from app.models import db

app = create_app()
with app.app_context():
    # Read and execute migration SQL
    with open('migrations/001_add_portal_analytics.sql', 'r') as f:
        sql = f.read()
    db.engine.execute(sql)
    print("Migration completed successfully!")
```

## Migration Order

1. **001_add_portal_analytics.sql** - Adds portal analytics tracking with event deduplication

## Rollback (if needed)

To rollback the analytics migration:

```sql
-- Remove portal_events table
DROP TABLE IF EXISTS portal_events CASCADE;

-- Remove new columns from portals
ALTER TABLE portals
DROP COLUMN IF EXISTS last_viewed_at,
DROP COLUMN IF EXISTS last_copied_at;
```

## Important Notes

- All timestamps are stored in UTC (without timezone)
- The `event_day` column is used for daily deduplication
- The unique constraint prevents duplicate 'view' events for the same profile/portal/day
- Foreign key uses `ON DELETE CASCADE` so events are deleted if portal is deleted
