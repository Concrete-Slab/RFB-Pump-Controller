from contextlib import contextmanager
import cv2

@contextmanager
def open_video_device(index: int):
    cap = cv2.VideoCapture(index)
    try:
        yield cap
    finally:
        cap.release()

@contextmanager
def open_cv2_window(name: str):
    try:
        cv2.namedWindow(name)
        yield name
    finally:
        cv2.destroyWindow(name)