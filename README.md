# 당NO life — DevDay Seoul 2026

건강 입력 → 현재·미래 AI 위험 선별 → 맞춤 챌린지 → 건강 습관과 숲 화면.

- 오늘의 할 일: [데일리 뭐하징](DAILY.md)
- 실행 안내: [SETUP.md](SETUP.md)
- 기능 시작 상태: [PREWORK.md](PREWORK.md)
- 당일 작업·검증: [DAY_OF_WORK.md](DAY_OF_WORK.md)

## 작업 시작

```sh
git clone https://github.com/AI-HealthCare-05/dangno-life-devday-2026.git
cd dangno-life-devday-2026
python3 restore_workspace.py
python3 -m venv .venv
. .venv/bin/activate
sh build-project.sh
sh start-project.sh
```

소스·동적 시각 자산은 브라우저 업로드 제한에 맞춰 분할 보관합니다. 체크섬을 확인하고 app/, src/, configs/, scripts/를 저장소 루트에 복원하며 Git 이력과 팀 작업 문서를 보존합니다. 복원 후 소스 파일은 팀원이 feature 브랜치/PR로 추적하여 반영합니다.

모델은 build에서 별도 다운로드·체크섬 검증합니다. 모델 바이너리·DB·API 키는 Git에 넣지 않습니다. Linux에서는 LightGBM용 libgomp1이 필요합니다.

합성 입력의 실제 예측·챌린지 기록은 사전 검증했습니다. OCR/CV/RAG 외부 연결·숲 보상·모바일 전체 흐름·AWS 배포는 추가 검증 대상입니다. 결과는 진단·처방이 아닌 위험 선별·건강교육으로 표현합니다.
