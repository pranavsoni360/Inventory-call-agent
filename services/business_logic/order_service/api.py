from fastapi import FastAPI
from pydantic import BaseModel
from shared.database.mongo_client import db

app = FastAPI()

class Order(BaseModel):
    customer_id: str
    item: str
    quantity: int

@app.post("/order/update")
def update_order(order: Order):
    db.orders.insert_one(order.dict())
    return {"status": "saved"}
