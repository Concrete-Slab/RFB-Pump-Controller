import torch
import torch.nn as nn
from abc import ABC, abstractmethod

class ReLUConv(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=1, stride: int|None=None, bias=True, rectify=True,pad=0) -> None:
        if stride is None:
            stride = kernel_size
        self.conv = nn.Conv2d(in_channels,out_channels,kernel_size=kernel_size,stride=stride,bias=bias,padding=pad)
        self.bn = nn.BatchNorm2d(out_channels)
        self.rectify = rectify
        self.relu = nn.ReLU()
    def forward(self,x: torch.Tensor):
        x = self.conv(x)
        x = self.bn(x)
        if self.rectify:
            return self.relu(x)
        return x
    @property
    def in_channels(self) -> int:
        return self.conv.in_channels
    @property
    def out_channels(self) -> int:
        return self.conv.out_channels

class ResBlock(nn.Module,ABC):
    @abstractmethod
    def forward(self,x: torch.Tensor) -> torch.Tensor:
        pass
    @property
    @abstractmethod
    def in_channels(self) -> int:
        pass
    @property
    @abstractmethod
    def out_channels(self) -> int:
        pass
    @classmethod
    @abstractmethod
    def generate_network(self,in_channels: int, out_features: int, repetition_list: list[int], pooled=False, entry_channels=64) -> "BaseResNet":
        pass

class BottleneckBlock(ResBlock):
    def __init__(self, in_channels, intermediate_channels, out_channels, stride=1, identity_transform: nn.Module|None=None) -> None:
        self.conv1 = ReLUConv(in_channels,intermediate_channels,kernel_size=1,stride=1)
        self.conv2 = ReLUConv(intermediate_channels,intermediate_channels,kernel_size=3,stride=stride,pad=1)
        self.conv3 = ReLUConv(intermediate_channels,out_channels,kernel_size=1,stride=1,rectify=False)
        self.relu = nn.ReLU()
        self.identity_transformer = identity_transform
    @property
    def in_channels(self) -> int:
        return self.conv1.in_channels
    @property
    def out_channels(self) -> int:
        return self.conv3.out_channels
    def forward(self,x: torch.Tensor) -> torch.Tensor:
        identity = x.clone()
        if self.identity_transformer:
            identity = self.identity_transformer(identity)
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = x + identity
        x = self.relu(x)
        return x

    @classmethod
    def generate_network(cls, in_channels: int, out_features: int,repetition_list: list[int],pooled=False,expansion=4,entry_channels=64) -> "BaseResNet":
        layers = [*BaseResNet._make_section(entry_channels,entry_channels*expansion,repeats[0],intermediate_channels=entry_channels)]
        input_channels = entry_channels * expansion
        intermediate_channels = int(input_channels/2)
        output_channels = intermediate_channels * expansion
        for repeats in repetition_list[1:]:
            layers = [*layers,*BaseResNet._make_section(input_channels,output_channels,repeats,stride=2,intermediate_channels=intermediate_channels)]
            input_channels = output_channels
            intermediate_channels = int(input_channels/2)
            output_channels = intermediate_channels * expansion
        if pooled:
            return PooledResNet(layers,in_channels=in_channels,out_features=out_features)
        else:
            return ClassicResNet(layers,in_channels=in_channels,out_features=out_features)

class DoubleBlock(ResBlock):
    def __init__(self, in_channels, out_channels, stride=1, identity_transform:nn.Module|None = None) -> None:
        self.conv1 = ReLUConv(in_channels,out_channels,kernel_size=3,stride=stride,pad=1)
        self.conv2 = ReLUConv(out_channels,out_channels,kernel_size=3,stride=1,rectify=False,pad=1)
        self.identity_transform = identity_transform
        self.relu = nn.ReLU()
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        identity = x.clone()
        if self.identity_transform:
            identity = self.identity_transform(x)
        x = self.conv1(x)
        x = self.conv2(x)
        x = x + identity
        x = self.relu(x)
        return x
    @property
    def in_channels(self) -> int:
        return self.conv1.in_channels
    @property
    def out_channels(self) -> int:
        return self.conv2.out_channels

    @classmethod
    def generate_network(self,in_channels: int, out_features: int, repetition_list: list[int], pooled=False, entry_channels=64) -> "BaseResNet":
        layers = [*BaseResNet._make_section(entry_channels,entry_channels,repetition_list[0])]
        channels = entry_channels
        for repeats in repetition_list[1:]:
            layers = [*layers, *BaseResNet._make_section(channels,channels*2,repeats,stride=2)]
            channels = channels*2
        if pooled:
            return PooledResNet(layers,in_channels=in_channels,out_features=out_features)
        else:
            return ClassicResNet(layers,in_channels=in_channels,out_features=out_features)

