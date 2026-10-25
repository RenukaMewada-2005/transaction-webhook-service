
import time

from app import create_app

app = create_app()
client = app.test_client()

payloads = [
    {
        "transaction_id": "LATENCY_TEST_003",
        "source_account": "ACC101",
        "destination_account": "ACC102",
        "amount": 100,
        "currency": "INR",
    },
    {
        "transaction_id": "LATENCY_TEST_004",
        "source_account": "ACC101",
        "destination_account": "ACC102",
        "amount": 200,
        "currency": "INR",
    },
]

for payload in payloads:
    start = time.perf_counter()

    response = client.post(
        "/v1/webhooks/transactions",
        json=payload,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    print("\nTransaction:", payload["transaction_id"])
    print("HTTP status:", response.status_code)
    print("Response time: {:.2f} ms".format(elapsed_ms))
    print("Under 500 ms:", elapsed_ms < 500)
    print("Response:", response.get_json())
