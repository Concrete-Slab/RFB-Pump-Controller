from enum import Enum, StrEnum
from pathlib import Path
from dataclasses import dataclass, asdict
import json
from typing import Any, Iterable
import numpy as np
import torch.optim.lr_scheduler
import inspect
import os

LOG_DIR = Path(__file__).absolute().parent / "logs"
DATASET_DIR = Path(__file__).absolute().parent / "Datasets" / "Dataset_ORIGINAL"
ROOT_DIRECTORY = Path(__file__).absolute().parent / "Datasets"

class LogStage(StrEnum):
    STEP = "step"
    EPOCH = "epoch"

@dataclass
class Configuration:
    dataset: Path = DATASET_DIR
    ensure_factor: int|None = None
    alpha_channel: bool = False
    random_seed: int|None = None
    batch_size: int = 32
    tune_batch_size: bool = False
    learning_rate: float = 1e-3
    pin_memory: bool = True
    proportion_validation:float = 0.2
    proportion_testing:float = 0.02
    persistent_workers:bool = False
    num_workers:int = 0
    max_epochs:int = 1000
    min_epochs:int = 0
    matmul_precision:str = "32-true"
    precision:str = "highest"
    lr_name: str|None = None
    lr_args: str|None = None
    training_mixins: dict[str,dict[str,Any]]|None = None
    shuffle_dataset: bool = True
    experiment_name: str = "Experiment 0"

    @staticmethod
    def from_json(jsonpath: Path|str, model_name: str="segmentation_model", root_directory: Path=ROOT_DIRECTORY):
        with open(jsonpath,"r") as jf:
            json_obj = json.load(jf)
        
        if "lr_scheduler" in json_obj.keys():
            lr_config = json_obj.pop("lr_scheduler")
            json_obj["lr_name"],json_obj["lr_args"] = _extract_lr_scheduler(lr_config)
        else:
            json_obj["lr_name"],json_obj["lr_args"] = None,None            
        
        if "dataset" in json_obj.keys():
            ds_name = str(json_obj["dataset"])
            dataset_directory = root_directory/ds_name
            if not os.path.isdir(dataset_directory):
                raise ConfigurationException("Dataset "+ds_name+f" could not be found in {root_directory.as_posix()}. Please try a different folder name or root directory")
            json_obj["dataset"] = dataset_directory
            
            if "experiment_name" not in json_obj.keys():
                experiment_name = model_name + "-" + ds_name
                json_obj["experiment_name"] = experiment_name

        # _check_missing_args(json_obj.keys())
        _check_extra_args(json_obj.keys())

        return Configuration(**json_obj)

    def generate_json(self):
        out = asdict(self)

        out["directory"] = out["directory"].as_posix()

        # handle learning rate
        name = out.pop("lr_name")
        args = out.pop("lr_args")
        if args is None:
            args = {}
        if name is not None:
            out = {
                **out,
                "lr_scheduler": {
                    "class": name,
                    "args": args
                }
            }
        else:
            out = {
                **out,
                "lr_scheduler": None
            }
        # handle callbacks
        cbs = out.pop("training_mixins")
        cb_dict = {}
        if cbs is None or len(cbs) == 0:
            out = {
                **out,
                "training_mixins": None
            }
        else:
            for cb in cbs:
                cb_dict = {
                    **cb_dict,
                    cb.__class__.__name__: cb.state_dict()
                }
            out = {
                **out,
                "callbacks": cb_dict
            }
        return out

def _extract_lr_scheduler(initial_config: dict[str,Any]|None) -> tuple[str|None,dict[str,Any]|None]:
    if initial_config is None:
        return None,None
    name = str(initial_config.pop("class"))
    if name not in dir(torch.optim.lr_scheduler):
        raise ConfigurationException(f"lr_scheduler class {name} is not a learning rate scheduler in torch.optim.lr_scheduler")
    args = initial_config.pop("args")
    if "monitor" in args.keys():
        metric = Metrics.from_name(args["monitor"])
        args = {**args,"mode":metric.mode}
    elif name == "ReduceLROnPlateau":
        raise ConfigurationException("lr_scheduler class ReduceLROnPlateau requires the \"monitor\" argument (string name from Metrics options)")
    return name, args

def _check_extra_args(keys: Iterable[str]):
    members = inspect.getmembers(Configuration)
    fields = list(list(filter(lambda x: x[0] == '__dataclass_fields__', members))[0][1].values())
    field_names = [field.name for field in fields]
    for key in keys:
        if key not in field_names:
            raise ConfigurationException(f"Key {key} is not a recognised configuration variable")
        
class ConfigurationException(Exception):
    pass



@dataclass
class BaseMetric:
    name: str
    mode: str

class Metrics(Enum):
    train_loss = BaseMetric("train_loss","min")
    val_loss = BaseMetric("val_loss","min")
    test_loss = BaseMetric("test_loss","min")
    mean_train_loss = BaseMetric("mean_train_loss","min")
    mean_val_loss = BaseMetric("mean_val_loss","min")
    mean_test_loss = BaseMetric("mean_test_loss","min")
    val_accuracy = BaseMetric("val_accuracy","max")
    test_accuracy = BaseMetric("test_accuracy","max")
    val_iou = BaseMetric("val_iou","max")
    test_iou = BaseMetric("test_iou","max")
    
    @classmethod
    def from_name(cls,name: str) -> BaseMetric:
        for p in cls:
            if isinstance(p,BaseMetric) and p.name == name:
                return p
        raise MetricException(f"{name} is not a recognised metric name")
    
    @property
    def mode(self):
        return self.value.mode
    @property
    def name(self):
        return self.value.name
    
class MetricException(Exception):
    pass


if __name__ == "__main__":
    m = torch.nn.Linear(1,1)
    c = Configuration.from_json("configuration.json",m.__class__.__name__)
    j = c.generate_json()
    print(j)
