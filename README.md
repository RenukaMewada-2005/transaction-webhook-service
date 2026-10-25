# Transaction Webhook Service

This is a small Flask service for receiving payment transaction webhooks. It
saves each transaction to PostgreSQL and is designed to process it in the
background, so the webhook request can return quickly.

## Live links

- **API:** <https://transaction-webhook-service-28y0.onrender.com/>
- **Try the API in your browser:** <https://transaction-webhook-service-28y0.onrender.com/docs>
- **GitHub repository:** <https://github.com/RenukaMewada-2005/transaction-webhook-service>

## What the service does

- Accepts transactions at `POST /v1/webhooks/transactions` and returns
  `202 Accepted` after saving them.
- Prevents duplicate transactions when the same `transaction_id` is sent more
  than once.
- Lets you check a transaction with
  `GET /v1/transactions/<transaction_id>`.
- Provides a health check at `GET /`.
- Provides interactive API documentation at `GET /docs`.
- Includes a worker that waits 30 seconds to simulate processing, then marks a
  transaction as `PROCESSED`.

The webhook endpoint saves the transaction and its job with one PostgreSQL
statement to reduce database round trips. Actual response time still depends
on the database and network, so it may vary between deployments.

## Run it locally

You need Python 3.10 or newer and a PostgreSQL database. In PowerShell, open
the project folder and install the dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create a `.env` file in the project folder and add your PostgreSQL connection
string:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Replace the example values with your own database details. Do not share or
commit your `.env` file.

Create the database tables for local development:

```powershell
python
```

At the Python prompt, run:

```python
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
```

Then enter `exit()` to close the Python prompt. For a production deployment,
use a database migration or deployment process to manage tables.

Start the API:

```powershell
python .\run.py
```

To process transactions locally, open a second PowerShell window in the
project folder and start the worker:

```powershell
.\.venv\Scripts\python.exe -m app.worker
```

Both the API and worker use the same `DATABASE_URL`. The API can accept and
store webhooks without the worker, but transactions will not finish processing
until a worker is running.

## Try the API

### Interactive docs

With the app running locally, open <http://127.0.0.1:5000/docs>. To try the
deployed API, open <https://transaction-webhook-service-28y0.onrender.com/docs>.
Use the **Try it out** button in Swagger UI to send requests. The docs page
loads its Swagger UI files from a public CDN.

The OpenAPI description is also available at `/openapi.json`.

### Health check

Send a `GET /` request. A healthy service responds with its status and current
time:

```json
{
  "status": "HEALTHY",
  "current_time": "2026-10-25T07:00:00+00:00"
}
```

### Submit a transaction

Send a `POST /v1/webhooks/transactions` request with a JSON body:

```json
{
  "transaction_id": "txn_abc123def456",
  "source_account": "acc_user_789",
  "destination_account": "acc_merchant_456",
  "amount": 1500,
  "currency": "INR"
}
```

For example, from PowerShell when the app is running locally:

```powershell
curl.exe -X POST http://127.0.0.1:5000/v1/webhooks/transactions `
  -H "Content-Type: application/json" `
  -d '{"transaction_id":"txn_abc123def456","source_account":"acc_user_789","destination_account":"acc_merchant_456","amount":1500,"currency":"INR"}'
```

A new webhook responds with `202 Accepted`:

```json
{
  "message": "Transaction accepted for processing",
  "transaction_id": "txn_abc123def456",
  "status": "PROCESSING"
}
```

Sending the same transaction ID again also returns `202`, without adding a
duplicate job. Invalid input returns `400`. A database error returns `500`.

### Check transaction status

After submitting the webhook, send:

```http
GET /v1/transactions/txn_abc123def456
```

The response includes the transaction details, its status, and timestamps.
`processed_at` is `null` while the transaction is still processing. Once the
worker finishes, the status changes to `PROCESSED` and `processed_at` is set.
The worker processes jobs in order, one at a time, and checks for new work
every two seconds.

## Check webhook response time

The timing script sends requests to the database configured in your `.env`
file and prints each response time:

```powershell
.\.venv\Scripts\python.exe .\test_webhook_timing.py
```

It uses the sample transaction IDs in the script. If those transactions are
already in the database, it measures duplicate requests. To measure a new
transaction, change the sample IDs first.

Other database checks are available:

```powershell
.\.venv\Scripts\python.exe .\test_db_connection.py
.\.venv\Scripts\python.exe .\test_db_timing.py
.\.venv\Scripts\python.exe .\test_worker_recovery.py
```

These scripts need the database tables to exist. The worker recovery check
creates a test job and removes it when it finishes.

## Why I used these tools

- **Flask** keeps the API simple and lightweight.
- **Flask-SQLAlchemy and SQLAlchemy** handle the database models and queries.
- **PostgreSQL** stores transactions and jobs. Its conflict handling helps
  prevent duplicate transactions when webhook requests are repeated.
- **A separate worker** keeps the 30-second simulated delay out of the API
  request. It marks jobs as processing, completes them after the delay, and
  makes old stuck jobs available for retry.

## Render deployment

The app is connected to GitHub and deployed as a Render web service. The
current service runs the API, but it does **not** run the background worker.
That means you can use `/docs` to test the endpoints and webhook requests can
be saved, but transactions may stay `PROCESSING` until a worker is running.

To run the API as a Render web service, use this start command:

```bash
gunicorn --bind 0.0.0.0:$PORT run:app
```

The worker needs to run as a separate, always-on process and use the same
PostgreSQL database. Its start command is:

```bash
python -m app.worker
```

If your Render plan does not include a background worker, you would need an
always-on worker elsewhere to complete transactions. Set `DATABASE_URL` in
the Render environment settings (and on the worker host). Keep database
credentials private.
