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
