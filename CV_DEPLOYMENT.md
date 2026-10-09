# CV CPU 런타임 배포

현재 서버의 식단 CV가 준비되지 않은 원인은 모델 3개와 torch/timm/LiteRT 미설치, Drive 번들 환경설정 누락이다. OpenAI 보조 판별 활성화만으로 로컬 CV를 대신하지 않는다.

## 준비 및 검증

Ubuntu/Python 3.12 기준. API 환경변수와 모델을 Git에 넣지 않는다. 모델은 기존 공유 `models/artifacts` 경로를 사용한다. 디스크 여유 최소 2GiB를 확보한다. CPU 패키지만 설치하며 CUDA 패키지를 설치하지 않는다.

```sh
.venv/bin/python -m pip install --no-cache-dir -r CV_REQUIREMENTS.txt
.venv/bin/python CV_BOOTSTRAP.py
```

공개 모델 전달 경로에서 파일을 내려받고 기존 모델 레지스트리의 SHA-256 3개를 모두 검증한 후 배치한다. 실제 분류기와 세그멘터를 로드하고 합성 이미지로 추론한다. 합성 이미지 검증은 음식 인식 정확도 평가가 아니다. 키를 조회하거나 외부 VLM에 이미지를 전송하지 않는다.

성공 후 서비스를 재시작하고 `/api/v1/ready`의 `food_vision_ready=true`, 식사 사진 업로드 및 사용자 확인 흐름을 점검한다. `--check-only`는 다운로드 없이 모델 검증과 실제 추론만 수행한다.

```sh
.venv/bin/python CV_BOOTSTRAP.py --check-only
sudo systemctl restart dangno-life
curl --fail http://127.0.0.1:8000/api/v1/ready
```

1GiB 메모리 인스턴스에서는 추론을 한 번에 하나씩 수행하고 OOM·응답 시간을 관찰한다. 운영 이미지나 사용자 사진은 커밋하지 않는다. 런타임 검증 실패 시 준비 완료로 표시하거나 개발용 판별로 우회하지 않는다.

## 검증

`python3 CV_BOOTSTRAP_TEST.py`: 마지막 파일 체크섬 실패 시 기존 모델 3개 보존 및 검증된 캐시의 네트워크 호출 방지.
