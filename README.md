# Transaction Webhook Service

A Flask API that accepts transaction webhooks, persists transactions and
processing jobs in PostgreSQL, and processes jobs asynchronously in a separate
worker process.

## Features

- `POST /v1/webhooks/transactions` validates a webhook, stores it and its job,
  then responds with `202 Accepted`.
- Duplicate `transaction_id` values are accepted without creating a second
  transaction or job.
- The worker simulates external processing with a 30-second delay, then updates
  the transaction status and processing timestamp.
- `GET /v1/transactions/<transaction_id>` returns the stored transaction.
- `GET /` is a health check.
- `GET /docs` serves interactive Swagger UI for trying the API endpoints.
- `GET /openapi.json` serves the OpenAPI specification used by Swagger UI.

The webhook handler performs its database insert as a single PostgreSQL
statement. This reduces database round trips, but response time still depends
on the network and database latency; the service cannot guarantee a sub-500 ms
response under every deployment condition.

## Requirements

- Python 3.10 or newer
- PostgreSQL
- Dependencies listed in `requirements.txt`

## Run locally

In PowerShell, from the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file in the repository root and set the connection string for
your PostgreSQL database:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Keep `.env` and database credentials private. Do not commit them to Git.

Create the database tables before starting the API or worker. For local
development, run:

```powershell
python
```

Then, in the Python prompt:

```python
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
```

Exit the Python prompt with `exit()`. For production, create and update the
schema through your database migration/deployment process rather than relying on
`db.create_all()`.

Start the API in one PowerShell window:

```powershell
python .\run.py
```

Start the background worker in a second window:

```powershell
.\.venv\Scripts\python.exe -m app.worker
```

Both processes need the same `DATABASE_URL`. The worker is a separate process;
starting the API alone does not process queued transactions.

## API

### Interactive API documentation

Open [http://127.0.0.1:5000/docs](http://127.0.0.1:5000/docs) while running
locally, or visit the deployed [`/docs`](https://transaction-webhook-service-28y0.onrender.com/docs)
page to try the health check, submit a webhook, and retrieve transaction status.
The interactive page loads Swagger UI assets from a public CDN.

### Health check

```http
GET /
```

Example response:

```json
{
  "status": "HEALTHY",
  "current_time": "2026-10-25T07:00:00+00:00"
}
```

### Receive a transaction webhook

```http
POST /v1/webhooks/transactions
Content-Type: application/json
```

Request body:

```json
{
  "transaction_id": "txn_abc123def456",
  "source_account": "acc_user_789",
  "destination_account": "acc_merchant_456",
  "amount": 1500,
  "currency": "INR"
}
```

Example PowerShell request:

```powershell
curl.exe -X POST http://127.0.0.1:5000/v1/webhooks/transactions `
  -H "Content-Type: application/json" `
  -d '{"transaction_id":"txn_abc123def456","source_account":"acc_user_789","destination_account":"acc_merchant_456","amount":1500,"currency":"INR"}'
```

A new transaction returns `202 Accepted`, for example:

```json
{
  "message": "Transaction accepted for processing",
  "transaction_id": "txn_abc123def456",
  "status": "PROCESSING"
}
```

A repeat webhook for the same ID also returns `202 Accepted` and does not create
a second job. Invalid input returns `400 Bad Request`; a database error returns
`500 Internal Server Error`.

### Retrieve transaction status

```http
GET /v1/transactions/txn_abc123def456
```

Example response:

```json
{
  "transaction_id": "txn_abc123def456",
  "source_account": "acc_user_789",
  "destination_account": "acc_merchant_456",
  "amount": "1500.00",
  "currency": "INR",
  "status": "PROCESSING",
  "created_at": "2026-10-25T07:00:00+00:00",
  "processed_at": null
}
```

After the worker completes the simulated processing, `status` becomes
`PROCESSED` and `processed_at` contains the completion timestamp. The worker
waits 30 seconds per job and polls for pending work every 2 seconds. Jobs are
processed sequentially by each worker process.

## Tests and timing checks

Run the webhook timing script against the configured database:

```powershell
.\.venv\Scripts\python.exe .\test_webhook_timing.py
```

It reports HTTP status and elapsed time for its sample transaction IDs. Those
IDs may already exist in the database, in which case the script measures the
duplicate-webhook path. Change the sample IDs in `test_webhook_timing.py` to
measure a new-transaction request. The script sends real requests to the
configured database.

Other database-backed diagnostic scripts:

```powershell
.\.venv\Scripts\python.exe .\test_db_connection.py
.\.venv\Scripts\python.exe .\test_db_timing.py
.\.venv\Scripts\python.exe .\test_worker_recovery.py
```

`test_worker_recovery.py` creates a temporary database job and removes it after
the check. These scripts require the database tables to exist.

## Technical choices

- **Flask** provides a small HTTP API with straightforward endpoint handling.
- **Flask-SQLAlchemy and SQLAlchemy** map transactions and jobs to PostgreSQL.
- **PostgreSQL** provides persistent storage and an atomic `ON CONFLICT DO
  NOTHING` insert for transaction idempotency.
- **A separate polling worker** keeps the 30-second simulated processing delay
  out of the webhook request path. It marks jobs as processing before the
  delay, completes them afterward, and resets jobs that remain in processing
  for more than five minutes so they can be retried.

## Deployment

This service is deployed on Render and connected to the GitHub repository:

- **Public API:** <https://transaction-webhook-service-28y0.onrender.com/>
- **Interactive API docs:** <https://transaction-webhook-service-28y0.onrender.com/docs>
- **GitHub repository:** <https://github.com/RenukaMewada-2005/transaction-webhook-service>

Check the deployment with `GET /` or submit a webhook to
`POST /v1/webhooks/transactions` at the public API URL.

The currently deployed Render service is a web service. It runs the API, but
does not run the background worker. Therefore, webhook requests can be
accepted and stored, but their status remains `PROCESSING` until a worker is
running against the same PostgreSQL database. To complete transactions in
production, deploy a separate worker service or run the worker on another
always-on host. Configure the API service with this start command:

```bash
gunicorn --bind 0.0.0.0:$PORT run:app
```

When an always-on worker host is available, configure its start command as:

```bash
python -m app.worker
```

Set `DATABASE_URL` in each service's Render environment settings. Keep database
credentials private; do not commit them to the repository.
