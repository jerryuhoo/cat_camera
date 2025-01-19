from picamera2 import Picamera2
import cv2
import requests
import time
from datetime import datetime
import torch
from torchvision import transforms
from PIL import Image
from threading import Lock

# Telegram Bot configuration
BOT_TOKEN = ""  # Replace with your Telegram Bot Token
CHAT_ID = ""  # Replace with your Telegram Chat ID
# Load a pre-trained cat detection model (e.g., YOLOv5 or MobileNet)
model = torch.hub.load("ultralytics/yolov5", "yolov5n")  # Using YOLOv5 nano model
model.classes = [15]  # COCO class index for 'cat'
print(model.names, flush=True)


# Global lock to prevent concurrent access to resources
lock = Lock()


def capture_photo_with_picamera(picam2):
    """
    Capture a photo using Picamera2 and return it as an OpenCV image (numpy array).
    """
    try:
        frame = picam2.capture_array()  # Capture the image directly as a numpy array
        # Convert RGB to BGR for OpenCV
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return frame
    except Exception as e:
        print(f"Error capturing photo: {e}", flush=True)
        return None


def add_timestamp(image):
    """
    Add current time as text to the top-right corner of the image.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    color = (0, 255, 0)  # Green color in BGR
    thickness = 2

    # Calculate text position
    text_size = cv2.getTextSize(timestamp, font, font_scale, thickness)[0]
    text_x = image.shape[1] - text_size[0] - 10
    text_y = 30

    # Add timestamp
    cv2.putText(image, timestamp, (text_x, text_y), font, font_scale, color, thickness)
    return image


def send_telegram_photo(photo_path):
    """
    Send a photo to Telegram
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as photo:
        files = {"photo": photo}
        data = {"chat_id": CHAT_ID}
        response = requests.post(url, files=files, data=data)
    if response.status_code == 200:
        print("Photo sent successfully!", flush=True)
    else:
        print("Failed to send photo:", response.text, flush=True)


def detect_motion(prev_frame, current_frame, threshold=10000):
    """
    Detect motion by comparing the previous and current frame.
    """
    # Convert frames to grayscale
    gray_prev = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray_current = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

    # Calculate absolute difference
    diff = cv2.absdiff(gray_prev, gray_current)

    # Threshold the difference to create a binary image
    _, diff_binary = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

    # Count non-zero pixels (motion area)
    motion_area = cv2.countNonZero(diff_binary)

    if motion_area > threshold:
        print(f"Motion area: {motion_area}", flush=True)  # Debugging

    # Return True if motion area exceeds the threshold
    return motion_area > threshold


def detect_cat(image):
    """
    Detects cats using a pre-trained YOLOv5 model.
    Always prints the confidence for the 'cat' class, even if no cats are detected.
    """
    with lock:  # Ensure YOLO inference is thread-safe
        # Resize image to reduce model inference time
        resized_image = cv2.resize(image, (640, 480))

        # Convert the image to a PIL image
        pil_image = Image.fromarray(cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB))

        # Perform detection
        results = model(pil_image)
        detections = results.pandas().xyxy[
            0
        ]  # Get detection results as a Pandas DataFrame

        # Check if any detection exists
        if detections.empty:
            print("No objects detected in the frame.", flush=True)
            return False

        # Iterate through detections and check for 'cat'
        cat_detected = False
        for _, row in detections.iterrows():
            if row["name"] == "cat":
                print(
                    f"Detected: cat with confidence: {row['confidence']:.2f}",
                    flush=True,
                )
                if row["confidence"] > 0.3:  # Confidence threshold
                    cat_detected = True

        # If no cat is detected but there are detections
        if not cat_detected:
            print("No cat detected in this frame.", flush=True)

        return cat_detected


def motion_detection_and_notify():
    """
    Detect motion using frame difference and send a notification when motion is detected.
    """
    picam2 = Picamera2()
    picam2.configure(picam2.create_preview_configuration(main={"size": (1920, 1080)}))
    picam2.start()

    prev_frame = None
    last_detection_time = 0
    cooldown_period = 30  # Cooldown period in seconds

    try:
        while True:
            # Capture a photo with Picamera2
            with lock:  # Ensure exclusive access to the camera
                current_frame = capture_photo_with_picamera(picam2)

            if current_frame is None:
                print("Failed to capture photo, retrying...", flush=True)
                time.sleep(5)
                continue

            # Initialize previous frame
            if prev_frame is None:
                prev_frame = current_frame
                continue

            # Detect motion
            current_time = time.time()
            if detect_motion(prev_frame, current_frame) and (
                current_time - last_detection_time > cooldown_period
            ):
                detection_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{detection_time}] Motion detected!", flush=True)

                # Further detect if a cat is present
                if detect_cat(current_frame):
                    # Add timestamp to the image
                    frame_with_timestamp = add_timestamp(current_frame)

                    # Save the detected photo
                    detected_photo_path = "motion_detected.jpg"
                    cv2.imwrite(detected_photo_path, frame_with_timestamp)

                    # Send the photo to Telegram
                    send_telegram_photo(detected_photo_path)

                    # Update last detection time
                    last_detection_time = current_time

            # Update the previous frame
            prev_frame = current_frame
            time.sleep(2)
    finally:
        picam2.stop()


# Main program
if __name__ == "__main__":
    try:
        motion_detection_and_notify()
    except KeyboardInterrupt:
        print("Program stopped by user.", flush=True)
