# 오늘이 XAI 로컬 검증과 배포 복구 검토

검증일: 2026-10-14. 로컬 대상은 `local-develop`, 배포 API는 `https://www.dang-no.life`다. 사용자 DB를 수정하거나 예측·보상 기록을 추가하지 않았다. 모델·학습 기준표본·개인 입력은 Git과 이 문서에 포함하지 않는다.

## 로컬 확인 결과

| 단계 | 확인 결과 |
| --- | --- |
| 서버·모델 | `/health` 200, `/api/v1/ready` 200. Today14 v3·Tomorrow RF25 v2 승인 모델 사용 |
| 저장된 오늘이 | `explanation_status=approved`, 표시 허용·SHAP·가산성 검증 모두 true. 선택 요인 3개, 전체 요인 9개, 요인 테이블 3개 |
| 실제 조회 함수 | 저장된 결과의 소유자 ID를 사용한 `read_risk_factors` 호출에서 승인 응답·전체 그래프 9개·`complete=true` 반환. SQLite `query_only=ON`으로 쓰기 차단 |
| 새 계산 | 개인정보와 무관한 합성 입력으로 실제 `_demo_current_explanation` 실행 성공. 약 2초, `exact_grouped_shap_train_reference_v2`, 승인 설명 3개·전체 9개, 가산성 오차 약 1e-12 |
| 기준표본 | 학습 연도 2016–2020, 제외 연도 2021–2024, 128행·14입력 열. 모델·파일 SHA-256과 열 순서 검증 성공. 행 원문 미출력 |
| 화면 | 실제 로컬 웹 소스에 합성 결과를 전달해 390px·1024px에서 설명 제목, 요인 3개, 그래프 9개, 상세보기 토글과 화면 내 배치 확인. 브라우저의 실제 API 호출은 차단 |
| 회귀 검증 | 기준표본·SHAP·공개 계약·수치 표시 pytest 17개 통과 |

현재 ADB 장치가 연결되지 않아 휴대폰의 로컬 APK 화면은 이번에 직접 확인하지 못했다. 화면 검증은 실제 로컬 웹 코드와 합성 응답으로 수행했으며 저장 결과 검증과 구분한다. 원본 계산·응답을 변경하지 않았다.

## 배포에서 확인한 사실과 미확인 사항

- 공개 `/health` 200, `/api/v1/ready` 503. 현재와 미래 모델 경로는 사용 가능하고 모델 버전은 로컬과 같다. 503의 공개 원인은 음식 사진 CV 미준비이며, 이것만으로 오늘이 XAI 실패 원인으로 단정할 수 없다.
- 현재 ready 검사에는 오늘이 SHAP 기준표본 로딩·체크섬 검증과 XAI 표시 허용 값이 포함되지 않는다. 모델 준비 상태가 true여도 오늘이 XAI가 성공했다는 뜻은 아니다.
- 모델 다운로드 설정 `configs/model_delivery/google_drive_models.json`에는 오늘이·내일이 모델만 있고 XAI `background.csv` 전달 항목이 없다. 별도 준비 작업에서 기준표본 파일이 빠질 가능성이 있다.
- 로컬에서 기준표본 로더의 `FileNotFoundError`를 재현하면 실제 설명 함수가 `unavailable`, 표시 불허, 빈 요인을 반환한다. 과거 배포 화면의 오늘이 XAI 대기 상태와 동일한 실패 형태다. **배포 서버 내부 파일·환경값·사용자별 최신 결과를 직접 조회하지 못했으므로 기준표본 누락은 우선 가설이며 확정 원인이 아니다.**
- 공개 화면 JS 파일 조회는 연결이 중간에 종료되어 현재 서버 프런트엔드 전체를 비교하지 못했다. APK는 내장 웹 자산도 따로 확인해야 한다.

## 복구 순서

