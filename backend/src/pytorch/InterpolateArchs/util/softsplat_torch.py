import torch
##########################################################
device = "cuda" if torch.cuda.is_available() else "cpu"


torch.set_float32_matmul_precision("medium")
torch.set_grad_enabled(False)


@torch.inference_mode()
@torch.compile
def main_softsplat(
        tenIn: torch.Tensor, tenFlow: torch.Tensor
    ):
        N, C, H, W = tenIn.size()
        device = tenIn.device
        origdtype = tenIn.dtype

        # Initialize output tensor
        tenOut = torch.zeros_like(tenIn)
        
        # Create meshgrid of pixel coordinates
        gridY, gridX = torch.meshgrid(
            torch.arange(H, device=device, dtype=origdtype),
            torch.arange(W, device=device, dtype=origdtype),
            indexing='ij'
        )  # [H, W]
        gridY,gridX = (gridY.unsqueeze(0).unsqueeze(0).expand(N, 1, H, W), gridX.unsqueeze(0).unsqueeze(0).expand(N, 1, H, W))
        batch_indices = torch.arange(N, device=device).view(N, 1, 1).expand(N, H, W).reshape(-1)

        # Compute fltX and fltY
        fltX = gridX + tenFlow[:, 0:1, :, :]
        fltY = gridY + tenFlow[:, 1:2, :, :]

        # Flatten variables
        fltX_flat = fltX.reshape(-1)
        fltY_flat = fltY.reshape(-1)
        tenIn_flat = tenIn.permute(0, 2, 3, 1).reshape(-1, C)

        

        # Finite mask
        finite_mask = torch.isfinite(fltX_flat) & torch.isfinite(fltY_flat)
        

        fltX_flat = fltX_flat[finite_mask]
        fltY_flat = fltY_flat[finite_mask]
        tenIn_flat = tenIn_flat[finite_mask]
        batch_indices = batch_indices[finite_mask]

        # Compute integer positions
        intNW_X = torch.floor(fltX_flat).to(dtype=torch.int32)
        intNW_Y = torch.floor(fltY_flat).to(dtype=torch.int32)
        intNE_X = intNW_X + 1
        intNE_Y = intNW_Y
        intSW_X = intNW_X
        intSW_Y = intNW_Y + 1
        intSE_X = intNW_X + 1
        intSE_Y = intNW_Y + 1

        # Compute weights
        fltNW = (intSE_X - fltX_flat) * (intSE_Y - fltY_flat)
        fltNE = (fltX_flat - intSW_X) * (intSW_Y - fltY_flat)
        fltSW = (intNE_X - fltX_flat) * (fltY_flat - intNE_Y)
        fltSE = (fltX_flat - intNW_X) * (fltY_flat - intNW_Y)

        # Prepare output tensor flat
        tenOut_flat = tenOut.permute(0, 2, 3, 1).reshape(-1, C)

        # Define positions and weights
        positions = [
            (intNW_X, intNW_Y, fltNW),
            (intNE_X, intNE_Y, fltNE),
            (intSW_X, intSW_Y, fltSW),
            (intSE_X, intSE_Y, fltSE),
        ]

        H, W = int(H), int(W)

        for intX, intY, weight in positions:
            # Valid indices within image bounds
            valid_mask = (intX >= 0) & (intX < W) & (intY >= 0) & (intY < H)

            idx_b = batch_indices[valid_mask]
            idx_x = intX[valid_mask]
            idx_y = intY[valid_mask]
            w = weight[valid_mask]
            vals = tenIn_flat[valid_mask] * w.unsqueeze(1)

            # Compute linear indices
            idx_NHW = idx_b * H * W + idx_y * W + idx_x

            # Accumulate values using index_add_
            tenOut_flat.index_add_(0, idx_NHW, vals).to(dtype=origdtype)

        # Reshape tenOut back to [N, C, H, W]
        tenOut = tenOut_flat.view(N, H, W, C).permute(0, 3, 1, 2)
        return tenOut


class SoftSplat(torch.nn.Module):
    def __init__(self, mode: str, width: int = 0, height: int = 0):
        super(SoftSplat, self).__init__()
        self.mode = mode
        mode_parts = mode.split("-")
        mode_main = mode_parts[0]
        self.mode_sub = mode_parts[1] if len(mode_parts) > 1 else None
        self.op = None
        self.normalize = False
        match mode:
            case "avg":
                self.op = self.avg
            case "linear":
                self.op = self.linear
            case "soft":
                self.op = self.soft
        
        if mode_main in ["avg", "linear", "soft"]:
            self.normalize = True

    @torch.inference_mode()
    def norm(self, tenOut: torch.Tensor):
        if self.normalize:
            tenNormalize = tenOut[:, -1:, :, :]

            self.normalize_modes = {
                None: lambda x: x + 0.0000001,
                "addeps": lambda x: x + 0.0000001,
                "zeroeps": lambda x: torch.where(
                    x == 0.0, torch.tensor(1.0, device=x.device,dtype=x.dtype), x
                ),
                "clipeps": lambda x: x.clip(0.0000001, None),
            }

            if self.mode_sub in self.normalize_modes:
                tenNormalize = self.normalize_modes[self.mode_sub](tenNormalize)

            tenOut = tenOut[:, :-1, :, :] / tenNormalize
        return tenOut

    @staticmethod
    @torch.inference_mode()
    def avg(tenIn: torch.Tensor):
        return torch.cat(
                [
                    tenIn,
                    tenIn.new_ones([tenIn.shape[0], 1, tenIn.shape[2], tenIn.shape[3]]),
                ],
                1,
            ),
    @staticmethod
    @torch.inference_mode()
    def linear(tenIn: torch.Tensor, tenMetric: torch.Tensor):
        return torch.cat([tenIn * tenMetric, tenMetric], 1)
    
    @staticmethod
    @torch.inference_mode()
    @torch.jit.script
    def soft(tenIn: torch.Tensor, tenMetric: torch.Tensor):
        return torch.cat([tenIn * tenMetric.exp(), tenMetric.exp()], 1)

    @torch.inference_mode()
    def forward(self, tenIn, tenFlow, tenMetric, strMode: str = "soft"):
        if self.op is not None:
            tenIn = self.op(tenIn, tenMetric)
        
        tenOut = main_softsplat(tenIn, tenFlow)
        tenOut = self.norm(tenOut)

        return tenOut
    

warp = SoftSplat("soft")
