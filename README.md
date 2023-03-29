# rtspserver-ffmpeg
Build an ffmpeg RTSP distribution server using an old alpine:3.8 Docker Image.

## 0. 前準備
- `git clone`
    ```bash
    git clone https://github.com/PINTO0309/rtspserver-ffmpeg.git && cd rtspserver-ffmpeg
    ```
- `xxxx.mp4` ファイルを `rtspserver-ffmpeg` フォルダの直下にコピーしておく

## 1. `docker compose` パターン
- `docker compose` 経由でコンテナを起動
    ```bash
    docker compose up -d
    ```
- `docker compose` 経由でコンテナを起動したあとに `docker compose exec` コマンドを使用して `ffmpeg` によるRTSP配信開始指示、`-stream_loop -1` は無限ループ再生オプション
    ```bash
    docker compose exec rtspserver-ffmpeg \
    ffmpeg -re -stream_loop -1 -i xxxx.mp4 http://localhost:8090/feed.ffm
    ```
- `docker compose` 経由でコンテナを起動したあとに配信用コンテナを終了
    ```bash
    docker compose down
    ```

## 2. `docker run` パターン
- `docker build` で Docker Image をローカルに生成 (Docker HubからPullするだけで問題ない場合は実施不要)
    ```bash
    docker build -t pinto0309/rtspserver-ffmpeg:latest -f Dockerfile.ffmpegrtsp .
    docker push pinto0309/rtspserver-ffmpeg:latest
    ```
- `docker run` 経由でデーモンとしてコンテナをバックエンド起動
    ```bash
    docker run --rm -d \
    -p 8554:8554 \
    -p 8090:8090 \
    -v ${PWD}/ffserver.conf:/etc/ffserver.conf \
    -v ${PWD}:/home/user/ \
    --net=host \
    --name rtspserver-ffmpeg \
    pinto0309/rtspserver-ffmpeg:latest
    ```
- `docker run` 経由でコンテナを起動したあとに `docker exec` コマンドを使用して `ffmpeg` によるRTSP配信開始指示、`-stream_loop -1` は無限ループ再生オプション
    ```bash
    docker exec rtspserver-ffmpeg \
    ffmpeg -re -stream_loop -1 -i xxxx.mp4 http://localhost:8090/feed.ffm
    ```
- `docker run` 経由でコンテナを起動したあとに配信用コンテナを終了
    ```bash
    docker stop rtspserver-ffmpeg
    ```

## 3. 配信映像の受信テスト
- `vlc` を使用したRTSP配信内容の確認
    ```bash
    vlc rtsp://0.0.0.0:8554/unicast
    ```
