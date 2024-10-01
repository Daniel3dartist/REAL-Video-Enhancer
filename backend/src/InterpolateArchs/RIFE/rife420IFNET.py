import torch
import torch.nn as nn


from torch.nn.functional import interpolate


def conv(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):
    return nn.Sequential(
        nn.Conv2d(
            in_planes,
            out_planes,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=True,
        ),
        nn.LeakyReLU(0.2, True),
    )


def conv_bn(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):
    return nn.Sequential(
        nn.Conv2d(
            in_planes,
            out_planes,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=False,
        ),
        nn.BatchNorm2d(out_planes),
        nn.LeakyReLU(0.2, True),
    )


class MyPixelShuffle(nn.Module):
    def __init__(self, upscale_factor):
        super(MyPixelShuffle, self).__init__()
        self.upscale_factor = upscale_factor

    def forward(self, x):
        b, c, hh, hw = x.size()
        out_channel = c // (self.upscale_factor**2)
        h = hh * self.upscale_factor
        w = hw * self.upscale_factor
        x_view = x.view(
            b, out_channel, self.upscale_factor, self.upscale_factor, hh, hw
        )
        return x_view.permute(0, 1, 4, 2, 5, 3).reshape(b, out_channel, h, w)


class Head(nn.Module):
    def __init__(self):
        super(Head, self).__init__()
        self.cnn0 = nn.Conv2d(3, 32, 3, 2, 1)
        self.cnn1 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn2 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(32, 8, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x, feat=False):
        x0 = self.cnn0(x)
        x = self.relu(x0)
        x1 = self.cnn1(x)
        x = self.relu(x1)
        x2 = self.cnn2(x)
        x = self.relu(x2)
        x3 = self.cnn3(x)
        if feat:
            return [x0, x1, x2, x3]
        return x3


class ResConv(nn.Module):
    def __init__(self, c, dilation=1):
        super(ResConv, self).__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, dilation, dilation=dilation, groups=1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)), requires_grad=True)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):
        return self.relu(self.conv(x) * self.beta + x)


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):
        super(IFBlock, self).__init__()
        self.conv0 = nn.Sequential(
            conv(in_planes, c // 2, 3, 2, 1),
            conv(c // 2, c, 3, 2, 1),
        )
        self.convblock = nn.Sequential(
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
        )
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(c, 4 * 6, 4, 2, 1), nn.PixelShuffle(2)
        )

    def forward(self, x, flow=None, scale=1):
        x = interpolate(
            x, scale_factor=1.0 / scale, mode="bilinear", align_corners=False
        )
        if flow is not None:
            flow = (
                interpolate(
                    flow, scale_factor=1.0 / scale, mode="bilinear", align_corners=False
                )
                / scale
            )
            x = torch.cat((x, flow), 1)
        feat = self.conv0(x)
        feat = self.convblock(feat)
        tmp = self.lastconv(feat)
        tmp = interpolate(tmp, scale_factor=scale, mode="bilinear", align_corners=False)
        flow = tmp[:, :4] * scale
        mask = tmp[:, 4:5]
        return flow, mask


class IFNet(nn.Module):
    def __init__(
        self,
        scale=1.0,
        ensemble=False,
        dtype=torch.float32,
        device="cuda",
        width=1920,
        height=1080,
        backwarp_tenGrid=None,
        tenFlow_div=None,
    ):
        super(IFNet, self).__init__()
        self.block0 = IFBlock(7 + 16, c=192)
        self.block1 = IFBlock(8 + 4 + 16, c=128)
        self.block2 = IFBlock(8 + 4 + 16, c=96)
        self.block3 = IFBlock(8 + 4 + 16, c=64)
        self.encode = Head()
        self.device = device
        self.dtype = dtype
        self.scale_list = [8 / scale, 4 / scale, 2 / scale, 1 / scale]
        self.ensemble = ensemble
        self.width = width
        self.height = height
        self.backWarp = backwarp_tenGrid
        self.tenFlow = tenFlow_div

        self.paddedHeight = backwarp_tenGrid.shape[2]
        self.paddedWidth = backwarp_tenGrid.shape[3]

        self.blocks = [self.block0, self.block1, self.block2, self.block3]

    def warp(self, tenInput, tenFlow):
        tenFlow = torch.cat(
            [tenFlow[:, 0:1] / self.tenFlow[0], tenFlow[:, 1:2] / self.tenFlow[1]], 1
        )

        g = (self.backWarp + tenFlow).permute(0, 2, 3, 1)
        return torch.nn.functional.grid_sample(
            input=tenInput,
            grid=g,
            mode="bilinear",
            padding_mode="border",
            align_corners=True,
        )

    def forward(self, img0, img1, timestep, f0, f1):
        warped_img0 = img0
        warped_img1 = img1
        flow = None
        mask = None
        for i in range(4):
            if flow is None:
                flow, mask = self.blocks[i](
                    torch.cat((img0, img1, f0, f1, timestep), 1),
                    None,
                    scale=self.scale_list[i],
                )
                if self.ensemble:
                    f_, m_ = self.blocks[i](
                        torch.cat((img1, img0, f1, f0, 1 - timestep), 1),
                        None,
                        scale=self.scale_list[i],
                    )
                    flow = (flow + torch.cat((f_[:, 2:4], f_[:, :2]), 1)) / 2
                    mask = (mask + (-m_)) / 2
            else:
                wf0 = self.warp(f0, flow[:, :2])
                wf1 = self.warp(f1, flow[:, 2:4])
                fd, m0 = self.blocks[i](
                    torch.cat(
                        (
                            warped_img0,
                            warped_img1,
                            wf0,
                            wf1,
                            timestep,
                            mask,
                        ),
                        1,
                    ),
                    flow,
                    scale=self.scale_list[i],
                )
                if self.ensemble:
                    f_, m_ = self.blocks[i](
                        torch.cat(
                            (
                                warped_img1,
                                warped_img0,
                                wf1,
                                wf0,
                                1 - timestep,
                                -mask,
                            ),
                            1,
                        ),
                        torch.cat((flow[:, 2:4], flow[:, :2]), 1),
                        scale=self.scale_list[i],
                    )
                    fd = (fd + torch.cat((f_[:, 2:4], f_[:, :2]), 1)) / 2
                    mask = (m0 + (-m_)) / 2
                else:
                    mask = m0
                flow = flow + fd
            warped_img0 = self.warp(img0, flow[:, :2])
            warped_img1 = self.warp(img1, flow[:, 2:4])
        mask = torch.sigmoid(mask)
        return (
            (warped_img0 * mask + warped_img1 * (1 - mask))[
                :, :, : self.height, : self.width
            ][0]
            .permute(1, 2, 0)
            .mul(255)
        )