1. **실제 실행 프로세스 안에서 기준표본을 검증한다.** 현재 공개 배포는 `redis=embedded-demo`, `demo_artifact_inference_enabled=true`이므로 오늘이 설명은 FastAPI 내장 경로에서 실행된다. FastAPI 컨테이너/프로세스를 먼저 확인한다. 별도 worker 운영으로 변경하면 worker에서도 동일하게 확인한다.
   - `models/registry/xai/today-train-reference-v2.json`
   - `models/artifacts/xai/today-train-reference-v2/background.csv`
   - 기준표본 SHA-256: `7f76fbebe5b26c426796de81088def9a420f104920c1b7fed750553f552c97d9`
   - 연동 모델: `knhanes-today14-sk180-service-v3`; 모델 SHA-256: `2189257587690adfcdf74702f69b516c0a8559cef6059ebd90d003e008c079b1`
   - `load_today_background`로 파일 존재·권한·모델 결합·열 순서·행 수·학습 분할을 함께 검사한다. 단순히 파일 이름만 맞추거나 검증 조건을 제거하지 않는다.
2. **파일이 없다면 보호된 아티팩트 전달 경로로 설치한다.** 검증된 동일 파일을 별도로 제공하고 컨테이너의 `/app/models` 아래에 읽기 전용으로 마운트한다. Git·공개 정적 자산·APK에 기준표본을 넣지 않는다. 원자료로 다시 생성할 때는 `scripts/provision-today-xai-background.py`의 원자료 해시·Train 전용 선정 조건을 그대로 유지한다.
3. **승인 게이트와 코드 버전을 맞춘다.** 승인된 운영 구성에 따라 실제 실행 환경의 `XAI_DISPLAY_ALLOWED=true`를 확인한다. Today14 모델 manifest·SHAP 기준 manifest·`xai_background.py`·저장/조회 코드가 같은 릴리스인지 확인한다. 승인·가산성·SHAP 표시 조건을 우회하거나 내일이 요인을 오늘이로 복사하지 않는다.
4. **복구 후 새로 분석한다.** 설명은 예측 job과 요인 테이블에 저장된다. 과거 `unavailable` 결과를 조회만 해서는 다시 계산되지 않는다. 사용자가 건강정보로 새 분석을 실행하거나, 운영자가 검증된 설명 재계산 절차를 따로 구현한다. 상태 글자만 `approved`로 바꾸지 않는다.
5. **조회·화면까지 확인한다.** 새 결과의 `explanation_status=approved`, job 설명의 SHAP·가산성 true, 요인 테이블 존재를 확인한다. 소유자로 `/api/v1/predictions/{id}/risk-factors`를 조회해 표시 허용·전체 그래프 완전성을 검증한다. 요인 방향이 부족하면 3개보다 적은 유효 요인이 정상일 수 있다. 마지막으로 서버 프런트와 APK 내장 프런트의 결과 ID·현재/미래 요청 분리가 맞는지 확인한다.

## 반복 장애 방지

- XAI 준비 상태를 기본 모델·음식 사진 CV 상태와 구분해 추가한다. 기준표본 파일과 모델 결합을 검사하여 `today_xai_ready`를 제공하고 시작 시 선검증한다. 진단용 공개 응답에는 개인정보·내부 경로를 넣지 않는다.
- `safe_explanation`과 `_demo_current_explanation`은 현재 예외를 모두 일반 `unavailable`로 바꾸며, 요인 저장 실패도 삼킨다. 내부 로그에는 `REFERENCE_MISSING`, `REFERENCE_CHECKSUM_MISMATCH`, `MODEL_REFERENCE_MISMATCH`, `EXPLANATION_FAILED`, `FACTOR_PERSIST_FAILED` 등 원인 코드와 비민감 식별 정보만 남기도록 개선한다. 입력값·학습행·토큰은 기록하지 않는다.
- 모델 전달 체크리스트에 기준표본을 추가하고, 배포 직후 합성 입력의 가산성 및 승인 응답을 확인한다. 운영 DB에 가짜 사용자 결과를 생성하지 않는 검증 방식으로 운영한다.

이번 작업은 점검·검토이며 배포 서버 파일, 설정, DB 및 서비스 코드는 변경하지 않았다. 로컬 서버는 기존 설정으로 시작해 검증했다. 상세 진단 산출물은 상위 작업 폴더 `outputs/today-xai-*-20261014.*`에 있으며 원문 건강정보가 아닌 상태·합성 입력 결과만 포함한다.
