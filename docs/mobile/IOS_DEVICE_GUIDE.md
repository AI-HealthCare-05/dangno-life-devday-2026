# 개인 iPhone 구동

## CSS 수정 화면을 시뮬레이터에서 바로 확인하기

아래 명령은 **개발 중에만** 사용한다. 저장소 루트에서 터미널 두 개를 열고, 첫 번째 터미널은 계속 켜 둔다.

```sh
# 터미널 1: 원본 CSS 감시·개발 서버
pnpm dev:ios:web

# 터미널 2: iOS 앱에 개발 서버 연결 (처음 한 번)
pnpm sync:ios
pnpm dev:ios:connect
```

Xcode에서 iOS 시뮬레이터를 선택하고 Run을 누른다. VS Code에서 **iOS 전용** `src/frontend/mobile/ios.css`를 수정·저장하면 시뮬레이터의 스타일시트가 자동 갱신된다. Android는 기존 `mobile.css`를 사용한다. 공통 `src/frontend/styles.css`와 `src/frontend/navigation.css`도 감시한다. HTML·JavaScript·이미지 변경, 네이티브 설정 변경은 이 CSS 전용 감시 대상이 아니므로 `pnpm sync:ios` 후 다시 실행한다. 개발 서버를 종료하면 앱은 그 서버에 접속할 수 없으므로, 일반 실행으로 돌아갈 때는 `pnpm sync:ios`로 번들 설정을 복원하고 Xcode에서 재실행한다.

iOS 앱의 생년월일은 영어 월 선택창 대신 숫자 8자리(예: `19711009`)로 직접 입력한다. 점·하이픈을 넣어도 입력 완료 시 서버 형식(`1971-10-09`)으로 정리된다. 유효하지 않은 날짜는 제출되지 않는다. Android와 브라우저의 기존 날짜 선택기는 유지한다.

상단 간당간당 로고는 어느 서비스 단계에서 눌러도 레트로 인트로를 다시 연다. 로그인된 경우에도 인트로 재생 요청(`intro=replay`)은 서비스 홈으로 자동 이동하지 않는다.

iOS 레트로 인트로에서는 하단의 별도 '시작' 이동 바를 숨긴다. 로그인·회원가입 화면에서도 인트로와 같은 간결한 상단바 배치를 유지한다.

iOS 상단바는 스크롤 중에도 안전 영역 바로 아래에 고정한다. 키보드가 열려 화면이 이동하면 보이는 영역의 위쪽 오프셋도 반영한다. 인트로 외 화면은 실제 상단바 높이만큼 본문 여백을 자동으로 확보한다.

당근의 숲 전체 화면에는 서비스 상단바가 없으므로 해당 높이만큼의 본문 여백을 적용하지 않는다. 실기기에서 상태 표시줄 아래 큰 빈 공간 없이 게임 화면이 이어지는지 확인한다.

iPhone 너비에서는 주요 메뉴 5개와 가입 후 단계 메뉴 3개를 각각 전체 너비의 균등 칸에 가운데 정렬한다. 이용확인 나무판은 화면 너비 기준으로 가운데 배치한다.

'글자 크게'를 켜도 iOS 상단바의 로고·계정 버튼은 기존 좌우 배치를 유지한다. 상단 조작 버튼만 폭과 글자 크기를 제한해 로고를 덮지 않게 한다.

긴급 증상 등 이용확인 안전 안내창은 나무판 내부가 아닌 화면 기준 팝업으로 표시한다. 작은 iPhone에서도 버튼과 긴 문구가 좌우로 잘리지 않고 팝업 내부를 스크롤할 수 있어야 한다.

이 명령은 `127.0.0.1`에만 바인딩하므로 Mac의 iOS 시뮬레이터용이다. 실제 iPhone은 별도의 네트워크·iOS 보안 설정이 필요하며 여기서는 지원하지 않는다. 운영용 `capacitor.config.json`에는 개발 서버 주소를 저장하지 않는다.

**팀원의 Mac에서 수행할 가이드다. 이 PR 작업 환경에서는 iOS 컴파일·서명·실기기 검증을 완료하지 않았다.** Android APK를 iPhone에 설치할 수 없으며 Windows에서 Xcode 빌드를 할 수 없다.

## 1. 준비

