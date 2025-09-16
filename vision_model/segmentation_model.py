from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable
import cv2
import numpy as np
import torch
from torch.optim import Optimizer
from vision_model.GLOBALS import Metrics, Configuration, LogStage
from vision_model.common_functions import reduce_mask
import torch.nn as nn
import torch.optim.lr_scheduler as lrs
import segmentation_models_pytorch as smp

@runtime_checkable
class SupportsLog(Protocol):
    def log(self,data: float, metric: Metrics, stage: LogStage) -> None: ...

class _ValueList:
    """List that retains the minimum required memory space, avoiding hefty append calls during training"""
    def __init__(self, initial: list[torch.NumberType]|None=None):
        if initial is None:
            initial = []
        self.values = initial
        self.__i = len(initial)
    def append(self, val: torch.NumberType):
        if len(self.values) == self.__i:
            self.values.append(val)
        else:
            self.values[self.__i] = val
        self.__i += 1
    def getavg(self):
        avg = sum(self.values[:self.__i+1])/(self.__i+1)
        self.clear()
        return avg
    def clear(self):
        for i in range(0,len(self.values)):
            self.values[i] = float("nan")
        self.__i = 0

    def __getitem__(self,index: int):
        if index>=len(self):
            raise IndexError(f"Index {index} is out of range for _ValueList of length {len(self)}")
        return self.values[index]
    def __len__(self):
        return self.__i
    def __iter__(self):
        return self.values[:self.__i+1]

