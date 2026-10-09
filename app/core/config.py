import os
import uuid
import zoneinfo
from dataclasses import field
from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Env(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="allow")

    ENV: Env = Env.LOCAL
    SECRET_KEY: str = f"default-secret-key{uuid.uuid4().hex}"
    TIMEZONE: zoneinfo.ZoneInfo = field(default_factory=lambda: zoneinfo.ZoneInfo("Asia/Seoul"))
    TEMPLATE_DIR: str = os.path.join(Path(__file__).resolve().parent.parent, "templates")

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "pw1234"
    DB_NAME: str = "ai_health"
    DB_CONNECT_TIMEOUT: int = 5
    DB_CONNECTION_POOL_MAXSIZE: int = 10
    DB_GENERATE_SCHEMAS: bool = False
    DATABASE_URL: str | None = None
    DEMO_MODE: bool = False
    DEMO_ARTIFACT_INFERENCE_ENABLED: bool = False
    XAI_DISPLAY_ALLOWED: bool = False
    CHALLENGE_V2_ENABLED: bool = False
    CHALLENGE_V2_CONTENT_APPROVED: bool = False
    CHALLENGE_V2_REVIEWER_IDS: list[int] = []

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_STREAM: str = "ai:jobs"
    REDIS_CONSUMER_GROUP: str = "ai-workers"
    REDIS_JOB_TTL_SECONDS: int = 86400

    PREDICTION_PROVIDER: str = "development"
    ML_RESEARCH_ENDPOINTS_ENABLED: bool = False
    ML_SHARED7_MODEL_URI: str = ""
    ML_SHARED8_MODEL_URI: str = ""
    ML_FIRST_INTERVAL_MODEL_URI: str = ""
    ML_RF25_MODEL_URI: str = ""
    PREDICTION_TIMEOUT_SECONDS: int = 30
    MODEL_PRELOAD_ENABLED: bool = False
    PREDICTION_MODEL_KEY: str = "diabetes_incidence"
    PREDICTION_MODEL_VERSION: str = "rf25-tuned-education4-v2"
    PREDICTION_FEATURE_SCHEMA_VERSION: str = "klosa_stage3_25features_education4_v2"
    PREDICTION_INPUT_SCHEMA_VERSION: str = "diabetes-incidence-api-education4-v2"
    PREDICTION_PREPROCESSING_VERSION: str = "train-median-indicator-mode-onehot-education4-v2"
    PREDICTION_TARGET_DEFINITION_VERSION: str = "next-observation-new-diabetes-v1"
    PREDICTION_CALIBRATION_VERSION: str = "not_probability_calibrated-v1"
    PREDICTION_MODEL_ARTIFACT_DIGEST: str = "45f7de434a887b82aaff86a3b6afd8e99f75ebdc8bb3c0cd320484db9b71ad8e"
    PREDICTION_THRESHOLD_VERSION: str = "education4-validation-spec043-caution-recall090-v2"
    PREDICTION_DECISION_THRESHOLD: float | None = 0.02113653615781283
    PREDICTION_MODEL_MIN_AGE: int = 45
    PREDICTION_MODEL_MAX_AGE: int | None = 105
    PREDICTION_MODEL_POPULATION: str = "undiagnosed_klosa_age_45_105"
    PREDICTION_PROMOTION_STATUS: str = "approved"
    PREDICTION_OPERATIONAL_MODEL_ACTIVATED: bool = True
    MODEL_URI: str = "models/artifacts/candidates/diabetes_incidence/rf25-tuned-education4-v2/model.joblib"
    MODEL_MANIFEST_URI: str = "models/registry/diabetes_incidence/candidates/rf25-tuned-education4-v2.json"
    CURRENT_SCREENING_MODEL_VERSION: str = "knhanes-today14-sk180-service-v3"
    CURRENT_SCREENING_FEATURE_SCHEMA_VERSION: str = "knhanes-today-14features-missing-indicator-v2"
    CURRENT_SCREENING_INPUT_SCHEMA_VERSION: str = "today-api-required-alcohol-optional-education-v2"
    CURRENT_SCREENING_PREPROCESSING_VERSION: str = (
        "train-median-indicator-mode-onehot-categorical-indicator-waist-estimator-v2"
    )
    CURRENT_SCREENING_TARGET_DEFINITION_VERSION: str = "current-diabetes-signal-v1"
    CURRENT_SCREENING_THRESHOLD_VERSION: str = "today14-missing-indicator-validation-spec042-v2"
    CURRENT_SCREENING_DECISION_THRESHOLD: float = 0.022445685526736606
    CURRENT_SCREENING_MODEL_ARTIFACT_DIGEST: str = "2189257587690adfcdf74702f69b516c0a8559cef6059ebd90d003e008c079b1"
    CURRENT_SCREENING_MODEL_URI: str = (
        "models/artifacts/candidates/diabetes_current_screening/knhanes-today14-sk180-service-v3/model.joblib"
    )
    CURRENT_SCREENING_MANIFEST_URI: str = (
        "models/registry/diabetes_current_screening/candidates/knhanes-today14-sk180-service-v3.json"
    )
    CURRENT_SCREENING_RUNTIME: str = "today14"
    CURRENT_SCREENING_PROMOTION_STATUS: str = "approved"
    CURRENT_SCREENING_OPERATIONAL_MODEL_ACTIVATED: bool = True
    SAFETY_COPY_VERSION: str = "2026-08-19-v1"

    # 식사 사진에서 채소 포함 여부만 자동 판별합니다. 칼로리·영양소는 계산하지 않습니다.
    FOOD_VISION_PROVIDER: str = "local_kfood"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_VLM_MODEL: str = "gpt-4o-mini"
    OPENAI_VLM_FALLBACK_ENABLED: bool = False
    FOOD_VISION_TIMEOUT_SECONDS: int = 20
    FOOD_PHOTO_MAX_BYTES: int = 8 * 1024 * 1024
    KFOOD_CLASSIFIER_PATH: Path = Path("models/artifacts/food_vision/kfood/best.pt")
    KFOOD_CLASSIFIER_META_PATH: Path = Path("models/artifacts/food_vision/kfood/meta.json")
    KFOOD_CLASSIFIER_META_SHA256: str = "a193e1faf4e7c266e0ba4481451ded587fcd01cfc7d89c60d834bac63e14e0b3"
    KFOOD_CLASSIFIER_SHA256: str = "4c4df6ba2b9d3daf77f7ffe107285df17a360342729177d15465ba9872d42726"
    KFOOD_SEGMENTER_PATH: Path = Path("models/artifacts/food_vision/kfood/1.tflite")
    KFOOD_SEGMENTER_SHA256: str = "edb7df52467afd02a502d7765ca7ac82e63ad86082c72e18135764f1b1817b52"
    KFOOD_SEGMENTATION_CONFIG_PATH: Path = Path("configs/food_vision/seg_config.json")
    KFOOD_DISH_VEGETABLES_PATH: Path = Path("configs/food_vision/dish_vegetables.json")
    KFOOD_DRIVE_FILE_ID: str = ""
    KFOOD_BUNDLE_SHA256: str = ""
    KFOOD_BUNDLE_DIR: Path = Path("models/artifacts/food_vision/kfood")
    KFOOD_BUNDLE_DOWNLOAD_TIMEOUT_SECONDS: int = 120
    FOOD_COVERAGE_PASS_THRESHOLD: float = 0.50
    VEGETABLE_RATIO_PASS_THRESHOLD: float = 0.30

    HEALTH_EDUCATION_EMBEDDING_PROVIDER: str = "development"
    HEALTH_EDUCATION_EMBEDDING_MODEL: str = "text-embedding-3-small"
    HEALTH_EDUCATION_GENERATION_PROVIDER: str = "development"
    HEALTH_EDUCATION_TIMEOUT_SECONDS: int = 20
    HEALTH_EDUCATION_KEYWORD_WEIGHT: float = 0.5
    HEALTH_EDUCATION_EMBEDDING_WEIGHT: float = 0.5
    HEALTH_EDUCATION_RELEVANCE_THRESHOLD: float = 0.18
    HEALTH_EDUCATION_TOP_K: int = 6
    HEALTH_EDUCATION_MAX_CITATIONS: int = 3
    HEALTH_EDUCATION_RETRIEVER: str = "memory"
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "health_education"
    QDRANT_API_KEY: str = ""

    # 위치 기반 근처 의료기관 조회. 진단·처방을 대신하지 않고, 위치 기반 안내만 제공합니다.
    MEDICAL_FACILITY_SEARCH_PROVIDER: str = "development"
    KAKAO_REST_API_KEY: str = ""
    # 브라우저 지도 SDK용 공개 키입니다. REST API 키와 분리하고 도메인 제한을 적용합니다.
    KAKAO_JAVASCRIPT_KEY: str = ""
    # 카테고리 검색(HP8, 반경 내 병원 전체) 대신 키워드 검색으로 좁혀서 반환하기로 결정(2026-09-02 팀 회의).
    MEDICAL_FACILITY_SEARCH_KEYWORDS: str = "당뇨"
    MEDICAL_FACILITY_SEARCH_CATEGORY_GROUP_CODE: str = "HP8"
    # 텍스트 매칭 특성상 "내과" 키워드가 "구강내과"(치과 표기)까지 걸려서 치과가 섞여 들어오는 문제가 있어
    # 카테고리 이름에 아래 단어가 포함되면 결과에서 제외합니다(2026-09-02 팀 회의 이후 발견/보완).
    MEDICAL_FACILITY_SEARCH_EXCLUDED_CATEGORY_KEYWORDS: str = "치과,한의원"
    MEDICAL_FACILITY_SEARCH_TIMEOUT_SECONDS: int = 10
    MEDICAL_FACILITY_DEFAULT_RADIUS_METERS: int = 5000
    MEDICAL_FACILITY_MAX_RESULTS: int = 15

    # 국립중앙의료원 전국 응급의료기관 정보 조회 서비스
    EMERGENCY_FACILITY_SEARCH_PROVIDER: str = "nemc"
    NEMC_SERVICE_KEY: str = ""
    NEMC_EMERGENCY_API_URL: str = "https://apis.data.go.kr/B552657/ErmctInfoInqireService/getEgytLcinfoInqire"
    NEMC_EMERGENCY_TIMEOUT_SECONDS: int = 10
    EMERGENCY_FACILITY_MAX_RESULTS: int = 10

    # 건강검진 결과통보서 OCR. 원본은 요청 처리 중 메모리에만 두고, 추출 초안은 사용자 확인 후에만 반영합니다.
    HEALTH_CHECKUP_OCR_PROVIDER: str = "clova"
    CLOVA_OCR_URL: str = ""
    CLOVA_OCR_SECRET: str = ""
    CLOVA_OCR_TIMEOUT_SECONDS: int = 20
    CLOVA_OCR_MAX_BYTES: int = 10 * 1024 * 1024
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_OCR_MODEL: str = "claude-haiku-4-5-20251001"
    CLAUDE_OCR_TIMEOUT_SECONDS: int = 25
    CLAUDE_OCR_MAX_BYTES: int = 10 * 1024 * 1024

    COOKIE_DOMAIN: str = "localhost"
    FRONTEND_BASE_URL: str = "http://localhost:8001"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 14 * 24 * 60
    JWT_LEEWAY: int = 5
