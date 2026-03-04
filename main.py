import os
import hmac
import hashlib
import requests
import json
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

# ===== ENV =====
PAYOS_CLIENT_ID = os.getenv("PAYOS_CLIENT_ID")
PAYOS_API_KEY = os.getenv("PAYOS_API_KEY")
PAYOS_CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY")

BUBBLE_APP_NAME = os.getenv("BUBBLE_APP_NAME")
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

PAYOS_URL = "https://api-merchant.payos.vn/v2/payment-requests"


# ==============================
# ATO ENGINE
# ==============================

def get_open_ato_markets():
    url = f"https://{BUBBLE_APP_NAME}.bubbleapps.io/api/1.1/obj/market"

    params = {
        "constraints": json.dumps([
            {
                "key": "is_ato",  # FIXED
                "constraint_type": "equals",
                "value": True
            }
        ])
    }

    headers = {
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print("ERROR fetching ATO markets:", response.text)
        return []

    return response.json()["response"]["results"]


def close_ato(market_id: str):
    url = f"https://{BUBBLE_APP_NAME}.bubbleapps.io/api/1.1/obj/market/{market_id}"

    headers = {
        "Authorization": f"Bearer {BUBBLE_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "is_ato": False  # FIXED
    }

    response = requests.patch(url, headers=headers, json=payload)
    print("Closed ATO:", market_id, response.status_code)


def check_and_close_ato():
    markets = get_open_ato_markets()
    now = datetime.now(timezone.utc)

    print(f"Checking {len(markets)} ATO markets...")

    for market in markets:
        try:
            ato_end_time = datetime.fromisoformat(
                market["ato_end_time"].replace("Z", "+00:00")
            )

            if ato_end_time <= now:
                close_ato(market["_id"])

        except Exception as e:
            print("ATO parsing error:", e)


async def ato_loop():
    while True:
        try:
            check_and_close_ato()
        except Exception as e:
            print("ATO LOOP ERROR:", e)

        await asyncio.sleep(30)


# ==============================
# LIFESPAN
# ==============================

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(ato_loop())
    print("ATO background loop started")
    yield
    task.cancel()
    print("ATO background loop stopped")


app = FastAPI(lifespan=lifespan)


# ==============================
# PAYOS SECTION
# ==============================

class CreatePaymentRequest(BaseModel):
    amount: int = Field(ge=1000)
    orderCode: int


def create_signature(data: dict):
    raw_data = (
        f"amount={data['amount']}"
        f"&cancelUrl={data['cancelUrl']}"
        f"&description={data['description']}"
        f"&orderCode={data['orderCode']}"
        f"&returnUrl={data['returnUrl']}"
    )

    return hmac.new(
        PAYOS_CHECKSUM_KEY.encode(),
        raw_data.encode(),
        hashlib.sha256
    ).hexdigest()


@app.post("/create-payment")
def create_payment(req: CreatePaymentRequest):

    payload = {
        "orderCode": req.orderCode,
        "amount": req.amount,
        "description": str(req.orderCode)[:9],
        "cancelUrl": "https://marketcast.bubbleapps.io/version-test/cancel_transaction",
        "returnUrl": "https://marketcast.bubbleapps.io/version-test/payment_success"
    }

    payload["signature"] = create_signature(payload)

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    response = requests.post(PAYOS_URL, json=payload, headers=headers)
    return response.json()


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