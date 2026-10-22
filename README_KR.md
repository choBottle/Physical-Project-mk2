# OsmoCam 스트림 개조판 사용 설명서

DJI Osmo Nano 라이브뷰를 PC에서 받아 두 갈래로 내보내는 도구.

- **가상 웹캠**: OBS Virtual Camera. Zoom·Unity `WebCamTexture` 등에서 일반 웹캠처럼 선택
- **HTTP 스트림**: MJPEG. 같은 망이나 Tailscale로 연결된 다른 기기에서 URL로 수신

원본은 [luisreysan/osmocam](https://github.com/luisreysan/osmocam) 1.2.1. 비공식 프로젝트이고 DJI와 무관하다. 원본 영문 설명은 `README.md`에 그대로 있다.

---

## 1. 동작 구조

```
Osmo Nano ──BLE(페어링·Wi-Fi 정보)──▶ PC
          ──Wi-Fi(카메라 AP, H.264 720p)──▶ PC ─┬─▶ OBS Virtual Camera
                                                   └─▶ HTTP :38090 (MJPEG)
```

- 카메라 주소는 `192.168.2.1`. 실행하는 동안 PC의 Wi‑Fi 어댑터는 카메라 AP에 붙어 있다
- 출력은 1280×720 30fps 라이브뷰. 4K 녹화 화질이 아님

## 2. 준비물

| 항목 | 내용 |
|---|---|
| OS | Windows 10/11 |
| 무선 | Bluetooth LE + Wi‑Fi 둘 다 켜져 있어야 함 |
| Python | 3.10~3.14 (3.14 권장, 3.15는 일부 패키지 빌드 없음) |
| 가상캠 | OBS Studio 설치만 하면 됨. 실행해 둘 필요 없음 |
| 별도 회선 | 유선 랜, 두 번째 Wi‑Fi 동글, USB 테더링 중 하나. 스트림을 다른 기기로 보내려면 필수 |
| 카메라 | Mimo 앱으로 활성화를 마친 상태 |

## 3. 실행

1. 카메라를 켜고 휴대폰의 DJI Mimo 앱을 종료한다. 카메라는 앱 하나만 받는다
2. 이 폴더에서 `osmocam.bat`을 실행한다. 첫 실행은 가상환경 생성과 패키지 설치로 1분쯤 걸린다
3. 처음 한 번은 카메라 화면에 **"OSMO"** 승인 창이 뜬다. 20초 안에 승인
4. 종료는 콘솔에서 **Ctrl+C**. Wi‑Fi는 원래 네트워크로 돌아간다

실행하면 콘솔에 바로 복사해 쓸 수 있는 주소가 찍힌다. 카메라 Wi‑Fi 접속 직후에 한 번 더 찍히는데, 이때 목록이 실제로 쓸 수 있는 주소다.

```
========================================================================
STREAM URLS
  This PC     http://127.0.0.1:38090/stream
  Tailscale   http://100.101.7.42:38090/stream
  LAN (이더넷) http://192.168.0.23:38090/stream
  Firewall: allow inbound TCP 38090 if another machine can't connect.
  Also: /snapshot.jpg (one frame)  /status (JSON)  / (preview page)
========================================================================
```

기본값으로 모든 어댑터에서 받기 때문에 옵션 없이 실행해도 LAN·Tailscale 주소로 바로 접속된다. `--bind 127.0.0.1`로 실행하면 LAN·Tailscale 주소는 "OFF"로 표시되고 이 PC에서만 볼 수 있다. Tailscale IP는 `tailscale ip -4`로 찾기 때문에 Tailscale이 꺼져 있으면 목록에 안 나온다.

용도별 실행 예시:

```bat
:: 기본: 가상캠 + 모든 어댑터로 스트림 송출 (같은 망·Tailscale에서 접속 가능)
osmocam.bat

:: 이 PC에서만 사용 (LAN 송출 끔)
osmocam.bat --bind 127.0.0.1

:: Tailscale 망에만 송출 (공용 망에 붙어 있을 때 권장)
osmocam.bat --bind 100.x.y.z

:: 가상캠 없이 스트림만
osmocam.bat --no-vcam

:: 대역폭 줄이기
osmocam.bat --stream-fps 15 --jpeg-quality 60
```

## 4. 옵션

### 개조판에서 추가한 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--bind ADDR` | `0.0.0.0` | HTTP 서버가 받을 주소. 기본은 모든 어댑터, `127.0.0.1`이면 이 PC만, 특정 IP를 주면 그 어댑터만 |
| `--stream-fps N` | `0` | 클라이언트별 MJPEG 프레임 상한. 0이면 들어오는 대로 전부(최대 30) |
| `--jpeg-quality N` | `80` | JPEG 화질 1~95. 낮출수록 대역폭 감소 |

### 원본 옵션

| 옵션 | 설명 |
|---|---|
| `--no-vcam` | 가상캠 없이 HTTP만 |
| `--preview-port N` | HTTP 포트. 기본 38090, 0이면 끔 |
| `--scan` | 주변 Osmo 카메라 목록만 출력하고 종료 |
| `--address ADDR` | 특정 카메라 지정 (`--scan` 결과의 주소) |
| `--interface NAME` | 카메라에 붙일 Wi‑Fi 어댑터. 예: `"Wi-Fi 2"` |
| `--home NETWORK` | 종료 후 돌아갈 Wi‑Fi 이름 |
| `--stall N` | N초 동안 영상이 없으면 라이브뷰 재시작. 기본 3 |
| `--help` | 전체 옵션 |

Wi‑Fi 어댑터가 두 개라면 `--interface`로 카메라용을 지정하고 나머지 하나로 망 연결을 유지한다.

포트가 이미 쓰이고 있으면 `--preview-port`로 바꾼다. 사용 중인지 확인은 `netstat -ano | findstr :38090`. Windows가 Hyper-V·WSL용으로 예약한 범위에 걸리면 바인딩이 실패하니 `netsh int ipv4 show excludedportrange protocol=tcp`로 확인할 것

## 5. HTTP 엔드포인트

| 경로 | 내용 |
|---|---|
| `/` | 브라우저 미리보기 페이지 |
| `/stream` | MJPEG 스트림 (`multipart/x-mixed-replace`) |
| `/snapshot.jpg` | 최신 프레임 한 장. 아직 프레임이 없으면 503 |
| `/status` | JSON 상태값 |

`/status` 응답 예시:

```json
{"frames": 5321, "age_ms": 12, "width": 1280, "height": 720, "stream_clients": 1}
```

`age_ms`는 마지막 프레임이 들어온 뒤 지난 시간이다. 이 값이 1000을 넘기면 영상이 끊긴 것으로 보면 된다. 모든 응답에 CORS(`*`)와 no-cache 헤더가 붙어 있어 브라우저나 WebGL에서 바로 받을 수 있다.

## 6. 받는 쪽 예시

**브라우저**

```html
<img src="http://100.x.y.z:38090/stream">
```

**Python / OpenCV**

```python
import cv2
cap = cv2.VideoCapture("http://100.x.y.z:38090/stream")
while True:
    ok, frame = cap.read()
    if not ok:
        break
    cv2.imshow("osmo", frame)
    if cv2.waitKey(1) == 27:
        break
```

**ffplay / VLC**

```
ffplay -fflags nobuffer http://100.x.y.z:38090/stream
```

**Unity (같은 PC)**

가상캠으로 받는 쪽이 제일 간단하다.

```csharp
var tex = new WebCamTexture("OBS Virtual Camera", 1280, 720, 30);
rawImage.texture = tex;
tex.Play();
```

**Unity (다른 PC)**

`/snapshot.jpg`를 주기적으로 받아 텍스처에 덮어쓰는 방식이 가장 단순하다. 실측 fps는 망 상태에 따라 10~20 정도로 떨어진다.

```csharp
IEnumerator Poll(string url, RawImage target) {
    var tex = new Texture2D(2, 2);
    target.texture = tex;
    while (true) {
        using var req = UnityWebRequest.Get(url);
        yield return req.SendWebRequest();
        if (req.result == UnityWebRequest.Result.Success)
            tex.LoadImage(req.downloadHandler.data);
        yield return null;
    }
}
// StartCoroutine(Poll("http://100.x.y.z:38090/snapshot.jpg", rawImage));
```

30fps를 그대로 받아야 하면 `/stream`을 `DownloadHandlerScript`로 받아 JPEG 경계(`FF D8` ~ `FF D9`)를 잘라 쓰는 방식으로 바꾼다.

## 7. Tailscale로 쓸 때

- 이 PC의 Tailscale IP 확인: `tailscale ip -4`
- 기본값(`0.0.0.0`)이면 Tailscale로도 바로 접속된다. 다만 스트림에 인증이 없어서 같은 망의 누구나 볼 수 있다. 공용 망에 붙어 있다면 `--bind 100.x.y.z`로 Tailscale IP만 지정할 것. 대신 이 PC에서도 `127.0.0.1`이 아니라 Tailscale IP로 접속해야 한다
- **인터넷 회선이 따로 있어야 한다.** Wi‑Fi가 카메라에 묶여 있으니 유선 랜이나 두 번째 어댑터가 없으면 Tailscale도 끊긴다
- `tailscale ping <상대 기기>` 결과가 `via DERP`면 중계 서버를 거치는 상태다. MJPEG 30fps는 수십 Mbps라 중계 경로에선 버벅인다. `--stream-fps`와 `--jpeg-quality`를 낮출 것
- Tailscale ACL을 쓰고 있다면 상대 기기 → 이 PC 38090 포트가 허용돼 있어야 한다

## 8. 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `Bluetooth radio is not powered on` | PC 블루투스가 꺼져 있음. `Win+A`에서 켜고, 없으면 장치 관리자에서 어댑터 사용 설정 |
| `No DJI Osmo camera found` | 카메라를 켜고 가까이 둔다. Mimo 앱 연결을 끊는다. `--scan`으로 확인 |
| approve 단계에서 멈춤 | 카메라 화면의 "OSMO" 승인 (20초 제한) |
| 오류 `0x80342002` | PC Wi‑Fi가 꺼져 있음. 비행기 모드 확인 |
| 다른 기기에서 접속 안 됨 | 방화벽 인바운드 TCP 38090 허용. Tailscale 어댑터가 공용 프로필로 잡혀 있을 수 있으니 공용도 체크 |
| 시작 로그에 LAN 주소가 안 뜸 | 유선 랜이나 두 번째 어댑터가 아직 연결 전. 접속 자체에는 영향 없음 |
| 앱에 OBS Virtual Camera가 안 보임 | OBS 설치 후 그 앱을 재시작 |
| 화면이 멈추거나 검게 나옴 | `/status`의 `age_ms` 확인. 영상이 3초 끊기면 자동으로 라이브뷰를 재시작함 |
| 카메라 발열 | Wi‑Fi 스트리밍 전력 소모. Vision Dock이나 충전기에 연결 |

## 9. 원본 대비 변경 사항

수정한 파일은 `osmocam.py` 하나다. 원본은 같은 폴더의 `osmocam.py.orig`에 있다.

- HTTP 서버 바인딩 주소를 `--bind`로 지정할 수 있게 하고 기본값을 `0.0.0.0`(모든 어댑터)으로 둠 (원본은 127.0.0.1 고정)
- 스트림의 20fps 고정 sleep 제거, `--stream-fps`로 상한 선택
- JPEG를 프레임당 한 번만 인코딩해 모든 클라이언트가 공유. 보는 쪽이 없으면 인코딩하지 않음
- `--jpeg-quality` 추가
- `/status` 엔드포인트, CORS·no-cache 헤더 추가
- 시작 로그에 LAN 스트림 주소 출력 (카메라 대역 192.168.2.x 제외)
- 시작할 때 접속 주소를 완성된 형태로 출력. 이 PC의 LAN IP(어댑터 이름 포함)와 Tailscale IP를 자동 탐지하고, 카메라 Wi‑Fi에 붙은 뒤 한 번 더 출력
- 기본 포트를 8090에서 38090으로 변경. 8090은 다른 개발 서버와 자주 겹치기 때문. 예전처럼 쓰려면 `--preview-port 8090`

가상캠 경로와 BLE·Wi‑Fi 연결 로직은 손대지 않았다.

원래대로 되돌리려면 `osmocam.py`를 지우고 `osmocam.py.orig`의 이름을 `osmocam.py`로 바꾸면 된다.

## 10. 주의

- 카메라 펌웨어가 업데이트되면 동작하지 않을 수 있다. 쓸 만하면 펌웨어 업데이트를 미룰 것
- 카메라 Wi‑Fi 비밀번호 등 연결 정보는 `%LOCALAPPDATA%\osmo-pc\cameras.json`에 저장된다
- 라이선스는 원본과 같은 MIT. pyvirtualcam은 GPL-2.0 (`NOTICE.md` 참고)
