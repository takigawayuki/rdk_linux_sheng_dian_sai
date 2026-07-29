import argparse
import select
import sys
import termios
import time
import tty
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np


DEFAULT_CALIBRATION_FILE = Path(__file__).with_name("camera_calibration.npz")
DEFAULT_SAMPLE_ROOT = Path(__file__).with_name("calibration_samples")
CAMERA_FOURCC = "MJPG"
CAMERA_FPS = 120.0


class TerminalKeyReader:
    """Read single terminal keys without blocking the camera display loop."""

    def __init__(self):
        self.fd = None
        self.original_settings = None

    def start(self):
        if not sys.stdin.isatty():
            return False
        self.fd = sys.stdin.fileno()
        self.original_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return True

    def read(self):
        if self.fd is None:
            return None
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if not readable:
            return None
        character = sys.stdin.read(1)
        return ord(character) if character else None

    def close(self):
        if self.fd is not None and self.original_settings is not None:
            termios.tcsetattr(
                self.fd, termios.TCSADRAIN, self.original_settings
            )
        self.fd = None
        self.original_settings = None


def open_camera(index, width, height):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(
            f"Cannot open camera {index}. Check /dev/video{index} and camera permissions."
        )

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*CAMERA_FOURCC))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    fourcc_value = int(cap.get(cv2.CAP_PROP_FOURCC))
    actual_fourcc = "".join(
        chr((fourcc_value >> (8 * byte_index)) & 0xFF)
        for byte_index in range(4)
    )
    actual_width = int(round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
    actual_height = int(round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    print(
        "Camera negotiated: "
        f"{actual_fourcc} {actual_width}x{actual_height} @ {actual_fps:.2f} FPS"
    )

    errors = []
    if actual_fourcc != CAMERA_FOURCC:
        errors.append(f"format is {actual_fourcc!r}, expected {CAMERA_FOURCC}")
    if (actual_width, actual_height) != (width, height):
        errors.append(
            f"resolution is {actual_width}x{actual_height}, expected {width}x{height}"
        )
    if actual_fps <= 0 or abs(actual_fps - CAMERA_FPS) > 1.0:
        errors.append(f"frame rate is {actual_fps:.2f}, expected {CAMERA_FPS:.0f}")
    if errors:
        cap.release()
        raise RuntimeError(
            "Camera does not support the required capture mode: "
            + "; ".join(errors)
            + ". Run v4l2-ctl -d /dev/video0 --list-formats-ext to inspect modes."
        )
    return cap


class Undistorter:
    """Load camera calibration and cache the remapping table for each frame size."""

    def __init__(self, calibration_file, alpha=0.0):
        calibration_file = Path(calibration_file)
        if not calibration_file.exists():
            raise FileNotFoundError(
                f"Calibration file not found: {calibration_file}\n"
                "Run the tune task first; see --help for the command."
            )

        with np.load(calibration_file, allow_pickle=False) as data:
            self.camera_matrix = data["camera_matrix"].astype(np.float64)
            self.dist_coeffs = data["dist_coeffs"].astype(np.float64)
            self.calibration_size = tuple(int(v) for v in data["image_size"])

        self.alpha = alpha
        self.cached_size = None
        self.map_x = None
        self.map_y = None

    def _build_maps(self, frame_size):
        calib_width, calib_height = self.calibration_size
        frame_width, frame_height = frame_size
        calib_ratio = calib_width / calib_height
        frame_ratio = frame_width / frame_height
        if abs(calib_ratio - frame_ratio) > 0.01:
            raise ValueError(
                "Current resolution has a different aspect ratio from calibration: "
                f"{frame_width}x{frame_height} vs {calib_width}x{calib_height}. "
                "Run the tune task again at the current resolution."
            )

        scaled_matrix = self.camera_matrix.copy()
        scaled_matrix[0, :] *= frame_width / calib_width
        scaled_matrix[1, :] *= frame_height / calib_height
        new_matrix, _ = cv2.getOptimalNewCameraMatrix(
            scaled_matrix,
            self.dist_coeffs,
            frame_size,
            self.alpha,
            frame_size,
        )
        self.map_x, self.map_y = cv2.initUndistortRectifyMap(
            scaled_matrix,
            self.dist_coeffs,
            None,
            new_matrix,
            frame_size,
            cv2.CV_16SC2,
        )
        self.cached_size = frame_size

    def apply(self, frame):
        height, width = frame.shape[:2]
        frame_size = (width, height)
        if self.cached_size != frame_size:
            self._build_maps(frame_size)
        return cv2.remap(
            frame, self.map_x, self.map_y, cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT
        )


def create_undistorter(args):
    if args.no_undistort:
        return None
    return Undistorter(args.calibration, args.alpha)


def process_frame(frame, undistorter):
    if undistorter is not None:
        frame = undistorter.apply(frame)
    return cv2.rotate(frame, cv2.ROTATE_180)


def camera_test(args):
    cap = open_camera(args.camera, args.width, args.height)
    undistorter = create_undistorter(args)
    number = 0
    prev_time = time.time()
    last_log_time = prev_time
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Camera opened, but no frame could be read.")

            frame = process_frame(frame, undistorter)
            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time) if curr_time != prev_time else 0
            prev_time = curr_time
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("USB Camera - undistorted", frame)
            if curr_time - last_log_time >= 1.0:
                print(f"Frame number: {number}, FPS: {fps:.1f}")
                last_log_time = curr_time
            number += 1
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def video_record_by_frame(args):
    cap = open_camera(args.camera, args.width, args.height)
    undistorter = create_undistorter(args)
    ret, frame = cap.read()
    if not ret:
        cap.release()
        raise RuntimeError("Camera opened, but no frame could be read.")

    frame = process_frame(frame, undistorter)
    frame_height, frame_width = frame.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    out = cv2.VideoWriter(
        args.output, fourcc, args.output_fps, (frame_width, frame_height)
    )
    if not out.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot create video file: {args.output}")

    prev_time = time.time()
    try:
        while True:
            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time) if curr_time != prev_time else 0
            prev_time = curr_time
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("frame", frame)
            out.write(frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to read a frame from the camera.")
            frame = process_frame(frame, undistorter)
    finally:
        cap.release()
        out.release()
        cv2.destroyAllWindows()


def picture_record_by_click(args):
    cap = open_camera(args.camera, args.width, args.height)
    undistorter = create_undistorter(args)
    print("Press 's' to save a picture, 'q' to quit.")
    prev_time = time.time()
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to read a frame from the camera.")
            frame = process_frame(frame, undistorter)

            curr_time = time.time()
            fps = 1.0 / (curr_time - prev_time) if curr_time != prev_time else 0
            prev_time = curr_time
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.imshow("frame", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("s"):
                timestamp = time.strftime("%m%d_%H%M%S")
                filename = f"{timestamp}.jpg"
                cv2.imwrite(filename, frame)
                print(f"Saved {filename}")
            elif key == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def detect_checkerboard(frame, pattern_size):
    """Run the expensive corner search outside the display/capture loop."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(
        gray,
        pattern_size,
        cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE,
    )
    if not found:
        return False, None, frame
    refined = cv2.cornerSubPix(
        gray,
        corners,
        (11, 11),
        (-1, -1),
        (
            cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER,
            30,
            0.001,
        ),
    )
    return True, refined, frame


def calibrate_camera(args):
    """Calibrate the camera from manually captured checkerboard views."""
    pattern_size = (args.board_cols, args.board_rows)
    object_template = np.zeros(
        (args.board_cols * args.board_rows, 3), dtype=np.float32
    )
    object_template[:, :2] = np.mgrid[
        0:args.board_cols, 0:args.board_rows
    ].T.reshape(-1, 2)
    object_template[:, :2] *= args.square_size

    cap = open_camera(args.camera, args.width, args.height)
    object_points = []
    image_points = []
    sample_paths = []
    image_size = None
    window = "Checkerboard calibration"
    detection_future = None
    latest_corners = None
    latest_detection_frame = None
    detection_id = 0
    captured_detection_id = -1
    minimum_samples = 12
    cancelled = False
    last_message = ""
    message_until = 0.0
    sample_dir = DEFAULT_SAMPLE_ROOT / time.strftime("%Y%m%d_%H%M%S")
    sample_dir.mkdir(parents=True, exist_ok=False)
    print(
        "\n========== Checkerboard calibration started ==========\n"
        f"Board: {args.board_cols}x{args.board_rows} inner corners, "
        f"square size: {args.square_size:.2f} mm\n"
        f"Captured images: {sample_dir}\n"
        "Move the board around the center, edges and corners at varied angles.\n"
        "Keys:\n"
        "  SPACE : capture the current detected checkerboard\n"
        "  D     : undo the last capture and delete its image\n"
        f"  Q     : finish and calibrate (minimum {minimum_samples} images)\n"
        "  ESC   : cancel without calibration\n"
        "Keys work in both this terminal and the camera window.\n"
        "======================================================="
    )
    detector = ThreadPoolExecutor(max_workers=1, thread_name_prefix="checkerboard")
    terminal_keys = TerminalKeyReader()
    terminal_enabled = terminal_keys.start()
    if terminal_enabled:
        print("[INPUT READY] Terminal single-key input enabled; no Enter needed.")
    else:
        print("[INPUT NOTICE] Click the camera window before pressing keys.")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to read a frame from the camera.")

            image_size = (frame.shape[1], frame.shape[0])
            if detection_future is None:
                detection_future = detector.submit(
                    detect_checkerboard, frame.copy(), pattern_size
                )
            elif detection_future.done():
                found, corners, detected_frame = detection_future.result()
                latest_corners = corners if found else None
                latest_detection_frame = detected_frame if found else None
                detection_id += 1
                detection_future = detector.submit(
                    detect_checkerboard, frame.copy(), pattern_size
                )

            found = latest_corners is not None
            if found:
                cv2.drawChessboardCorners(
                    frame, pattern_size, latest_corners, True
                )

            status = "FOUND" if found else "SEARCHING"
            color = (0, 255, 0) if found else (0, 0, 255)
            cv2.putText(
                frame,
                f"{status}  Samples: {len(image_points)}/{args.samples}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                color,
                2,
            )
            cv2.putText(
                frame,
                "SPACE capture | D undo | Q finish",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                1,
            )
            if time.monotonic() < message_until:
                cv2.rectangle(
                    frame, (2, 2), (frame.shape[1] - 3, frame.shape[0] - 3),
                    (0, 255, 0), 5,
                )
                cv2.putText(
                    frame,
                    last_message,
                    (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                )
            cv2.imshow(window, frame)

            window_key = cv2.waitKey(1) & 0xFF
            terminal_key = terminal_keys.read()
            key = terminal_key if terminal_key is not None else window_key
            if key == ord(" "):
                if not found:
                    print("[NOT CAPTURED] Checkerboard has not been detected yet.")
                    continue
                if captured_detection_id == detection_id:
                    print("[NOT CAPTURED] Wait for a new detection or move the board.")
                    continue
                sample_number = len(image_points) + 1
                sample_path = sample_dir / f"sample_{sample_number:02d}.png"
                if not cv2.imwrite(str(sample_path), latest_detection_frame):
                    print(f"[SAVE FAILED] Could not write: {sample_path}")
                    continue
                object_points.append(object_template.copy())
                image_points.append(latest_corners.copy())
                sample_paths.append(sample_path)
                captured_detection_id = detection_id
                last_message = f"CAPTURED {len(image_points)}/{args.samples}"
                message_until = time.monotonic() + 1.0
                print(
                    f"[CAPTURED] {len(image_points)}/{args.samples}  "
                    f"image: {sample_path}"
                )
                if len(image_points) >= args.samples:
                    print("[CAPTURE COMPLETE] Target sample count reached; calibrating...")
                    break
            elif key in (ord("d"), ord("D")):
                if image_points:
                    object_points.pop()
                    image_points.pop()
                    removed_path = sample_paths.pop()
                    removed_path.unlink(missing_ok=True)
                    captured_detection_id = -1
                    last_message = f"UNDO  {len(image_points)}/{args.samples}"
                    message_until = time.monotonic() + 1.0
                    print(
                        f"[UNDO] Deleted {removed_path}; "
                        f"{len(image_points)} samples remain."
                    )
                else:
                    print("[UNDO FAILED] There are no captured samples.")
            elif key in (ord("q"), ord("Q")):
                if len(image_points) < minimum_samples:
                    print(
                        f"[CANNOT FINISH] {len(image_points)} samples captured; "
                        f"at least {minimum_samples} are required."
                    )
                    last_message = f"NEED {minimum_samples - len(image_points)} MORE"
                    message_until = time.monotonic() + 1.5
                    continue
                print(
                    f"[CAPTURE COMPLETE] Finishing with "
                    f"{len(image_points)} samples; calibrating..."
                )
                break
            elif key == 27:
                cancelled = True
                print(
                    f"[CANCELLED] Calibration cancelled. "
                    f"Captured images remain in: {sample_dir}"
                )
                break
    finally:
        cap.release()
        detector.shutdown(wait=True, cancel_futures=True)
        terminal_keys.close()
        cv2.destroyAllWindows()

    if cancelled:
        return
    if len(image_points) < minimum_samples:
        raise RuntimeError(
            f"Only {len(image_points)} valid samples were captured; "
            f"at least {minimum_samples} are required. Calibration was not saved."
        )

    rms, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        object_points, image_points, image_size, None, None
    )
    per_view_errors = []
    for obj, observed, rvec, tvec in zip(
        object_points, image_points, rvecs, tvecs
    ):
        projected, _ = cv2.projectPoints(
            obj, rvec, tvec, camera_matrix, dist_coeffs
        )
        error = cv2.norm(observed, projected, cv2.NORM_L2)
        per_view_errors.append(error / np.sqrt(len(projected)))
    mean_error = float(np.mean(per_view_errors))

    calibration_file = Path(args.calibration)
    np.savez(
        calibration_file,
        camera_matrix=camera_matrix,
        dist_coeffs=dist_coeffs,
        image_size=np.asarray(image_size, dtype=np.int32),
        board_size=np.asarray(pattern_size, dtype=np.int32),
        square_size_mm=np.asarray(args.square_size),
        rms=np.asarray(rms),
        mean_reprojection_error=np.asarray(mean_error),
        method=np.asarray("checkerboard"),
    )

    print(f"Calibration saved to: {calibration_file}")
    print(f"RMS error: {rms:.4f} px")
    print(f"Mean reprojection error: {mean_error:.4f} px")
    print("Camera matrix:\n", camera_matrix)
    print("Distortion coefficients:\n", dist_coeffs.ravel())
    if rms > 1.0:
        print("WARNING: RMS error is high. Recalibrate with sharper, varied views.")


def _do_nothing(_value):
    pass


def _trackbar_value(window, name, center, scale):
    return (cv2.getTrackbarPos(name, window) - center) / scale


def tune_distortion(args):
    """Tune lens correction against straight objects without a checkerboard."""
    cap = open_camera(args.camera, args.width, args.height)
    ret, frame = cap.read()
    if not ret:
        cap.release()
        raise RuntimeError("Camera opened, but no frame could be read.")

    height, width = frame.shape[:2]
    image_size = (width, height)
    radial_center = 2000
    tangent_center = 2000
    k1 = k2 = p1 = p2 = 0.0
    focal_ratio = 1.0
    alpha = args.alpha

    calibration_file = Path(args.calibration)
    if calibration_file.exists():
        with np.load(calibration_file, allow_pickle=False) as data:
            old_matrix = data["camera_matrix"].astype(np.float64)
            old_dist = data["dist_coeffs"].astype(np.float64).ravel()
            old_size = tuple(int(v) for v in data["image_size"])
        if abs(old_size[0] / old_size[1] - width / height) <= 0.01:
            focal_ratio = old_matrix[0, 0] / old_size[0]
            values = np.pad(old_dist, (0, max(0, 4 - len(old_dist))))
            k1, k2, p1, p2 = (float(v) for v in values[:4])
            print(f"Loaded existing parameters from: {calibration_file}")
        else:
            print("Existing parameters use another aspect ratio; starting from zero.")

    window = "Undistortion tuning"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.createTrackbar(
        "K1", window,
        int(np.clip(round(k1 * 1000 + radial_center), 0, 4000)),
        4000, _do_nothing,
    )
    cv2.createTrackbar(
        "K2", window,
        int(np.clip(round(k2 * 1000 + radial_center), 0, 4000)),
        4000, _do_nothing,
    )
    cv2.createTrackbar(
        "P1", window,
        int(np.clip(round(p1 * 10000 + tangent_center), 0, 4000)),
        4000, _do_nothing,
    )
    cv2.createTrackbar(
        "P2", window,
        int(np.clip(round(p2 * 10000 + tangent_center), 0, 4000)),
        4000, _do_nothing,
    )
    cv2.createTrackbar(
        "Focal x1000", window,
        int(np.clip(round(focal_ratio * 1000), 100, 3000)),
        3000, _do_nothing,
    )
    cv2.createTrackbar(
        "Alpha %", window, int(round(alpha * 100)), 100, _do_nothing
    )

    undistorter = Undistorter.__new__(Undistorter)
    undistorter.calibration_size = image_size
    undistorter.cached_size = None
    undistorter.map_x = None
    undistorter.map_y = None
    last_values = None
    show_original = False
    saved = False
    print(
        "Aim at door/window frames, tiles, or other straight lines.\n"
        "Adjust K1 first, then K2. Only adjust P1/P2 for asymmetric distortion.\n"
        "Keys: v = original/corrected, r = reset, s = save, q = quit"
    )
    try:
        while True:
            current_values = (
                _trackbar_value(window, "K1", radial_center, 1000.0),
                _trackbar_value(window, "K2", radial_center, 1000.0),
                _trackbar_value(window, "P1", tangent_center, 10000.0),
                _trackbar_value(window, "P2", tangent_center, 10000.0),
                max(cv2.getTrackbarPos("Focal x1000", window), 100) / 1000.0,
                cv2.getTrackbarPos("Alpha %", window) / 100.0,
            )
            if current_values != last_values:
                k1, k2, p1, p2, focal_ratio, alpha = current_values
                focal = focal_ratio * width
                undistorter.camera_matrix = np.array(
                    [[focal, 0.0, (width - 1) / 2.0],
                     [0.0, focal, (height - 1) / 2.0],
                     [0.0, 0.0, 1.0]],
                    dtype=np.float64,
                )
                undistorter.dist_coeffs = np.array(
                    [[k1, k2, p1, p2, 0.0]], dtype=np.float64
                )
                undistorter.alpha = alpha
                undistorter.cached_size = None
                last_values = current_values

            if show_original:
                display = frame
                mode = "ORIGINAL"
            else:
                display = undistorter.apply(frame)
                mode = "CORRECTED"
            display = cv2.rotate(display, cv2.ROTATE_180)
            cv2.putText(
                display, mode, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 255, 255), 2,
            )
            cv2.putText(
                display,
                f"k1={k1:.3f} k2={k2:.3f} p1={p1:.4f} p2={p2:.4f}",
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1,
            )
            cv2.imshow(window, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("v"):
                show_original = not show_original
            elif key == ord("r"):
                cv2.setTrackbarPos("K1", window, radial_center)
                cv2.setTrackbarPos("K2", window, radial_center)
                cv2.setTrackbarPos("P1", window, tangent_center)
                cv2.setTrackbarPos("P2", window, tangent_center)
                cv2.setTrackbarPos("Focal x1000", window, 1000)
                cv2.setTrackbarPos("Alpha %", window, 0)
            elif key == ord("s"):
                np.savez(
                    calibration_file,
                    camera_matrix=undistorter.camera_matrix,
                    dist_coeffs=undistorter.dist_coeffs,
                    image_size=np.asarray(image_size, dtype=np.int32),
                    method=np.asarray("manual_straight_lines"),
                )
                saved = True
                print(f"Parameters saved to: {calibration_file}")
            elif key == ord("q"):
                break

            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to read a frame from the camera.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
    if not saved:
        print("Exited without saving parameters.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="USB camera preview, recording and lens-distortion correction",
        epilog=(
            "Checkerboard: python CameraTest_Cali_qipan.py --task calibrate "
            "--width 640 --height 480 --board-cols 9 --board-rows 6 "
            "--square-size 23"
        ),
    )
    parser.add_argument(
        "--task",
        choices=("camera_test", "video_record_by_frame",
                 "picture_record_by_click", "calibrate", "tune"),
        default="camera_test",
    )
    parser.add_argument("--camera", type=int, default=0, help="V4L2 camera index")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument(
        "--calibration", type=Path, default=DEFAULT_CALIBRATION_FILE,
        help="camera calibration .npz file",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.0,
        help="0 crops invalid borders; 1 keeps the full field of view",
    )
    parser.add_argument(
        "--no-undistort", action="store_true",
        help="show or record the original distorted image",
    )
    parser.add_argument("--output", default="output.avi")
    parser.add_argument("--output-fps", type=float, default=CAMERA_FPS)
    parser.add_argument(
        "--board-cols", type=int, default=9,
        help="checkerboard inner-corner columns",
    )
    parser.add_argument(
        "--board-rows", type=int, default=6,
        help="checkerboard inner-corner rows",
    )
    parser.add_argument(
        "--square-size", type=float, default=23.0,
        help="measured checkerboard square size in millimeters",
    )
    parser.add_argument(
        "--samples", type=int, default=20,
        help="number of checkerboard views to capture",
    )
    args = parser.parse_args()
    if not 0.0 <= args.alpha <= 1.0:
        parser.error("--alpha must be between 0 and 1")
    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be positive")
    if args.board_cols <= 1 or args.board_rows <= 1:
        parser.error("--board-cols and --board-rows must be greater than 1")
    if args.square_size <= 0:
        parser.error("--square-size must be positive")
    if args.samples < 12:
        parser.error("--samples must be at least 12")
    return args


def main():
    args = parse_args()
    if args.task == "video_record_by_frame":
        video_record_by_frame(args)
    elif args.task == "picture_record_by_click":
        picture_record_by_click(args)
    elif args.task == "calibrate":
        calibrate_camera(args)
    elif args.task == "tune":
        tune_distortion(args)
    else:
        camera_test(args)


if __name__ == "__main__":
    main()
