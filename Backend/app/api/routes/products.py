from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.models.product import Product, Batch
from app.schemas.domain import ProductResponse, BatchResponse
from datetime import date

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=List[ProductResponse])
def list_products(
    storage: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product)
    if storage:
        query = query.filter(Product.storage_requirements == storage)
    return query.all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod


@router.get("/{product_id}/batches", response_model=List[BatchResponse])
def list_product_batches(product_id: str, db: Session = Depends(get_db)):
    batches = db.query(Batch).filter(Batch.product_id == product_id).order_by(Batch.expiry_date.asc()).all()
    today = date.today()
    result = []
    for b in batches:
        b_dict = BatchResponse.from_orm(b)
        b_dict.days_to_expiry = (b.expiry_date - today).days
        result.append(b_dict)
    return result

