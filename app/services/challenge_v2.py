"""Additive daily pilot. Never rewrites legacy cycles, logs or risk estimates."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.challenge_v2 import V2Preferences, V2SessionInput
from app.models.challenge_v2 import (
    ChallengeV2Assignment as Assignment,
)
from app.models.challenge_v2 import (
    ChallengeV2Day as Day,
)
from app.models.challenge_v2 import (
    ChallengeV2Enrollment as Enrollment,
)
from app.models.challenge_v2 import (
    ChallengeV2Evidence as Evidence,
)
from app.models.challenge_v2 import (
    ChallengeV2Reward as Reward,
)
from app.models.challenge_v2 import (
    ChallengeV2Session as Session,
)
from app.models.forest import ForestInventory
from app.models.health import Consent
from app.models.users import User
from app.repositories.challenge_v2_repository import ChallengeV2Repository
from app.repositories.forest_repository import ForestRepository
from app.repositories.game_repository import GameRepository
from app.repositories.health_repository import HealthRepository
from app.services.challenge_v2_catalog import (
    NOTICE,
    candidates_for,
    eligible,
    exceptions_for,
    mix_valid,
    select_plan,
)
from app.services.challenge_wallet import credit_daily_bonus, v2_receipt_key
from app.services.forest import REWARD_ITEMS
from app.services.forest_wallet import ForestWalletService

KST = ZoneInfo("Asia/Seoul")
DOMAIN_MIX_POLICY_VERSION = "2.2-domain-mix"


def now_kst():
    return datetime.now(UTC).astimezone(KST)


def enabled():
    return config.DEMO_MODE or (config.CHALLENGE_V2_ENABLED and config.CHALLENGE_V2_CONTENT_APPROVED)


async def review_available():
    return await User.filter(id__in=config.CHALLENGE_V2_REVIEWER_IDS, is_admin=True, is_active=True).exists()


def require_enabled():
    if not enabled():
        raise HTTPException(503, "챌린지 V2는 콘텐츠·개인정보 운영 승인 전 비활성 상태입니다.")


async def safety(user_id):
    repo = HealthRepository()
    consent = await Consent.filter(user_id=user_id, consent_item="health_data").order_by("-id").first()
    if not consent or not consent.is_agreed or consent.withdrawn_at:
        raise HTTPException(403, "건강정보 동의가 필요합니다.")
    state = await repo.latest_eligibility(user_id)
    if not state or not state.service_eligible or state.has_diabetes_diagnosis or state.has_urgent_warning_sign:
        raise HTTPException(403, "이용 가능 확인과 의료 안내를 먼저 확인해 주세요. 챌린지를 배정할 수 없습니다.")
    if await repo.open_follow_up(user_id):
        raise HTTPException(403, "의료기관 안내를 먼저 확인해 주세요.")
    return state


async def locked_user(user_id):
    require_enabled()
    user = await User.filter(id=user_id, is_active=True).select_for_update().first()
    if not user:
        raise HTTPException(403, "사용할 수 없는 계정입니다.")
    await safety(user_id)
    return user


async def active_assignments(day_id):
    return await ChallengeV2Repository().assignments(day_id)


async def preferences(user_id):
    enrollment = await Enrollment.get_or_none(user_id=user_id)
    if not enrollment:
        raise HTTPException(409, "챌린지 설정을 먼저 저장해 주세요.")
    return V2Preferences(**enrollment.preferences)


async def recent_goals(user_id, today):
    ids = await Day.filter(
        user_id=user_id, assigned_date__gte=today - timedelta(days=6), assigned_date__lt=today
    ).values_list("id", flat=True)
    return await Assignment.filter(day_id__in=ids).exclude(status="replaced").values_list("goal", flat=True)


async def replace_day_plan(day, pref, user_id):
    """Publish a fresh active trio without deleting the day's audit history."""
    plan = select_plan(
        pref,
        day.assigned_date.toordinal(),
        await recent_goals(user_id, day.assigned_date),
        await review_available(),
    )
    if len(plan["items"]) != 3 or {x["domain"] for x in plan["items"]} != {"diet", "activity", "routine"}:
        return False
    active = await active_assignments(day.id)
    revisions = {item.slot: item.revision for item in active}
    for item in active:
        item.status = "replaced"
        await item.save()
    for slot, goal in enumerate(plan["items"], 1):
        await Assignment.create(
            day_id=day.id,
            slot=slot,
            revision=revisions.get(slot, 0) + 1,
            replacement_reason="preference",
            goal=goal,
        )
    snapshot = dict(day.eligibility_snapshot or {})
    snapshot["preferences"] = pref.model_dump()
    snapshot["substitutions"] = plan["substitutions"]
    day.eligibility_snapshot = snapshot
    day.exception_reasons = plan["proof_mix_exception_reason"]
    day.policy_version = DOMAIN_MIX_POLICY_VERSION
    await day.save()
    return True


