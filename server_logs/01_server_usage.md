# 외부 서버 사용 내역

## SERVER_01
- 팀 / 제출자 ID: 당NO life / MEMBER_01 (팀장 별칭; 행사 플랫폼 ID는 등록 정보로 확인)
- 서버 유형 / OS: AWS EC2, 서울 리전, t3.micro / Ubuntu 24.04.4 LTS, Linux 6.17.0-1017-aws x86_64
- 사용 목적: 웹·API 배포, 현재·미래 위험 선별 모델 추론, 챌린지
- 접속 방식: EC2 Instance Connect 웹 터미널 / SSH, AWS 관리형 임시 공개키
- 모델·서비스: 현재 knhanes-today14-sk180-service-v3, 미래 rf25-tuned-education4-v2 (기존 모델 자산); Nginx HTTPS, Let's Encrypt, DNS. OCR·RAG 외부 API 사용 여부·건수는 이번 수집으로 확인하지 않음.
- 수집 요청 범위: 2026-10-09T00:00:00+09:00 ~ 2026-10-09T14:51:42+09:00. 행사일 검색 구간이며 작업 시작을 자정으로 주장하지 않음.
- 실제 성공 인증 관찰 범위: 2026-10-09T04:12:14+00:00 ~ 2026-10-09T05:50:30+00:00 (UTC; KST 13:12:14~14:50:30)
- 수집 시각 / 시간대: 2026-10-09T14:51:42+09:00 / +09:00
- 배포 코드 SHA: 84ae89e9647c16520e7cad2234ffec37d4de745e; DEPLOYED_COMMIT.json 선언 및 릴리스 식별자 일치. .git 부재로 git rev-parse 실패(exit 128).
- 배포 코드 변경 여부: working tree 확인 불가. RUNTIME_FIXES 58개·CORE_FEATURE_FIXES 5개 파일 after SHA-256 및 패치 해시 일치. 전체 파일 무변경을 증명하지 않음.
- 외부 확인: HTTPS /api/health HTTP 200, 프로젝트 systemd active/running.
- 원본 보관: 서버의 저장소 밖 비공개 증빙 폴더에 원본 성공 인증 발췌·별칭 대응표·수집 결과 보관(디렉터리 700, 파일 600). 지정 검토자·전달 경로·보관기한은 운영진 확정 후 적용.
- 원본 성공 인증 발췌 SHA-256: c8ad1236c5fd5a9497e76cc5eec0e8bae8ad3ec792c27f45e50ff1f88fd79f9e (IP 해시가 아님)
- 가명처리: SERVER_01, MEMBER_01, ACCOUNT_01, IP_01, KEY_01~KEY_03. timestamp/결과/프로토콜/PID/포트 유지.
- 접근 가능 사용자: 사용자 확인에 따르면 팀장만 접근 가능. 팀원·공유 계정 접근 없음. AWS IAM 전체 권한 감사는 미수행.
- 임시 키: EC2 Instance Connect 접속별 키 지문 3종은 서로 다른 사람을 의미하지 않음.
- 출발 IP: 게스트 SSH의 AWS 중계 주소이며 개인 단말 IP·신원을 뜻하지 않음.
- 누락·제한: 성공 인증만 수집; 세션 종료·작업 내역·AWS 콘솔 로그인/CloudTrail 미수집. journalctl exit 0, stderr 없음. 최초 관찰 이전/로테이션 범위의 완전성 확인 불가. 수집 이후 및 17:00 마감까지 미포함.
- 수집 방법: journalctl -t sshd -t sshd-session, short-iso, 위 구간의 해당 계정 Accepted publickey/password/keyboard-interactive 줄만 발췌. 기존 읽기 권한 사용; 권한·로깅 변경 없음.
- 복수 서버: 이번 수집 대상은 SERVER_01 한 대.
- 금지 정보: .env, API 키, 비밀키, 쿠키, 프로세스 인자, 전체 히스토리, 무관한 계정 기록 미수집.

## 제출 해석
배포 SHA와 증빙 커밋 SHA는 별개다. 증빙 SHA는 이 파일을 추가한 GitHub PR/병합 기록에서 확인한다.
공개본에는 서버 주소·실계정·실명·실IP·내부 경로를 포함하지 않는다. 공개 서비스 링크는 PR 설명과 제출 플랫폼에 기재한다.
외부 서버 증빙 제출 가이드(2026-10-09 확인)는 규격 초안이다. 보완 기한과 원본 전달 정책은 운영진 공지가 우선이다.
