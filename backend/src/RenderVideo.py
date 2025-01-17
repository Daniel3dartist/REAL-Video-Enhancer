from threading import Thread
import os
import math
from time import sleep

from .FFmpeg import FFMpegRender
from .utils.SceneDetect import SceneDetect
from .utils.Util import printAndLog, log, removeFile


class Render(FFMpegRender):
    """
    Subclass of FFmpegRender
    FFMpegRender options:
    inputFile: str, The path to the input file.
    outputFile: str, The path to the output file.
    interpolateTimes: int, this sets the multiplier for the framerate when interpolating, when only upscaling this will be set to 1.
    encoder: str, The exact name of the encoder ffmpeg will use (default=libx264)
    pixelFormat: str, The pixel format ffmpeg will use, (default=yuv420p)

    interpolateOptions:
    interpolationMethod
    upscaleModel
    backend (pytorch,ncnn,tensorrt)
    device (cpu,cuda)
    precision (float16,float32)

    NOTE:
    Everything in here has to happen in a specific order:
    Get the video properties (res,fps,etc)
    set up upscaling/interpolation, this gets the scale for upscaling if upscaling is the current task
    assign framechunksize to a value, as this is needed to catch bytes and set up shared memory
    set up shared memory
    """

    def __init__(
        self,
        inputFile: str,
        outputFile: str,
        # backend settings
        backend="pytorch",
        device="default",
        precision="float16",
        # model settings
        upscaleModel=None,
        interpolateModel=None,
        interpolateFactor: int = 1,
        tile_size=None,
        # ffmpeg settings
        custom_encoder: str = "libx264",
        pixelFormat: str = "yuv420p",
        benchmark: bool = False,
        overwrite: bool = False,
        crf: str = "18",
        video_encoder_preset: str = "x264",
        audio_encoder_preset: str = "aac",
        audio_bitrate: str = "192k",
        # misc
        pausedFile=None,
        sceneDetectMethod: str = "pyscenedetect",
        sceneDetectSensitivity: float = 3.0,
        sharedMemoryID: str = None,
        trt_optimization_level: int = 3,
        upscale_output_resolution: str = None,
        UHD_mode: bool = False,
        slomo_mode: bool = False,
        dynamic_scaled_optical_flow: bool = False,
        ensemble: bool = False,
    ):
        if pausedFile is None:
            pausedFile = os.path.basename(inputFile) + "_paused_state.txt"
        self.inputFile = inputFile
        self.pausedFile = pausedFile
        with open(self.pausedFile, "w") as f:
            f.write("False")
        self.backend = backend
        self.upscaleModel = upscaleModel
        self.interpolateModel = interpolateModel
        self.tilesize = tile_size
        self.device = device
        self.precision = precision
        self.upscaleTimes = 1  # if no upscaling, it will default to 1
        self.interpolateFactor = interpolateFactor
        # max timestep is a hack to make sure ncnn cache frames too early, and ncnn breaks if i modify the code at all so ig this is what we are doing
        self.maxTimestep = (interpolateFactor - 1) / interpolateFactor
        self.ncnn = self.backend == "ncnn"
        self.ceilInterpolateFactor = math.ceil(self.interpolateFactor)
        self.setupRender = self.returnFrame  # set it to not convert the bytes to array by default, and just pass chunk through
        self.setupFrame0 = None
        self.interpolateOption = None
        self.upscaleOption = None
        self.isPaused = False
        self.sceneDetectMethod = sceneDetectMethod
        self.sceneDetectSensitivty = sceneDetectSensitivity
        self.sharedMemoryID = sharedMemoryID
        self.trt_optimization_level = trt_optimization_level
        self.uncacheNextFrame = False
        self.UHD_mode = UHD_mode
        self.dynamic_scaled_optical_flow = dynamic_scaled_optical_flow
        self.ensemble = ensemble
        # get video properties early
        self.getVideoProperties(inputFile)

        printAndLog("Using backend: " + self.backend)
        # upscale has to be called first to get the scale of the upscale model
        if upscaleModel:
            self.setupUpscale()

            printAndLog("Using Upscaling Model: " + self.upscaleModel)
        if interpolateModel:
            self.setupInterpolate()

            printAndLog("Using Interpolation Model: " + self.interpolateModel)

        super().__init__(
            inputFile=inputFile,
            outputFile=outputFile,
            interpolateFactor=interpolateFactor,
            upscaleTimes=self.upscaleTimes,
            custom_encoder=custom_encoder,
            pixelFormat=pixelFormat,
            benchmark=benchmark,
            overwrite=overwrite,
            crf=crf,
            video_encoder_preset=video_encoder_preset,
            audio_encoder_preset=audio_encoder_preset,
            audio_bitrate=audio_bitrate,
            sharedMemoryID=sharedMemoryID,
            channels=3,
            upscale_output_resolution=upscale_output_resolution,
            slowmo_mode=slomo_mode,
        )

        self.sharedMemoryThread.start()
        self.renderThread = Thread(target=self.render)
        self.readPausedFileThread1 = Thread(target=self.readPausedFileThread)
        self.ffmpegReadThread = Thread(target=self.readinVideoFrames)
        self.ffmpegWriteThread = Thread(target=self.writeOutVideoFrames)

        self.ffmpegReadThread.start()
        self.ffmpegWriteThread.start()
        self.renderThread.start()
        self.readPausedFileThread1.start()

    def readPausedFileThread(self):
        activate = True
        self.prevState = False
        while not self.writingDone:
            if os.path.isfile(self.pausedFile):
                with open(self.pausedFile, "r") as f:
                    self.isPaused = f.read().strip() == "True"
                    activate = self.prevState != self.isPaused
                if activate:
                    if self.isPaused:
                        if self.interpolateOption:
                            self.interpolateOption.hotUnload()
                        if self.upscaleOption:
                            self.upscaleOption.hotUnload()
                        print("\nRender Paused")
                    else:
                        print("\nResuming Render")
                        if self.upscaleOption:
                            self.upscaleOption.hotReload()
                        if self.interpolateOption:
                            self.interpolateOption.hotReload()
                self.prevState = self.isPaused
            sleep(1)

    def render(self):
        while True:
            if not self.isPaused:
                frame = self.readQueue.get()
                if frame is None:
                    break

                if self.interpolateModel:
                    self.interpolateOption(
                        img1=frame,
                        writeQueue=self.writeQueue,
                        transition=self.sceneDetect.detect(frame),
                        upscaleModel=self.upscaleOption,
                    )
                if self.upscaleModel:
                    frame = self.upscaleOption(
                        self.upscaleOption.frame_to_tensor(frame)
                    )

                self.writeQueue.put(frame)
            else:
                sleep(1)
        self.writeQueue.put(None)
        removeFile(self.pausedFile)

    def setupUpscale(self):
        """
        This is called to setup an upscaling model if it exists.
        Maps the self.upscaleTimes to the actual scale of the model
        Maps the self.setupRender function that can setup frames to be rendered
        Maps the self.upscale the upscale function in the respective backend.
        For interpolation:
        Mapss the self.undoSetup to the tensor_to_frame function, which undoes the prep done in the FFMpeg thread. Used for SCDetect
        """
        printAndLog("Setting up Upscale")
        if self.backend == "pytorch" or self.backend == "tensorrt":
            from .pytorch.UpscaleTorch import UpscalePytorch

            self.upscaleOption = UpscalePytorch(
                self.upscaleModel,
                device=self.device,
                precision=self.precision,
                width=self.width,
                height=self.height,
                backend=self.backend,
                tilesize=self.tilesize,
                trt_optimization_level=self.trt_optimization_level,
            )
            self.upscaleTimes = self.upscaleOption.getScale()

        if self.backend == "ncnn":
            from .ncnn.UpscaleNCNN import UpscaleNCNN, getNCNNScale

            path, last_folder = os.path.split(self.upscaleModel)
            self.upscaleModel = os.path.join(path, last_folder, last_folder)
            self.upscaleTimes = getNCNNScale(modelPath=self.upscaleModel)
            self.upscaleOption = UpscaleNCNN(
                modelPath=self.upscaleModel,
                num_threads=1,
                scale=self.upscaleTimes,
                gpuid=0,  # might have this be a setting
                width=self.width,
                height=self.height,
                tilesize=self.tilesize,
            )

        if self.backend == "directml":  # i dont want to work with this shit
            from .onnx.UpscaleONNX import UpscaleONNX

            upscaleONNX = UpscaleONNX(
                modelPath=self.upscaleModel,
                precision=self.precision,
                width=self.width,
                height=self.height,
            )

    def setupInterpolate(self):
        log("Setting up Interpolation")
        self.sceneDetect = SceneDetect(
            sceneChangeMethod=self.sceneDetectMethod,
            sceneChangeSensitivity=self.sceneDetectSensitivty,
            width=self.width,
            height=self.height,
        )
        if self.sceneDetectMethod != "none":
            printAndLog("Scene Detection Enabled")

        else:
            printAndLog("Scene Detection Disabled")

        if self.backend == "ncnn":
            from .ncnn.InterpolateNCNN import InterpolateRIFENCNN

            self.interpolateOption = InterpolateRIFENCNN(
                interpolateModelPath=self.interpolateModel,
                width=self.width,
                height=self.height,
                max_timestep=self.maxTimestep,
                interpolateFactor=self.ceilInterpolateFactor,
            )

        if self.backend == "pytorch" or self.backend == "tensorrt":
            from .pytorch.InterpolateTorch import InterpolateFactory

            self.interpolateOption = InterpolateFactory.build_interpolation_method(
                self.interpolateModel,
                self.backend,
            )(
                modelPath=self.interpolateModel,
                ceilInterpolateFactor=self.ceilInterpolateFactor,
                width=self.width,
                height=self.height,
                device=self.device,
                dtype=self.precision,
                backend=self.backend,
                UHDMode=self.UHD_mode,
                trt_optimization_level=self.trt_optimization_level,
                ensemble=self.ensemble,
                dynamicScaledOpticalFlow=self.dynamic_scaled_optical_flow,
            )
