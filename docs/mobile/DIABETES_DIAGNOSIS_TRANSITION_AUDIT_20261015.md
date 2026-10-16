# 로컬 앱 이용 중 당뇨병 진단 갱신 경로 점검 — 2026-10-15

## 범위와 검증 방법

- 대상: local-develop 소스 및 로컬 API.
- 실제 실행 서버 http://127.0.0.1:8000 의 /health 200 및 OpenAPI 경로를 읽기 전용으로 확인했다.
- 변경 요청은 실제 이용자 계정에 보내지 않았다. 같은 FastAPI 앱을 인증 사용자 의존성만 합성 계정으로 대체하고 SQLite 메모리 DB에서 실행했다. 실제 사용자 DB·개인정보는 변경하지 않았다.
- 프런트엔드는 app.js와 intro-retro-app.js의 실제 제출 처리 및 상태 함수를 VM에서 실행했다. 실제 휴대폰 화면 조작 검증은 하지 않았다.
- 이번 작업은 점검과 문서화이며 앱 동작은 수정하지 않았다.

## 입력 경로

로그인 → 홈 → 건강정보 관리 → 새 건강정보 기록하기 → 상단 이용확인 → “당뇨병을 진단받은 적이 있나요?”에 예 → 확인하고 계속하기.

새 건강정보 버튼 자체는 건강정보 입력 단계(4)로 이동하므로 진단 여부를 변경하려면 이용확인 단계(3)를 선택해야 한다. 마이페이지 개인정보 수정에는 별도 진단 변경 항목이 없다. 진단 날짜를 별도로 받는 필드는 없으며 이용확인 기록의 생성 시간이 남는다.

제출 시 프로필을 PATCH /api/v1/users/me 로 저장한 뒤 POST /api/v1/eligibility-checks 에 has_diabetes_diagnosis: true 를 보낸다. 긴급 증상 또는 당일 진료 문진 분기에 걸리면 이 제출 전에 화면 안내로 반환될 수 있다.

## 서버 응답과 저장 결과

51세, 동의 완료, 응급 징후 없음인 합성 계정으로 확인했다.

| 요청·상태 | 응답·효과 |
| --- | --- |
| POST /api/v1/eligibility-checks, 진단 예 | 200; 새 이용확인 이력 저장 |
| GET /api/v1/eligibility-checks/latest | 200; has_diabetes_diagnosis=true 복원 |
| 진단 후 POST /api/v1/health-checkups | 403; 의료기관 안내 우선 |
| 진단 후 POST /api/v1/prediction-jobs, 오늘이 | 403; PREDICTION_NOT_ALLOWED |
| 진단 후 POST /api/v1/prediction-jobs, 내일이 | 403; PREDICTION_NOT_ALLOWED |
| 진단 후 POST /api/v1/challenge-cycles | 403; 의료기관 안내 우선 |
| 기존 건강정보 GET | 200; 과거 기록 유지 |
| 진단 후 POST /api/v1/current-screening-inputs | 201; 보조 입력은 저장되어 제한 불일치 확인 |

주요 저장 응답:

```json
{
  "has_diabetes_diagnosis": true,
  "service_eligible": true,
  "challenge_eligible": false,
  "current_health_check_eligible": false,
  "future_prediction_eligible": false,
  "model_eligible": false,
  "reason_codes": ["DIAGNOSED_DIABETES"],
  "next_action": "clinician_guidance"
}
```

service_eligible은 현재 구현에서 성인·동의 여부를 나타내므로 true가 유지된다. 실제 분석·챌린지 허용 여부는 개별 capability와 진단 여부로 판단한다. 이 응답을 서비스 전체 허용으로 해석하면 안 된다.

HealthService.check_eligibility는 DIAGNOSED_DIABETES 후속 안내를 생성하고 기존 active/scheduled 4주 챌린지를 terminated, ended_reason=DIAGNOSED_DIABETES로 바꾼다. completed 기록은 유지한다. 같은 진단 예를 반복 저장해도 미확인 동일 안내는 중복 생성하지 않았다. 이 검증은 기존 ChallengeCycle 대상이며 별도 파일럿 V2 상태 전환 전체를 검증한 것은 아니다.

## 화면 처리와 발견된 불일치

1. 진단 저장 직후 현재·미래 분석 및 챌린지 capability는 모두 false, medicalGuidanceRequired는 true로 전환되고 D01 의료 안내를 표시한다.
2. 기존 state.cycle, state.currentScreeningPrediction, state.prediction은 제출 처리에서 갱신·정리하지 않는다. 따라서 화면과 서버 상태가 잠시 달라질 수 있다. VM 상태 검증이며 모든 UI에서 반드시 노출된다고 단정하지 않는다.
3. 메인 앱의 openDashboardHealthEdit는 차단된 currentHealth를 연령만으로 true로 복원하고 건강정보 입력을 연다. 레트로 앱의 새 기록 버튼도 직접 입력을 연다. 서버의 신규 건강정보/분석 차단은 유지되어 저장 시 403을 받는다.
4. current-screening-inputs는 동의와 기존 건강정보 소유권만 확인해 진단 후에도 201로 저장한다. 분석 작업 생성은 계속 403으로 차단된다.
5. 나중에 이용확인에서 진단 아니요를 다시 저장하면 model_eligible이 true로 복원된다. 입력 정정을 허용하는 동작이나 진단 이력을 고려한 추가 확인 정책은 없다. 이를 오류로 확정하기보다 재허용 정책을 정할 필요가 있다.
6. 신규 진단 사실만 갱신하는 전용 메뉴와 진단일 입력은 없다.

## 개선 권고

- 건강정보 관리에 진단 여부 변경 메뉴를 명확히 표시한다.
- 진단 갱신 성공 후 서버에서 최신 챌린지·이용권한을 재조회하고 기존 결과는 과거 기록임을 구분한다.
- 모든 건강정보 입력 진입점과 보조 입력 API의 접근 기준을 같은 정책으로 맞춘다.
- 진단 답변을 다시 아니요로 바꿀 때의 정정·재허용 기준을 명시한다.

## 근거

- app/services/health.py: eligibility_payload, create_current_screening_input, check_eligibility, create_checkup.
- app/repositories/health_repository.py: latest_eligibility, stop_active_cycles.
- app/services/ai_jobs.py: _ensure_prediction_eligibility.
- src/frontend/app.js: openDashboardHealthEdit, eligibility-form submit.
- src/frontend/intro-retro-app.js: eligibility-form submit, dashboard-edit-health.
- 기존 tests/frontend/health_management_navigation.test.cjs: 11개 통과.
- 상위 작업 폴더 outputs/diagnosis-transition-audit-20261015/server-responses.json: 메모리 DB API 응답.
- 같은 폴더 frontend-check.json: 메인·레트로 양쪽 상태 검증.
