
import time
from datetime import timedelta

from sqlalchemy import select, update

from app import create_app
from app.extensions import db
from app.models import Transaction, TransactionJob, utc_now


PROCESSING_DELAY_SECONDS = 30
POLL_INTERVAL_SECONDS = 2

STALE_JOB_TIMEOUT_SECONDS = 300  # 5 minutes


def recover_stale_jobs():
    """Reset jobs that have been stuck in PROCESSING for over 5 minutes."""

    cutoff_time = utc_now() - timedelta(
        seconds=STALE_JOB_TIMEOUT_SECONDS
    )

    result = db.session.execute(
        update(TransactionJob)
        .where(
            TransactionJob.status == "PROCESSING",
            TransactionJob.updated_at < cutoff_time,
        )
        .values(
            status="PENDING",
            updated_at=utc_now(),
        )
    )

    db.session.commit()

    if result.rowcount:
        print(f"Recovered {result.rowcount} stale job(s).")

def process_job(job_id):
    """Process one pending transaction job."""

    with db.session.begin():
        job = db.session.execute(
            select(TransactionJob)
            .where(TransactionJob.id == job_id)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()

        if job is None or job.status != "PENDING":
            return

        job.status = "PROCESSING"
        job.attempts += 1

        transaction = db.session.get(
            Transaction,
            job.transaction_id
        )

        if transaction is None:
            job.status = "FAILED"
            return

        transaction.status = "PROCESSING"

    # Simulate an external API call without holding a database lock.
    time.sleep(PROCESSING_DELAY_SECONDS)

    with db.session.begin():
        job = db.session.execute(
            select(TransactionJob)
            .where(TransactionJob.id == job_id)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()

        if job is None or job.status != "PROCESSING":
            return

        transaction = db.session.get(
            Transaction,
            job.transaction_id
        )

        if transaction is None:
            job.status = "FAILED"
            return

        transaction.status = "PROCESSED"
        transaction.processed_at = utc_now()

        job.status = "COMPLETED"


def run_worker():
    """Continuously look for pending jobs."""

    app = create_app()

    print("Background worker started.")
    print("Waiting for pending transaction jobs...")

    with app.app_context():
        while True:
            try:
                recover_stale_jobs()
                job_id = db.session.execute(
                    select(TransactionJob.id)
                    .where(TransactionJob.status == "PENDING")
                    .order_by(TransactionJob.created_at)
                    .limit(1)
                ).scalar_one_or_none()

                db.session.remove()

                if job_id is None:
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue

                print(f"Processing job ID: {job_id}")

                process_job(job_id)

                print(f"Finished processing job ID: {job_id}")

            except KeyboardInterrupt:
                print("Background worker stopped.")
                break

            except Exception as error:
                db.session.rollback()
                db.session.remove()
                print(f"Worker error: {error}")
                time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker()
