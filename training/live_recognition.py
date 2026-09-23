"""
Continuous webcam authentication loop, intended to run on a kiosk PC
next to the entrance camera. Captures a frame every few seconds,
POSTs it to the running FastAPI server's /api/auth/login-face
endpoint, and prints the result. All DB writes and Telegram/Email
alerts happen server-side (see app/services/attendance.py), so
multiple kiosks can share one backend safely.

Usage:
    python training/live_recognition.py --server http://localhost:8000 --camera-id CAM-01
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import cv2
import requests

from app.face.camera import capture_frame, open_camera


def main():
    parser = argparse.ArgumentParser(description="Live face-recognition authentication loop")
    parser.add_argument("--server", default="http://localhost:8000")
    parser.add_argument("--camera-id", default="CAM-01")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--interval", type=float, default=3.0, help="Seconds between recognition attempts")
    parser.add_argument("--key", default="camera-secret-api-key", help="Camera API Key")
    parser.add_argument("--insecure", action="store_true", help="Bypass SSL certificate verification for self-signed certificates")
    args = parser.parse_args()

    print(f"Starting live recognition against {args.server} (camera {args.camera_id}). Ctrl+C to stop.")

    with open_camera(args.camera_index) as cap:
        while True:
            frame = capture_frame(cap)
            cv2.imshow("Live Authentication - Ctrl+C in terminal to stop", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue

            try:
                response = requests.post(
                    f"{args.server}/api/auth/login-face",
                    files={"file": ("frame.jpg", buffer.tobytes(), "image/jpeg")},
                    data={"camera_id": args.camera_id},
                    headers={"X-Camera-Key": args.key},
                    verify=not args.insecure,
                    timeout=10,
                )
                response.raise_for_status()
                result = response.json()
                if result.get("authenticated"):
                    print(f"✅ {result['full_name']} authenticated ({result['confidence']*100:.1f}%)")
                else:
                    print(f"⚠ {result['message']}")
            except requests.RequestException as exc:
                print(f"Request to server failed: {exc}")

            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cv2.destroyAllWindows()
