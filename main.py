import os
import hmac
import hashlib
import requests
import json
import time
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ===== ENV =====
PAYOS_CLIENT_ID = os.getenv("PAYOS_CLIENT_ID")
PAYOS_API_KEY = os.getenv("PAYOS_API_KEY")
PAYOS_CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY")

PAYOS_URL = "https://api-merchant.payos.vn/v2/payment-requests"


# ===== REQUEST MODEL =====
class CreatePaymentRequest(BaseModel):
    amount: int = Field(ge=1000)
    orderCode: int

class CheckPayment(BaseModel):
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
def create_payment(req: CreatePaymentRequest):

    payload = {
        "orderCode": req.orderCode,
        "amount": req.amount,
        "description": str(req.orderCode),  # <= 9 ký tự
        "cancelUrl": "https://marketcast.bubbleapps.io/version-test/cancel_transaction",
        "returnUrl": "https://marketcast.bubbleapps.io/version-test/payment_success"
    }

    # Tạo chữ ký
    payload["signature"] = create_signature(payload)

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(PAYOS_URL, json=payload, headers=headers)

    return response.json()

# ===== CHECK PAYMENT ENDPOINT =====
@app.get("/check-payment/{orderCode}")
def check_payment(orderCode: int):
    
    url = f"{PAYOS_URL}/{orderCode}"

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=response.text
        )

    return response.json()


# ===== RUN =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)