from fastapi import APIRouter

from app.api.routes import auth, dashboard, finance, integrations, intelligence, marketplace, payments, system


api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(finance.router)
api_router.include_router(payments.router)
api_router.include_router(integrations.router)
api_router.include_router(marketplace.router)
api_router.include_router(intelligence.router)
api_router.include_router(system.router)
