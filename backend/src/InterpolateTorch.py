import torch
import torch.nn.functional as F
import math
import os
from .Util import currentDirectory, printAndLog, errorAndLog, modelsDirectory

torch.set_float32_matmul_precision("high")
torch.set_grad_enabled(False)


class InterpolateRifeTorch:
    @torch.inference_mode()
    def __init__(
        self,
        interpolateModelPath: str,
        interpolateArch: str = "rife413",
        width: int = 1920,
        height: int = 1080,
        device: str = "default",
        dtype: str = "float16",
        backend: str = "pytorch",
        UHDMode: bool = False,
        ensemble: bool = False,
        # trt options
        trt_workspace_size: int = 0,
        trt_max_aux_streams: int | None = None,
        trt_optimization_level: int = 5,
        trt_cache_dir: str = modelsDirectory(),
        trt_debug: bool = False,
    ):
        if device == "default":
            if torch.cuda.is_available():
                device = torch.device(
                    "cuda", 0
                )  # 0 is the device index, may have to change later
            else:
                device = torch.device("cpu")
        else:
            decice = torch.device(device)

        printAndLog("Using device: " + str(device))


        self.interpolateModel = interpolateModelPath
        self.width = width
        self.height = height
        self.device = device
        self.dtype = self.handlePrecision(dtype)
        self.backend = backend
        scale = 1
        if UHDMode:
            scale = 0.5

        state_dict = torch.load(
            interpolateModelPath, map_location=self.device, weights_only=True, mmap=True
        )

        tmp = max(32, int(32 / scale))
        self.pw = math.ceil(self.width / tmp) * tmp
        self.ph = math.ceil(self.height / tmp) * tmp
        self.padding = (0, self.pw - self.width, 0, self.ph - self.height)

        # detect what rife arch to use
        match interpolateArch:
            case "rife46":
                from .InterpolateArchs.RIFE.rife46IFNET import IFNet

                v1 = True
            case "rife47":
                from .InterpolateArchs.RIFE.rife47IFNET import IFNet

                v1 = True
            case "rife413":
                from .InterpolateArchs.RIFE.rife413IFNET import IFNet

                v1 = False
            case "rife420":
                from .InterpolateArchs.RIFE.rife420IFNET import IFNet

                v1 = False
            case "rife421":
                from .InterpolateArchs.RIFE.rife421IFNET import IFNet

                v1 = False
            case _:
                errorAndLog("Invalid Interpolation Arch")

        # if 4.6 v1
        if v1:
            self.tenFlow_div = torch.tensor(
                [(self.pw - 1.0) / 2.0, (self.ph - 1.0) / 2.0],
                dtype=self.dtype,
                device=self.device,
            )
            tenHorizontal = (
                torch.linspace(-1.0, 1.0, self.pw, dtype=self.dtype, device=self.device)
                .view(1, 1, 1, self.pw)
                .expand(-1, -1, self.ph, -1)
            ).to(dtype=self.dtype, device=self.device)
            tenVertical = (
                torch.linspace(-1.0, 1.0, self.ph, dtype=self.dtype, device=self.device)
                .view(1, 1, self.ph, 1)
                .expand(-1, -1, -1, self.pw)
            ).to(dtype=self.dtype, device=self.device)
            self.backwarp_tenGrid = torch.cat([tenHorizontal, tenVertical], 1)

        else:
            # if v2
            h_mul = 2 / (self.pw - 1)
            v_mul = 2 / (self.ph - 1)
            self.tenFlow_div = torch.Tensor([h_mul, v_mul]).to(
                device=self.device, dtype=self.dtype
            )

            self.backwarp_tenGrid = torch.cat(
                (
                    (torch.arange(self.pw) * h_mul - 1)
                    .reshape(1, 1, 1, -1)
                    .expand(-1, -1, self.ph, -1),
                    (torch.arange(self.ph) * v_mul - 1)
                    .reshape(1, 1, -1, 1)
                    .expand(-1, -1, -1, self.pw),
                ),
                dim=1,
            ).to(device=self.device, dtype=self.dtype)

        self.flownet = IFNet(
            scale=scale,
            ensemble=ensemble,
            dtype=self.dtype,
            device=self.device,
        )

        state_dict = {
            k.replace("module.", ""): v for k, v in state_dict.items() if "module." in k
        }
        self.flownet.load_state_dict(state_dict=state_dict, strict=False)
        self.flownet.eval().to(device=self.device, dtype=self.dtype)

        if self.backend == "tensorrt":
            import tensorrt
            import torch_tensorrt

            
            trt_engine_path = os.path.join(
                os.path.realpath(trt_cache_dir),
                (
                    f"{os.path.basename(self.interpolateModel)}"
                    + f"_{self.pw}x{self.ph}"
                    + f"_{'fp16' if self.dtype == torch.float16 else 'fp32'}"
                    + f"_scale-{scale}"
                    + f"_ensemble-{ensemble}"
                    + f"_{torch.cuda.get_device_name(self.device)}"
                    + f"_trt-{tensorrt.__version__}"
                    + (
                        f"_workspace-{trt_workspace_size}"
                        if trt_workspace_size > 0
                        else ""
                    )
                    + (
                        f"_aux-{trt_max_aux_streams}"
                        if trt_max_aux_streams is not None
                        else ""
                    )
                    + (
                        f"_level-{trt_optimization_level}"
                        if trt_optimization_level is not None
                        else ""
                    )
                    + ".ts"
                ),
            )
            if not os.path.isfile(trt_engine_path):
                inputs = [
                torch.zeros((1, 3, self.ph, self.pw), dtype=self.dtype, device=device),
                torch.zeros((1, 3, self.ph, self.pw), dtype=self.dtype, device=device),
                torch.zeros((1, 1, self.ph, self.pw), dtype=self.dtype, device=device),
                torch.zeros((2,), dtype=self.dtype, device=device),
                torch.zeros((1, 2, self.ph, self.pw), dtype=self.dtype, device=device),
                ]
                self.flownet = torch_tensorrt.compile(
                        self.flownet,
                        ir="dynamo",
                        inputs=inputs,
                        enabled_precisions={self.dtype},
                        debug=trt_debug,
                        workspace_size=trt_workspace_size,
                        min_block_size=1,
                        max_aux_streams=trt_max_aux_streams,
                        optimization_level=trt_optimization_level,
                        device=device,
                    )

                torch_tensorrt.save(self.flownet, trt_engine_path, inputs=inputs)

            self.flownet = torch.export.load(trt_engine_path).module()

    def handlePrecision(self, precision):
        if precision == "float32":
            return torch.float32
        if precision == "float16":
            return torch.float16

    @torch.inference_mode()
    def process(self, img0, img1, timestep):
        timestep = torch.full(
            (1, 1, self.ph, self.pw), timestep, dtype=self.dtype, device=self.device
        )

        output = self.flownet(
            img0, img1, timestep, self.tenFlow_div, self.backwarp_tenGrid
        )
        return self.tensor_to_frame(output)

    @torch.inference_mode()
    def tensor_to_frame(self, frame: torch.Tensor):
        """
        Takes in a 4d tensor, undoes padding, and converts to np array for rendering
        """
        frame = frame[:, :, : self.height, : self.width][0]
        return (
            frame.squeeze(0)
            .permute(1, 2, 0)
            .float()
            .mul(255)
            .byte()
            .contiguous()
            .cpu()
            .numpy()
        )

    @torch.inference_mode()
    def frame_to_tensor(self, frame) -> torch.Tensor:
        frame = (
            torch.frombuffer(
                frame,
                dtype=torch.uint8,
            )
            .reshape(self.height, self.width, 3)
            .to(device=self.device, dtype=self.dtype, non_blocking=True)
            .permute(2, 0, 1)
            .unsqueeze(0)
            / 255.0
        )
        return F.pad(
            (frame),
            self.padding,
        )
