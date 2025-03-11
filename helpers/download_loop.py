from pytubefix import YouTube # This is solution
from shutil import move
YouTube('https://www.youtube.com/watch?v=992eWJp0_No').streams.first().download()
yt = YouTube('https://www.youtube.com/watch?v=992eWJp0_No')
video_file = yt.streams.filter(progressive=True, file_extension='mp4') .order_by('resolution').desc().first().download()
move(video_file, 'helpers/loop.mp4')