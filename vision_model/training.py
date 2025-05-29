from abc import ABC, abstractmethod
from logging import warning
from typing import Any
from segmentation_model import SegmentationModule, GenericModule
import segmentation_models_pytorch as smp
import torch
from GLOBALS import Configuration, Metrics
from vision_model.ImageTransforms import Compose,Flip,Affine
from pathlib import Path
from datamodules import SegmentationDataModule,DataModule
import torch.utils.data as data
from vision_model.loggers import Logger, CSVLogger

import tqdm
# from torch.profiler import profile,ProfilerActivity
# from torch.utils.viz._cycles import warn_tensor_cycles

class TrainingMixin(ABC):
    def on_train_epoch_end(self, trainer: "Trainer", module: GenericModule) -> None:
        pass
    def on_train_epoch_start(self, trainer: "Trainer", module: GenericModule) -> None:
        pass
    def on_val_epoch_start(self, trainer: "Trainer", module: GenericModule) -> None:
        pass
    def on_val_epoch_end(self, trainer: "Trainer", module: GenericModule) -> None:
        pass
    def on_fit_end(self, trainer: "Trainer", module: GenericModule) -> None:
        pass

    @classmethod
    def extract_from_json(cls, mixins_dict: dict[str,dict[str,Any]]|None,experiment_name: str) -> list["TrainingMixin"]:
        mi_list = []
        if mixins_dict is None:
            return mi_list
        for mi_name, arg_dict in mixins_dict.items():
            if "monitor" in arg_dict:
                metric = Metrics.from_name(arg_dict["monitor"])
                arg_dict = {**arg_dict,"mode":metric.mode}
            if mi_name == "ModelSaver":
                filename = experiment_name + "-{epoch:02d}-{" + arg_dict["monitor"] + ":.2e}"
                arg_dict = {**arg_dict,"filename":filename}
            mi_index = cls.__subclasses__().index(mi_name)
            mi = cls.__subclasses__()[mi_index](**arg_dict)
            mi_list.append(mi)
        return mi_list
    
    @classmethod
    def to_json(cls, mixins: list["TrainingMixin"]) -> dict[str,dict[str,Any]]:
        mi_out: dict[str,dict[str,Any]] = {}
        if len(mixins) < 1:
            return mi_out
        for mi in mixins:
            mi_out = {**mi_out, 
                      mi.__class__.__name__: mi.as_dict()}
        return mi_out

    @abstractmethod
    def as_dict(self) -> dict[str,Any]:
        pass

class EarlyStopping(TrainingMixin):

    def __eval_lt(self,val: float):
        return val<self._prev_best
    def __eval_gt(self,val: float):
        return val>self._prev_best

    def __init__(self, monitor: Metrics, patience: int, **kwargs):
        super().__init__()
        self._monitor = monitor
        self._patience = patience
        self._patience_counter = 0
        if monitor.mode == "min":
            self._prev_best = float("inf")
            self._eval = self.__eval_lt
        else:
            self._prev_best = float("-inf")
            self._eval = self.__eval_gt
    
    def as_dict(self):
        return {
            "monitor": self._monitor.name,
            "patience": self._patience
        }

    def on_val_epoch_end(self, trainer, module):
        if module.logger is None:
            return
        try:
            val = module.logger.get_recent(self._monitor)
            if self._eval(val):
                self._prev_best = val
                self._patience_counter = 0
            else:
                self._patience_counter += 1
        except KeyError:
            pass
        if self._patience_counter > self._patience:
            trainer.stop()

def _eval_lt(val1: float,val2: float):
    return val1<val2
def _eval_gt(val1: float,val2: float):
    return val1>val2

class ModelSaver(TrainingMixin):

    def __init__(self, monitor: Metrics, experiment_name: str, save_last_k = 1, **kwargs):
        self._monitor = monitor
        self._experiment_name = experiment_name
        if monitor.mode == "min":
            self._prev_bests = [float("inf")]*save_last_k
            self._eval = _eval_lt
        else:
            self._prev_bests = [float("-inf")]*save_last_k
            self._eval = _eval_gt
        self._prev_bests = [float("inf") if monitor.mode == "min" else float("-inf")]*save_last_k
        self._save_last_k = save_last_k

    def as_dict(self):
        return {
            "monitor": self._monitor.name,
            "save_last_k": self._save_last_k,
        }

    def on_val_epoch_end(self, trainer, module):
        if module.logger is None:
            return
        try:
            val = module.logger.get_recent(self._monitor)
            if self._eval(val,self._prev_bests[-1]):
                k = self._place_val(val)
                fname = self._get_filename(module,k=k)
                trainer.save_next(fname)

        except KeyError:
            pass
    def _place_val(self,val):
        i = 0
        while i<len(self._prev_bests):
            if self._eval(val,self._prev_bests[i]):
                self._prev_bests[i] = val
                break
        return i
    
    def _get_filename(self,epoch: int,k=1):
        k_str = str(k)
        if k==1:
            k_str = "best"
        elif k_str[-1] == 1 and (len(k_str) == 1 or (len(k_str)>1 and k_str[-2] != 1)):
                k_str += k_str+"st"
        else:
            k_str+="th"

        name = f"{self._experiment_name}_{k_str}_{self._monitor.name}_epoch={epoch}"
        return name

