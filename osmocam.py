#!/usr/bin/env python3
"""OsmoCam: use a DJI Osmo camera as a webcam over Wi-Fi (unofficial).

    osmocam.bat / ./osmocam.sh             # the virtual camera + the MJPEG stream on every adapter, port 38090
    osmocam.bat / ./osmocam.sh --no-vcam   # preview page only (no virtual camera needed)
    osmocam.bat / ./osmocam.sh --scan      # list the DJI Osmo cameras nearby and exit
    osmocam.bat / ./osmocam.sh --bind 127.0.0.1 # this computer only, nothing on the LAN

The camera's live view (H.264, 1280x720 at 30 fps) arrives over the camera's own Wi-Fi access point and
is sent to a virtual camera, which Zoom, Teams, Meet and others can select: "OBS Virtual Camera" on
Windows and macOS (OBS Studio must be installed), a v4l2loopback device on Linux.

The first time, the camera asks to approve "OSMO" on its screen. While OsmoCam runs, the computer's Wi-Fi
is joined to the camera, so internet has to come from another adapter (Ethernet, USB tethering or a
second Wi-Fi adapter). Ctrl+C stops it and puts the Wi-Fi back on the previous network.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import av
import numpy as np
from bleak.exc import BleakError

from camlink import ble, datalink, models, wifi
from camlink.registry import DEFAULT_TRANSPORT, CameraRegistry, other_transport
from camlink.util import fine_timer, log
from camlink.video import VideoDecoder

# The OBS Virtual Camera on Windows and macOS; on Linux, a v4l2loopback device (see the README).
SYSTEM = "linux" if sys.platform.startswith("linux") else sys.platform
VCAM_BACKEND = "v4l2loopback" if SYSTEM == "linux" else "obs"
VCAM_HINTS = {
    "win32": "install OBS Studio (it does not need to be open)",
    "darwin": "install OBS Studio 30 or newer, click Start Virtual Camera in it once and allow its system "
              "extension (System Settings > Privacy & Security), then start OsmoCam again",
    "linux": "load v4l2loopback: sudo modprobe v4l2loopback devices=1 exclusive_caps=1 card_label=OsmoCam",
}
LIVE_VIEW_SIZE = (1280, 720)        # the camera's live view; other sizes are scaled (and letterboxed) to it


class Latency:
    """Rolling latency, in ms, from the first packet of a frame to the frame leaving for the webcam."""

    def __init__(self) -> None:
        self._samples: list[float] = []
        self._lock = threading.Lock()

    def add(self, ms: float) -> None:
        with self._lock:
            self._samples.append(ms)

    def drain(self) -> tuple[float, float]:
        """(median, 95th percentile) of the samples since the last call."""
        with self._lock:
            samples, self._samples = sorted(self._samples), []
        if not samples:
            return 0.0, 0.0
        return samples[len(samples) // 2], samples[min(len(samples) - 1, int(len(samples) * 0.95))]


class Outputs:
    """Sends decoded frames to the virtual camera and keeps the latest one for the preview page."""

    def __init__(self, use_vcam: bool, fps: int) -> None:
        self.use_vcam = use_vcam
        self.fps = fps
        self.cam = None
        self.latest: av.VideoFrame | None = None
        self.seq = 0
        self.cond = threading.Condition()
        self.latency = Latency()
        self._vcam_lock = threading.Lock()   # the decoder thread sends while the main thread may close
        self._closed = False
        self.last_frame_time = 0.0
        self.jpeg_quality = 80
        self._jpeg_lock = threading.Lock()
        self._jpeg_seq = -1
        self._jpeg: bytes = b""
        self.stream_clients = 0          # MJPEG clients connected right now
        self.stream_parts = 0            # JPEGs sent to all of them so far
        self.stream_bytes = 0
        self._stream_lock = threading.Lock()

    def count_sent(self, size: int) -> None:
        with self._stream_lock:
            self.stream_parts += 1
            self.stream_bytes += size

    def jpeg(self, frame: av.VideoFrame, seq: int) -> bytes:
        """The frame as JPEG, encoded once per frame however many clients are watching. Encoding only
        happens when someone asks, so the virtual camera path pays nothing when nobody streams."""
        with self._jpeg_lock:
            if seq != self._jpeg_seq:
                buffer = io.BytesIO()
                frame.to_image().save(buffer, "JPEG", quality=self.jpeg_quality)
                self._jpeg, self._jpeg_seq = buffer.getvalue(), seq
            return self._jpeg

    def on_frame(self, frame: av.VideoFrame, first_packet: float = 0.0) -> None:
        if self.use_vcam:
            self._to_vcam(frame)
        if first_packet:
            self.latency.add((time.perf_counter() - first_packet) * 1000)
        with self.cond:
            self.latest = frame
            self.seq += 1
            self.last_frame_time = time.monotonic()
            self.cond.notify_all()

    def open_vcam(self) -> None:
        """Open the virtual camera before connecting to the camera. Opening it can take several seconds,
        and fails when it is missing (macOS takes ~13 s to say so): done while video flows, that stalls the
        live view. Without it, OsmoCam carries on with the preview page only."""
        if not self.use_vcam:
            return
        import pyvirtualcam

        width, height = LIVE_VIEW_SIZE
        log("Opening the virtual camera...")
        try:
            cam = pyvirtualcam.Camera(width, height, self.fps, fmt=pyvirtualcam.PixelFormat.I420, backend=VCAM_BACKEND)
        except Exception as error:  # noqa: BLE001 - missing driver or extension: keep the preview page
            self.use_vcam = False
            log(f"Virtual camera unavailable: {error}")
            log(f"Carrying on with the preview page only. To use the camera as a webcam, {VCAM_HINTS[SYSTEM]}.")
            return
        with self._vcam_lock:
            self.cam = cam
        log(f"Virtual camera ready: {cam.device} {width}x{height} @ {self.fps} fps")

    def _to_vcam(self, frame: av.VideoFrame) -> None:
        with self._vcam_lock:
            if self._closed or self.cam is None:
                return
            try:
                self.cam.send(fit_i420(frame, self.cam.width, self.cam.height))
            except Exception as error:  # noqa: BLE001 - the device went away: keep the preview page going
                log(f"Virtual camera stopped: {error}")
                self.use_vcam = False
                with contextlib.suppress(Exception):
                    self.cam.close()
                self.cam = None

    def close(self) -> None:
        with self._vcam_lock:
            self._closed = True
            if self.cam is not None:
                self.cam.close()
                self.cam = None


def fit_i420(frame: av.VideoFrame, width: int, height: int) -> np.ndarray:
    """The frame as I420 at the virtual camera's size: scaled to fit and, when its shape differs (a 4:3
    live view), centred between black bars instead of stretched."""
    if (frame.width, frame.height) == (width, height):
        return (frame if frame.format.name == "yuv420p" else frame.reformat(format="yuv420p")).to_ndarray()
    scale = min(width / frame.width, height / frame.height)
    w, h = max(2, int(frame.width * scale) & ~1), max(2, int(frame.height * scale) & ~1)
    planes = frame.reformat(width=w, height=h, format="yuv420p").to_ndarray().ravel()
    out = np.empty(width * height * 3 // 2, np.uint8)
    y, u, v = out[:width * height], out[width * height:width * height * 5 // 4], out[width * height * 5 // 4:]
    y[:], u[:], v[:] = 16, 128, 128                                   # black
    x0, y0 = (width - w) // 4 * 2, (height - h) // 4 * 2              # even offsets, centred
    y.reshape(height, width)[y0:y0 + h, x0:x0 + w] = planes[:w * h].reshape(h, w)
    for target, source in ((u, planes[w * h:w * h * 5 // 4]), (v, planes[w * h * 5 // 4:])):
        target.reshape(height // 2, width // 2)[y0 // 2:(y0 + h) // 2, x0 // 2:(x0 + w) // 2] = source.reshape(h // 2, w // 2)
    return out.reshape(height * 3 // 2, width)


TAILNET = ipaddress.ip_network("100.64.0.0/10")     # Tailscale hands out addresses from this range
CAMERA_NET = ipaddress.ip_network("192.168.2.0/24")  # the camera's own access point
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(command: list[str], timeout: float = 4.0) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
        return done.stdout if done.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _tailscale_ips() -> list[str]:
    exe = shutil.which("tailscale")
    if not exe and SYSTEM == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")):
            candidate = os.path.join(base, "Tailscale", "tailscale.exe") if base else ""
            if candidate and os.path.exists(candidate):
                exe = candidate
                break
    if not exe and SYSTEM == "darwin" and os.path.exists("/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        exe = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    return _run([exe, "ip", "-4"]).split() if exe else []


def local_addresses() -> list[tuple[str, str]]:
    """(address, adapter name) for every IPv4 address of this computer that another machine could use:
    no loopback, no link-local, no camera network. Adapter names come from Windows when it can say."""
    names: dict[str, str] = {}
    if SYSTEM == "win32":
        # PowerShell pipes in the OEM code page (cp949 on Korean Windows) unless told otherwise
        script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                  "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
                  "ForEach-Object { $_.IPAddress + '|' + $_.InterfaceAlias }")
        for line in _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], 8).splitlines():
            address, _, alias = line.strip().partition("|")
            if address:
                names[address] = alias
    with contextlib.suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            names.setdefault(info[4][0], "")
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("10.255.255.255", 1))          # sends nothing: only asks for the default route
        names.setdefault(probe.getsockname()[0], "")
    for address in _tailscale_ips():
        names.setdefault(address, "Tailscale")
    usable = []
    for address, alias in names.items():
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or ip in CAMERA_NET:
            continue
        usable.append((address, alias))
    # Tailscale first, then the rest in address order
    return sorted(usable, key=lambda item: (ipaddress.ip_address(item[0]) not in TAILNET, ipaddress.ip_address(item[0])))


def _label(address: str, alias: str) -> str:
    if ipaddress.ip_address(address) in TAILNET or "tailscale" in alias.lower():
        return "Tailscale"
    return f"LAN ({alias})" if alias else "LAN"


def announce_urls(host: str, port: int) -> None:
    """Print complete stream URLs for this machine, ready to copy."""
    line = "=" * 72
    log(line)
    log("STREAM URLS")
    if host in ("127.0.0.1", "localhost"):
        log(f"  This PC     http://127.0.0.1:{port}/stream")
        others = local_addresses()
        if others:
            log("  LAN/Tailscale are OFF (--bind 127.0.0.1). Start without it to serve:")
            for address, alias in others:
                log(f"  {_label(address, alias):<11} http://{address}:{port}/stream")
    else:
        rows = [("This PC", "127.0.0.1")] if host == "0.0.0.0" else []
        rows += [(_label(a, n), a) for a, n in (local_addresses() if host == "0.0.0.0" else [(host, "")])]
        for label, address in rows:
            log(f"  {label:<11} http://{address}:{port}/stream")
        if len(rows) <= 1 and host == "0.0.0.0":
            log("  (no LAN or Tailscale address yet: connect Ethernet, a second adapter or Tailscale)")
        log(f"  Firewall: allow inbound TCP {port} if another machine can't connect.")
    log("  Also: /snapshot.jpg (one frame)  /status (JSON)  / (preview page)")
    log(line)


def start_preview(outputs: Outputs, port: int, host: str = "0.0.0.0", max_fps: float = 0.0) -> None:
    """The preview page plus an MJPEG stream. Bound to every adapter (0.0.0.0) by default; --bind 127.0.0.1 keeps it
    on this computer, a single address keeps it on that adapter. Other machines reach it through Ethernet,
    a second adapter or Tailscale (the Wi-Fi adapter is on the camera).

    /              preview page
    /stream        MJPEG (multipart/x-mixed-replace), for <img>, OpenCV, ffmpeg, VLC, Unity
    /snapshot.jpg  the latest frame
    /status        JSON: frames so far, age of the latest frame, size, connected stream clients
    """
    page = (b"<!doctype html><title>OsmoCam</title><body style='margin:0;background:#111;display:grid;"
            b"place-items:center;height:100vh'><img src='/stream' style='max-width:100%;max-height:100vh'>")
    min_interval = 1 / max_fps if max_fps > 0 else 0.0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def _headers(self, status: int, content_type: str, length: int | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin", "*")
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.end_headers()

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._headers(200, "text/html", len(page))
                self.wfile.write(page)
                return
            if path == "/status":
                with outputs.cond:
                    frame, seq, stamp = outputs.latest, outputs.seq, outputs.last_frame_time
                body = json.dumps({
                    "frames": seq,
                    "age_ms": round((time.monotonic() - stamp) * 1000) if stamp else None,
                    "width": frame.width if frame is not None else None,
                    "height": frame.height if frame is not None else None,
                    "stream_clients": outputs.stream_clients,
                }).encode()
                self._headers(200, "application/json", len(body))
                self.wfile.write(body)
                return
            if path not in ("/stream", "/snapshot.jpg"):
                self.send_error(404)
                return
            single = path == "/snapshot.jpg"
            if not single:
                self._headers(200, "multipart/x-mixed-replace; boundary=frame")
                with outputs._stream_lock:
                    outputs.stream_clients += 1
            last, sent_at = -1, 0.0
            try:
                while True:
                    with outputs.cond:
                        outputs.cond.wait_for(lambda: outputs.seq != last, timeout=2)
                        frame, last = outputs.latest, outputs.seq
                    if frame is None:
                        if single:
                            self.send_error(503, "no frame yet")
                            return
                        continue
                    jpeg = outputs.jpeg(frame, last)
                    if single:
                        self._headers(200, "image/jpeg", len(jpeg))
                        self.wfile.write(jpeg)
                        return
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n"
                                     % len(jpeg) + jpeg + b"\r\n")
                    outputs.count_sent(len(jpeg))
                    if min_interval:
                        wait = min_interval - (time.monotonic() - sent_at)
                        if wait > 0:
                            time.sleep(wait)
                        sent_at = time.monotonic()
            except OSError:
                return
            finally:
                if not single:
                    with outputs._stream_lock:
                        outputs.stream_clients -= 1

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="preview").start()
    announce_urls(host, port)


async def scan(seconds: float) -> None:
    log(f"Listening for DJI Osmo cameras for {seconds:.0f} s...")
    found = await ble.scan(seconds)
    if not found:
        log("No DJI Osmo camera found. Is it on and close to the computer?")
    for cam in sorted(found.values(), key=lambda c: -c["rssi"]):
        notes = [cam["power"] or "", "tested" if cam["tested"] else "untested", cam["unsupported"] or ""]
        print(f"  {cam['address']}  {cam['name'] or '?':20} {cam['model']:18} {cam['rssi']} dBm  "
              + ", ".join(n for n in notes if n))


async def run(args: argparse.Namespace) -> None:
    stop = threading.Event()
    outputs = Outputs(not args.no_vcam, args.fps)
    outputs.jpeg_quality = args.jpeg_quality
    await asyncio.to_thread(outputs.open_vcam)
    decoder = VideoDecoder(outputs.on_frame, stop)
    decoder.start()
    if args.preview_port:
        start_preview(outputs, args.preview_port, args.bind, args.stream_fps)
    registry = CameraRegistry()
    address = args.address or (registry.last_used() or {}).get("address")
    home = args.home or wifi.current_network(args.interface)
    if home.lower().startswith(models.NAME_PREFIXES):
        home = ""                    # started while still on a camera's network: nothing to return to
    deadline = time.monotonic() + args.seconds if args.seconds else None
    link: ble.BleLink | None = None
    session: datalink.Datalink | None = None
    task: asyncio.Future | None = None
    joined = False

    def time_up() -> bool:
        return stop.is_set() or (deadline is not None and time.monotonic() > deadline)

    async def pair() -> ble.BleLink:
        new = ble.BleLink()
        await new.connect(address, args.approve_timeout)
        registry.remember(new)
        return new

    try:
        link = await pair()
        address = link.address
        sessions = 0
        while not time_up():
            sessions += 1
            if link is None or link.disconnected.is_set():
                log("Bluetooth link is down, waking the camera again")
                try:
                    link = await pair()
                except Exception as error:  # noqa: BLE001 - keep trying: the Wi-Fi may still be up
                    log(f"Could not wake the camera: {error}")
                    link = None
            camera = registry.get(address) or {}
            ssid, password = camera.get("ssid"), camera.get("password")
            joined = True
            await asyncio.to_thread(wifi.join, ssid, password, args.join_timeout, args.interface)
            if sessions == 1 and args.preview_port:
                # The Wi-Fi adapter is on the camera now and its old address is gone: print what is left.
                await asyncio.to_thread(announce_urls, args.bind, args.preview_port)
            transport = camera.get("transport") or dict(DEFAULT_TRANSPORT)
            if transport.get("poke", True):
                await asyncio.to_thread(datalink.poke)
            session = datalink.Datalink(port=transport.get("port", datalink.DATALINK_PORT), on_video=decoder.feed,
                                        liveview=models.liveview_mode(camera.get("model_id")))
            decoder.reset()
            task = asyncio.ensure_future(asyncio.to_thread(session.run))
            started = time.monotonic()
            report = (started, 0, 0)
            stream_report = (outputs.stream_parts, outputs.stream_bytes)
            while not task.done():
                await asyncio.sleep(0.5)
                now = time.monotonic()
                stalled = now - (session.last_video or started)
                if time_up():
                    session.stop()
                elif stalled > args.stall and not session.stopped.is_set():
                    log(f"No video for {stalled:.1f} s, restarting the live view ({session.summary()})")
                    session.stop()
                if now - report[0] >= args.report:
                    frames, video_bytes = decoder.frames, session.stats["video_bytes"]
                    span = now - report[0]
                    median, p95 = outputs.latency.drain()
                    log(f"{(frames - report[1]) / span:5.1f} fps  {(video_bytes - report[2]) * 8 / span / 1e6:4.1f} Mbit/s  "
                        f"latency {median:3.0f}/{p95:3.0f} ms (median/p95)  dropped={decoder.dropped} "
                        f"errors={decoder.errors} session={sessions}")
                    report = (now, frames, video_bytes)
                    parts, sent = outputs.stream_parts, outputs.stream_bytes
                    watching = outputs.stream_clients
                    if watching:
                        per_client = (parts - stream_report[0]) / span / watching
                        log(f"  stream: {per_client:5.1f} fps per client  {(sent - stream_report[1]) * 8 / span / 1e6:4.1f} Mbit/s total  "
                            f"{(sent - stream_report[1]) / max(1, parts - stream_report[0]) / 1024:4.0f} KB/frame  clients={watching}")
                    stream_report = (parts, sent)
            try:
                await task
            except RuntimeError as error:
                if "handshake" in str(error):
                    other = other_transport(transport)
                    log(f"{error}; trying UDP {other['port']} next")
                    registry.set_transport(address, other)
            except Exception as error:  # noqa: BLE001 - a failed session is retried
                log(f"Live view session ended: {error}")
            if not time_up():
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        log("Ctrl+C: stopping...")
        raise
    finally:
        # Shut down in order: end the live view session (its thread would otherwise keep Python from
        # exiting), stop the decoder before closing the virtual camera it writes to, then give the Wi-Fi
        # back and release the camera.
        if session is not None:
            session.stop()
        if task is not None and not task.done():
            await asyncio.wait({task}, timeout=2)
        stop.set()
        decoder.join(timeout=2)
        outputs.close()
        if joined:
            await asyncio.to_thread(wifi.restore, home, args.interface)
        if link is not None:
            with contextlib.suppress(Exception):
                await link.close()
        log(f"Stopped. frames={decoder.frames} decode_errors={decoder.errors}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-vcam", action="store_true", help="don't send the picture to the virtual camera")
    parser.add_argument("--preview-port", type=int, default=38090, help="port of the preview page and stream (0 = off)")
    parser.add_argument("--bind", default="0.0.0.0",
                        help="address the preview/stream server listens on (default 0.0.0.0 = every adapter; "
                             "127.0.0.1 = this computer only; or one adapter's IP)")
    parser.add_argument("--stream-fps", type=float, default=0,
                        help="cap the MJPEG stream per client (0 = every frame, up to 30)")
    parser.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality of the stream, 1-95")
    parser.add_argument("--fps", type=int, default=30, help="frame rate announced to the virtual camera")
    parser.add_argument("--scan", action="store_true", help="list the DJI Osmo cameras nearby and exit")
    parser.add_argument("--address", help="Bluetooth address of the camera, as --scan lists it (default: the one "
                                          "used last, else the first DJI Osmo found)")
    parser.add_argument("--interface", help="Wi-Fi adapter to use: 'Wi-Fi 2' on Windows, en0 on macOS, wlan0 "
                                            "on Linux (default: the first one)")
    parser.add_argument("--home", help="Wi-Fi network to return to (default: the current one)")
    parser.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = run until Ctrl+C)")
    parser.add_argument("--stall", type=float, default=3.0, help="restart the live view after N s without video")
    parser.add_argument("--report", type=float, default=10.0, help="seconds between stats lines")
    parser.add_argument("--join-timeout", type=float, default=45)
    parser.add_argument("--approve-timeout", type=float, default=90)
    args = parser.parse_args()
    try:
        with fine_timer():
            asyncio.run(scan(8) if args.scan else run(args))
    except KeyboardInterrupt:
        pass
    except BleakError as error:
        log(f"Bluetooth is not available: {error} ({ble.UNAVAILABLE_HINT})")
        sys.exit(1)
    except wifi.WifiError as error:
        log(f"Could not connect over Wi-Fi: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
