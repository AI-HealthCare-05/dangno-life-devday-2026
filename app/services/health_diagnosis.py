"""Editable daily diagnosis assertions, independent of immutable eligibility answers."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from tortoise.transactions import in_transaction

from app.models.health import EligibilityCheck, HealthCheckup, HealthDiagnosisRecord

SERVICE_TIMEZONE = ZoneInfo("Asia/Seoul")
DIAGNOSIS_BLOCK_CODE = "DIABETES_DIAGNOSIS_RECORDED"


def service_today() -> date:
    return datetime.now(SERVICE_TIMEZONE).date()


def diagnosis_record_payload(item) -> dict[str, object]:
    day = getattr(item, "record_date", None) or item.created_at.astimezone(SERVICE_TIMEZONE).date()
    eligibility_id = getattr(item, "eligibility_check_id", item.id)
    return {
        "record_id": f"diagnosis-{item.id}", "diagnosis_record_id": item.id,
        "record_type": "diabetes_diagnosis", "record_date": day.isoformat(),
        "label": "당뇨병 진단", "source": "self_report",
        "source_checkup_id": getattr(item, "source_checkup_id", None),
        "eligibility_check_id": eligibility_id,
        "created_at": item.created_at, "updated_at": getattr(item, "updated_at", item.created_at),
        "prediction_allowed": False, "analysis_allowed": False,
        "analysis_block_reason": DIAGNOSIS_BLOCK_CODE,
    }


async def backfill_legacy_diagnoses() -> None:
    """Idempotent import; never resurrect assertions withdrawn or moved by a user."""
    async with in_transaction():
        records = await HealthDiagnosisRecord.all()
        processed = {int(value) for record in records for value in record.eligibility_check_ids}
        by_day = {(record.user_id, record.record_date): record for record in records}
        for event in await EligibilityCheck.filter(has_diabetes_diagnosis=True).order_by("created_at", "id"):
            if event.id in processed:
                continue
            day = event.created_at.astimezone(SERVICE_TIMEZONE).date()
            record = by_day.get((event.user_id, day))
            if record is None:
                record = await HealthDiagnosisRecord.create(
                    user_id=event.user_id, record_date=day, eligibility_check_id=event.id,
                    eligibility_check_ids=[event.id],
                )
                by_day[(event.user_id, day)] = record
            else:
                record.eligibility_check_ids = [*record.eligibility_check_ids, event.id]
                await record.save(update_fields=["eligibility_check_ids"])
            processed.add(event.id)


async def diagnosis_records(user_id: int) -> list[dict[str, object]]:
    items = await HealthDiagnosisRecord.filter(user_id=user_id, is_active=True).order_by("-record_date", "-id")
    return [diagnosis_record_payload(item) for item in items]


async def diagnosed_on(user_id: int, record_date: date) -> bool:
    return await HealthDiagnosisRecord.filter(user_id=user_id, record_date=record_date, is_active=True).exists()


async def diagnosis_context(user_id: int, request):
    record = None
    checkup = None
    if request.health_checkup_id is not None:
        checkup = await HealthCheckup.get_or_none(id=request.health_checkup_id, user_id=user_id)
        if checkup is None:
            raise HTTPException(404, detail="건강정보 기록을 찾을 수 없습니다.")
    if request.diagnosis_record_id is not None:
        record = await HealthDiagnosisRecord.get_or_none(id=request.diagnosis_record_id, user_id=user_id)
        if record is None:
            raise HTTPException(404, detail="진단 기록을 찾을 수 없습니다.")
        if checkup is None and record.source_checkup_id is not None:
            checkup = await HealthCheckup.get_or_none(id=record.source_checkup_id, user_id=user_id)
    day = checkup.checkup_date if checkup else request.record_date or (record.record_date if record else service_today())
    if checkup is not None and request.record_date is not None and request.record_date != day:
        raise HTTPException(422, detail="다시 기록하는 건강정보의 날짜와 일치해야 합니다.")
    if record is None and checkup is None and request.record_date is not None and request.record_date != service_today():
        raise HTTPException(422, detail="과거 기록을 변경하려면 다시 기록에서 시작해 주세요.")
    if record is not None and record.record_date != day:
        if await HealthDiagnosisRecord.filter(user_id=user_id, record_date=day, is_active=True).exclude(id=record.id).exists():
            raise HTTPException(409, detail="해당 날짜에 진단 기록이 있습니다. 해당 내역에서 다시 기록해 주세요.")
    return day, checkup, record


async def save_diagnosis_answer(user_id: int, request, event, day, checkup, record):
    if not request.has_diabetes_diagnosis and record is None:
        return None
    async with in_transaction():
        if record is None:
            record, _ = await HealthDiagnosisRecord.get_or_create(user_id=user_id, record_date=day)
        if record.record_date != day:
            duplicate = await HealthDiagnosisRecord.filter(user_id=user_id, record_date=day).exclude(id=record.id).first()
            if duplicate is not None:
                if duplicate.is_active:
                    raise HTTPException(409, detail="해당 날짜에 진단 기록이 있습니다. 해당 내역에서 다시 기록해 주세요.")
                record.is_active = False
                await record.save(update_fields=["is_active", "updated_at"])
                duplicate.eligibility_check_ids = list(dict.fromkeys([*duplicate.eligibility_check_ids, *record.eligibility_check_ids]))
                record = duplicate
        record.record_date = day
        record.source_checkup_id = checkup.id if checkup else record.source_checkup_id
        record.eligibility_check_id = event.id
        record.eligibility_check_ids = list(dict.fromkeys([*record.eligibility_check_ids, event.id]))
        record.is_active = request.has_diabetes_diagnosis
        record.deleted_at = None
        await record.save()
    return record


async def delete_diagnosis_record(user_id: int, record_id: int):
    record = await HealthDiagnosisRecord.get_or_none(id=record_id, user_id=user_id, is_active=True)
    if record is None:
        raise HTTPException(404, detail="진단 기록을 찾을 수 없습니다.")
    record.is_active = False
    record.deleted_at = datetime.now(SERVICE_TIMEZONE)
    await record.save(update_fields=["is_active", "deleted_at", "updated_at"])
    return {"diagnosis_record_id": record.id, "deleted": True}


async def attach_diagnosis_context(event):
    record = await HealthDiagnosisRecord.filter(user_id=event.user_id, eligibility_check_id=event.id).first()
    event.context_record_date = record.record_date if record else service_today()
    event.diagnosis_record_snapshot = diagnosis_record_payload(record) if record and record.is_active else None
    return event


async def ensure_record_analysis_allowed(user_id: int, record_date: date) -> None:
    if await diagnosed_on(user_id, record_date):
        raise HTTPException(403, detail={
            "error_code": DIAGNOSIS_BLOCK_CODE,
            "message": "당뇨병 진단이 기록된 날짜에는 예측·분석을 이용할 수 없습니다.",
            "record_date": record_date.isoformat(),
        })


async def ensure_prediction_read_allowed(item, user_id: int) -> None:
    checkup = await HealthCheckup.get_or_none(id=item.health_checkup_id, user_id=user_id)
    if checkup is not None:
        await ensure_record_analysis_allowed(user_id, checkup.checkup_date)


async def visible_predictions(items, user_id: int):
    blocked_dates = await HealthDiagnosisRecord.filter(user_id=user_id, is_active=True).values_list("record_date", flat=True)
    if not blocked_dates:
        return items
    blocked_ids = set(await HealthCheckup.filter(user_id=user_id, checkup_date__in=blocked_dates).values_list("id", flat=True))
    return [item for item in items if item.health_checkup_id not in blocked_ids]
