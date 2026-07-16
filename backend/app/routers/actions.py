"""
Actions router — aggregates plans, impact, funnel, reports, and portfolio sub-routers.
Public paths remain under /actions/*.
"""

from fastapi import APIRouter

from app.routers import (
    actions_plans,
    actions_impact,
    actions_funnel,
    actions_reports,
    actions_portfolio,
)

router = APIRouter(prefix="/actions", tags=["actions"])
router.include_router(actions_plans.router)
router.include_router(actions_impact.router)
router.include_router(actions_funnel.router)
router.include_router(actions_reports.router)
router.include_router(actions_portfolio.router)