class GenericModule(ABC):
    def __init__(self, 
                 model: torch.nn.Module,
                 device: torch.DeviceObjType,
                 learning_rate: float,
                 initial_batchnorm = False,
                 alpha_channel = False,
                 lr_scheduler_name: str|None = None,
                 lr_scheduler_args: dict[str,Any]|None = None) -> None:
        super().__init__()
        self._device = device
        model.to(device)
        self.model = model
        self.training_losses = _ValueList()
        self.validation_losses = _ValueList()
        self.val_ious = _ValueList()
        self.val_accuracies = _ValueList()
        self.test_accuracies = _ValueList()
        self.learning_rate = learning_rate
        self.test_ious = _ValueList()
        self.training = False
        self.epoch = 0
        self._bn0 = nn.BatchNorm2d(4 if alpha_channel else 3) if initial_batchnorm else None
        self.lr_name = lr_scheduler_name
        self.lr_args = lr_scheduler_args
        self.__logger: SupportsLog|None = None

    @property
    def logger(self) -> SupportsLog|None:
        return self.__logger

    @logger.setter
    def logger(self,val: SupportsLog|None):
        if not (val is None or isinstance(val,SupportsLog)):
            raise ValueError("Module's logger must be either None or a an instance of Logger")


    def log(self,name: Metrics, val: torch.NumberType, on_step = False):
        if self.logger is not None:
            self.logger.log(val,name,LogStage.STEP if on_step else LogStage.EPOCH)

    def train(self):
        self.training = True
        self.epoch=0
        self.model.train()
    
    def eval(self):
        self.training = False
        self.model.eval()

    @property
    @abstractmethod
    def loss_fn(self) -> Callable[...,torch.Tensor]:
        # if self.epoch<28:
        #     return lambda inp, target: self._dice(inp,target) + self._bce(inp,target)
        # return self._dice
        pass

    def training_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:
        inps,targets = batch
        inps.to(self._device)
        targets.to(self._device)
        preds = self.forward(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        loss_flt = loss.item()
        self.training_losses.append(loss_flt)
        self.log(Metrics.train_loss,loss_flt,on_step=True)
        return loss
    
    def test_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:
        inps,targets = batch
        preds = self(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        # loss_flt = loss.item()
        # self.log(Metrics.test_loss,loss_flt)
        return loss
    
    def validation_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:

        inps,targets = batch
        preds = self.forward(inps)
        loss = self.loss_fn(preds,targets)
        # self.log(Metrics.val_loss,loss.item())
        self.validation_losses.append(loss.item())
        return loss
    
    def on_train_epoch_end(self) -> None:
        self.epoch+=1
        mean_train_loss = self.training_losses.getavg()
        self.log(Metrics.mean_train_loss,mean_train_loss)

    def on_val_epoch_end(self) -> None:
        mean_val_loss = self.validation_losses.getavg()
        self.log(Metrics.mean_val_loss,mean_val_loss)

    def configure_optimizers(self) -> tuple[Optimizer,list[lrs.LRScheduler]]:
        #TODO fix this class
        optimizer = torch.optim.AdamW(self.model.parameters(),lr = self.learning_rate)

        if self.lr_name is None:
            return (optimizer,[])
        
        try:
            lr_class = getattr(lrs,self.lr_name)
        except AttributeError:
            raise ModuleException(f"{self.lr_name} is not a learning rate scheduler in package torch.optim.lr_scheduler")

        if self.lr_args is None:
            return (optimizer,[lr_class(optimizer)])

        config_args = {}
        for key in ["interval","frequency","monitor","strict","name"]:
            if key in self.lr_args.keys():
                val = self.lr_args.pop(key)
                config_args = {**config_args,key:val}
        
        if self.lr_name == "ReduceLROnPlateau" and "monitor" not in config_args.keys():
            raise ModuleException("ReduceLROnPlateau requires the \"monitor\" argument (string name from Metrics options)")

        lr_scheduler = lr_class(optimizer,**self.lr_args)

        if len(config_args.keys()) == 0:
            return (optimizer,[lr_scheduler])
        
        raise ValueError("Some configurement arguments are unrecognised")
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self._bn0 is not None:
            x = self._bn0(x)
        return self.model(x)

    @classmethod
    def from_configuration(cls,model: nn.Module,config: Configuration):
        return cls(
            model,
            learning_rate=config.learning_rate,
            alpha_channel=config.alpha_channel,
            lr_scheduler_name=config.lr_name,
            lr_scheduler_args=config.lr_args,
        )
    
    @classmethod
    def load_from_checkpoint(cls,ckpt_path: Path, model: torch.nn.Module, device: torch.DeviceObjType, learning_rate=0.01, **kwargs):
        map_location = None if torch.cuda.is_available() else {"cuda:0":"cpu"}
        checkpoint = torch.load(ckpt_path,map_location=map_location)
        model.load_state_dict(checkpoint["state_dict"])
        return cls(model, device, learning_rate, **kwargs)

class ModuleException(Exception):
    pass

class SegmentationModule(GenericModule):

    def __init__(self, model: nn.Module, learning_rate: float, initial_batchnorm=False, alpha_channel=False, lr_scheduler_name: str | None = None, lr_scheduler_args: dict[str, Any] | None = None) -> None:
        super().__init__(model, learning_rate, initial_batchnorm, alpha_channel, lr_scheduler_name, lr_scheduler_args)
        self._bce = nn.BCEWithLogitsLoss()
        self._dice = smp.losses.DiceLoss(smp.losses.BINARY_MODE,from_logits=True)

    @property
    def loss_fn(self) -> Callable[[torch.Tensor,torch.Tensor],torch.Tensor]:
        if self.epoch < 40:
            return self._dice
        return lambda inp,target: self._bce(inp,target) + self._dice(inp,target)

    def validation_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> None:
        inps,targets = batch
        inps.to(self._device)
        targets.to(self._device)
        preds: torch.Tensor = self.forward(inps)
        loss = self.loss_fn(preds,targets)
        # self.log(Metrics.val_loss,loss.item())
        self.validation_losses.append(loss.item())
        iou = self.get_iou(targets,preds)
        accuracy = self.get_accuracy(targets.detach(),preds.detach())
        self.val_accuracies.append(accuracy.detach().item())
        self.val_ious.append(iou.detach().item())
        return loss

    def on_val_epoch_end(self) -> None:
        super().on_val_epoch_end()
        mean_accuracy = self.val_accuracies.getavg()
        mean_iou = self.val_ious.getavg()
        self.log(Metrics.val_iou,mean_iou)
        self.log(Metrics.val_accuracy,mean_accuracy)


    def test_step(self, batch: tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> torch.Tensor:
        inps,targets = batch
        preds = self.forward(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        # loss_flt = loss.item()
        # self.log(Metrics.test_loss,loss_flt)
        accuracy = self.get_accuracy(targets.detach(),preds.detach())
        iou = self.get_iou(targets.detach(),preds.detach())
        self.test_accuracies.append(accuracy.detach().item())
        self.test_ious.append(iou.detach().item())
        return loss
    
    def on_test_epoch_end(self) -> None:
        test_accuracy = min(self.test_accuracies)
        test_iou = min(self.test_ious)
        self.log(Metrics.test_accuracy,test_accuracy)
        self.log(Metrics.test_iou,test_iou)
        self.test_accuracies.clear()
        self.test_ious.clear()

    @classmethod
    def get_accuracy(cls, target: torch.Tensor, prediction: torch.Tensor):
        # generate predictions from logits
        prediction = torch.sigmoid(prediction).detach()
        threshold = torch.Tensor([0.5]).to(prediction.device).detach()
        prediction = (prediction>=threshold).float().detach()

        num_correct = (target==prediction).sum().detach()
        num_pixels = torch.numel(prediction)
        return (num_correct/num_pixels).detach()
    @classmethod
    def get_iou(cls, target: torch.Tensor, prediction: torch.Tensor):
        # generate predictions from logits
        prediction = torch.sigmoid(prediction).detach()
        threshold = torch.Tensor([0.5]).to(prediction.device).detach()
        prediction = (prediction>=threshold).float()

        intersection = (prediction*target).detach()
        union = (prediction+target-intersection).detach()
        return (intersection.sum()/union.sum()).detach()
    
    def forward(self,x: torch.Tensor):
        if self.training:
            return super().forward(x)
        else:
            x = super().forward(x)
            batch_size = x.shape[0]
            lst_x = [torch.zeros_like(x[0])]*batch_size
            for i in range(0,len(lst_x)):
                lst_x[i] = reduce_mask(x[i])
            return torch.stack(lst_x)

class BBoxModule(GenericModule):
    pass