async def enroll(user, pref):
    if not pref.transition_consent:
        raise HTTPException(422, "기존 기록을 유지하는 V2 전환에 동의해 주세요.")
    async with in_transaction():
        await locked_user(user.id)
        existing = await Enrollment.get_or_none(user_id=user.id)
        cycle = await HealthRepository().active_cycle(user.id)
        starts_on = existing.starts_on if existing else now_kst().date() + timedelta(days=bool(cycle))
        await Enrollment.update_or_create(
            user_id=user.id,
            defaults={
                "mode": pref.mode,
                "starts_on": starts_on,
                "preferences": pref.model_dump(),
            },
        )
        current_day = await Day.get_or_none(user_id=user.id, assigned_date=now_kst().date())
        if current_day and starts_on <= now_kst().date():
            # Defer publication until /today is read, so the preferences write
            # remains compatible with in-flight evidence and audit operations.
            current_day.policy_version = "2.1-preference-pending"
            await current_day.save(update_fields=["policy_version"])
        # Withdrawal destroys private photos immediately; goal/session history stays intact.
        if not pref.photo_consent:
            await Evidence.filter(user_id=user.id).update(content=None)
            await Evidence.filter(user_id=user.id, verification_status="pending").update(
                verification_status="inconclusive"
            )
            day_ids = await Day.filter(user_id=user.id).values_list("id", flat=True)
            await (
                Assignment.filter(day_id__in=day_ids, verification_status="pending")
                .exclude(status__in=["completed", "replaced"])
                .update(verification_status="inconclusive")
            )
        return {
            "starts_on": starts_on.isoformat(),
            "preferences": pref.model_dump(),
            "notice": "기존 기록은 유지됩니다. 새 선호는 다음 배정에 적용되며 안전 제한은 즉시 적용됩니다.",
        }


async def today(user, create=False):
    require_enabled()
    async with in_transaction():
        await locked_user(user.id)
        enrollment = await Enrollment.get_or_none(user_id=user.id)
        if not enrollment:
            return {"enrolled": False, "items": [], "notice": NOTICE}
        day = await Day.get_or_none(user_id=user.id, assigned_date=now_kst().date())
        if not day and create and enrollment.starts_on <= now_kst().date():
            pref = V2Preferences(**enrollment.preferences)
            state = await safety(user.id)
            plan = select_plan(
                pref,
                now_kst().date().toordinal(),
                await recent_goals(user.id, now_kst().date()),
                await review_available(),
            )
            cycle = await HealthRepository().active_cycle(user.id)
            day = await Day.create(
                user_id=user.id,
                assigned_date=now_kst().date(),
                cycle_id=cycle.id if cycle else None,
                eligibility_snapshot={
                    "eligibility_id": state.id,
                    "preferences": pref.model_dump(),
                    "substitutions": plan["substitutions"],
                },
                exception_reasons=plan["proof_mix_exception_reason"],
                policy_version=DOMAIN_MIX_POLICY_VERSION,
            )
            for slot, goal in enumerate(plan["items"], 1):
                await Assignment.create(day_id=day.id, slot=slot, goal=goal)
        if day:
            # Plans created by the older policy can contain two cards from one
            # domain. Replace only their active view; prior assignments,
            # sessions and rewards remain immutable history.
            active = await active_assignments(day.id)
            domains = {item.goal.get("domain") for item in active}
            if (
                day.policy_version != DOMAIN_MIX_POLICY_VERSION
                or len(active) != 3
                or domains != {"diet", "activity", "routine"}
            ):
                pref = V2Preferences(**enrollment.preferences)
                await replace_day_plan(day, pref, user.id)
        result = await day_payload(day) if day else {"items": [], "completed": 0}
        return {
            **result,
            "enrolled": True,
            "starts_on": enrollment.starts_on.isoformat(),
            "preferences": enrollment.preferences,
            "notice": NOTICE,
        }


async def owned_assignment(user_id, assignment_id, writable=True):
    item = await Assignment.get_or_none(id=assignment_id)
    day = await Day.get_or_none(id=item.day_id, user_id=user_id) if item else None
    if not day:
        raise HTTPException(404, "배정을 찾을 수 없습니다.")
    if writable and (day.assigned_date != now_kst().date() or item.status == "replaced"):
        raise HTTPException(409, "현재 배정일의 활성 카드만 기록할 수 있습니다.")
    return item, day


