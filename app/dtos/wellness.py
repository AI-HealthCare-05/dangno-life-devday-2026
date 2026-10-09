from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class WearableConnectionRequest(BaseModel):
    provider: Literal["development_mock", "file_import", "apple_health_export", "android_health_connect"] = (
        "development_mock"
    )
    scopes: list[Literal["activity", "sleep", "heart_rate"]] = Field(default_factory=lambda: ["activity"])


class WearableDailyItem(BaseModel):
    summary_date: date
    steps: int | None = Field(default=None, ge=0, le=200_000)
    active_minutes: int | None = Field(default=None, ge=0, le=1_440)
    sleep_minutes: int | None = Field(default=None, ge=0, le=1_440)
    resting_heart_rate: int | None = Field(default=None, ge=25, le=250)

    @model_validator(mode="after")
    def require_one_measurement(self) -> WearableDailyItem:
        if all(
            value is None for value in (self.steps, self.active_minutes, self.sleep_minutes, self.resting_heart_rate)
        ):
            raise ValueError("하나 이상의 웨어러블 측정값이 필요합니다.")
        return self


class WearableImportRequest(BaseModel):
    connection_id: int = Field(gt=0)
    items: list[WearableDailyItem] = Field(min_length=1, max_length=31)


class WearableHealthCandidateApplyRequest(BaseModel):
    exercise_days_per_week: float = Field(ge=0, le=7)
    exercise_minutes: float = Field(ge=0, le=720)
    regular_exercise: bool


class RagQuestionRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class RagCitationResponse(BaseModel):
    document_id: str
    title: str
    url: HttpUrl
    checked_at: date


class RagQuestionDataResponse(BaseModel):
    answer: str
    answer_status: Literal[
        "grounded",
        "insufficient_evidence",
        "medical_safety_refusal",
        "emergency_redirect",
    ]
    citations: list[RagCitationResponse]
    retrieval_method: str
    medical_notice: str


class ResponseMeta(BaseModel):
    request_id: str
    timestamp: datetime


class RagQuestionResponse(BaseModel):
    data: RagQuestionDataResponse
    meta: ResponseMeta


class QuizAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=100)


class FoodAnalysisRequest(BaseModel):
    image_name: str = Field(min_length=1, max_length=200)


class FoodAnalysisConfirmRequest(BaseModel):
    confirmed_category: Literal["곡류", "채소", "과일", "단백질", "유제품", "혼합식", "확인불가"]


class OcrDraftRequest(BaseModel):
    document_name: str = Field(min_length=1, max_length=200)
    extracted_fields: dict[str, str | int | float | None] = Field(default_factory=dict)
    ocr_text: str | None = Field(default=None, min_length=2, max_length=20_000)

    @model_validator(mode="after")
    def require_extracted_fields_or_text(self) -> OcrDraftRequest:
        if not self.extracted_fields and not self.ocr_text:
            raise ValueError("추출 필드 또는 OCR 텍스트가 필요합니다.")
        return self


class OcrHealthApplyRequest(BaseModel):
    height_cm: float | None = Field(default=None, ge=120, le=220)
    weight_kg: float | None = Field(default=None, ge=25, le=250)
    waist_cm: float | None = Field(default=None, ge=45, le=160)
    systolic_bp: int | None = Field(default=None, ge=70, le=250)
    diastolic_bp: int | None = Field(default=None, ge=40, le=150)

    @model_validator(mode="after")
    def validate_update(self) -> OcrHealthApplyRequest:
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("갱신할 건강정보를 하나 이상 확인해 주세요.")
        if self.systolic_bp is not None and self.diastolic_bp is not None and self.systolic_bp <= self.diastolic_bp:
            raise ValueError("수축기 혈압은 이완기 혈압보다 커야 합니다.")
        return self


class NotificationPreferenceRequest(BaseModel):
    in_app_enabled: bool = True
    challenge_reminder_enabled: bool = True
    weekly_report_enabled: bool = True
    quiet_start_hour: int = Field(default=21, ge=0, le=23)
    quiet_end_hour: int = Field(default=8, ge=0, le=23)
