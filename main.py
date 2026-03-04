import os
import hmac
import hashlib
import requests
import json
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ===== ENV =====
PAYOS_CLIENT_ID = os.getenv("PAYOS_CLIENT_ID")
PAYOS_API_KEY = os.getenv("PAYOS_API_KEY")
PAYOS_CHECKSUM_KEY = os.getenv("PAYOS_CHECKSUM_KEY")
BUBBLE_BASE_URL = os.getenv("BUBBLE_BASE_URL")
BUBBLE_API_KEY = os.getenv("BUBBLE_API_KEY")

PAYOS_URL = "https://api-merchant.payos.vn/v2/payment-requests"


def sort_obj_by_key(obj: dict) -> dict:
    return dict(sorted(obj.items()))

def sort_obj_by_key(obj: dict) -> dict:
    return dict(sorted(obj.items()))


def convert_obj_to_query_str(obj: dict) -> str:
    query_string = []

    for key, value in obj.items():

        if isinstance(value, (int, float, bool)):
            value_str = str(value)

        elif value in [None, "null", "NULL"]:
            value_str = ""

        elif isinstance(value, list):
            value_str = json.dumps(
                [sort_obj_by_key(item) for item in value],
                separators=(",", ":")
            ).replace("None", "null")

        else:
            value_str = str(value)

        query_string.append(f"{key}={value_str}")

    return "&".join(query_string)


def verify_webhook_signature(data: dict, received_signature: str) -> bool:

    sorted_data = sort_obj_by_key(data)
    data_query_str = convert_obj_to_query_str(sorted_data)

    calculated_signature = hmac.new(
        PAYOS_CHECKSUM_KEY.encode("utf-8"),
        msg=data_query_str.encode("utf-8"),
        digestmod=hashlib.sha256
    ).hexdigest()

    return calculated_signature == received_signature

def get_transaction_from_bubble(order_code: int):

    url = f"{BUBBLE_BASE_URL}/transaction?constraints=[{{\"key\":\"orderCode\",\"constraint_type\":\"equals\",\"value\":{order_code}}}]"

    headers = {
        "Authorization": f"Bearer {BUBBLE_API_KEY}"
    }

    res = requests.get(url, headers=headers)
    data = res.json()

    results = data.get("response", {}).get("results", [])

    if not results:
        return None

    return results[0]

def update_transaction_success(transaction_id: str):

    url = f"{BUBBLE_BASE_URL}/transaction/{transaction_id}"

    headers = {
        "Authorization": f"Bearer {BUBBLE_API_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "status": "SUCCESS",
        "processed": True
    }

    return requests.patch(url, json=body, headers=headers)

# ===== REQUEST MODEL =====
class CreatePaymentRequest(BaseModel):
    amount: int = Field(ge=1000)
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

@app.post("/webhook/payos")
async def payos_webhook(request: Request):

    body = await request.json()

    data = body.get("data")
    received_signature = body.get("signature")

    if not data or not received_signature:
        raise HTTPException(status_code=400, detail="Invalid payload")

    # 1️⃣ Verify chữ ký
    if not verify_webhook_signature(data, received_signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # 2️⃣ Chỉ xử lý nếu thanh toán thành công
    if not (body.get("success") and data.get("code") == "00"):
        return {"status": "ignored"}

    order_code = data["orderCode"]
    amount_paid = data["amount"]

    # 3️⃣ Lấy transaction từ Bubble
    transaction = get_transaction_from_bubble(order_code)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # 4️⃣ Kiểm tra amount khớp
    if transaction["amount"] != amount_paid:
        raise HTTPException(status_code=400, detail="Amount mismatch")

    # 5️⃣ Chống xử lý 2 lần
    if transaction.get("processed"):
        return {"status": "already_processed"}

    # 6️⃣ Update SUCCESS
    update_transaction_success(transaction["_id"])

    print(f"Thanh toán thành công cho order {order_code}")

    return {"status": "success"}

# ===== RUN =====
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)