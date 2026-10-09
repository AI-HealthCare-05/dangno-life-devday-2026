# 팀원에게 별도로 전달할 파일 및 서버 준비

## 별도 파일 목록

클라이언트 APK에는 서버 모델·DB·API 비밀키를 넣지 않는다. Git으로 소스와 설정 계약을 공유하고, 아래 파일은 역할에 따라 따로 준비한다.

| 파일 | 필요한 사람 | 전달 / 준비 방법 |
| --- | --- | --- |
| 배포 APK | 직접 빌드하지 않는 Android 팀원 | 최신 준비 파일은 작업 폴더의 `outputs/mobile/gandang-deployment-current.apk`. `https://www.dang-no.life`, `life.dangno.app.deployment`, 이름 `간당간당(배포)`이다. 파일과 SHA-256·API 주소·소스 커밋을 함께 전달하며 Git에 넣지 않는다. 팀이 직접 빌드하면 `app-debug.apk`가 생성된다. 배포 서버 계정을 사용한다. |
| 로컬 APK | PC API를 시험하는 Android 팀원 | `build:mobile:local`로 별도 빌드한다. `http://127.0.0.1:8000`, `life.dangno.app`이며 ADB reverse와 PC 서버가 필요하다. 배포 앱과 동시에 설치한다. |
| 제작자 무료 고양이 팩 | 원본 펫 그림을 사용할 앱 제작자 | `scripts/import_forest_kittens.ps1`의 공식 출처·조건에 따라 각자 내려받는다. 원본 PNG는 PR/Git에서 제외하며 없는 경우 기존 펫 대체 그림을 사용한다. 개인 APK에는 설치된 자산이 포함될 수 있으므로 재배포 전 원저작자 조건을 확인한다. |
| 오늘이 `models/artifacts/candidates/diabetes_current_screening/knhanes-today14-sk180-service-v3/model.joblib` | 로컬/팀 API 서버 담당자 | 기존 Drive 공급 스크립트로 내려받고 Registry SHA-256을 검증한다. |
| 내일이 `models/artifacts/candidates/diabetes_incidence/rf25-tuned-education4-v2/model.joblib` | API 서버 담당자 | 위와 동일. 모델·전처리·임계값 계약을 임의 변경하지 않는다. |
| 음식 CV `models/artifacts/food_vision/kfood/best.pt`, `meta.json`, `1.tflite` | 사진 인증 API 서버 담당자 | CV Drive 공급 스크립트로 세 파일을 검증한 뒤 배치한다. |
| 오늘이 SHAP `models/artifacts/xai/today-train-reference-v2/background.csv` | 오늘이 SHAP를 실행할 승인된 서버 담당자 | Git 제외. Train 참조 행을 포함하므로 공개 링크·PR·APK·일반 팀 APK 묶음에 넣지 않는다. 권한이 있는 내부 경로로 전달하거나 승인된 학습 자료에서 재생성한다. Registry의 SHA-256과 모델 버전이 맞아야 한다. |
| `.env.local-mobile` | 각 로컬 서버 담당자 | 공유하지 않고 `scripts/setup-local-mobile.py`로 각자 생성한다. 운영·외부 API 키는 담당자가 별도 환경변수/비밀 관리로 설정한다. |
| iOS 설치물 | iPhone 팀원 | 공용 APK나 임의 IPA가 아니다. 각자 Xcode/Personal Team으로 설치하거나 팀에서 서명한 TestFlight 빌드로 제공한다. |
| `node_modules`, `.venv`, SDK/JDK/Gradle/Xcode | 각 개발자 | 전달하지 않고 lockfile·가이드대로 설치한다. |
| 사용자 SQLite·원본 사진·원자료·토큰·키스토어/서명 개인키 | 전달 대상 없음 | 기존 계정·건강정보는 공유하지 않는다. 테스트 계정을 새로 만든다. |

