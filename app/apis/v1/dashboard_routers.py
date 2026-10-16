from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from app.apis.responses import envelope
from app.apis.v1.prediction_routers import prediction_payload
from app.dependencies.security import get_request_user
from app.models.model_registry import ModelRegistry
from app.models.users import User
from app.prediction.contracts import CURRENT_SCREENING_MODEL_KEY, LIFETIME_RISK_MODEL_KEY
from app.repositories.health_repository import HealthRepository
from app.services import challenge_v2
from app.services.challenges import ChallengeService
from app.services.engagement import EngagementService
from app.services.health_diagnosis import visible_predictions

dashboard_router = APIRouter(tags=["Dashboard and guidance"])

DASHBOARD_DISCLAIMER = "위험 범주와 챌린지 수행률은 진단, 질병의 호전 또는 치료 효과를 의미하지 않습니다."


@dashboard_router.get("/dashboard/summary")
async def dashboard_summary(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    repo = HealthRepository()
    # The home card is specifically the current-screening ("오늘이") result.
    # A newer future-incidence result must not replace or hide that card.
    prediction = await repo.latest_prediction_for_model_key(user.id, CURRENT_SCREENING_MODEL_KEY)
    if prediction is not None and not await visible_predictions([prediction], user.id):
        prediction = None
    cycle = await repo.active_cycle(user.id)
    follow_up = await repo.open_follow_up(user.id)
    cycle_data = await ChallengeService().cycle_payload(cycle, user.id) if cycle is not None else None
    risk_card = prediction_payload(prediction) if prediction is not None else None
    return envelope(
        {
            "risk_cards": [] if risk_card is None else [risk_card],
            "daily_challenge_v2": await challenge_v2.dashboard_snapshot(user),
            "current_cycle": cycle_data,
            "next_action": None
            if follow_up is None
            else {
                "action_id": follow_up.id,
                "type": follow_up.action_type,
                "reason_code": follow_up.reason_code,
                "priority": follow_up.priority,
                "message": "생활습관 챌린지보다 의료기관의 확인을 먼저 권합니다.",
            },
            "risk_change": None,
            "risk_change_notice": "검증 전 점수를 개선율이나 치료 효과로 비교하지 않습니다.",
            "disclaimer": DASHBOARD_DISCLAIMER,
        }
    )


@dashboard_router.get("/dashboard/challenge-progress")
async def challenge_progress(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    repo = HealthRepository()
    v2_progress = await challenge_v2.progress_summary(user)
    cycle = await repo.active_cycle(user.id)
    today = date.today()
    shared_groups = (await EngagementService().list_shared_groups(user))["items"]
    shared_progress = []
    for group in shared_groups:
        active_members = [member for member in group["members"] if member["status"] == "active"]
        period_end = min(today, group["end_date"])
        elapsed_days = max(0, (period_end - group["start_date"]).days + 1)
        planned = elapsed_days * len(active_members)
        completed = sum(member["completed_days"] for member in active_members)
        shared_progress.append(
            {
                "group_id": group["group_id"],
                "title": group["title"],
                "common_goal": group["common_goal"],
                "completed": completed,
                "planned_to_date": planned,
                "completion_rate": round(completed / planned * 100, 1) if planned else 0.0,
            }
        )
    shared_completed = sum(group["completed"] for group in shared_progress)
    shared_planned = sum(group["planned_to_date"] for group in shared_progress)
    shared_goals = {
        "completed": shared_completed,
        "planned_to_date": shared_planned,
        "completion_rate": round(shared_completed / shared_planned * 100, 1) if shared_planned else 0.0,
        "groups": shared_progress,
    }
    if cycle is None:
        return envelope(
            {
                "cycle": None,
                "challenge_v2": v2_progress,
                "recent_7_days": {"completed": 0, "planned": 0, "completion_rate": 0.0},
                "four_weeks": None,
                "shared_goals": shared_goals,
                "notice": "수행률은 질병의 호전이나 치료 효과를 의미하지 않습니다.",
            }
        )
    logs = await repo.logs_for_cycle(cycle.id, user.id)
    user_challenges = await repo.list_user_challenges(cycle.id, user.id)
    recent_start = max(cycle.start_date, today - timedelta(days=6))
    recent_logs = [item for item in logs if recent_start <= item.log_date <= today]
    recent_days = max(0, (min(today, cycle.end_date) - recent_start).days + 1)
    recent_planned = recent_days * len(user_challenges)
    recent_completed = sum(1 for item in recent_logs if item.is_completed)
    total_days = max(0, min((today - cycle.start_date).days + 1, 28))
    total_planned = total_days * len(user_challenges)
    return envelope(
        {
            "cycle_id": cycle.id,
            "challenge_v2": v2_progress,
            "recent_7_days": {
                "completed": recent_completed,
                "planned": recent_planned,
                "completion_rate": round(recent_completed / recent_planned * 100, 1) if recent_planned else 0.0,
            },
            "four_weeks": {
                "completed": sum(1 for item in logs if item.is_completed),
                "planned_to_date": total_planned,
                "completion_rate": round(sum(1 for item in logs if item.is_completed) / total_planned * 100, 1)
                if total_planned
                else 0.0,
            },
            "shared_goals": shared_goals,
            "notice": "수행률은 질병의 호전이나 치료 효과를 의미하지 않습니다.",
        }
    )


@dashboard_router.get("/dashboard/lifetime-risk")
async def lifetime_risk_summary(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    """API-LIFE-005: 연령별 당뇨 위험 전망 대시보드 카드.

    diabetes_lifetime_risk에 대해 ModelRegistry.is_active=True인 승인 모델이
    없는 동안에는(현재 항상 이 상태) available=False와 안내 문구만 반환한다 —
    준비되지 않은 기능을 카드 형태로 노출해 혼동을 주지 않기 위함이다.
    """
    active_model = await ModelRegistry.active_for(LIFETIME_RISK_MODEL_KEY)
    if active_model is None:
        return envelope(
            {
                "available": False,
                "status": "not_ready",
                "card": None,
                "message": "연령별 당뇨 위험 전망 기능은 아직 준비 중입니다.",
            }
        )
    repo = HealthRepository()
    prediction = await repo.latest_prediction_for_model_key(user.id, LIFETIME_RISK_MODEL_KEY)
    if prediction is not None and not await visible_predictions([prediction], user.id):
        prediction = None
    if prediction is None or prediction.risk_curve_status != "available":
        return envelope(
            {
                "available": False,
                "status": "not_applicable" if prediction is None else prediction.risk_curve_status,
                "card": None,
                "message": "아직 생성된 연령별 위험 전망이 없습니다.",
            }
        )
    points = await repo.risk_curve_points(prediction.id)
    return envelope(
        {
            "available": True,
            "status": prediction.risk_curve_status,
            "card": {
                "prediction_id": prediction.id,
                "predicted_at": prediction.predicted_at,
                "point_count": len(points),
                "detail_url": f"/api/v1/predictions/{prediction.id}/risk-curve",
            },
            "disclaimer": "이 전망은 통계적 위험 추정치이며 개인의 확정된 미래를 의미하지 않습니다.",
        }
    )


@dashboard_router.get("/follow-up-actions")
async def list_follow_up_actions(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    repo = HealthRepository()
    items = await repo.list_follow_ups(user.id)
    blocking_ids = {item.id for item in await repo.open_follow_ups(user.id)}
    return envelope(
        {
            "items": [
                {
                    "action_id": item.id,
                    "trigger_source": item.trigger_source,
                    "trigger_entity_id": item.trigger_entity_id,
                    "action_type": item.action_type,
                    "reason_code": item.reason_code,
                    "priority": item.priority,
                    "acknowledged_at": item.acknowledged_at,
                    "blocking": item.id in blocking_ids,
                    "created_at": item.created_at,
                    "message": "검사·치료·복약은 담당 의료진의 지침을 따라주세요.",
                }
                for item in items
            ]
        }
    )


@dashboard_router.patch("/follow-up-actions/{action_id}/acknowledge")
async def acknowledge_follow_up(
    action_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await ChallengeService().acknowledge_follow_up(user, action_id)
    return envelope({"action_id": item.id, "acknowledged_at": item.acknowledged_at})


@dashboard_router.get("/recommendations")
async def reviewed_recommendations() -> dict[str, object]:
    items = await ChallengeService().ensure_catalog()
    return envelope(
        {
            "type": "reviewed_general_health_templates",
            "personalized_medical_advice": False,
            "items": [
                {
                    "title": item.title,
                    "description": item.description,
                    "safety": item.safety_copy,
                    "source": {"title": item.source_title, "url": item.source_url},
                }
                for item in items
            ],
            "medication_notice": "복용 중인 약을 임의로 시작·중단하거나 용량을 변경하지 마세요.",
        }
    )
