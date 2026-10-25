
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class Transaction(db.Model):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True
    )

    source_account: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    destination_account: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    amount: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PROCESSING"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transaction_amount_positive"),
        CheckConstraint(
            "status IN ('PROCESSING', 'PROCESSED')",
            name="ck_transaction_status"
        ),
    )


class TransactionJob(db.Model):
    __tablename__ = "transaction_jobs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )

    transaction_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING"
    )

    attempts: Mapped[int] = mapped_column(
        nullable=False,
        default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')",
            name="ck_transaction_job_status"
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_transaction_job_attempts"
        ),
    )
