from typing import Any
import torch
from torch.optim import Optimizer
import lightning.pytorch as L
from .GLOBALS import Metrics, Configuration
import torch.nn as nn
import torch.optim.lr_scheduler as lrs
from typing import TypeVar, Generic

_T = TypeVar("_T")
class GenericModule(L.LightningModule,Generic[_T]):
    def __init__(self, 
                 model: torch.nn.Module, 
                 learning_rate: float,
                 lr_scheduler_name: str|None = None,
                 lr_scheduler_args: dict[str,Any]|None = None) -> None:
        super().__init__()
        self.model = model
        self.learning_rate = learning_rate
        self.save_hyperparameters(ignore=("model",))
        self.training_losses = []
        self.validation_losses = []
        self.val_ious = []
        self.val_accuracies = []
        self.epoch = 0
        self.loss_fn = nn.BCEWithLogitsLoss()
        self.lr_name = lr_scheduler_name
        self.lr_args = lr_scheduler_args
    
    def training_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:
        self.log("memory",torch.cuda.memory_allocated(),on_step=True)
        self.log("max_memory",torch.cuda.max_memory_allocated(),on_step=True)
        inps,targets = batch
        preds = self.model(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        loss_flt = loss.item()
        self.training_losses.append(loss_flt)
        self.log(Metrics.train_loss.name,loss_flt,prog_bar=True,batch_size=_get_bsize(inps))
        return loss
    
    def test_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> torch.Tensor:
        inps,targets = batch
        preds = self.model(inps)
        loss: torch.Tensor = self.loss_fn(preds,targets)
        loss_flt = loss.item()
        self.log(Metrics.test_loss.name,loss_flt,prog_bar=True,batch_size=_get_bsize(inps))
        return loss
    
    def forward(self, x: torch.Tensor) -> _T:
        return self.model(x)
    
    def validation_step(self, batch: tuple[torch.Tensor,torch.Tensor], batch_idx: int) -> None:

        inps,targets = batch
        preds = self.model(inps)
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

    @classmethod
    def from_configuration(cls,model: nn.Module,config: Configuration):
        return cls(
            model,
            learning_rate=config.learning_rate,
            lr_scheduler_name=config.lr_name,
            lr_scheduler_args=config.lr_args,
        )

class ModuleException(Exception):
    pass

class SegmentationModule(GenericModule[torch.Tensor]):

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
    

def _get_bsize(x: torch.Tensor) -> int:
    if len(x.shape) == 4:
        return x.shape[0]
    else:
        return 1

class BBoxModule(GenericModule):
    pass