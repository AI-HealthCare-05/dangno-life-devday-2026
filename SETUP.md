# 실행·팀 작업 시작

브라우저 업로드 용량 제한 때문에 실행 소스와 시각 자산을 체크섬이 있는 분할 파일로 보관합니다. Git 인증이 연결되면 복원한 소스를 feature 브랜치/PR로 반영합니다.

```sh
git clone https://github.com/AI-HealthCare-05/dangno-life-devday-2026.git
cd dangno-life-devday-2026
python3 restore_workspace.py
python3 -m venv .venv
. .venv/bin/activate
sh build-project.sh
sh start-project.sh
```

소스는 app/, src/, configs/, scripts/가 저장소 루트에 복원됩니다. .git 이력을 보존하고 기존 파일 내용이 다르면 덮어쓰지 않습니다. 복원 후 소스는 Git 추적 가능한 상태이며 팀원이 feature 브랜치에서 커밋·PR로 반영합니다.

AWS Ubuntu에서는 Python 가상환경과 LightGBM용 libgomp1이 필요합니다. 환경변수/모델은 서버에 별도로 설치합니다. 현재 AWS 서버 생성·HTTPS·외부 접속은 검증되지 않았습니다. 다른 팀원의 수정 파일이 있으면 복원 전에 백업하고 확인하세요.

모델·DB·API 키는 포함하지 않습니다. 외부 OCR/CV/RAG 연결은 별도 작업이며 기존 코드 존재를 기능 완료로 표시하지 않습니다.
