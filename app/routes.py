
from decimal import Decimal, InvalidOperation
import logging
from flask import Blueprint, Response, jsonify, request
from sqlalchemy import literal, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Transaction, TransactionJob, utc_now


webhook_bp = Blueprint("webhook", __name__)

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Transaction Webhook Service API",
        "version": "1.0.0",
        "description": (
            "Accepts transaction webhooks and provides transaction status. "
            "The background worker must be running to complete processing."
        ),
    },
    "servers": [{"url": "/"}],
    "paths": {
        "/": {
            "get": {
                "summary": "Health check",
                "responses": {
                    "200": {
                        "description": "Service is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "HEALTHY"},
                                        "current_time": {
                                            "type": "string",
                                            "format": "date-time",
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/v1/webhooks/transactions": {
            "post": {
                "summary": "Submit a transaction webhook",
                "description": (
                    "Returns 202 after the transaction and job are persisted. "
                    "Repeated transaction IDs are accepted without creating "
                    "duplicate jobs."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/TransactionWebhook"},
                            "example": {
                                "transaction_id": "txn_abc123def456",
                                "source_account": "acc_user_789",
                                "destination_account": "acc_merchant_456",
                                "amount": 1500,
                                "currency": "INR",
                            },
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Transaction accepted or already received",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {"type": "string"},
                                        "transaction_id": {"type": "string"},
                                        "status": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "400": {"description": "Invalid request body"},
                    "500": {"description": "Could not save transaction"},
                },
            }
        },
        "/v1/transactions/{transaction_id}": {
            "get": {
                "summary": "Get transaction status",
                "parameters": [
                    {
                        "name": "transaction_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Transaction details",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/Transaction"
                                }
                            }
                        },
                    },
                    "404": {"description": "Transaction not found"},
                },
            }
        },
    },
    "components": {
        "schemas": {
            "TransactionWebhook": {
                "type": "object",
                "required": [
                    "transaction_id",
                    "source_account",
                    "destination_account",
                    "amount",
                    "currency",
                ],
                "properties": {
                    "transaction_id": {"type": "string", "example": "txn_abc123def456"},
                    "source_account": {"type": "string", "example": "acc_user_789"},
                    "destination_account": {
                        "type": "string",
                        "example": "acc_merchant_456",
                    },
                    "amount": {"type": "number", "exclusiveMinimum": 0, "example": 1500},
                    "currency": {"type": "string", "minLength": 3, "maxLength": 3, "example": "INR"},
                },
            },
            "Transaction": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string"},
                    "source_account": {"type": "string"},
                    "destination_account": {"type": "string"},
                    "amount": {"type": "string", "example": "1500.00"},
                    "currency": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["PROCESSING", "PROCESSED"],
                    },
                    "created_at": {"type": "string", "format": "date-time"},
                    "processed_at": {
                        "type": "string",
                        "format": "date-time",
                        "nullable": True,
                    },
                },
            },
        }
    },
}


@webhook_bp.get("/openapi.json")
def openapi_spec():
    return jsonify(OPENAPI_SPEC)


@webhook_bp.get("/docs")
def api_docs():
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Transaction Webhook Service API Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css">
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
    <script>
      window.onload = () => SwaggerUIBundle({
        url: "./openapi.json",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis],
        layout: "BaseLayout",
        deepLinking: true
      });
    </script>
  </body>
</html>"""
    return Response(html, mimetype="text/html")


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
