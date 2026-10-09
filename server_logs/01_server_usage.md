# 외부 서버 사용 내역

## SERVER_01
- 팀 / 제출자 ID: 당NO Life / MEMBER_01 (팀장 별칭; 행사 참가자 ID는 플랫폼 등록 정보로 확인)
- 서버 유형 / OS: AWS EC2, 서울 리전, t3.micro / Ubuntu 24.04.4 LTS, Linux 6.17.0-1017-aws x86_64
- 사용 목적: 웹·API 배포, 현재·미래 위험 선별 모델 추론, 챌린지.
- 접속 방식: EC2 Instance Connect 웹 터미널 / SSH, AWS 관리형 임시 공개키.
- 모델·서비스: 현재 knhanes-today14-sk180-service-v3, 미래 rf25-tuned-education4-v2 (기존 모델 자산); Nginx HTTPS, Let's Encrypt, DNS. 이번 수집은 모델 실행 및 OCR·RAG 호출 여부·건수를 재검증하지 않음.
- 로그 검색 구간: 2026-10-09T00:00:00+09:00 ~ 2026-10-09T16:31:40+09:00. 행사일 전체 검색이며 자정부터 작업했다는 의미가 아님. 실제 작업 시작 시각은 별도 확정하지 못함.
- 실제 성공 인증 관찰 범위: 2026-10-09T04:12:14+00:00 ~ 2026-10-09T06:24:48+00:00 (UTC; KST 13:12:14~15:24:48), 성공 인증 4건.
- 수집 시각 / 시간대: 2026-10-09T16:31:40+09:00 / +09:00.
- 배포 코드 기본 SHA: a8a4d20a861dddb45147bb969d687867f52b9a72.
- 선택 적용: 5017d3f9137ffab963c2f9feb04afe4a7e69ea2f의 src/frontend/intro-retro.html·retro-intro.css, 이후 9bc81dd8c063a586db79f7d158899daa410597ac의 src/frontend/retro-intro.css. DEPLOYED_COMMIT.json 두 단계 선언으로 확인. 단일 최신 main 전체 배포를 주장하지 않음.
- 변경 여부: .git 부재로 git rev-parse/status 실패(exit 128); clean 여부 확인 불가. 현재 RUNTIME_FIXES 63개·CORE_FEATURE_FIXES 5개 파일 after SHA-256 및 패치 해시 일치. 전체 소스 무변경을 증명하지 않음.
- 서비스 상태: 공개 HTTPS /api/health HTTP 200, 프로젝트 systemd active/running, 프로젝트 프로세스 7333 python.
- 원본 보관: 저장소 밖 서버 비공개 증빙 폴더에 원본 성공 인증 발췌·별칭 대응표·수집 결과를 접근 제한(디렉터리 700, 파일 600)하여 보관. 기존 원본도 유지. 원본 전달 대상·경로·보관기한은 운영진 확정 필요.
- 원본 성공 인증 발췌 SHA-256: df8699d3458d145fdcce31f257ebc0ded03be3b68c4b4e549be14388ccb655f2 (IP 해시가 아님).
- 가명처리: SERVER_01, MEMBER_01, ACCOUNT_01, IP_01~IP_02, KEY_01~KEY_04. 기존 별칭을 유지하고 새 접속 식별자에 추가 별칭 부여. 시각·결과·프로토콜·PID·포트 유지.
- 허용 접근자: 팀장만 접근 가능하다는 사용자 확인에 기반. 팀원·공유 계정 접근 없음. AWS IAM 전체 권한 감사는 미수행.
- IP·키 해석: 출발 IP는 EC2 Instance Connect 중계 주소이며 개인 단말 신원 증거가 아님. 임시 키 4종은 4명의 사용자를 의미하지 않음.
- 수집 방법: journalctl -t sshd -t sshd-session, short-iso; 해당 계정 Accepted publickey/password/keyboard-interactive 줄만 발췌. journalctl exit 0, 경고 없음. 기존 읽기 권한 사용; 로깅·권한 변경 없음.
- 누락·제한: 성공 인증만 수집. 세션 종료·작업 내용·AWS 콘솔 로그인/CloudTrail 미수집. 최초 관찰 이전 및 로테이션 범위 완전성 확인 불가. 수집 시각 이후와 17:00 마감까지 기록은 미포함. 플랫폼/웹 콘솔 증빙은 이번 SSH 발췌만으로 대체되지 않음.
- 복수 서버: 이번 수집 대상 SERVER_01 한 대.
- 금지 정보: .env, API 키, 비밀키, 토큰, 쿠키, 프로세스 인자, 전체 명령 히스토리 및 무관한 계정 기록을 수집·제출하지 않음.

## 제출 해석
배포 코드 기본 SHA·선택 적용 SHA와 증빙 커밋 SHA는 별개입니다. 증빙 커밋은 이 갱신 PR/병합 기록에서 확인합니다.
공개 저장소에는 가명본 5개 파일만 제출합니다. 원본·가명 매핑·내부 경로·실명·실계정·실IP·키 지문은 포함하지 않습니다.
가이드 확인일: 2026-10-09. 가이드는 제출 규격 초안이며 보완기한·마지막 수집 시점·원본 제공 정책은 운영진 공지가 우선입니다.
