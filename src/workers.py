
from PyQt5 import QtWidgets, uic
import sys
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from PyQt5.QtWidgets import QApplication, QWidget, QInputDialog, QLineEdit, QFileDialog, QMessageBox, QListWidget, QListWidgetItem
from PyQt5.QtGui import QTextCursor
import mainwindow
import os
from threading import *
from src.settings import *
from src.return_data import *
from time import sleep

class pb2X(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    def __init__(self,parent, videoName):
        QThread.__init__(self, parent)
        self.videoName = videoName
        self.settings = Settings()
   
    def run(self):
        """Long-running task."""
        
        while ManageFiles.isfolder(f'{self.settings.RenderDir}/{self.videoName}_temp/output_frames/') == False:
            sleep(1)
        

        total_input_files = len(os.listdir(f'{self.settings.RenderDir}/{self.videoName}_temp/input_frames/'))
        total_output_files = total_input_files * 2
        
        
        
        
        
        while ManageFiles.isfolder(f'{self.settings.RenderDir}/{self.videoName}_temp/') == True:
                if ManageFiles.isfolder(f'{self.settings.RenderDir}/{self.videoName}_temp/') == True:
                    try:
                        files_processed = len(os.listdir(f'{self.settings.RenderDir}/{self.videoName}_temp/output_frames/'))
                    except:
                        pass
                    try:
                        latest_image = self.get_latest_image()
                    except:
                        latest_image= None

                    sleep(0.5)
                    
                    self.progress.emit(files_processed)
        self.finished.emit()


class showLogs(QObject):
    finished = pyqtSignal()
    extractionProgress = pyqtSignal(int)
    
    def __init__(self,parent, videoName):
        QThread.__init__(self, parent)
        self.videoName = videoName
        self.settings = Settings()
    def run(self):
        """Long-running task."""
        
        while os.path.exists(f'{self.settings.RenderDir}/{self.videoName}_temp/output_frames/') == False:
            if os.path.exists(f'{self.settings.RenderDir}/{self.videoName}_temp/input_frames/'):
                files_extracted = len(os.listdir(f'{self.settings.RenderDir}/{self.videoName}_temp/input_frames/'))
                self.extractionProgress.emit(files_extracted)
        self.finished.emit()