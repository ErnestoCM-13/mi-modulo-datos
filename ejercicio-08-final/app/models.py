from pydantic import BaseModel

class TransactionIn(BaseModel):
    transaction_id: str
    timestamp: str
    user_id: int
    merchant_id: int
    amount: float
    category: str
    country_code: str
    status: str