Drive 출처: [프로젝트 지정 폴더](https://drive.google.com/drive/folders/1jhPrlVGf8jlykOYVCIEbeuX0vTvv122o). 오늘이/내일이 세부 파일 계약은 기존 `configs/model_delivery/google_drive_models.json`, CV는 `configs/model_delivery/google_drive_cv.json`을 따른다. 접근 권한이 없으면 모델 담당자가 권한을 제공해야 하며 다른 모델로 대신하지 않는다.

APK 공유 담당자는 별도 전달 전에 다음을 확인한다.

```powershell
Get-FileHash -Algorithm SHA256 src/frontend/native/android/app/build/outputs/apk/debug/app-debug.apk
```

API 주소가 바뀌면 APK도 다시 만든다. 서로 다른 PC가 만든 debug 서명은 다를 수 있어 업데이트 설치가 거부될 수 있다. 같은 제작자의 APK로 갱신하는 것을 우선한다.

## 로컬 서버 새로 준비하기

Windows/Linux CPU 서버 기준이다. iOS 앱을 빌드하는 Mac에는 서버 모델을 복사할 필요 없이 준비된 HTTPS API를 연결할 수 있다.

Windows에서 Python 3.13 공식 배포를 설치하고 저장소 루트에서 실행한다.

```powershell
py -3.13 -m venv .venv
& .venv/Scripts/python.exe -m pip install -r requirements-local-mobile.txt
& .venv/Scripts/python.exe scripts/setup-local-mobile.py
& .venv/Scripts/python.exe scripts/provision-models-google-drive.py
& .venv/Scripts/python.exe scripts/provision-cv-google-drive.py
& .venv/Scripts/python.exe scripts/check-local-cv.py
```

`requirements-local-mobile.txt`는 검증 환경의 Windows/Linux CPU 버전이다. PyTorch 2.8.0+cpu·torchvision 0.23.0+cpu를 사용한다. macOS의 Python 서버 설치까지 검증한 파일은 아니다.

오늘이 SHAP 참조 파일은 Drive 공급 스크립트에 포함되지 않는다. 위 표의 경로에 승인된 파일을 준비한다. 권한 있는 모델 담당자가 동일 학습 CSV를 가지고 있다면 다음으로 만들 수 있다. 원자료/전처리 CSV를 앱 팀원에게 일반 공유할 필요는 없다.

```powershell
& .venv/Scripts/python.exe scripts/provision-today-xai-background.py '승인된-학습-CSV-경로'
& .venv/Scripts/python.exe scripts/check-local-xai.py
& .venv/Scripts/python.exe scripts/check-local-photo-verification.py
& .venv/Scripts/python.exe scripts/run-local-mobile.py
```

Linux는 `python3.13 -m venv .venv` 및 `.venv/bin/python`으로 같은 순서를 실행한다. 서버는 `127.0.0.1:8000`에 바인딩한다. 터미널을 열어 둔 상태에서 `Ctrl+C`로 종료한다. Windows 숨김 실행이 필요하면 기존 `scripts/start-local-mobile.ps1` / `stop-local-mobile.ps1`을 사용할 수 있다.

`setup-local-mobile.py`는 독립 SECRET_KEY를 생성하고 기존 `.env.local-mobile`을 덮어쓰지 않는다. DEMO_MODE는 로컬 SQLite·내장 작업 실행을 위해 사용하며 `DEMO_ARTIFACT_INFERENCE_ENABLED=true`와 `PREDICTION_PROVIDER=artifact`로 실제 승인 모델을 실행한다. 앱 빌드는 localhost 모델 미리보기 활성화를 차단한다.

브라우저에서 `http://127.0.0.1:8000/api/v1/health`, `/api/v1/ready` 및 `/api/docs`를 확인한다. 로컬 테스트 계정으로 가입한다. 기존 사용자의 DB를 복사하지 않는다.

외부 검진표 OCR을 사용하려면 서버에서 `HEALTH_CHECKUP_OCR_PROVIDER`와 해당 공급자 변수(`CLOVA_OCR_URL`, `CLOVA_OCR_SECRET` 또는 `ANTHROPIC_API_KEY`)를 설정한다. 외부 OCR 설정이 없으면 합성 예시와 입력란 반영 UI만 검증할 수 있다. 지도·메일·OpenAI VLM도 관련 키를 가진 담당자가 별도로 설정해야 한다. 키 없이 작동했다고 표시하지 않는다.

SQLite/PyTorch 실행이 Windows 정책에 의해 차단되면 프로젝트의 검증된 복구 도구와 공식 런타임을 사용한다. `scripts/repair-local-sqlite.ps1 -Apply`는 프로젝트 전용 Python 3.13.15 환경만 대상으로 검사한다. 일반 Python 설치나 다른 버전에 무조건 적용하지 않는다. 보안 정책을 해제하거나 DLL을 임의로 바꾸지 않는다.

## iOS 및 팀 공유용 HTTPS API

가장 간단한 방법은 서버 담당자가 이 PR의 서버 코드·모델·SHAP 배경·필요한 공급자 설정을 적용한 HTTPS 테스트 API 주소를 제공하는 것이다. 기존 운영 서버가 이 PR의 `model_analysis`, `shap_graph`, 입력값 표시 응답을 제공하지 않으면 새 UI와 서버 계약이 맞지 않을 수 있다.

기존 서버가 없을 때 같은 Wi-Fi의 로컬 개발 서버를 HTTPS로 연결할 수 있다. 다음은 **구성 예시이며 이 작업에서 실제 네트워크 공개나 iPhone 검증을 수행하지 않았다.** 원본 사진이나 실제 건강정보 없이 테스트 계정으로 준비한다.

1. 서버 PC에서 위 로컬 API를 실행한다. [공식 Caddy](https://caddyserver.com/docs/install)를 설치한다.
2. `outputs/mobile/Caddyfile`에 아래 예시의 IP를 서버 PC의 같은 Wi-Fi 주소로 바꾸어 저장한다. Caddy는 해당 주소에만 바인딩한다. 8000 서버는 계속 loopback으로 둔다.

```caddyfile
https://192.168.1.10:8443 {
    bind 192.168.1.10
    tls internal
    reverse_proxy 127.0.0.1:8000
}
```

3. `caddy run --config outputs/mobile/Caddyfile --adapter caddyfile`로 실행한다. 방화벽은 사용 중인 사설 네트워크의 8443 포트에만 허용한다. 공유기 포트 포워딩·인터넷 공개는 필요 없다.
4. `caddy environ`에서 `caddy.AppDataDir` 위치를 확인한다. 해당 위치의 `pki/authorities/local/root.crt` **공개 인증서만** iPhone에 전달한다. `root.key` 등 개인키는 전달하지 않는다.
5. iPhone에서 인증서 프로파일을 설치하고 설정 → 일반 → 정보 → 인증서 신뢰 설정에서 직접 설치한 개발 인증서를 신뢰한다. Safari에서 `https://192.168.1.10:8443/api/v1/health`가 인증서 오류 없이 열리는지 확인한다.
6. iOS 빌드의 `MOBILE_API_ORIGIN`을 이 HTTPS 주소로 지정한다. 앱의 로컬 네트워크 권한도 허용한다. 시험 종료 후 필요 없는 개발 인증서 프로파일과 신뢰 설정을 제거한다.

Caddy 내부 CA와 기기 신뢰: [Caddy HTTPS](https://caddyserver.com/docs/automatic-https), [Apple 수동 인증서 신뢰](https://support.apple.com/en-us/102390). 같은 Wi-Fi라도 AP 격리·회사 방화벽·IP 변경으로 연결이 막힐 수 있다. HTTPS 인증서 검증을 끄는 방식으로 우회하지 않는다.
