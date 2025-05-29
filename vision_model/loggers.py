from vision_model.GLOBALS import Metrics, Configuration, LogStage
from abc import ABC, abstractmethod
import torch
import json
import os
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).absolute().parent / "logs"



class Logger(ABC):

    def __init__(self,experiment_name: str) -> None:
        
        folder_path = LOG_DIR/experiment_name
        if not os.path.isdir(folder_path):
            os.mkdir(folder_path)
        self._root = folder_path

    @property
    def experiment_name(self):
        return self._root.parts[-1]

    @property
    def root(self):
        return self._root
    
    @property
    def checkpoint_folder(self):
        ckpt_pth = self._root/"checkpoints"
        if not os.path.isdir(ckpt_pth):
            os.mkdir(ckpt_pth)
        return ckpt_pth
    
    @property
    def configuration_file(self):
        return self._root/"configuration.json"
    
    @property
    def checkpoints(self) -> list[Path]:
        ckpts = [self.checkpoint_folder/filename for filename in os.listdir(self.checkpoint_folder) if (os.path.isfile(self.checkpoint_folder/filename) and len(filename)>8 and filename[-8:] == ".pth.tar")]
        return ckpts
    
    def save_pytorch_checkpoint(self,
                                model: torch.nn.Module,
                                optimiser: torch.optim.Optimizer|None = None, 
                                lr_schedulers: list[torch.optim.lr_scheduler.LRScheduler]|None = None, 
                                filename="torch_checkpoint.pth.tar", 
                                custom_message=None) -> Path:
        state = {"state_dict": model.state_dict()}
        if optimiser:
            state = {**state, "optimizer_dict":optimiser.state_dict()}
        if lr_schedulers is not None and len(lr_schedulers)>0:
            state = {**state, "lr_scheduler_dicts": [scheduler.state_dict() for scheduler in lr_schedulers]}
        print(f"=> Saving checkpoint {filename}" if custom_message is None else custom_message)
        torch.save(state, self.checkpoint_folder/filename)
        return self.checkpoint_folder/filename
    
    def load_pytorch_checkpoint(self, model: torch.nn.Module, optimiser: torch.optim.Optimizer = None, lr_schedulers: list[torch.optim.lr_scheduler.LRScheduler]|None = None, filename="torch_checkpoint.pth.tar", custom_message=None):
        if not os.path.exists(self.checkpoint_folder/filename):
            raise FileNotFoundError(f"Experiment {self.experiment_name} does not have a checkpoint under the filename {filename}")
        print(f"=> Loading checkpoint {filename}" if custom_message is None else custom_message)
        checkpoint: dict[str,Any] = torch.load(self.checkpoint_folder/filename)
        model.load_state_dict(checkpoint["state_dict"])
        if optimiser and "optimizer" in checkpoint.keys():
            optimiser.load_state_dict(checkpoint["optimizer"])
        if lr_schedulers is not None and len(lr_schedulers)>0 and "lr_scheduler_dicts" in checkpoint.keys():
            for i,scheduler in enumerate(lr_schedulers):
                scheduler.load_state_dict(checkpoint["lr_scheduler_dicts"][i])

    def save_configuration(self,configuration: Configuration):
        with open(self.configuration_file,"w") as f:
            json.dump(configuration.generate_json(),f)
    def load_configuration(self) -> Configuration:
        if not os.path.exists(self.configuration_file):
            raise FileNotFoundError(f"Experiment {self.experiment_name} does not have a configuration file")
        with open(self.configuration_file,"r") as f:
            return Configuration.from_json(json.load(f))


    # abstract methods
    @abstractmethod
    def log(self, data: float, metric: Metrics, stage: LogStage):
        raise NotImplementedError()
    
    @abstractmethod
    def save_logs(self, filename: str|None = None):
        raise NotImplementedError()
    
    @classmethod
    def load_logs(cls, filename: str|None = None) -> "Logger":
        """This should be an *abstract* class method, but python has deprecated every native way of achieving this :("""
        raise NotImplementedError()
    
    @abstractmethod
    def next_step(self) -> None:
        raise NotImplementedError()
    
    @abstractmethod
    def get_recent(self, metric: Metrics):
        raise NotImplementedError()