class StochasticWeightAveraging(TrainingMixin):
    def __init__(self):
        raise NotImplementedError()
        
def _get_device_type(device: str):
    if device[0:4] == "cuda":
        return "cuda"
    if device == "cpu":
        return "cpu"
    raise ValueError("Device type must be \"cuda:<int>\" or \"cpu\"")

class Trainer:

    def __init__(self, min_epochs = 0, max_epochs = 100, mixins: list[TrainingMixin]|None = None):
        if mixins is None:
            mixins = []
        self._mixins = mixins
        self._running = False
        self._continue_running = False
        self._max_epochs = max_epochs
        self._min_epochs = min_epochs
        self._save_next_path: Path|None = None
        self._epoch = 0

    @classmethod
    def from_configuration(cls, configuration: Configuration) -> "Trainer":
        return Trainer(min_epochs=configuration.min_epochs,
                       max_epochs=configuration.max_epochs,
                       mixins=TrainingMixin.extract_from_json(configuration.training_mixins,configuration.experiment_name))

    def save_next(self, path: Path):
        self._save_next_path = path

    def stop(self):
        if self._epoch < self._min_epochs:
            return # min_epochs overrides any signal to stop
        self._continue_running = False

    def _perform_training_epoch(self, module: GenericModule, scaler: torch.cuda.amp.GradScaler ,optimizer: torch.optim.Optimizer, dl: data.DataLoader):
        for mi in self._mixins:
            mi.on_train_epoch_start(self,module)

        for batch_idx, batch_data in enumerate(dl):
            optimizer.zero_grad()

            with torch.autocast(device_type=_get_device_type(module._device)):
                loss = module.training_step(batch_data, batch_idx)
            
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        
        module.on_train_epoch_end()
        
        for mi in self._mixins:
            mi.on_train_epoch_end(self,module)

    @torch.no_grad
    def _perform_val_epoch(self, module: GenericModule, dl: data.DataLoader):
        for mi in self._mixins:
            mi.on_val_epoch_start(self,module)
        
        for batch_idx, batch_data in enumerate(dl):
            module.validation_step(batch_data,batch_idx)

        module.on_val_epoch_end()

        for mi in self._mixins:
            mi.on_val_epoch_end(self,module)

    def fit(self, module: GenericModule, dm: DataModule, logger: Logger|None = None, ckpt_path: Path|None = None):
        dm.setup("fit")
        train_loader = dm.train_dataloader()
        val_loader = dm.val_dataloader()

        scaler = torch.cuda.amp.GradScaler()
        optimizer, schedulers = module.configure_optimizers()
        
        

        if ckpt_path is not None:
            map_location = None if torch.cuda.is_available() else {"cuda:0":"cpu"}
            checkpoint: dict[str,Any] = torch.load(ckpt_path,map_location=map_location)
            module.model.load_state_dict(checkpoint["state_dict"])
            optimizer.load_state_dict(checkpoint["optimizer_dict"])
            for i,scheduler in enumerate(schedulers):
                scheduler.load_state_dict(checkpoint["lr_scheduler_dicts"][i])
            if "epoch" in checkpoint.keys():
                self._epoch = checkpoint["epoch"]
        
        module.train()
        module.logger = logger
        module.epoch = self._epoch
        

        while self._epoch < self._max_epochs and self._continue_running:

            ## perform training epoch
            self._perform_training_epoch(module,scaler,optimizer,train_loader)

            ## step the learning rate schedulers if needed
            for scheduler in schedulers:
                scheduler.step()

            ## perform validation epoch
            self._perform_val_epoch(module,val_loader)

            self._maybe_save_model(logger,module.model,optimizer=optimizer,lr_schedulers=schedulers)

            self._epoch += 1
    def _maybe_save_model(self,logger: Logger|None,model: torch.nn.Module, optimizer: torch.optim.Optimizer, lr_schedulers: list[torch.optim.lr_scheduler.LRScheduler]):
        if logger is None:
            warning("Model save requested but no logger available.")
            return
        if self._save_next_path is not None:
            ## TODO save model and other states here
            logger.save_pytorch_checkpoint(model,optimiser=optimizer,lr_schedulers=lr_schedulers,filename=self._save_next_path)
            self._save_next_path = None

    @property
    def epoch(self):
        return self._epoch


