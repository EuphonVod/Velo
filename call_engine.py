import asyncio
import threading
import json
import numpy as np
import sounddevice as sd
import websocket as ws_client

from aiortc import (
    RTCPeerConnection, RTCSessionDescription, RTCIceCandidate,
    RTCConfiguration, RTCIceServer
)
from aiortc.contrib.media import MediaPlayer


STUN_SERVERS = [
    RTCIceServer(urls="stun:stun.l.google.com:19302"),
    RTCIceServer(urls="stun:stun1.l.google.com:19302"),
]
from aiortc import MediaStreamTrack
from av import AudioFrame
import fractions
import queue
import cv2
from av import AudioFrame, VideoFrame

class MicTrack(MediaStreamTrack):
    """Capture le micro via sounddevice (par index) et le fournit à aiortc."""
    kind = "audio"

    def __init__(self, device=None, samplerate=48000, channels=1):
        super().__init__()
        self.samplerate = samplerate
        self.channels = channels
        self._queue = queue.Queue()
        self._timestamp = 0
        self.stream = sd.InputStream(
            device=device,
            samplerate=samplerate,
            channels=channels,
            dtype="int16",
            blocksize=960,
            callback=self._cb,
        )
        self.stream.start()
        self.video_track = None
        self.video_sender = None
        self.on_remote_video = None
        self._remote_video_task = None

    def _cb(self, indata, frames, time, status):
        self._queue.put(indata.copy())

    async def recv(self):
        import asyncio
        #recupere bloc audio
        while True:
            try:
                data = self._queue.get_nowait()
                break
            except queue.Empty:
                await asyncio.sleep(0.005)
        frame = AudioFrame.from_ndarray(
            data.reshape(1, -1), format="s16", layout="mono" if self.channels == 1 else "stereo"
        )
        frame.sample_rate = self.samplerate
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self.samplerate)
        self._timestamp += data.shape[0]
        return frame

    def stop(self):
        try:
            self.stream.stop(); self.stream.close()
        except Exception:
            pass


def list_dshow_mics():
    """Noms complets des micros DirectShow via pygrabber (Windows, sans ffmpeg)."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        graph = FilterGraph()
        return graph.get_input_devices()  #list des noms complet
    except Exception as e:
        print("pygrabber error:", e)
        return []


def default_mic_dshow():
    mics = list_dshow_mics()
    if not mics:
        return "audio=default"
    # try mic par defaut
    try:
        default_name = sd.query_devices(kind="input")["name"]
        short = default_name.split("(")[0].strip().lower()
        for m in mics:
            if short and short in m.lower():
                return f"audio={m}"
    except Exception:
        pass
    return f"audio={mics[0]}"

try:
    from PIL import ImageGrab
    HAS_IMAGEGRAB = True
except Exception:
    HAS_IMAGEGRAB = False


class CameraTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, device_index=0, fps=15):
        super().__init__()
        self.cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.fps = fps
        self._timestamp = 0

    async def recv(self):
        import asyncio
        await asyncio.sleep(1 / self.fps)
        ret, frame = self.cap.read()
        if not ret:
            #frame noire si échec
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        vframe = VideoFrame.from_ndarray(frame, format="rgb24")
        vframe.pts = self._timestamp
        vframe.time_base = fractions.Fraction(1, self.fps)
        self._timestamp += 1
        return vframe

    def stop(self):
        try:
            self.cap.release()
        except Exception:
            pass


class ScreenTrack(MediaStreamTrack):
    """Capture l'écran via PIL ImageGrab."""
    kind = "video"

    def __init__(self, fps=10):
        super().__init__()
        self.fps = fps
        self._timestamp = 0

    async def recv(self):
        import asyncio
        await asyncio.sleep(1 / self.fps)
        img = ImageGrab.grab()
        frame = np.array(img)
        #gestion taille (peu impacter performance)
        h, w = frame.shape[:2]
        scale = min(1.0, 1280 / w)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        vframe = VideoFrame.from_ndarray(frame, format="rgb24")
        vframe.pts = self._timestamp
        vframe.time_base = fractions.Fraction(1, self.fps)
        self._timestamp += 1
        return vframe

    def stop(self):
        pass


