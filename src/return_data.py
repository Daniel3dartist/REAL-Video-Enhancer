import cv2
import os 
class Fps:
    def return_video_fps(videopath):
        video=cv2.VideoCapture(fr'{videopath}')
        return video.get(cv2.CAP_PROP_FPS)
    
class VideoName:
    def return_video_name(videopath):
        return os.path.basename(videopath)
    def return_video_framerate(videopath):
        video = cv2.VideoCapture(videopath)
        return video.get(cv2.CAP_PROP_FPS)
    def return_video_frame_count(videopath):
        video = cv2.VideoCapture(videopath)
        return video.get(cv2.CAP_PROP_FRAME_COUNT)
class ManageFiles:
    
    def create_folder(folderpath):
        if os.path.exists(folderpath) == False:
            os.mkdir(folderpath)

    def create_file(filepath):
        if os.path.isfile(filepath) == False:
            os.mknod(filepath)

    def isfile(filepath):
        return os.path.isfile(filepath)
            
    def isfolder(folderpath):
        return os.path.exists(folderpath)