class BaseResNet(nn.Module):
    def __init__(self, resblocks: list[ResBlock], in_channels=3, out_features: int = 5) -> None:
        self.resblocks = nn.ModuleList(resblocks)
        init_channels = resblocks[0].in_channels
        self._out_channels = resblocks[-1].out_channels
        self.conv1 = nn.Conv2d(in_channels=in_channels,out_channels=init_channels,kernel_size=(7,7),stride=2)
        self.mp = nn.MaxPool2d(kernel_size=3,stride=2)
        self.bn1 = nn.BatchNorm2d(init_channels)

    def forward(self, x: torch.Tensor):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.mp(x)
        for block in self.resblocks:
            x = block(x)
        return x
    
    @staticmethod
    def _make_section(in_channels,out_channels,repeats,stride=1,intermediate_channels: int|None=None,zero_pad = False):
        lst: list[ResBlock] = []
        if in_channels != out_channels or stride != 1:
            if zero_pad:
                identity_transform = ReLUConv(in_channels,out_channels,kernel_size=1,stride=stride,bias=False,rectify=False)
            else:
                identity_transform = ReLUConv(in_channels,out_channels,kernel_size=1,stride=stride,bias=False,rectify=False)
        else:
            identity_transform = None
        # first layer with identity transform and non-unity stride
        if intermediate_channels:
            lst.append(BottleneckBlock(in_channels,intermediate_channels,out_channels,stride=stride,identity_transform=identity_transform))
        else:
            lst.append(DoubleBlock(in_channels,out_channels,stride=stride,identity_transform=identity_transform))
        # remaining layers
        for i in range(1,repeats):
            if intermediate_channels:
                lst.append(BottleneckBlock(intermediate_channels,intermediate_channels,out_channels))
            else:
                lst.append(DoubleBlock(out_channels,out_channels))
        return lst
    
class ClassicResNet(BaseResNet):
    def __init__(self, resblocks: list[ResBlock], in_channels=3, out_features: int = 5) -> None:
        super().__init__(resblocks, in_channels, out_features)
        self.ap = nn.AdaptiveAvgPool2d((1,1))
        self.bn2 = nn.BatchNorm2d(self._out_channels)
        self.fcl = nn.Linear(self._out_channels,out_features)
    def forward(self, x: torch.Tensor):
        x = super().forward(x)
        x = self.ap(x)
        x = self.bn2(x)
        x = self.fcl(x)
        return x

class PooledResNet(BaseResNet):
    def __init__(self, resblocks: list[ResBlock], in_channels=3, out_features: int = 5) -> None:
        super().__init__(resblocks, in_channels, out_features)
        self.conv_final = nn.Conv2d(self._out_channels,out_features,kernel_size=3,stride=1,padding=1)
        self.bn2 = nn.BatchNorm2d(out_features)
        self.relu = nn.ReLU()
        self.ap = nn.AdaptiveAvgPool2d((1,1))
    def forward(self, x: torch.Tensor):
        x = super().forward(x)
        x = self.conv_final(x)
        x = self.bn2(x)
        x = self.ap(x)
        return x

def ResNet50(pooled=False,in_channels: int = 3, out_features: int = 5):
    return BottleneckBlock.generate_network(in_channels,out_features,[3,4,6,3],pooled=pooled)
def ResNet101(pooled=False,in_channels: int = 3, out_features: int = 5):
    return BottleneckBlock.generate_network(in_channels,out_features,[3,4,23,3],pooled=pooled)
def ResNet152(pooled=False,in_channels: int = 3, out_features: int = 5):
    return BottleneckBlock.generate_network(in_channels,out_features,[3,8,36,3],pooled=pooled)
def ResNet18(pooled=False,in_channels: int = 3, out_features: int =  5):
    return DoubleBlock.generate_network(in_channels,out_features,[2,2,2,2],pooled=pooled)
def ResNet34(pooled=False,in_channels: int = 3, out_features: int = 5):
    return DoubleBlock.generate_network(in_channels,out_features,[3,4,6,3],pooled=pooled)