- macOS에서 Xcode 26 이상과 Command Line Tools를 설치한다. 프로젝트 최소 기기 버전은 iOS 15이다.
- [공통 준비](README.md#공통-준비)로 PR 브랜치·Node 22 이상·pnpm 11.19.0·의존성을 준비한다.
- Xcode → Settings → Apple Accounts에서 자신의 Apple Account에 로그인한다.
- iPhone을 Mac에 연결하고 '이 컴퓨터를 신뢰'를 허용한다. iOS 16 이상은 설정 → 개인정보 보호 및 보안 → 개발자 모드를 켜고 재시작한다.

공식 안내: [Capacitor 환경](https://capacitorjs.com/docs/getting-started/environment-setup), [Apple 실제 기기 실행](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices).

## 2. API 주소 선택

기존 서버가 정상 운영 중이면 기본 HTTPS 주소로 빌드할 수 있다. 비활성화되어 있으면 [개발 HTTPS 서버 연결](TEAM_HANDOFF.md#ios-및-팀-공유용-https-api)을 먼저 준비한다.

**iPhone의 `127.0.0.1`은 Mac이나 Windows PC가 아니다. ADB reverse는 iOS에서 사용할 수 없다.** 유효한 HTTPS API를 선택한다. 현재 코드가 비루프백 HTTP를 거부하므로 `http://192.168...` 주소로 바꾸거나 광범위한 ATS 예외를 추가하지 않는다.

```sh
export MOBILE_API_ORIGIN='https://팀에서-정한-API-호스트'
pnpm build:mobile:deployment
pnpm exec cap sync ios
pnpm exec cap open ios
unset MOBILE_API_ORIGIN
```

기본 `https://www.dang-no.life`를 쓰려면 `export`·`unset`만 생략한다. 프로젝트는 Swift Package Manager를 사용하므로 CocoaPods는 기본 실행에 필요 없다. `cap sync ios`가 생성 자산과 pnpm 플러그인 경로를 다시 연결한다. 체크아웃만 하고 바로 Xcode를 열면 `public` 또는 플러그인이 없을 수 있다.

## 3. 서명 및 기기 설치

1. Xcode에서 `src/frontend/native/ios/App/App.xcodeproj`를 연다. scheme `App`과 연결한 실제 iPhone을 선택한다.
2. Target `App` → Signing & Capabilities에서 Automatically manage signing을 켜고 자신의 Team 또는 Personal Team을 지정한다.
3. Bundle Identifier 충돌 시 자신의 고유 ID로 변경한다. 공용 ID `life.dangno.app` 변경은 개인 로컬 설정으로 관리하고 팀 공용 파일에 임의로 커밋하지 않는다.
4. Run을 누르고 서명·Swift Package 다운로드·설치를 기다린다. 요청되면 개발자 인증서와 앱 실행을 기기에서 허용한다.
5. 카메라·사진·개발 서버 로컬 네트워크 권한 안내를 확인하고 필요 권한을 허용한다.

무료 Personal Team으로 자신의 기기에 설치할 수 있으나 프로비저닝은 7일 후 만료되어 재빌드·재설치가 필요하다. 여러 팀원에게 TestFlight로 배포하려면 Apple Developer Program과 App Store Connect를 별도로 준비한다. [Apple Personal Team 안내](https://developer.apple.com/help/account/basics/about-your-developer-account).

## 4. 실기기 확인

- 첫 실행·로그인·숲 진입·서비스 홈 복귀·로그아웃·앱 종료·재실행·토큰 만료를 각각 시험한다. sessionStorage 기반 페이지 이동 유지와 OS 종료 이후 장기 로그인 유지는 구분한다.
- 오늘이/내일이 서버 결과·수치·SHAP 표시, 챌린지 촬영·선택·취소·권한 거부·제출·재시도 확인.
- 건강정보 입력 OCR은 외부 OCR 공급자 설정이 있어야 실제 사진 추출이 된다. 동의·미리보기·반영·제출을 확인한다.
- 노치·홈 인디케이터·키보드·큰 글자·가로/세로·인트로 스크롤·숲 화면·아바타 렌더링 확인.
- HealthKit·푸시 알림·백그라운드 동기화는 이번 PR에서 실제 연동을 제공하지 않는다.

Mac이 없는 팀원은 팀의 Mac 담당자가 기기별 서명을 준비하거나 TestFlight 배포를 진행해야 한다. 모바일 웹으로 화면을 확인할 수 있지만 네이티브 설치·권한·성능 검증을 대신하지는 않는다.
# iOS 팝업 표시 확인

iOS에서 글자 크기를 키운 뒤 기본정보 수정, 긴급 증상 확인, 진단 도움말, 기록 팝업을 열어 화면 좌우 밖으로 내용이나 버튼이 잘리지 않는지 확인합니다. 긴 내용은 팝업 내부에서 스크롤되어야 하고 상태 표시줄과 하단 홈 인디케이터를 가리지 않아야 합니다. 긴급 안내 결과도 같은 기준으로 확인합니다.
