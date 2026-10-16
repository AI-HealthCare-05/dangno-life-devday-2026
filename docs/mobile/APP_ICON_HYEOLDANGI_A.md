# 혈당이 A안 앱 아이콘 — 2026-10-15

승인된 A안 얼굴 디자인을 로컬·배포 앱의 네이티브 아이콘에 공통 적용했다.

- 원본: `scripts/mobile/assets/hyeoldangi-app-icon-a.png` (1254×1254).
- 원본 SHA-256: `9a1198bca7bb62bf5c7966c2833e79f348c3150c35e699f13be9cef83f2c0a9c`.
- Android: mdpi~xxxhdpi 일반·원형·adaptive foreground PNG 15개.
- Adaptive 아이콘: 108dp 레이어 안의 중앙 66dp에 원본을 맞춰 원형 마스크와 움직임에 필요한 여백을 확보했다. 기존 adaptive XML 참조는 유지한다.
- iOS: 기존 AppIcon.appiconset이 참조하는 불투명 RGB 1024×1024 아이콘을 갱신했다. Windows에서는 iOS 설치 빌드를 검증하지 않았다.
- 디자인을 다시 그리지 않고 승인된 이미지의 크기와 여백만 조정했다.
- 웹 페이지의 로고·파비콘은 별도 자산이므로 이번 네이티브 아이콘 변경 대상에 포함하지 않았다.

## 재생성

Pillow가 설치된 Python에서 저장소 루트를 기준으로 실행한다.

```powershell
python scripts/mobile/generate-app-icons.py
```

스크립트는 해상도·불투명 RGB·iOS 카탈로그 연결을 확인하고 각 산출물의 해시를 출력한다.

## 설치 파일 검증

현재 BlueStacks에 설치된 로컬·배포 APK를 각각 보관한 후 아이콘 PNG 15개만 교체하고, 정렬 및 기존 debug 인증서로 재서명했다. APK 내부의 그 외 파일(웹 번들, API 주소, AndroidManifest, resources.arsc 등)은 원본과 바이트 단위로 같음을 검증했다. 패키지는 로컬 `life.dangno.app`, 배포 `life.dangno.app.deployment`로 유지한다.

상위 작업 폴더 `outputs/app-icon-applied-20261015/`에 APK, 아이콘 검증 결과, payload 비교 결과를 보관한다. 기존 앱을 삭제하거나 데이터를 초기화하지 않고 업데이트 설치한다. 운영 서버에 업로드하거나 커밋·푸시하지 않는다.
