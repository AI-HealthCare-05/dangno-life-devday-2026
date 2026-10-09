# 팀원 Drive 예측모델 연결 점검 — 2026-10-09

현재·미래 예측모델 및 원본 manifest를 팀원 Google Drive에서 새로 내려받고, 고정된 SHA-256 검증 후 로컬 작업용 서비스의 모델 경로에 설치했습니다.

## 모델 무결성

| 구분 | 모델 버전 | 파일 크기 | SHA-256 |
|---|---|---:|---|
| 현재 | knhanes-today14-sk180-service-v3 | 6,486,837 bytes | 2189257587690adfcdf74702f69b516c0a8559cef6059ebd90d003e008c079b1 |
| 미래 | rf25-tuned-education4-v2 | 2,281,448 bytes | 45f7de434a887b82aaff86a3b6afd8e99f75ebdc8bb3c0cd320484db9b71ad8e |

두 파일 모두 binary·Drive manifest·저장소 registry에 등록된 체크섬 및 모델 버전과 일치했습니다. 모델 바이너리, API 키, 인증 다운로드 URL, 사용자 건강정보는 이 PR에 포함하지 않습니다.

## 실행 검증

- 새로 받은 실제 모델로 41개 입력·추론 계약 점검 통과. 선택 입력 누락, 교육 코드, 지원 연령 경계, 필수값 누락, 잘못된 입력 및 반복 실행을 점검했습니다.
- 합성 계정으로 가입 → 프로필·동의·건강정보 입력 → 현재·미래 예측 작업 → 결과 조회 API 흐름 통과.
- 내부 DB에 실제 추론 점수 저장 확인: 현재 0.038280703743, 미래 0.019677395911. 합성 입력의 연결 확인 값이며 성능 재평가나 의료 진단 결과가 아닙니다.
- 후보 상태에서는 공개 점수·위험 범주 비노출 확인.
- 로컬 실행 환경: Python 3.12.14, scikit-learn 1.8.0, numpy 2.5.3, pandas 2.3.3, joblib 1.6.0.

## 원본 manifest와 저장소 차이

Drive 미래 원본은 promotion_status=candidate_only, operational_model_activated=false, medical_review_required=true입니다. 현재 원본도 medical_review_required=true이며 release_approval이 없습니다. 저장소의 approved/검토 완료 표기와 차이가 있어 이번 실행은 후보 상태로 설정했습니다. 의료 검토나 운영 승인을 이번 작업에서 새로 부여하지 않았습니다.

미래 원본 threshold_version은 education4-validation-spec043-moderate-recall090-v2이고 저장소 및 실제 로드 계약은 education4-validation-spec043-caution-recall090-v2입니다. 원본을 보존하고 차이를 기록했으며, 임계값 숫자와 승인 메타데이터를 변경하지 않았습니다. 원본 manifest를 그대로 덮어쓰면 버전 계약 충돌이 발생할 수 있습니다.

## 연결 설정 및 배포 인계

설치 경로는 각 registry의 artifact_local_path에 지정된 models/artifacts/candidates 아래 경로입니다. scripts/provision-models-google-drive.py는 다운로드 파일의 체크섬과 모델 버전을 검증하지만 운영 승인 상태를 검증하지는 않습니다.

점검 실행 설정(API 키 없음):

```dotenv
DEMO_MODE=true
DEMO_ARTIFACT_INFERENCE_ENABLED=true
PREDICTION_PROVIDER=artifact
PREDICTION_PROMOTION_STATUS=candidate_only
PREDICTION_OPERATIONAL_MODEL_ACTIVATED=false
CURRENT_SCREENING_PROMOTION_STATUS=candidate_only
CURRENT_SCREENING_OPERATIONAL_MODEL_ACTIVATED=false
```

AWS 배포·Linux 런타임 재검증은 아직 완료되지 않았습니다. AWS에서는 고정 의존성, OpenMP 런타임, 모델 다운로드 및 동일 API 흐름을 확인해야 합니다. 전체 ready 응답은 별도 CV 모델 미준비로 503이므로 전체 서비스 준비 완료를 의미하지 않습니다.

이 PR은 점검·로컬 연결 결과를 기록하는 문서 변경입니다. 실행 코드 또는 AWS 배포 변경을 포함하지 않습니다.
