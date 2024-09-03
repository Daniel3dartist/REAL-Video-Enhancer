import os
import warnings
import platform

def isFlatpak():
    return "FLATPAK_ID" in os.environ
if isFlatpak():
    cwd = os.path.join(os.path.expanduser("~"), ".var", "app", "io.github.tntwise.REAL-Video-Enhancer")
    if not os.path.exists(cwd):
        cwd = os.path.join(os.path.expanduser("~"), ".var", "app", "io.github.tntwise.REAL-Video-EnhancerV2")
else:
    cwd = os.getcwd()
with open(os.path.join(cwd, "backend_log.txt"), "w") as f:
    pass


def warnAndLog(message: str):
    warnings.warn(message)
    log("WARN: " + message)


def errorAndLog(message: str):
    log("ERROR: " + message)
    raise os.error("ERROR: " + message)


def printAndLog(message: str, separate=False):
    """
    Prints and logs a message to the log file
    separate, if True, activates the divider
    """
    if separate:
        message = message + "\n" + "---------------------"
    print(message)
    log(message=message)


def log(message: str):
    with open(os.path.join(cwd, "backend_log.txt"), "a") as f:
        f.write(message + "\n")


def currentDirectory():
    return cwd


def modelsDirectory():
    return os.path.join(cwd, "models")


def checkForPytorch() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        import torch
        import torchvision
        import spandrel

        return True
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))


def checkForTensorRT() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        import torch
        import torchvision
        import spandrel
        import tensorrt
        import torch_tensorrt

        return True
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))


def check_bfloat16_support() -> bool:
    """
    Function that checks if the torch backend supports bfloat16
    """
    import torch

    try:
        x = torch.tensor([1.0], dtype=torch.bfloat16)
        return True
    except RuntimeError:
        return False

def checkForDirectML() -> bool:
    """
    Function that checks if the onnxruntime DirectML backend is available
    """
    try:
        import onnxruntime as ort

        # Check if DirectML execution provider is available
        providers = ort.get_available_providers()
        if 'DmlExecutionProvider' in providers:
            return True
        else:
            log("DirectML execution provider not available")
            return False
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))
        return False

def checkForNCNN() -> bool:
    """
    function that checks if the pytorch backend is available
    """
    try:
        from rife_ncnn_vulkan_python import Rife
        from upscale_ncnn_py import UPSCALE

        return True
    except ImportError as e:
        log(str(e))
        return False
    except Exception as e:
        log(str(e))
