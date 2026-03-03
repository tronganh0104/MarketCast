import os
import hmac
import hashlib
import requests
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ===== ENV =====
PAYOS_CLIENT_ID = os.getenv("PAYOS_CLIENT_ID")
PAYOS_API_KEY = os.getenv("PAYOS_API_KEY")
PAYOS_CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY")

PAYOS_URL = "https://api.payos.vn/v2/payment-requests"


# ===== REQUEST MODEL =====
class PaymentRequest(BaseModel):
    amount: int
    orderCode: int


# ===== SIGNATURE FUNCTION =====
def create_signature(data: dict):

    raw_data = (
        f"amount={data['amount']}"
        f"&cancelUrl={data['cancelUrl']}"
        f"&description={data['description']}"
        f"&orderCode={data['orderCode']}"
        f"&returnUrl={data['returnUrl']}"
    )

    signature = hmac.new(
        PAYOS_CHECKSUM_KEY.encode(),
        raw_data.encode(),
        hashlib.sha256
    ).hexdigest()

    return signature


# ===== CREATE PAYMENT ENDPOINT =====
@app.post("/create-payment")
def create_payment(req: PaymentRequest):

    payload = {
        "orderCode": req.orderCode,
        "amount": req.amount,
        "description": "NAPTIEN",  # <= 9 ký tự
        "cancelUrl": "https://example.com/cancel",
        "returnUrl": "https://example.com/success"
    }

    # Tạo chữ ký
    payload["signature"] = create_signature(payload)

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    print("===== REQUEST TO PAYOS =====")
    print(payload)

    response = requests.post(PAYOS_URL, json=payload, headers=headers)

    print("===== RESPONSE FROM PAYOS =====")
    print(response.status_code)
    print(response.text)

    return response.json()

@app.post("/your-endpoint")
async def your_endpoint(request: PaymentRequest):
    body = await request.json()
    print("=== REQUEST BODY ===")
    print(body)
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}

# ===== RUN =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)