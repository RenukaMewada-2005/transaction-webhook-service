
import time

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    try:
        start = time.perf_counter()
        db.session.execute(db.text("SELECT 1"))
        print(
            "SELECT time: {:.2f} ms".format(
                (time.perf_counter() - start) * 1000
            )
        )

        start = time.perf_counter()
        db.session.execute(
            db.text(
                "SELECT 1 FROM transactions "
                "WHERE transaction_id = :transaction_id"
            ),
            {"transaction_id": "LATENCY_DIAGNOSTIC_ONLY"},
        )
        print(
            "Lookup time: {:.2f} ms".format(
                (time.perf_counter() - start) * 1000
            )
        )

    finally:
        db.session.rollback()
        db.session.remove()
