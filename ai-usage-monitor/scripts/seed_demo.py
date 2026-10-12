"""Create the local environment and seed labeled demo data."""

from backend.database import session_scope
from backend.main import init_database
from backend.services.demo_data import seed_demo


def main() -> None:
    init_database()
    with session_scope() as db:
        result = seed_demo(db)
    print(result)


if __name__ == "__main__":
    main()
