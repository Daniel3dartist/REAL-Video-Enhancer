import os

from .constants import MODELS_PATH
from .Util import createDirectory, extractTarGZ
from .ui.QTcustom import DownloadProgressPopup, NetworkCheckPopup


class DownloadModel:
    """
    Takes in the name of a model and the name of the backend in the GUI, and downloads it from a URL
    model: any valid model used by RVE
    backend: the backend used (pytorch, tensorrt, ncnn)
    """

    def __init__(
        self,
        modelFile: str,
        downloadModelFile: str,
        modelPath: str = MODELS_PATH,
    ):
        self.modelPath = modelPath
        self.downloadModelFile = downloadModelFile
        self.downloadModelPath = os.path.join(modelPath, downloadModelFile)
        createDirectory(modelPath)

        if os.path.isfile(os.path.join(self.modelPath, modelFile)) or os.path.exists(
            os.path.join(self.modelPath, modelFile)
        ):
            return
        if NetworkCheckPopup():
            self.downloadModel(
                modelFile=downloadModelFile, downloadModelPath=self.downloadModelPath
            )

    def downloadModel(self, modelFile: str = None, downloadModelPath: str = None):
        url = (
            "https://github.com/TNTwise/real-video-enhancer-models/releases/download/models/"
            + modelFile
        )
        title = "Downloading: " + modelFile
        DownloadProgressPopup(link=url, title=title, downloadLocation=downloadModelPath)
        print("Done")
        if "tar.gz" in self.downloadModelFile:
            print("Extracting File")
            extractTarGZ(self.downloadModelPath)


# just some testing code lol
