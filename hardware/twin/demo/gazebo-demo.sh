#!/bin/bash
# 트윈 시연 — 컨테이너 안에서 돈다 (run-demo.sh 가 띄운다). 저장소는 /repo (읽기 전용).
#   Gazebo(가상 화면 + noVNC 6080) · 트윈 게이트웨이 · 로봇 상태 중계 · 시뮬 로봇 노드(중앙 MQTT)
# 필요: ROS 2 Jazzy + Gazebo Harmonic 이 든 이미지, 중앙 스택 네트워크(mosquitto · otel-collector).
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq xvfb imagemagick x11vnc novnc python3-websockify xdotool >/dev/null
# 데비안이 깔아 둔 패키지와 겹쳐 실패하므로 --ignore-installed (버리는 컨테이너다)
pip install -q --break-system-packages --ignore-installed \
  paho-mqtt opentelemetry-sdk opentelemetry-exporter-otlp psutil protobuf >/tmp/pip.log 2>&1 || echo "pip 실패 — /tmp/pip.log"
source /opt/ros/jazzy/setup.bash >/dev/null 2>&1 || true
# 소프트웨어 렌더링(llvmpipe) 스레드를 묶는다. 안 묶으면 GUI 가 코어를 다 써서 서버 서비스 호출이 시간 초과된다.
export LP_NUM_THREADS=2 GZ_IP=127.0.0.1 LIBGL_ALWAYS_SOFTWARE=1 QT_QPA_PLATFORM=xcb DISPLAY=:1
Xvfb :1 -screen 0 1600x900x24 >/tmp/xvfb.log 2>&1 &
sleep 2
gz sim -r -v 1 empty.sdf --render-engine-gui ogre >/tmp/gz.log 2>&1 &
for i in $(seq 1 90); do gz service -l 2>/dev/null | grep -q /world/empty/create && break; sleep 1; done

python3 -u /repo/hardware/twin/twin_gateway.py --listen robots=25201 anchor360=25010 go1=25009 \
  --sink gazebo:empty --sink udp:127.0.0.1:25500 >/tmp/gw.log 2>&1 &
python3 -u /repo/hardware/pi/robot/robot_state_relay.py --node_id pi-demo --unity_ip 127.0.0.1:25201 \
  --ingress_port 15200 --log_sec 0 >/tmp/relay.log 2>&1 &

cd /repo/hardware/pi
HW_ENTITY_ID=go1-demo HW_ENTITY_TYPE=robot HW_DEVICE_TYPE=go1_robot HW_ZONE_ID=zoneA \
HW_CONTROLLER_LINK=sim HW_MEDIA_SENDER=none HW_BROKER_HOST=mosquitto \
HW_OTEL_ENDPOINT=http://otel-collector:4317 HW_SPOOL_PATH=/tmp/spool.jsonl \
HW_ENTITY_ID_FILE=/tmp/none HW_ZONE_ID_FILE=/tmp/none \
HW_TWIN_RELAY_HOST=127.0.0.1 HW_TWIN_RELAY_PORT=15200 PYTHONUNBUFFERED=1 \
  python3 -m robot.robot_node >/tmp/robot.log 2>&1 &
sleep 8
# 임무를 주면 시뮬 로봇이 원을 그리며 달린다 (중앙 MQTT 의 규약 명령 경로)
timeout 20 python3 -m bench.send_physical_command --broker mosquitto --device go1-demo \
  --action assign_mission --param mission_id=1 --param subtask=1 >/tmp/cmd.log 2>&1 || true

x11vnc -display :1 -forever -shared -nopw -localhost -rfbport 5900 -quiet >/tmp/vnc.log 2>&1 &
sleep 1
websockify --web /usr/share/novnc 6080 localhost:5900 >/tmp/ws.log 2>&1 &
W=$(xdotool search --name "Gazebo Sim" | head -1); xdotool windowmove "$W" 0 0 windowsize "$W" 1600 900
gz service -s /gui/move_to/pose --reqtype gz.msgs.GUICamera --reptype gz.msgs.Boolean --timeout 5000 \
  --req "pose: {position: {x: -1.5, y: 2.5, z: 17}, orientation: {x: -0.5, y: 0.5, z: 0.5, w: 0.5}}" >/dev/null
echo "트윈 시연 준비됨 — http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale"
sleep infinity
