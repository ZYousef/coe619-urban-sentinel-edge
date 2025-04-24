from pytubefix import YouTube  # Ensure pytube is correctly imported
from shutil import move
import os

# Specify the target path
target_path = 'helpers/loop.mp4'

# Check if the file already exists
if not os.path.exists(target_path):
    try:
        # Download the video
        yt = YouTube('https://www.youtube.com/watch?v=_yfmLXQrnEE')
        video_file = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first().download()

        # Ensure the directory exists
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # Move the file to the desired directory
        move(video_file, target_path)
        print("Video downloaded and moved successfully.")

    except FileNotFoundError:
        print("The downloaded file was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
else:
    print("The video file already exists at the target path.")
