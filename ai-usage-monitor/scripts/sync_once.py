"""Run one read-only sync. Providers without credentials are skipped with a status."""

from backend.database import session_scope
from backend.main import init_database
from backend.services.sync import sync_all


def main() -> None:
    init_database()
    with session_scope() as db:
        for result in sync_all(db):
            print(f"{result['provider']}: {result['status']} — {result['message']} (inserted {result['inserted']})")


if __name__ == "__main__":
    main()