def validate_session(goal, index, request, assigned_date):
    if not 1 <= index <= goal["target_sessions"]:
        raise HTTPException(422, "목표 회차 범위를 벗어났습니다.")
    if request.performed_at.tzinfo is None:
        raise HTTPException(422, "행동 시각에 시간대가 필요합니다.")
    performed = request.performed_at.astimezone(KST)
    if performed.date() != assigned_date or performed > now_kst():
        raise HTTPException(422, "배정일 안의 실제 수행 시각을 기록해 주세요.")
    if goal["goal_unit"] == "minute" and (request.quantity is None or request.quantity < goal["per_session_quantity"]):
        raise HTTPException(422, "회차별 최소 시간을 충족해야 합니다. 한 회차를 여러 회차로 세지 않습니다.")
    validate_content(goal, index, request, performed)


def validate_content(goal, index, request, performed):  # noqa: C901
    family = goal["family_id"]
    if family in {"D01", "D02", "D03"} and not request.note.strip():
        raise HTTPException(422, "회차별 내용 기록이 필요합니다.")
    if (
        family == "D03"
        and goal["difficulty"] == "H"
        and index == goal["target_sessions"]
        and not request.improvement.strip()
    ):
        raise HTTPException(422, "다음 날 개선점을 한 줄 적어 주세요.")
    if family == "H02":
        if goal.get("water_mission_version") == "cup-v1":
            if goal.get("water_goal_status") != "confirmed" or not goal.get("water_goal_cups"):
                raise HTTPException(422, "개인 음료 목표가 확인된 경우에만 물컵 체크를 완료할 수 있습니다.")
            if request.quantity is None or request.quantity < goal["water_goal_cups"]:
                raise HTTPException(422, "확인한 200mL 컵 개수를 모두 체크해 주세요.")
            expected_ml = goal["water_goal_cups"] * goal.get("water_cup_ml", 200)
            if request.intake_ml is None or request.intake_ml < expected_ml:
                raise HTTPException(422, "확인한 컵 개수에 맞는 섭취량을 함께 기록해 주세요.")
            return
        if request.intake_ml is None:
            raise HTTPException(422, "구간별 실제 양을 기록해 주세요. 0mL도 가능합니다.")
        start, end = [(0, 12), (12, 18), (18, 24)][index - 1]
        if not start <= performed.hour < end:
            raise HTTPException(422, "회차는 오전·오후·저녁 구간과 일치해야 합니다.")
    if family == "D02":
        if request.serving_amount is None or request.serving_unit is None or request.sugar_g is None:
            raise HTTPException(422, "기준량·단위·당류를 입력해 주세요. 0g도 유효합니다.")
        if goal["difficulty"] != "E" and (request.carbohydrate_g is None or not request.product_category.strip()):
            raise HTTPException(422, "총탄수화물과 같은 제품 종류를 기록해 주세요.")
        if goal["difficulty"] == "H" and index == 2 and not request.improvement.strip():
            raise HTTPException(422, "100g 또는 100mL 동일 기준량 비교를 기록해 주세요.")


async def check_overlap(item, day, index, request):
    if item.goal["domain"] != "activity":
        return
    ids = [x.id for x in await active_assignments(day.id) if x.goal["domain"] == "activity"]
    end = request.performed_at
    start = end - timedelta(minutes=request.quantity or 0)
    for previous in await Session.filter(assignment_id__in=ids):
        if previous.assignment_id == item.id and previous.session_index == index:
            continue
        old_end = previous.performed_at
        old_start = old_end - timedelta(minutes=previous.values.get("quantity") or 0)
        if start < old_end and old_start < end:
            raise HTTPException(409, "걷기·좌식중단 회차의 시간이 겹칩니다. 같은 활동을 이중 적립할 수 없습니다.")