class CSVLogger(Logger):

    _default_log_filename = "logs.csv"
    _extension = _default_log_filename[-4:]

    def __init__(self, experiment_name: str, max_epochs: int, steps_in_epoch: int):
        super().__init__(experiment_name)
        self._data = {metric: [float("nan")]*max_epochs*steps_in_epoch for metric in Metrics} # data arrays for each metric
        self._data_ptrs = {metric: -1 for metric in Metrics} # pointers to the last valid (non-nan) index in each metric's data
        self._pointer = 0
        self._max_ptr = max_epochs*steps_in_epoch
        self._steps_in_epoch = steps_in_epoch

        ## epoch for steps 0:steps_in_epoch-1 is stored in steps_in_epoch-1
    
    @property
    def _epoch(self):
        return self._pointer//self._steps_in_epoch + 1
    
    @_epoch.setter
    def _epoch(self, new_epoch: int):
        assert new_epoch > 0
        old_epoch = self._epoch
        self._pointer = (new_epoch-1)*self._steps_in_epoch + self._pointer % self._steps_in_epoch

        if new_epoch<old_epoch:
            # if the new epoch is lower than the current epoch, then we need to wipe any data after this epoch
            for metric in self._data:
                metric_pointer = self._data_ptrs[metric]
                self._data[metric][self._pointer:max(self._pointer,metric_pointer+1)] = float("nan")
                self._data_ptrs[metric] = min(self._pointer,metric_pointer)

    def next_step(self):
        self._pointer += 1

    def log(self,data: float, metric: Metrics, stage: Logger.Stage):
        if self._pointer >= self._max_ptr:
            raise RuntimeError("Logger has run out of memory")
        if stage == Logger.Stage.EPOCH and not self._isepoch():
            epoch_ptr = self._steps_in_epoch*self._epoch - 1
            self._copy_up_to_ptr(epoch_ptr)
        self._data[metric][self._pointer] = data
        self._data_ptrs[metric] = self._pointer
    
    def get_recent(self,metric: Metrics) -> float:
        ptr = self._data_ptrs[metric]
        if ptr >= 0:
            return self._data[metric][ptr]
        raise ValueError(f"Metric \"{metric.name}\" has no data written yet")
    
    def save_logs(self, filename: str|None = None):

        # input parsing
        if filename is None:
            filename = self._default_log_filename
        if len(filename)<5 or filename[:-4] != self._extension:
            filename += self._extension


        reduced_ptrs = {metric:ptr for metric,ptr in self._data_ptrs.items() if ptr>=0}
        metrics = list(reduced_ptrs.keys())
        max_index = max(reduced_ptrs.values())
        self._copy_up_to_ptr(max_index)
        
        # begin constructing the output string
        str_out = "step,epoch"
        # add the titles of each column
        for metric in metrics:
            str_out += metric.name+","
        str_out[-1] = "\n"

        # fill in each row with data
        for i in range(1,max_index):
            line = f"{i-1,i//self._steps_in_epoch+1}"
            for metric in metrics:
                line += str(self._data[metric][i])+","
            line[-1]="\n"
            str_out+=line
        
        #save str_out to file
        with open(self._root/filename, "w") as f:
            f.write(str_out)
    
    @classmethod
    def load_logs(cls, filename: str|None = None) -> "CSVLogger":
        raise NotImplementedError("Implement this")
        
    # private methods
    def _isepoch(self):
        return self._pointer % self._steps_in_epoch == 0
    
    def _copy_up_to_ptr(self, ptr: int):
        """this copies all last known values in each metric up to the index given by ptr"""
        
        nan = float("nan")
        # go through all steps from current step to the step before the next epoch
        start_ptr = max(1,self._pointer) # avoids -1 index if _pointer is 0
        for metric in self._data.keys():
            for i in range(start_ptr,ptr):
                if self._data[metric][i] == nan:
                    self._data[metric][i] = self._data[metric][i-1]
        self._pointer = ptr
        return