"""Manual/scheduled command: python -m services.market_ingest (from backend/)."""
import os
from datetime import date
from psycopg.types.json import Jsonb

from db import connection, init_db
from services.market_data import MarketDataError, SOURCE_URL, fetch_records


def refresh():
    init_db()
    with connection() as conn:
        run_id = conn.execute("INSERT INTO market_ingestion_runs(provider,source_url,status) VALUES (%s,%s,'running') RETURNING id", ("data.gov.in/AGMARKNET", SOURCE_URL)).fetchone()["id"]
    try:
        records = fetch_records(max_records=int(os.getenv("MARKET_REFRESH_MAX_RECORDS", "10000")))
        with connection() as conn:
            # executemany pipelines all rows in a few round trips instead of one
            # network round trip per record (10k records over a WAN link).
            with conn.cursor() as cur:
                cur.executemany("""
                    INSERT INTO market_prices (provider,source_record_key,commodity,variety,grade,state,district,mandi,observed_on,
                      minimum_price,modal_price,maximum_price,arrival_quantity,arrival_unit,price_unit,source_url,
                      source_updated_at,fetched_at,freshness,raw_metadata)
                    VALUES (%(provider)s,%(source_record_key)s,%(commodity)s,%(variety)s,%(grade)s,%(state)s,%(district)s,%(mandi)s,%(observed_on)s,
                      %(minimum_price)s,%(modal_price)s,%(maximum_price)s,%(arrival_quantity)s,%(arrival_unit)s,%(price_unit)s,
                      %(source_url)s,%(source_updated_at)s,%(fetched_at)s,%(freshness)s,%(raw_metadata)s)
                    ON CONFLICT (provider,source_record_key) DO UPDATE SET minimum_price=EXCLUDED.minimum_price, modal_price=EXCLUDED.modal_price,
                      maximum_price=EXCLUDED.maximum_price, fetched_at=EXCLUDED.fetched_at, freshness=EXCLUDED.freshness,
                      source_url=EXCLUDED.source_url, raw_metadata=EXCLUDED.raw_metadata
                """, [{**record, "raw_metadata": Jsonb(record["raw_metadata"])} for record in records])
            latest = max((r["observed_on"] for r in records), default=None)
            conn.execute("UPDATE market_ingestion_runs SET status='succeeded',completed_at=NOW(),pages_fetched=%s,records_fetched=%s,records_upserted=%s,latest_observed_on=%s WHERE id=%s", ((len(records) + 999) // 1000, len(records), len(records), latest, run_id))
        return {"status": "succeeded", "records_fetched": len(records), "latest_observed_on": latest}
    except (MarketDataError, ValueError) as exc:
        # Persist a sanitized diagnostic; the API key is never included in messages.
        with connection() as conn:
            conn.execute("UPDATE market_ingestion_runs SET status='failed',completed_at=NOW(),error_message=%s WHERE id=%s", (str(exc)[:300], run_id))
        raise
    except Exception:
        # Driver exceptions may include connection details. Store a generic
        # status message and let the CLI surface the exception to its operator.
        with connection() as conn:
            conn.execute("UPDATE market_ingestion_runs SET status='failed',completed_at=NOW(),error_message=%s WHERE id=%s", ("Market ingestion failed; inspect backend logs.", run_id))
        raise


if __name__ == "__main__":
    print(refresh())
