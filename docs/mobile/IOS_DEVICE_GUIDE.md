# 개인 iPhone 구동

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