class AudioPlayer:
    def __init__(self, device=None, samplerate=48000, channels=1):
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.stream = None
        self._buf = bytearray()
        self._lock = threading.Lock()

    def start(self):
        self.stream = sd.OutputStream(
            device=self.device,
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="int16",
            callback=self._cb,
            blocksize=960,
        )
        self.stream.start()

    def _cb(self, outdata, frames, time, status):
        need = frames * self.channels * 2  #int16 = 2 bytes
        with self._lock:
            if len(self._buf) >= need:
                chunk = self._buf[:need]
                del self._buf[:need]
                outdata[:] = np.frombuffer(chunk, dtype=np.int16).reshape(-1, self.channels)
            else:
                outdata.fill(0)

    def feed(self, data: bytes):
        with self._lock:
            self._buf.extend(data)

    def stop(self):
        try:
            if self.stream:
                self.stream.stop(); self.stream.close()
        except Exception:
            pass



class CallEngine:
    def __init__(self, base_ws_url, my_id, mic_index=None, speaker_index=None):
        self.base_ws_url = base_ws_url
        self.my_id = my_id
        self.mic_index = mic_index
        self.speaker_index = speaker_index
        self.mic_track = None
        self.video_track = None
        self.video_sender = None
        self.on_remote_video = None
        self._remote_video_task = None
        self.on_video_stopped = None
        self.pc = None
        self.signaling = None
        self.peer_id = None
        self.loop = None
        self.audio_out = None
        self._pending_offer = None
        self._play_task = None
        self._polite = False
        self._making_offer = False
        self._ignore_offer = False
        self.on_incoming = None
        self.on_connected = None
        self.on_ended = None
        self.on_unavailable = None

    #start call_engine
    def start(self):
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        url = f"{self.base_ws_url}/calls/ws/{self.my_id}"
        self.signaling = ws_client.WebSocketApp(
            url,
            on_message=self._on_signal,
            on_open=lambda ws: print(f"[CALL] Signaling connecté (user {self.my_id})"),
            on_error=lambda ws, e: print(f"[CALL] Signaling erreur: {e}"),
            on_close=lambda ws, c, r: print(f"[CALL] Signaling fermé: {c}"))
        threading.Thread(target=self.signaling.run_forever, daemon=True).start()
        self.loop.run_forever()

    def _on_signal(self, ws, raw):
        try:
            msg = json.loads(raw)
        except Exception:
            return
        asyncio.run_coroutine_threadsafe(self._handle_signal(msg), self.loop)

    def _send(self, msg):
        msg["to"] = self.peer_id
        if self.signaling:
            try:
                self.signaling.send(json.dumps(msg))
            except Exception as e:
                print("signal send error:", e)

    #creation de la connexion
    def _new_pc(self):
        pc = RTCPeerConnection(RTCConfiguration(iceServers=STUN_SERVERS))

        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                self.audio_out = AudioPlayer(device=self.speaker_index)
                self.audio_out.start()
                self._play_task = asyncio.ensure_future(self._drain(track))
            elif track.kind == "video":
                self._remote_video_task = asyncio.ensure_future(self._drain_video(track))

        @pc.on("connectionstatechange")
        async def on_state():
            print(f"[CALL] État connexion: {pc.connectionState}")
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await self._cleanup()
                if self.on_ended:
                    self.on_ended()
        return pc

    async def _drain(self, track):
        try:
            while True:
                frame = await track.recv()
                arr = frame.to_ndarray()
                if arr.dtype != np.int16:
                    arr = arr.astype(np.int16)
                self.audio_out.feed(arr.tobytes())
        except Exception:
            pass

    async def _drain_video(self, track):
        try:
            while True:
                frame = await track.recv()
                if self.on_remote_video:
                    img = frame.to_ndarray(format="rgb24")
                    self.on_remote_video(img)
        except Exception:
            pass

    def _add_mic(self):
        try:
            self.mic_track = MicTrack(device=self.mic_index)
            self.pc.addTrack(self.mic_track)
        except Exception as e:
            print("mic open error:", e)
            self.mic_track = None

    #screenshare/cam en toggle
    def start_camera(self):
        asyncio.run_coroutine_threadsafe(self._start_video("camera"), self.loop)

    def start_screen(self):
        asyncio.run_coroutine_threadsafe(self._start_video("screen"), self.loop)

    def stop_video(self):
        asyncio.run_coroutine_threadsafe(self._stop_video(), self.loop)

    async def _start_video(self, source):
        if not self.pc:
            return
        try:
            if self.video_track:
                self.video_track.stop()
                self.video_track = None
            if source == "camera":
                self.video_track = CameraTrack()
            else:
                self.video_track = ScreenTrack()
            if self.video_sender is None:
                self.video_sender = self.pc.addTrack(self.video_track)
            else:
                self.video_sender.replaceTrack(self.video_track)
            await self._negotiate()
        except Exception as e:
            import traceback
            print("[VIDEO] ERREUR:", e)
            traceback.print_exc()

    async def _stop_video(self):
        try:
            if self.video_track:
                self.video_track.stop()
                self.video_track = None
            if self.video_sender:
                self.video_sender.replaceTrack(None)
            self._send({"type": "video_stopped"})
            await self._negotiate()
        except Exception as e:
            print("[VIDEO] stop error:", e)

    # negociation
    async def _negotiate(self):
        if not self.pc:
            return
        try:
            self._making_offer = True
            offer = await self.pc.createOffer()
            await self.pc.setLocalDescription(offer)
            self._send({"type": "offer", "sdp": self.pc.localDescription.sdp})
        except Exception as e:
            print("[NEG] offer error:", e)
        finally:
            self._making_offer = False

    async def _handle_signal(self, msg):
        t = msg.get("type")

        if t == "call_invite":
            self.peer_id = msg["from"]
            self._pending_offer = msg.get("sdp")
            self._polite = True
            if self.on_incoming:
                self.on_incoming(msg["from"])

        elif t == "call_answer":
            answer = RTCSessionDescription(sdp=msg["sdp"], type="answer")
            await self.pc.setRemoteDescription(answer)
            if self.on_connected:
                self.on_connected()

        elif t == "offer":
            if not self.pc:
                return
            offer_collision = self._making_offer or self.pc.signalingState != "stable"
            self._ignore_offer = (not self._polite) and offer_collision
            if self._ignore_offer:
                print("[NEG] offre ignorée (glare, impolite)")
                return
            desc = RTCSessionDescription(sdp=msg["sdp"], type="offer")
            await self.pc.setRemoteDescription(desc)
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            self._send({"type": "answer", "sdp": self.pc.localDescription.sdp})

        elif t == "answer":
            if self.pc and self.pc.signalingState == "have-local-offer":
                answer = RTCSessionDescription(sdp=msg["sdp"], type="answer")
                await self.pc.setRemoteDescription(answer)

        elif t == "ice":
            if self.pc and msg.get("candidate"):
                try:
                    c = msg["candidate"]
                    cand = RTCIceCandidate(
                        sdpMid=c["sdpMid"],
                        sdpMLineIndex=c["sdpMLineIndex"],
                        candidate=c["candidate"],
                    )
                    await self.pc.addIceCandidate(cand)
                except Exception as e:
                    print("ICE error:", e)

        elif t == "call_end":
            await self._cleanup()
            if self.on_ended:
                self.on_ended()

        elif t == "call_unavailable":
            if self.on_unavailable:
                self.on_unavailable()
        elif t == "video_stopped":
            if self.on_video_stopped:
                self.on_video_stopped()

    #API publique
    def call(self, peer_id):
        self.peer_id = peer_id
        self._polite = False
        asyncio.run_coroutine_threadsafe(self._do_call(), self.loop)

    async def _do_call(self):
        self.pc = self._new_pc()
        self._add_mic()
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        self._send({"type": "call_invite", "sdp": self.pc.localDescription.sdp})

    def accept(self):
        asyncio.run_coroutine_threadsafe(self._do_accept(), self.loop)

    async def _do_accept(self):
        self.pc = self._new_pc()
        self._add_mic()
        offer = RTCSessionDescription(sdp=self._pending_offer, type="offer")
        await self.pc.setRemoteDescription(offer)
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        self._send({"type": "call_answer", "sdp": self.pc.localDescription.sdp})
        if self.on_connected:
            self.on_connected()

    def hangup(self):
        asyncio.run_coroutine_threadsafe(self._do_hangup(), self.loop)

    def decline(self):
        self.hangup()

    async def _do_hangup(self):
        self._send({"type": "call_end"})
        await self._cleanup()
        if self.on_ended:
            self.on_ended()

    async def _cleanup(self):
        try:
            if self._play_task:
                self._play_task.cancel()
        except Exception:
            pass
        try:
            if self._remote_video_task:
                self._remote_video_task.cancel()
        except Exception:
            pass
        try:
            if self.video_track:
                self.video_track.stop()
        except Exception:
            pass
        try:
            if self.mic_track:
                self.mic_track.stop()
        except Exception:
            pass
        try:
            if self.audio_out:
                self.audio_out.stop()
        except Exception:
            pass
        try:
            if self.pc:
                await self.pc.close()
        except Exception:
            pass
        self.pc = None
        self.video_track = None
        self.video_sender = None
        self.mic_track = None
        self._polite = False
        self._making_offer = False
        self._ignore_offer = False