import cv2

from xbhdcc_tools import detect_cameras, WebStreamer

if __name__ == "__main__":
    # detect_cameras()
    cap = cv2.VideoCapture(9, cv2.CAP_V4L2)
    streamer = WebStreamer(port=8081)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        streamer.update_frame(0, frame)
        streamer.update_frame(1, frame)


