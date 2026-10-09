# 당NO life — DevDay Seoul 2026

건강 입력으로 현재·미래 당뇨 위험을 선별하고, 일상 챌린지와 숲 화면으로 실천을 돕는 서비스입니다. 진단·처방 목적이 아닙니다.

## 실행

Python 가상환경을 활성화한 뒤 저장소 루트에서 실행합니다.

```sh
sh scripts/build-demo.sh
sh scripts/start-demo.sh
```

build는 의존성을 설치하고 모델을 별도 내려받아 SHA-256을 확인합니다. 모델/DB/API 키는 Git에 넣지 않습니다. Linux에서 LightGBM용 OpenMP가 필요합니다. AWS 서버 사양·외부 접속·HTTPS는 별도 확인 대상입니다.

실행 모드는 데모·실 모델 예측이며 OCR/CV/RAG 외부 서비스 연결은 별도 작업입니다. ready 503을 전체 준비 완료로 표시하지 않습니다.

사전 작업과 검증 한계는 PREWORK.md, 당일 변경은 DAY_OF_WORK.md, 파일 해시는 IMPORT_MANIFEST.json을 참고하세요. 현장 안내에 따라 작업을 시작하며 사전 기능과 당일 변경 기록을 구분합니다.