def _attempt_batch_run(module: GenericModule, optimizer: torch.optim.Optimizer, scaler: torch.cuda.amp.GradScaler, datamodule: DataModule, steps: int, verbose=False): 
    assert steps >= 1
    if verbose:
        print(f"Attempting batch size of {datamodule.batch_size}...")
    dataloader = datamodule.train_dataloader()
    try:
        ## generic training loop
        for batch_idx, batch_data in enumerate(dataloader):
            optimizer.zero_grad()

            with torch.autocast(device_type=_get_device_type(module._device)):
                loss = module.training_step(batch_data, batch_idx)
            
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            ## modification to do maximum of "steps" iterations, avoiding doing a full epoch of data
            if batch_idx >= steps:
                break
        if verbose:
            print("Passed!")
        return True
    except RuntimeError: # OOM error
        if verbose:
            print("Failed.")
        return False

def tune(module: GenericModule, datamodule: DataModule, steps_per_stage: int = 2, strict=True, verbose=False):
    module.train()

    optimizer = module.configure_optimizers()[0]
    scaler = torch.cuda.amp.GradScaler()


    test_passed = _attempt_batch_run(module,optimizer,scaler,datamodule,steps_per_stage, verbose=verbose)
    if test_passed:
        ## increase batch size until OOM error
        while test_passed:
            current_value = datamodule.batch_size
            datamodule.batch_size = datamodule.batch_size*2
            test_passed = _attempt_batch_run(module,optimizer,scaler,datamodule,steps_per_stage,verbose=verbose)
        datamodule.batch_size = current_value
        out = current_value
    else:
        ## decrease batch size until no OOM error
        while not test_passed and datamodule.batch_size>1:
            datamodule.batch_size = datamodule.batch_size // 2
            test_passed = _attempt_batch_run(module,optimizer,scaler,datamodule,steps_per_stage,verbose=verbose)
        if not test_passed:
            ## batch size of 1 doesnt fit in memory :(
            raise RuntimeError("Batch size of 1 does not fit in memory. Unable to proceed with training")
        out = current_value
    
    ## if strict is true, subtract 1 from batch size just to be extra careful!
    datamodule.batch_size = max(1,out-1) if strict else out
    return datamodule.batch_size

def train(
    model: torch.nn.Module,
    config_path: Path|str = "configuration.json",
    checkpoint_path: Path|str|None = None
):
    print("Reading Configuration")
    c = Configuration.from_json(config_path,model.__class__.__name__)
    torch.set_float32_matmul_precision(c.matmul_precision)   

    print("Configuring Data Module")
    transforms = Compose(
        Flip(p=0.5),
        Affine(shift_limit=0.1,scale_limit=0.4,rotate_limit=25,p=1),
    )
    dm = SegmentationDataModule.from_configuration(c,transforms)

    module = SegmentationModule.from_configuration(model,c)


    print("Initialising Trainer")
    mixins = TrainingMixin.extract_from_json(c.training_mixins,c.experiment_name)
    trainer = Trainer(
        min_epochs=c.min_epochs,
        max_epochs=c.max_epochs,
        mixins=mixins,
        checkpoint_path = checkpoint_path
    )
    logger = CSVLogger(c.experiment_name,c.max_epochs,dm.steps_in_epoch)

    if c.tune_batch_size:
        print("Tuning batch size...")
        tune(module,dm, strict=False, verbose=True)
    
    print("---------BEGIN TRAINING-----------")
    trainer.fit(
        module,
        dm,
        logger = logger,
        ckpt_path = checkpoint_path
    )

    ckpt = sorted(logger.checkpoints,key = lambda name: len(name))[-1]
    print(ckpt)
    logger.save_pytorch_checkpoint()


def main():
    print("Initialising Model")
    model = smp.UnetPlusPlus(encoder_name="resnet50",encoder_weights=None)
    train(model)

if __name__ == "__main__":
    main()