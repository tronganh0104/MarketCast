from fastapi import FastAPI
from routers import payment

app = FastAPI()

@app.get("/")
def root():
    return {"status": "API running"}


app.include_router(payment.router)