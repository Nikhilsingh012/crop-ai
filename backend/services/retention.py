"""Privacy retention job for opt-in community reports."""
from db import connection


def purge_expired_disease_reports():
    with connection() as conn:
        result = conn.execute("DELETE FROM disease_reports WHERE expires_at <= NOW()")
        return result.rowcount


if __name__ == "__main__":
    print(f"Expired reports purged: {purge_expired_disease_reports()}")
