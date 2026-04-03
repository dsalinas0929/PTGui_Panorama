import subprocess

cmd = [
    "ffmpeg",
    "-framerate", "15",
    "-pattern_type", "glob",
    "-i", "output/*.jpg",
    "-vf", "scale=3840:-2",
    "-c:v", "libx264",
    "-crf", "18",
    "-preset", "slow",
    "-pix_fmt", "yuv420p",
    "output_videos/output_ffmpeg.mp4"
]

subprocess.run(cmd, check=True)