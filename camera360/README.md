# camera360

360도 카메라(Insta360 Pro2) 촬영·스트리밍·장애물 검출 스크립트 모음.
자세한 운용 절차는 이 폴더의 날짜별 문서(`26xxxx_*.md`)를 본다. `구버전(참고금지)/` 는 보관용이라 참고하지 않는다.

## 주소·경로 설정

코드에는 특정 서버 주소·테일넷 이름·홈 경로를 박아 두지 않는다. 아무것도 설정하지 않으면
전부 `127.0.0.1`(localhost)과 스크립트 폴더 기준 상대경로로 동작한다.
실제 배포 주소는 환경변수로 준다 — 목록과 설명은 [`.env.example`](.env.example).

```bash
cp .env.example .env          # 값 채우기 (.env 는 커밋하지 않는다)
set -a && . ./.env && set +a  # 현재 셸에 올리기
```

| 변수 | 쓰는 곳 | 기본값 |
|---|---|---|
| `MK2_SERVER_HOST` | `stream_to_server.py`, `upload_equirect.py`, `anchor360_bridge.py`, `pro2_auto_bg.py` | `127.0.0.1` |
| `MK2_UPLOAD_URL` | `stream_to_server.py`(첫 번째 업로드), `pro2_auto_bg.py` | `http://$MK2_SERVER_HOST:7866/upload_pano` |
| `MK2_UPLOAD_STREAM_URL` | `stream_to_server.py`(두 번째 업로드), `upload_equirect.py` | `http://$MK2_SERVER_HOST:10001/upload_pano` |
| `MK2_ANCHOR360_URL` | `anchor360_bridge.py` | `http://$MK2_SERVER_HOST:7866/anchor360_latest` |
| `MK2_TWIN_HOSTS` | `anchor360_live.py` 장애물 UDP 받는 곳. 쉼표로 여러 곳(Unity와 다른 뷰어), 곳마다 `:포트` | `--unity-ip` 기본값 |
| `CONFIG_PATH` | `unidepth_dual_yolo.py` | 스크립트 옆 `unidepth_dual_yolo_config.yaml` |
| `CONTROL_URL` | `unidepth_dual_yolo.py` | `http://127.0.0.1:7864/command/go1` |
| `MK2_REDIS_PASSWORD` | `unidepth_dual_yolo.py` | 없음(config `redis.password`, 기본 빈 값) — 비밀값, 커밋 금지 |
| `MK2_CAPSTONE_DB` | `venv_image_requirements.txt`(editable 설치 경로) | 없음 — 설치 시 필수 |

- 명령줄 인자(`--upload`, `--server` 등)는 그대로 쓸 수 있고 환경변수보다 우선한다.
- `unidepth_dual_yolo_config.yaml` 의 모델 경로는 yaml 파일 폴더 기준 상대경로다. 절대경로·`~/` 로 바꿔도 된다.
- Insta360 Pro2가 아닌 360 카메라는 `upload_equirect.py`로 올리고, 검출 모델은 config `models.zeroshot_detector.backend`로 바꾼다. [docs/deployment/pluggability.md](../docs/deployment/pluggability.md)
- 문서 속 `<server-ip>`, `<tailscale-ip-*>`, `<tailnet-host-*>`, `~/` 는 각자 환경의 값으로 바꿔 읽는다.

## 설치

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt                          # 촬영 · 전송 · 수신
pip install -r requirements.txt -r requirements-vision.txt   # + 비전 추론 서버(GPU)
```

`venv_image_requirements.txt` 는 운영 비전 서버의 `pip freeze` 전체 기록이다(재현 참고용).