async def record_session(user, assignment_id, index, request: V2SessionInput):
    async with in_transaction():
        await locked_user(user.id)
        item, day = await owned_assignment(user.id, assignment_id)
        old = await Session.get_or_none(assignment_id=item.id, session_index=index)
        values = request.model_dump(mode="json")
        if old and old.values == values:
            return await day_payload(day)
        if old and item.goal["proof_type"] == "T1" and await Evidence.filter(assignment_id=item.id).exists():
            raise HTTPException(409, "사진에 연결된 기록은 변경할 수 없습니다. 대체 카드로 다시 시작해 주세요.")
        if (
            item.status == "completed"
            or await Evidence.filter(assignment_id=item.id, verification_status="passed").exists()
        ):
            raise HTTPException(409, "확인된 기록은 변경할 수 없습니다.")
        if not eligible(item.goal, await preferences(user.id), await review_available()):
            raise HTTPException(409, "현재 안전·촬영 조건과 맞지 않습니다. 안전 대체 카드를 선택해 주세요.")
        validate_session(item.goal, index, request, day.assigned_date)
        duplicate = Session.filter(assignment_id=item.id, performed_at=request.performed_at).exclude(
            session_index=index
        )
        if await duplicate.exists():
            raise HTTPException(409, "같은 시각의 회차를 두 번 셀 수 없습니다.")
        await check_overlap(item, day, index, request)
        if item.goal["family_id"] == "D02" and index == 2:
            first = await Session.get_or_none(assignment_id=item.id, session_index=1)
            if (
                not first
                or first.values["product_category"] != request.product_category
                or first.values["serving_unit"] != request.serving_unit
            ):
                raise HTTPException(422, "같은 종류·단위의 첫 번째 라벨부터 기록해 주세요.")
        await Session.update_or_create(
            assignment_id=item.id,
            session_index=index,
            defaults={"performed_at": request.performed_at, "values": values},
        )
        await aggregate(item, day, user)
        return await day_payload(day)


async def issue_reward(user, day, source, amount, chest=False):
    async with in_transaction() as connection:
        await ForestRepository().avatar(user)
        # User/wallet locks serialize simultaneous session and photo-review retries.
        if await Reward.filter(source_key=source).using_db(connection).select_for_update().first():
            return
        if chest:
            transaction, granted = await credit_daily_bonus(user, day.assigned_date, using_db=connection)
        else:
            transaction, granted = await GameRepository().credit(
                user.id,
                amount,
                "challenge_v2_reward",
                source,
                await v2_receipt_key(user.id, day.id, source),
                using_db=connection,
            )
        item_code = None
        if chest:
            owned = await ForestInventory.filter(user_id=user.id).values_list("item_code", flat=True)
            item_code = next((x for x in REWARD_ITEMS if x not in owned), None)
        await Reward.create(
            user_id=user.id,
            day_id=day.id,
            source_key=source,
            carrot_amount=transaction.amount if granted else 0,
            item_code=item_code,
            using_db=connection,
        )
        if item_code:
            await ForestInventory.get_or_create(
                user_id=user.id,
                item_code=item_code,
                defaults={"acquired_source": "challenge_v2_daily"},
                using_db=connection,
            )


async def aggregate(item, day, user):
    logs = await Session.filter(assignment_id=item.id).count()
    proofs = await Evidence.filter(assignment_id=item.id)
    goal = item.goal
    records_done = logs == goal["target_sessions"]
    uploads_done = (
        sum(x.content is not None and x.deletion_due_at > now_kst() for x in proofs) == goal["required_uploads"]
    )
    item.status = "in_progress" if logs or proofs else "assigned"
    item.verification_status = "not_required"
    complete = records_done and uploads_done
    if goal["proof_type"] == "T1":
        statuses = {x.verification_status for x in proofs}
        item.verification_status = next(
            (s for s in ["needs_retry", "inconclusive", "pending"] if s in statuses),
            "passed" if uploads_done and proofs else "not_required",
        )
        complete = complete and item.verification_status == "passed"
        if records_done and proofs:
            item.status = "submitted"
    if complete:
        item.status = "completed"
    await item.save()
    if complete:
        # Stable slot key survives replacements. Photo alternatives earn identical amounts.
        await issue_reward(user, day, f"v2-slot:{day.id}:{item.slot}", 10)
    active = await active_assignments(day.id)
    if active and all(x.status == "completed" for x in active):
        await issue_reward(user, day, f"v2-day:{user.id}:{day.assigned_date}", 50, chest=True)


