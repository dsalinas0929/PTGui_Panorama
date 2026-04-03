import cv2
import numpy as np
import os
from natsort import natsorted

image_folder = "output"
output_video = "output_videos/output_stabilized.mp4"
fps = 15

# ---- NEW: target resolution (fix codec issue) ----
TARGET_WIDTH = 3840  # change to 2560 or 1920 if needed

# Load images
images = natsorted([
    f for f in os.listdir(image_folder)
    if f.lower().endswith((".jpg", ".jpeg", ".png"))
])

# Read first frame
prev_frame = cv2.imread(os.path.join(image_folder, images[0]))
h, w = prev_frame.shape[:2]

# ---- NEW: compute resized dimensions ----
scale = TARGET_WIDTH / w
target_w = int(w * scale)
target_h = int(h * scale)

# ensure even dimensions (important for codecs)
target_w -= target_w % 2
target_h -= target_h % 2

prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)

# ---- UPDATED: safer codec ----
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_video, fourcc, fps, (target_w, target_h))

# Accumulated transform
transforms = np.zeros((len(images), 3), np.float32)

# --- STEP 1: Estimate transforms ---
for i in range(1, len(images)):
    print(f"Estimating transform for frame {i+1}/{len(images)}")
    curr_frame = cv2.imread(os.path.join(image_folder, images[i]))
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

    prev_pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200,
                                       qualityLevel=0.01, minDistance=30)

    curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, prev_pts, None)

    idx = status.flatten() == 1
    prev_pts = prev_pts[idx]
    curr_pts = curr_pts[idx]

    m, _ = cv2.estimateAffinePartial2D(prev_pts, curr_pts)

    if m is None:
        dx, dy, da = 0, 0, 0
    else:
        dx = m[0, 2]
        dy = m[1, 2]
        da = np.arctan2(m[1, 0], m[0, 0])

    transforms[i] = [dx, dy, da]
    prev_gray = curr_gray

# --- STEP 2: Smooth trajectory ---
trajectory = np.cumsum(transforms, axis=0)

def smooth(trajectory, radius=30):
    smoothed = np.copy(trajectory)
    for i in range(3):
        smoothed[:, i] = np.convolve(
            trajectory[:, i],
            np.ones(2 * radius + 1) / (2 * radius + 1),
            mode='same'
        )
    return smoothed

smoothed_trajectory = smooth(trajectory)
difference = smoothed_trajectory - trajectory
transforms_smooth = transforms + difference

# --- STEP 3: Apply transforms + brightness smoothing ---
prev_mean = None

for i in range(len(images)):
    print(f"Processing frame {i+1}/{len(images)}")
    frame = cv2.imread(os.path.join(image_folder, images[i]))

    dx, dy, da = transforms_smooth[i]

    m = np.array([
        [np.cos(da), -np.sin(da), dx],
        [np.sin(da),  np.cos(da), dy]
    ])

    stabilized = cv2.warpAffine(frame, m, (w, h))

    # --- Brightness smoothing ---
    gray = cv2.cvtColor(stabilized, cv2.COLOR_BGR2GRAY)
    mean_intensity = np.mean(gray)

    if prev_mean is None:
        prev_mean = mean_intensity

    alpha = prev_mean / (mean_intensity + 1e-6)
    stabilized = cv2.convertScaleAbs(stabilized, alpha=alpha, beta=0)

    prev_mean = 0.9 * prev_mean + 0.1 * mean_intensity

    # ---- NEW: resize BEFORE writing ----
    stabilized = cv2.resize(
        stabilized,
        (target_w, target_h),
        interpolation=cv2.INTER_AREA  # best for downscaling
    )

    out.write(stabilized)

out.release()
print("Done:", output_video)