- `opencv` を使用したRTSP配信内容の確認

    <details><summary>video.py</summary>

    ```python:video.py
    from pathlib import Path
    from enum import Enum
    from collections import deque
    from urllib.parse import urlparse
    import subprocess
    import threading
    import logging
    import cv2
    from typing import Tuple


    LOGGER = logging.getLogger(__name__)
    WITH_GSTREAMER = False # True


    class Protocol(Enum):
        IMAGE = 0
        VIDEO = 1
        CSI   = 2
        V4L2  = 3
        RTSP  = 4
        HTTP  = 5


    class VideoIO:
        def __init__(
            self,
            output_size: Tuple,
            input_uri: str,
            output_uri: str=None,
            output_fps: int=30,
            input_resolution: Tuple=(640, 480),
            frame_rate: int=30,
            buffer_size: int=10,
            proc_fps: int=30
        ):
            """Class for video capturing and output saving.
            Encoding, decoding, and scaling can be accelerated using the GStreamer backend.

            Parameters
            ----------
            output_size : tuple
                Width and height of each frame to output.
            input_uri : str
                URI to input stream. It could be image sequence (e.g. '%06d.jpg'), video file (e.g. 'file.mp4'),
                MIPI CSI camera (e.g. 'csi://0'), USB/V4L2 camera (e.g. '/dev/video0'),
                RTSP stream (e.g. 'rtsp://<user>:<password>@<ip>:<port>/<path>'),
                or HTTP live stream (e.g. 'http://<user>:<password>@<ip>:<port>/<path>')
            output_uri : str, optionals
                URI to an output video file.
            output_fps : int, optionals
                Output video recording frame rate. Specify a value less than 30.
            input_resolution : tuple, optional
                Original resolution of the input source.
                Useful to set a certain capture mode of a USB/CSI camera.
            frame_rate : int, optional
                Frame rate of the input source.
                Required if frame rate cannot be deduced, e.g. image sequence and/or RTSP.
                Useful to set a certain capture mode of a USB/CSI camera.
            buffer_size : int, optional
                Number of frames to buffer.
                For live sources, a larger buffer drops less frames but increases latency.
            proc_fps : int, optional
                Estimated processing speed that may limit the capture interval `cap_dt`.
                This depends on hardware and processing complexity.
            """
            self.size = output_size
            self.input_uri = input_uri
            self.output_uri = output_uri
            self.output_fps = output_fps
            self.resolution = input_resolution
            assert frame_rate > 0
            self.frame_rate = frame_rate
            assert buffer_size >= 1
            self.buffer_size = buffer_size
            assert proc_fps > 0
            self.proc_fps = proc_fps

            self.protocol = self._parse_uri(self.input_uri)
            if self.protocol == Protocol.V4L2:
                result = subprocess.check_output(
                    [
                        'sudo', 'chmod', '777', fr'{self.input_uri[:-1]}0'
                    ],
                    stderr=subprocess.PIPE
                ).decode('utf-8')
                result = subprocess.check_output(
                    [
                        'sudo', 'chmod', '777', fr'{self.input_uri[:-1]}1'
                    ],
                    stderr=subprocess.PIPE
                ).decode('utf-8')
            self.is_live = self.protocol != Protocol.IMAGE and self.protocol != Protocol.VIDEO
            if WITH_GSTREAMER:
                self.source = cv2.VideoCapture(self._gst_cap_pipeline(), cv2.CAP_GSTREAMER)
            else:
                self.source = cv2.VideoCapture(self.input_uri)

            self.frame_queue: deque = deque([], maxlen=self.buffer_size)
            self.cond = threading.Condition()
            self.exit_event = threading.Event()
            self.cap_thread = threading.Thread(target=self._capture_frames)

            ret, frame = self.source.read()
            if not ret:
                raise RuntimeError(f'Unable to read video stream: {self.input_uri}')
            self.frame_queue.append(frame)

            width = self.source.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = self.source.get(cv2.CAP_PROP_FRAME_HEIGHT)
            self.cap_fps = self.source.get(cv2.CAP_PROP_FPS)
            self.do_resize = (width, height) != self.size
            if self.cap_fps == 0:
                self.cap_fps = self.frame_rate # fallback to config if unknown
            LOGGER.info('%dx%d stream @ %d FPS', width, height, self.cap_fps)

            if self.output_uri is not None:
                Path(self.output_uri).parent.mkdir(parents=True, exist_ok=True)
                output_fps = 1 / self.cap_dt
                if WITH_GSTREAMER:
                    self.writer = cv2.VideoWriter(
                        self._gst_write_pipeline(),
                        cv2.CAP_GSTREAMER,
                        0,
                        fps=output_fps,
                        frameSize=self.size,
                        isColor=True
                    )
                else:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    self.writer = cv2.VideoWriter(
                        filename=self.output_uri,
                        fourcc=fourcc,
                        fps=output_fps if self.output_fps >= output_fps else self.output_fps,
                        frameSize=self.size,
                        isColor=True,
                    )

        @property
        def cap_dt(self):
            # limit capture interval at processing latency for live sources
            return 1 / min(self.cap_fps, self.proc_fps) if self.is_live else 1 / self.cap_fps

        def start_capture(self):
            """Start capturing from file or device."""
            if not self.source.isOpened():
                self.source.open(self._gst_cap_pipeline(), cv2.CAP_GSTREAMER)
            if not self.cap_thread.is_alive():
                self.cap_thread.start()

        def stop_capture(self):
            """Stop capturing from file or device."""
            with self.cond:
                self.exit_event.set()
                self.cond.notify()
            self.frame_queue.clear()
            self.cap_thread.join()

        def read(self):
            """Reads the next video frame.

            Returns
            -------
            ndarray
                Returns None if there are no more frames.
            """
            with self.cond:
                while len(self.frame_queue) == 0 and not self.exit_event.is_set():
                    self.cond.wait()
                if len(self.frame_queue) == 0 and self.exit_event.is_set():
                    return None
                frame = self.frame_queue.popleft()
                self.cond.notify()
            if self.do_resize:
                frame = cv2.resize(frame, self.size)
            return frame

        def write(self, frame):
            """Writes the next video frame."""
            assert hasattr(self, 'writer')
            self.writer.write(frame)

        def release(self):
            """Cleans up input and output sources."""
            self.stop_capture()
            if hasattr(self, 'writer'):
                self.writer.release()
            self.source.release()

        def _gst_cap_pipeline(self):
            gst_elements = str(subprocess.check_output('gst-inspect-1.0'))
            if 'nvvidconv' in gst_elements and self.protocol != Protocol.V4L2:
                # format conversion for hardware decoder
                cvt_pipeline = (
                    'nvvidconv interpolation-method=5 ! '
                    'video/x-raw, width=%d, height=%d, format=BGRx !'
                    'videoconvert ! appsink sync=false'
                    % self.size
                )
            else:
                cvt_pipeline = (
                    'videoscale ! '
                    'video/x-raw, width=%d, height=%d !'
                    'videoconvert ! appsink sync=false'
                    % self.size
                )

            if self.protocol == Protocol.IMAGE:
                pipeline = (
                    'multifilesrc location=%s index=1 caps="image/%s,framerate=%d/1" ! decodebin ! '
                    % (
                        self.input_uri,
                        self._img_format(self.input_uri),
                        self.frame_rate
                    )
                )
            elif self.protocol == Protocol.VIDEO:
                pipeline = 'filesrc location=%s ! decodebin ! ' % self.input_uri
            elif self.protocol == Protocol.CSI:
                if 'nvarguscamerasrc' in gst_elements:
                    pipeline = (
                        'nvarguscamerasrc sensor_id=%s ! '
                        'video/x-raw(memory:NVMM), width=%d, height=%d, '
                        'format=NV12, framerate=%d/1 ! '
                        % (
                            self.input_uri[6:],
                            *self.resolution,
                            self.frame_rate
                        )
                    )
                else:
                    raise RuntimeError('GStreamer CSI plugin not found')
            elif self.protocol == Protocol.V4L2:
                if 'v4l2src' in gst_elements:
                    pipeline = (
                        'v4l2src device=%s ! '
                        'video/x-raw, width=%d, height=%d, '
                        'format=YUY2, framerate=%d/1 ! '
                        % (
                            self.input_uri,
                            *self.resolution,
                            self.frame_rate
                        )
                    )
                else:
                    raise RuntimeError('GStreamer V4L2 plugin not found')
            elif self.protocol == Protocol.RTSP:
                pipeline = (
                    'rtspsrc location=%s latency=0 ! '
                    'capsfilter caps=application/x-rtp,media=video ! decodebin ! ' % self.input_uri
                )
            elif self.protocol == Protocol.HTTP:
                pipeline = 'souphttpsrc location=%s is-live=true ! decodebin ! ' % self.input_uri

            """
            'v4l2src device=/dev/video0 ! video/x-raw, width=640, height=480, format=YUY2, framerate=30/1 ! videoscale ! video/x-raw, width=640, height=480 !videoconvert ! appsink sync=false'
            """
            return pipeline + cvt_pipeline

        def _gst_write_pipeline(self):
            gst_elements = str(subprocess.check_output('gst-inspect-1.0'))
            # use hardware encoder if found
            if 'omxh264enc' in gst_elements:
                h264_encoder = 'omxh264enc preset-level=2'
            elif 'x264enc' in gst_elements:
                h264_encoder = 'x264enc pass=4'
            else:
                raise RuntimeError('GStreamer H.264 encoder not found')
            pipeline = (
                'appsrc ! autovideoconvert ! %s ! qtmux ! filesink location=%s '
                % (
                    h264_encoder,
                    self.output_uri
                )
            )
            return pipeline

        def _capture_frames(self):
            while not self.exit_event.is_set():
                ret, frame = self.source.read()
                with self.cond:
                    if not ret:
                        self.exit_event.set()
                        self.cond.notify()
                        break
                    # keep unprocessed frames in the buffer for file
                    if not self.is_live:
                        while (len(self.frame_queue) == self.buffer_size and
                               not self.exit_event.is_set()):
                            self.cond.wait()
                    self.frame_queue.append(frame)
                    self.cond.notify()

        @staticmethod
        def _parse_uri(uri):
            result = urlparse(uri)
            if result.scheme == 'csi':
                protocol = Protocol.CSI
            elif result.scheme == 'rtsp':
                protocol = Protocol.RTSP
            elif result.scheme == 'http':
                protocol = Protocol.HTTP
            else:
                if '/dev/video' in result.path:
                    protocol = Protocol.V4L2
                elif '%' in result.path:
                    protocol = Protocol.IMAGE
                else:
                    protocol = Protocol.VIDEO
            return protocol

        @staticmethod
        def _img_format(uri):
            img_format = Path(uri).suffix[1:]
            return 'jpeg' if img_format == 'jpg' else img_format
    ```

    </details>

    <details><summary>test_rtsp_recv.py</summary>

    ```python:test_rtsp_recv.py
    import cv2
    from videoio import VideoIO

    stream = VideoIO(
        output_size=(
            640,
            480
        ),
        input_uri=f'rtsp://0.0.0.0:8554/unicast',
        output_uri=None,
        output_fps=30,
        input_resolution=(
            640,
            480
        ),
        frame_rate=30,
        buffer_size=10,
    )
    stream.start_capture()

    try:
        while True:
            frame = stream.read()
            key = cv2.waitKey(1)
            if key == 27:  # ESC
                break
            if frame is None:
                continue
            cv2.imshow('test', frame)
    except Exception as ex:
        pass
    finally:
        if stream:
            stream.release()
    ```

    </details>

    ```bash
    python test_rtsp_recv.py
    ```

## 4. 謝辞
1. https://geek.tacoskingdom.com/blog/48
