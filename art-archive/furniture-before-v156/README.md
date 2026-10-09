# v156 교체 전 가구 원본 보관

2026-09-08, 사용자의 요청으로 `src/frontend/assets/furniture-v153/`의 PNG 24개를 수정 없이 복사했다.

- 이 폴더는 디자인 보관용이며 게임에서는 직접 참조하지 않는다.
- 모닥불(`campfire.png`)과 분수(`animated_fountain.png`)는 교체 대상에서 제외하여 게임에서도 v153 원본을 계속 사용한다.
- 다른 가구의 새로운 픽셀 그림은 `src/frontend/assets/furniture-v156/`에 있다.
- 24개 파일이 각각 v153 원본과 바이트 단위로 같은지 회귀 테스트에서 확인한다.
- 원본 v153 폴더도 삭제하지 않았다. 이 보관본과 Git 이력으로 이전 디자인을 복원할 수 있다.

생성/교체 이력: `docs/FOREST_ART_V156.md`.
