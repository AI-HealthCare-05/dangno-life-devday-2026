# AWS / www.dang-no.life

공유·제출 주소: https://www.dang-no.life

코드 기준: 이 저장소 main. AWS_DEPLOY.sh는 main을 새 릴리스 디렉터리에 내려받고 실제 커밋 SHA를 기록합니다. 실행 코드가 검증된 후 DNS를 변경합니다. 현재 문서·코드는 배포 준비이며 실제 AWS 연결 완료를 의미하지 않습니다.

## 최초 설치

Ubuntu 24.04의 로그인 사용자로 저장소를 clone하고 `bash AWS_DEPLOY.sh`를 실행합니다. EC2 생성·방화벽·DNS 변경은 이 스크립트에 포함하지 않습니다. 앱은 외부에 직접 노출하지 않고 127.0.0.1:8000에서 실행합니다. storage와 모델, .env는 ~/dangno-life/shared/에 유지됩니다. 별도 API 키는 사용자가 shared/.env에 직접 입력하며 출력하거나 Git에 넣지 않습니다.

## DNS와 HTTPS

가비아 DNS의 기존 www CNAME = dang-no.life.를 유지합니다. @ A 레코드 값은 새 서버의 고정 IPv4 주소로 변경합니다. 주소를 임의로 정하지 않으며 이전 A 값과 TTL을 기록합니다. 기존 웹 연결을 바꾸는 작업이므로 새 서버 동작 확인 후 전환합니다.

기존 Nginx 사이트와 충돌이 없는지 확인한 뒤 AWS_NGINX.conf를 /etc/nginx/sites-available/dangno-life에 설치하고 sites-enabled에 연결합니다. `sudo nginx -t`가 성공한 뒤 reload합니다. 웹 80/443만 공개하며 SSH 접근은 관리용으로 제한합니다. 앱·DB 포트는 공개하지 않습니다.

DNS 전파 후 Ubuntu 공식 패키지 certbot/python3-certbot-nginx를 설치합니다. `sudo certbot --nginx -d www.dang-no.life -d dang-no.life`의 약관·계정 등록은 사용자가 확인합니다. HTTPS 리디렉션과 갱신을 확인한 뒤 shared/.env의 ENV를 prod로 바꾸고 `sudo systemctl restart dangno-life`를 실행합니다. HTTP 단계에서는 합성 테스트만 사용합니다.

## 검증 및 업데이트

`/api/health` 200, 외부 HTTPS, 합성 계정의 현재·미래 예측, 챌린지·숲, 재시작 후 DB 유지가 완료 기준입니다. `/api/v1/ready`는 CV 등 추가 기능도 확인하므로 설치 범위에 따라 503일 수 있습니다. OCR/CV/RAG의 실제 연결은 별도 검증합니다.

main 업데이트는 수동으로 AWS_DEPLOY.sh를 다시 실행합니다. GitHub 자동 배포는 아직 연결하지 않았습니다. 코드 전환 전 설치를 끝내고 health 실패 시 이전 코드로 복구합니다. DB 마이그레이션은 자동 복구되지 않으므로 업데이트 전 DB 백업과 별도 호환성 검토가 필요합니다. 최초 설치 실패는 서버 로그를 확인합니다. 원본 의료자료·API 키·모델 바이너리·DB는 커밋하지 않습니다.