async def day_payload(day):
    items = []
    for item in await active_assignments(day.id):
        logs = await Session.filter(assignment_id=item.id).order_by("session_index")
        proofs = await Evidence.filter(assignment_id=item.id)
        items.append(
            {
                "id": item.id,
                "slot": item.slot,
                "revision": item.revision,
                "goal": item.goal,
                "status": item.status,
                "verification_status": item.verification_status,
                "sessions": [{"index": x.session_index, **x.values} for x in logs],
                "completed_sessions": len(logs),
                "total_quantity": sum(x.values.get("quantity") or 0 for x in logs),
                "intake_ml": sum(x.values.get("intake_ml") or 0 for x in logs),
                "evidence": [
                    {
                        "id": x.id,
                        "index": x.evidence_index,
                        "status": x.verification_status,
                        "expires_at": x.deletion_due_at.isoformat(),
                        "expired": x.content is None or x.deletion_due_at <= now_kst(),
                    }
                    for x in proofs
                ],
            }
        )
    wallet = await ForestWalletService().snapshot(await User.get(id=day.user_id))
    rewards = await Reward.filter(day_id=day.id).values("source_key", "carrot_amount", "item_code")
    return {
        "day_id": day.id,
        "date": day.assigned_date.isoformat(),
        "policy_version": day.policy_version,
        "items": items,
        "completed": sum(x["status"] == "completed" for x in items),
        "proof_mix_exception_reason": day.exception_reasons,
        "substitutions": day.eligibility_snapshot.get("substitutions", []),
        "user_id": day.user_id,
        "carrot_balance": wallet["carrot_balance"],
        "wallet_updated_at": wallet["wallet_updated_at"],
        "wallet_revision": wallet["wallet_revision"],
        "rewards": rewards,
        "chest_issued": any(x["source_key"].startswith("v2-day:") for x in rewards),
        "notice": NOTICE,
    }


async def replacement_options(user, assignment_id):
    item, day = await owned_assignment(user.id, assignment_id)
    pref = await preferences(user.id)
    active = await active_assignments(day.id)
    others = [x.goal for x in active if x.id != item.id]
    choices = candidates_for(pref, await review_available(), await recent_goals(user.id, day.assigned_date))
    return [
        x for x in choices if x["family_id"] not in {y["family_id"] for y in others} and x["code"] != item.goal["code"]
    ]


async def replace(user, assignment_id, request):
    async with in_transaction():
        await locked_user(user.id)
        item, day = await owned_assignment(user.id, assignment_id)
        if item.status == "completed":
            raise HTTPException(409, "완료된 슬롯은 바꾸지 않습니다.")
        choice = next(
            (x for x in await replacement_options(user, assignment_id) if x["code"] == request.template_code), None
        )
        if not choice:
            raise HTTPException(422, "중복 행동군 또는 안전·접근성·주간 제한에 맞지 않는 카드입니다.")
        others = [x.goal for x in await active_assignments(day.id) if x.id != item.id]
        if request.reason == "preference" and not mix_valid([*others, choice]):
            raise HTTPException(422, "선호 변경은 인증 유형과 난이도 각 1개를 유지해야 합니다.")
        if request.reason != "preference" and "EMH".index(choice["difficulty"]) > "EMH".index(item.goal["difficulty"]):
            raise HTTPException(422, "안전·접근성 대체로 난이도를 올릴 수 없습니다.")
        item.status = "replaced"
        await item.save()
        await Assignment.create(
            day_id=day.id, slot=item.slot, revision=item.revision + 1, replacement_reason=request.reason, goal=choice
        )
        day.exception_reasons = list(
            dict.fromkeys(
                day.exception_reasons
                + [f"replacement_{request.reason}"]
                + exceptions_for([*others, choice], await preferences(user.id), await review_available())
            )
        )
        await day.save()
        return await day_payload(day)


async def history(user, day_date: date):
    require_enabled()
    day = await Day.get_or_none(user_id=user.id, assigned_date=day_date)
    if not day:
        raise HTTPException(404, "해당 날짜의 배정이 없습니다.")
    return await day_payload(day)


async def dashboard_snapshot(user):
    if not enabled():
        return None
    try:
        return await today(user)
    except HTTPException as exc:
        return {"blocked": True, "notice": exc.detail, "items": []}


async def progress_summary(user):
    if not enabled() or not await Enrollment.filter(user_id=user.id).exists():
        return None
    current = now_kst().date()
    result = {}
    for label, span in [("recent_7_days", 7), ("four_weeks", 28)]:
        ids = await Day.filter(
            user_id=user.id, assigned_date__gte=current - timedelta(days=span - 1), assigned_date__lte=current
        ).values_list("id", flat=True)
        query = Assignment.filter(day_id__in=ids).exclude(status="replaced")
        result[label] = {
            "completed": await query.filter(status="completed").count(),
            "planned": await query.count(),
            "pending_review": await query.filter(verification_status="pending").count(),
        }
    return {**result, "notice": "회차·제출·확인 기록입니다. 위험 점수 감소나 치료 효과로 해석하지 않습니다."}
