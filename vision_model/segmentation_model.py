from abc import ABC, abstractmethod
from typing import Any
import cv2
import numpy as np
import torch
from torch.optim import Optimizer
import lightning.pytorch as L
from vision_model.GLOBALS import Metrics, Configuration
import torch.nn as nn
import torch.optim.lr_scheduler as lrs
import segmentation_models_pytorch as smp

class GenericModule(L.LightningModule,ABC):
    def __init__(self, 
                 model: torch.nn.Module, 
                 learning_rate: float,
                 initial_batchnorm = False,
                 alpha_channel = False,
                 lr_scheduler_name: str|None = None,
                 lr_scheduler_args: dict[str,Any]|None = None) -> None:
        super().__init__()
        self.model = model
        self.learning_rate = learning_rate
        self.save_hyperparameters(ignore=("model","initial_batchnorm"))
        self.training_losses = []
        self.validation_losses = []
        self.val_ious = []
        self.val_accuracies = []
        self.test_accuracies = []
        self.test_ious = []
        self.epoch = 0
        self._bn0 = nn.BatchNorm2d(4 if alpha_channel else 3) if initial_batchnorm else None
        self.lr_name = lr_scheduler_name
        self.lr_args = lr_scheduler_args

    @property
    @abstractmethod
    def loss_fn(self):
        # if self.epoch<28:
        #     return lambda inp, target: self._dice(inp,target) + self._bce(inp,target)
        # return self._dice
        pass

    def training_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:
        self.log("memory",torch.cuda.memory_allocated(),on_step=True)
        self.log("max_memory",torch.cuda.max_memory_allocated(),on_step=True)
        inps,targets = batch
        preds = self(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        loss_flt = loss.item()
        self.training_losses.append(loss_flt)
        self.log(Metrics.train_loss.name,loss_flt,prog_bar=True,batch_size=_get_bsize(inps))
        return loss
    
    def test_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:
        inps,targets = batch
        preds = self(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        loss_flt = loss.item()
        self.log(Metrics.test_loss.name,loss_flt,prog_bar=True,batch_size=_get_bsize(inps))
        return loss
    
    def validation_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> None:

        inps,targets = batch
        preds = self(inps)
        loss: float = self.loss_fn(preds,targets).item()
        self.log(Metrics.val_loss.name,loss,prog_bar=True,batch_size=_get_bsize(inps))
        self.validation_losses.append(loss)
    
    def on_train_epoch_end(self) -> None:
        self.log("epoch",self.epoch)
        self.epoch+=1
        mean_train_loss = sum(self.training_losses)/len(self.training_losses)
        mean_val_loss = sum(self.validation_losses)/len(self.validation_losses)
        self.log(Metrics.mean_train_loss.name,mean_train_loss)
        self.log(Metrics.mean_val_loss.name,mean_val_loss)
        self.training_losses.clear()
        self.validation_losses.clear()

    def configure_optimizers(self) -> Optimizer:
        optimizer = torch.optim.AdamW(self.model.parameters(),lr = self.learning_rate)

        if self.lr_name is None:
            return optimizer
        
        try:
            lr_class = getattr(lrs,self.lr_name)
        except AttributeError:
            raise ModuleException(f"{self.lr_name} is not a learning rate scheduler in package torch.optim.lr_scheduler")

        if self.lr_args is None:
            return {
                "optimizer": optimizer,
                "lr_scheduler": lr_class(optimizer)
            }

        config_args = {}
        for key in ["interval","frequency","monitor","strict","name"]:
            if key in self.lr_args.keys():
                val = self.lr_args.pop(key)
                config_args = {**config_args,key:val}
        
        if self.lr_name == "ReduceLROnPlateau" and "monitor" not in config_args.keys():
            raise ModuleException("ReduceLROnPlateau requires the \"monitor\" argument (string name from Metrics options)")

        lr_scheduler = lr_class(optimizer,**self.lr_args)

        if len(config_args.keys()) == 0:
            return {
                "optimizer": optimizer,
                "lr_scheduler": lr_scheduler
            }

        lrsc_dict = {
            "scheduler": lr_scheduler,
            **config_args
        }

        return {
            "optimizer": optimizer,
            "lr_scheduler": lrsc_dict
        }
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self._bn0 is not None:
            x = self._bn0(x)
        return self.model(x)

    @classmethod
    def from_configuration(cls,model: nn.Module,config: Configuration):
        return cls(
            model,
            learning_rate=config.learning_rate,
            initial_batchnorm=config.initial_batchnorm,
            alpha_channel=config.alpha_channel,
            lr_scheduler_name=config.lr_name,
            lr_scheduler_args=config.lr_args,

        )

class ModuleException(Exception):
    pass

class SegmentationModule(GenericModule):

    def __init__(self, model: nn.Module, learning_rate: float, initial_batchnorm=False, alpha_channel=False, lr_scheduler_name: str | None = None, lr_scheduler_args: dict[str, Any] | None = None) -> None:
        super().__init__(model, learning_rate, initial_batchnorm, alpha_channel, lr_scheduler_name, lr_scheduler_args)
        self._bce = nn.BCEWithLogitsLoss()
        self._dice = smp.losses.DiceLoss(smp.losses.BINARY_MODE,from_logits=True)

    @property
    def loss_fn(self):
        if self.epoch < 40:
            return self._dice
        return lambda inp,target: self._bce(inp,target) + self._dice(inp,target)

    def validation_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> None:
        inps,targets = batch
        preds: torch.Tensor = self.model(inps)
        loss = self.loss_fn(preds,targets).item()
        self.log(Metrics.val_loss.name,loss,prog_bar=True,batch_size=_get_bsize(inps))
        self.validation_losses.append(loss)
        iou = self.get_iou(targets,preds)
        accuracy = self.get_accuracy(targets.detach(),preds.detach())
        self.val_accuracies.append(accuracy.detach().item())
        self.val_ious.append(iou.detach().item())

    def on_train_epoch_end(self) -> None:
        super().on_train_epoch_end()
        mean_accuracy = sum(self.val_accuracies)/len(self.val_accuracies)
        mean_iou = sum(self.val_ious)/len(self.val_ious)
        self.log(Metrics.val_iou.name,mean_iou)
        self.log(Metrics.val_accuracy.name,mean_accuracy)
        self.val_accuracies.clear()
        self.val_ious.clear()

    def test_step(self, batch: tuple[torch.Tensor, torch.Tensor], batch_idx: int) -> torch.Tensor:
        loss = super().test_step(batch,batch_idx)
        inps,targets = batch
        preds: torch.Tensor = self.model(inps)
        accuracy = self.get_accuracy(targets.detach(),preds.detach())
        iou = self.get_iou(targets.detach(),preds.detach())
        self.test_accuracies.append(accuracy.detach().item())
        self.test_ious.append(iou.detach().item())
        return loss
    
    def on_test_epoch_end(self) -> None:
        test_accuracy = min(self.test_accuracies)
        test_iou = min(self.test_ious)
        self.log(Metrics.test_accuracy.name,test_accuracy)
        self.log(Metrics.test_iou.name,test_iou)
        self.log("worst_image",self.test_accuracies.index(test_accuracy))
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
                lst_x[i] = _reduce_mask(x[i])
            return torch.stack(lst_x)


def _reduce_mask(prediction: torch.Tensor, kernel_size=(10,10)):
    # generate predictions from logits
    prediction = torch.sigmoid(prediction).detach()
    threshold = torch.Tensor([0.5]).to(prediction.device).detach()
    original_device = prediction.device
    prediction = (prediction>=threshold).float().cpu()
    original_size = len(prediction.shape)
    # convert to numpy array
    while len(prediction.shape)>3:
        prediction = prediction.squeeze()
    while len(prediction.shape)<3:
        prediction = prediction.unsqueeze(0)
    mask = np.array(prediction)
    mask = np.transpose(mask,[1,2,0])
    # morph close to remove smaller blobs more efficiently
    kernel = np.ones(kernel_size)*255
    thresh = cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)*255
    thresh = thresh.astype(np.uint8)
    # find the contours around all remaining activations
    contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]
    # select the contour with the maximum area
    if len(contours)>0:
        max_contour = max(contours,key=cv2.contourArea)
        mask_out = np.zeros_like(mask,dtype=np.uint8)
        cv2.drawContours(mask_out,[max_contour],-1,255,thickness=cv2.FILLED)
        mask_out = mask_out.transpose(2,0,1)
    else:
        mask_out = thresh[:,:,np.newaxis]
    mask_tensor = torch.from_numpy((mask_out/255).astype(np.float32)).float().cpu()

    while len(mask_tensor.shape)<original_size:
        mask_tensor = mask_tensor.unsqueeze(0)
    while len(mask_tensor.shape)>original_size:
        mask_tensor = mask_tensor.squeeze()
    mask_tensor = mask_tensor.to(original_device)
    one = torch.Tensor([1]).to(original_device).detach()
    mask_tensor = torch.log(mask_tensor/(one-mask_tensor))
    return mask_tensor

def _get_bsize(x: torch.Tensor) -> int:
    if len(x.shape) == 4:
        return x.shape[0]
    else:
        return 1

class BBoxModule(GenericModule):
    pass