from datetime import timedelta

from app import create_app
from app.extensions import db
from app.models import TransactionJob, utc_now
from app.worker import recover_stale_jobs


app = create_app()

with app.app_context():
    test_job = TransactionJob(
        transaction_id="RECOVERY_TEST_001",
        status="PROCESSING",
        attempts=1,
        updated_at=utc_now() - timedelta(minutes=10),
    )

    db.session.add(test_job)
    db.session.commit()

    print("Before recovery:", test_job.status)

    recover_stale_jobs()

    db.session.refresh(test_job)

    print("After recovery:", test_job.status)

    # Remove the test record so it does not affect normal processing.
    db.session.delete(test_job)
    db.session.commit()

    print("Test record cleaned up.")