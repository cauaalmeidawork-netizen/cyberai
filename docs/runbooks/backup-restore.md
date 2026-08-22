# Backup And Restore Runbook

PostgreSQL is the source of truth, including pgvector data. Redis is transient.

## Backup

```bash
python scripts/pg_backup.py \
  --database-url "$NOMERCY_DATABASE__URL" \
  --output "backups/nomercy-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Store backups in encrypted object storage with at least 30 days retention for beta.

## Restore Validation

```bash
python scripts/pg_restore_check.py \
  --admin-url "$POSTGRES_ADMIN_URL" \
  --backup backups/nomercy-latest.dump \
  --database nomercy_restore_check
```

## Production Restore

1. Stop API/web traffic.
2. Restore the selected dump into a new PostgreSQL database.
3. Run `alembic upgrade head` against the restored database.
4. Point API secrets/config at the restored database.
5. Start API/web and run smoke tests.
6. Keep the previous database read-only until the incident is closed.
