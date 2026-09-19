"""Dashboard: métricas en tiempo real del negocio."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_or_create_settings
from app.models import Loan, Product, ProductStockLocation, User
from app.schemas import DashboardOut

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tenant_id = user.tenant_id
    threshold = get_or_create_settings(db).low_stock_threshold or 5

    total_products = (
        db.query(func.count(Product.id)).filter(Product.tenant_id == tenant_id).scalar() or 0
    )
    total_units = (
        db.query(func.coalesce(func.sum(Product.stock), 0))
        .filter(Product.tenant_id == tenant_id)
        .scalar()
    )
    capital_invested = db.query(
        func.coalesce(func.sum(Product.purchase_price * Product.stock), 0)
    ).filter(Product.tenant_id == tenant_id).scalar()
    potential_income = (
        db.query(func.coalesce(func.sum(Product.sale_price * Product.stock), 0))
        .filter(Product.tenant_id == tenant_id)
        .scalar()
    )

    active_loans = (
        db.query(func.count(Loan.id))
        .filter(Loan.tenant_id == tenant_id, Loan.quantity > Loan.returned_qty)
        .scalar()
        or 0
    )
    overdue_loans = (
        db.query(func.count(Loan.id))
        .filter(
            Loan.tenant_id == tenant_id,
            Loan.quantity > Loan.returned_qty,
            Loan.due_date < date.today(),
        )
        .scalar()
        or 0
    )
    low_stock_products = (
        db.query(func.count(Product.id))
        .filter(Product.tenant_id == tenant_id, Product.stock <= threshold)
        .scalar()
        or 0
    )

    low_stock_list = (
        db.query(Product)
        .filter(Product.tenant_id == tenant_id, Product.stock <= threshold)
        .order_by(Product.stock)
        .limit(10)
        .all()
    )

    overdue_loans_list = (
        db.query(Loan)
        .filter(
            Loan.tenant_id == tenant_id,
            Loan.quantity > Loan.returned_qty,
            Loan.due_date < date.today(),
        )
        .order_by(Loan.due_date)
        .limit(10)
        .all()
    )

    top_products = (
        db.query(
            Product.name,
            Product.stock,
            func.coalesce(Product.sale_price * Product.stock, 0).label("value"),
        )
        .filter(Product.tenant_id == tenant_id)
        .order_by(func.coalesce(Product.sale_price * Product.stock, 0).desc())
        .limit(5)
        .all()
    )

    # Últimos préstamos registrados (actividad reciente)
    recent_loans = (
        db.query(Loan)
        .filter(Loan.tenant_id == tenant_id)
        .order_by(Loan.loan_date.desc())
        .limit(6)
        .all()
    )

    # Préstamos creados por día en los últimos 7 días (para la gráfica de actividad)
    loans_last_7_days = []
    for i in range(6, -1, -1):
        day = date.today() - timedelta(days=i)
        count = (
            db.query(func.count(Loan.id))
            .filter(
                Loan.tenant_id == tenant_id,
                func.date(Loan.loan_date) == day,
            )
            .scalar()
            or 0
        )
        loans_last_7_days.append({"day": day.strftime("%d/%m"), "prestamos": count})

    # Stock total por ubicación (feature stock por ubicación)
    stock_rows = (
        db.query(
            ProductStockLocation.location,
            func.coalesce(func.sum(ProductStockLocation.quantity), 0),
        )
        .filter(ProductStockLocation.tenant_id == tenant_id)
        .group_by(ProductStockLocation.location)
        .order_by(func.coalesce(func.sum(ProductStockLocation.quantity), 0).desc())
        .all()
    )
    stock_by_location = [{"location": r[0], "quantity": int(r[1])} for r in stock_rows]

    return DashboardOut(
        total_products=total_products,
        total_units=total_units or 0,
        active_loans=active_loans,
        overdue_loans=overdue_loans,
        low_stock_products=low_stock_products,
        capital_invested=float(capital_invested or 0),
        potential_income=float(potential_income or 0),
        low_stock_list=[p for p in low_stock_list],
        overdue_loans_list=overdue_loans_list,
        top_products=[{"name": r[0], "stock": r[1], "value": float(r[2])} for r in top_products],
        recent_loans=recent_loans,
        loans_last_7_days=loans_last_7_days,
        stock_by_location=stock_by_location,
    )
