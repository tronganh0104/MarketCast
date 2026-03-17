from fastapi import APIRouter
from typing import List, Optional 
from pydantic import BaseModel, Field

router = APIRouter()

class Order(BaseModel):
    id: str
    price: int = Field(ge=1, le=99)
    remain: int = Field(gt=0)

class ATORequest(BaseModel):
    market_id: str
    orderbook_yes: List[Order]
    orderbook_no: List[Order]

class ATOResponse(BaseModel):
    clearing_price_yes: Optional[int]
    clearing_price_no: Optional[int]

def calculate_clearing_price(orderbook_yes, orderbook_no) -> int:
    yes_volume = [0] * 101
    no_volume = [0] * 101

    for o in orderbook_yes:
        yes_volume[o.price] += o.remain

    for o in orderbook_no:
        no_volume[o.price] += o.remain
    
    demand_yes = [0] * 101
    demand_no = [0] * 101
    running = 0
    for p in range(99, 0, -1):
        running += yes_volume[p]
        demand_yes[p] = running

    running = 0
    for p in range(99, 0, -1):
        running += no_volume[p]
        demand_no[p] = running
    
    best_p = None
    best_volume = 0
    for p in range(99, 0, -1):
        demand_y = demand_yes[p]
        demand_n = demand_no[100 - p]
        matched = min(demand_y, demand_n)
        if matched > best_volume:
            best_volume = matched
            best_p = p

    if best_volume == 0:
        return None

    return best_p

@router.post("/clear", response_model=ATOResponse)
def clear_ato(data: ATORequest):
    p = calculate_clearing_price(data.orderbook_yes, data.orderbook_no)

    if p is None:
        return {
            "clearing_price_yes": None,
            "clearing_price_no": None
        }

    return {
        "clearing_price_yes": p,
        "clearing_price_no": 100 - p
    }