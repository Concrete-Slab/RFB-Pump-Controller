from pathlib import Path
from dataclasses import dataclass, asdict
import json
from typing import Any, Iterable
from lightning.pytorch.callbacks import *
from torch.nn import Module
import torch.optim.lr_scheduler
import inspect
import os

LOG_DIR = Path(__file__).absolute().parent / "logs"
DATASET_DIR = Path(__file__).absolute().parent / "Datasets" / "Dataset_ORIGINAL"
ROOT_DIRECTORY = Path(__file__).absolute().parent / "Datasets"

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
    training_callbacks: list[Callback]|None = None
    shuffle_dataset: bool = True
    experiment_name: str = "Experiment 0"

    @staticmethod
    def from_json(jsonpath: Path|str, model: Module, root_directory: Path=ROOT_DIRECTORY):
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
                experiment_name = model.__class__.__name__ + "-" + ds_name
                json_obj["experiment_name"] = experiment_name

        if "callbacks" in json_obj.keys():
            callbacks_dict = dict(json_obj.pop("callbacks"))
            json_obj["training_callbacks"] = _extract_callbacks(callbacks_dict,experiment_name)
        else:
            json_obj["training_callbacks"] = []

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
        cbs = out.pop("training_callbacks")
        cb_dict = {}
        if cbs is None or len(cbs) == 0:
            out = {
                **out,
                "callbacks": None
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


def _extract_callbacks(callbacks: dict[str,Any]|None,experiment_name: str) -> list[Callback]:
    cb_list = []
    if callbacks is None:
        return cb_list
    for cb_name, arg_dict in callbacks.items():
        if "monitor" in arg_dict:
            metric = Metrics.from_name(arg_dict["monitor"])
            arg_dict = {**arg_dict,"mode":metric.mode}
        if cb_name == "ModelCheckpoint":
            filename = experiment_name + "-{epoch:02d}-{" + arg_dict["monitor"] + ":.2e}"
            arg_dict = {**arg_dict,"filename":filename}
        cb = globals()[cb_name](**arg_dict)
        cb_list.append(cb)
    return cb_list

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

def _check_missing_args(keys: Iterable[str]):
    members = inspect.getmembers(Configuration)
    fields = list(list(filter(lambda x: x[0] == '__dataclass_fields__', members))[0][1].values())
    missing_keys = []
    for field in fields:
        field_name = field.name
        if field_name not in keys:
            missing_keys.append(field_name)
    if len(missing_keys)>0:
        raise ConfigurationException("Configuration file is missing the following keys: " + ", ".join(missing_keys))

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

class Metrics:
    train_loss = BaseMetric("train_loss","min")
    val_loss = BaseMetric("val_loss","min")
    mean_train_loss = BaseMetric("mean_train_loss","min")
    mean_val_loss = BaseMetric("mean_val_loss","min")
    mean_test_loss = BaseMetric("mean_test_loss","min")
    val_accuracy = BaseMetric("val_accuracy","max")
    val_iou = BaseMetric("val_iou","max")
    test_accuracy = BaseMetric("test_accuracy","max")
    test_iou = BaseMetric("test_iou","max")
    test_loss = BaseMetric("test_loss","min")
    
    @classmethod
    def from_name(cls,name: str) -> BaseMetric:
        for p in dir(Metrics):
            try:
                p_obj = getattr(Metrics,p)
                if isinstance(p_obj,BaseMetric) and p_obj.name == name:
                    return p_obj
            except AttributeError:
                continue
        raise MetricException(f"{name} is not a recognised metric name")

class MetricException(Exception):
    pass


class LogFolder:
    def __init__(self,folder_path: Path,model: torch.nn.Module) -> None:
        if not folder_path.is_absolute():
            folder_path = folder_path.absolute()
        self.root = folder_path
        self.model = model
        self.__configuration = Configuration.from_json(folder_path/"configuration.json",model)
    @property
    def checkpoints(self) -> list[Path]:
        ckpt_folder = self.root/"checkpoints"
        ckpts = [ckpt_folder/filename for filename in os.listdir(ckpt_folder) if os.path.isfile(ckpt_folder/filename) and filename[-5:] == ".ckpt"]
        return ckpts
    @property
    def hparams(self) -> Path:
        return self.root/"hparams.yaml"
    @property
    def configuration(self) -> Configuration:
        return self.__configuration

    def save_pytorch_checkpoint(self, optimiser: torch.optim.Optimizer = None, filename="torch_checkpoint.pth.tar", custom_message=None):
        state = {"state_dict": self.model.state_dict()}
        if optimiser:
            state = {**state, "optimizer":optimiser.state_dict()}
        print("=> Saving checkpoint" if custom_message is None else custom_message)
        torch.save(state, self.root/filename)
    
    def load_pytorch_checkpoint(self, optimiser: torch.optim.Optimizer = None, filename="torch_checkpoint.pth.tar", custom_message=None):
        print("=> Loading checkpoint" if custom_message is None else custom_message)
        checkpoint = torch.load(filename)
        self.model.load_state_dict(checkpoint["state_dict"])
        if optimiser and "optimiser" in checkpoint.keys():
            optimiser.load_state_dict(checkpoint["optimiser"])

if __name__ == "__main__":
    m = torch.nn.Linear(1,1)
    c = Configuration.from_json("configuration.json",m)
    j = c.generate_json()
    print(j)
