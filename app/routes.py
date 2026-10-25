
from decimal import Decimal, InvalidOperation
import logging
from flask import Blueprint, request
from sqlalchemy import literal, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Transaction, TransactionJob, utc_now


webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.post("/v1/webhooks/transactions")
def receive_transaction():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Request body must be a JSON object"}, 400

    required_fields = [
        "transaction_id",
        "source_account",
        "destination_account",
        "amount",
        "currency",
    ]

    missing_fields = [
        field for field in required_fields
        if field not in data
    ]

    if missing_fields:
        return {
            "error": "Missing required fields",
            "fields": missing_fields,
        }, 400

    transaction_id = data["transaction_id"]
    source_account = data["source_account"]
    destination_account = data["destination_account"]
    currency = data["currency"]

    if not all(
        isinstance(value, str) and value.strip()
        for value in [
            transaction_id,
            source_account,
            destination_account,
            currency,
        ]
    ):
        return {
            "error": "Transaction ID, accounts, and currency must be non-empty strings"
        }, 400

    transaction_id = transaction_id.strip()
    source_account = source_account.strip()
    destination_account = destination_account.strip()
    currency = currency.strip().upper()

    if len(transaction_id) > 100:
        return {"error": "transaction_id must be at most 100 characters"}, 400

    if len(source_account) > 100 or len(destination_account) > 100:
        return {"error": "Account names must be at most 100 characters"}, 400

    if len(currency) != 3 or not currency.isalpha():
        return {"error": "currency must be a 3-letter code"}, 400

    try:
        raw_amount = data["amount"]

        if isinstance(raw_amount, bool):
            raise InvalidOperation

        amount = Decimal(str(raw_amount))

        if not amount.is_finite() or amount <= 0:
            raise InvalidOperation

        if amount.as_tuple().exponent < -2 or amount >= Decimal("10000000000"):
            raise InvalidOperation

    except (InvalidOperation, ValueError, TypeError):
        return {
            "error": "amount must be a positive number with at most 2 decimal places"
        }, 400

    now = utc_now()
    inserted_transaction = (
        postgresql_insert(Transaction)
        .values(
            transaction_id=transaction_id,
            source_account=source_account,
            destination_account=destination_account,
            amount=amount,
            currency=currency,
            status="PROCESSING",
            created_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=[Transaction.transaction_id]
        )
        .returning(Transaction.transaction_id)
        .cte("inserted_transaction")
    )
    insert_job = (
        postgresql_insert(TransactionJob)
        .from_select(
            [
                TransactionJob.transaction_id,
                TransactionJob.status,
                TransactionJob.attempts,
                TransactionJob.created_at,
                TransactionJob.updated_at,
            ],
            select(
                inserted_transaction.c.transaction_id,
                literal("PENDING"),
                literal(0),
                literal(now),
                literal(now),
            ),
        )
        .returning(TransactionJob.transaction_id)
    )

    try:
        with db.engine.connect() as connection:
            connection = connection.execution_options(
                isolation_level="AUTOCOMMIT"
            )
            inserted_id = connection.execute(
                insert_job
            ).scalar_one_or_none()
    except SQLAlchemyError:
        logging.exception("Could not save transaction webhook")
        return {"error": "Could not save transaction"}, 500

    if inserted_id is None:
        return {
            "message": "Transaction already received",
            "transaction_id": transaction_id,
        }, 202

    return {
        "message": "Transaction accepted for processing",
        "transaction_id": transaction_id,
        "status": "PROCESSING",
    }, 202


@webhook_bp.get("/v1/transactions/<transaction_id>")
def get_transaction(transaction_id):
    transaction = db.session.get(Transaction, transaction_id)

    if transaction is None:
        return {
            "error": "Transaction not found",
            "transaction_id": transaction_id,
        }, 404

    return {
        "transaction_id": transaction.transaction_id,
        "source_account": transaction.source_account,
        "destination_account": transaction.destination_account,
        "amount": str(transaction.amount),
        "currency": transaction.currency,
        "status": transaction.status,
        "created_at": (
            transaction.created_at.isoformat()
            if transaction.created_at else None
        ),
        "processed_at": (
            transaction.processed_at.isoformat()
            if transaction.processed_at else None
        ),
    }, 200
