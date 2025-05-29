import Datasets.dataset as ds
from pathlib import Path
from GLOBALS import Configuration
import torch
import torch.utils.data as data
from abc import ABC, abstractmethod
import math
from vision_model.ImageTransforms import Transform
from typing import Generic, TypeVar

## the class below is intended to function *like* a lightning.pytorch.LightningDataModule
## it has been modified so that lightining is not a dependency for this project

A = TypeVar("A")

DEFAULTS = Configuration()
class DataModule(ABC,Generic[A]):
    def __init__(self,
        dataset_path: Path,
        transforms: Transform|None = None,
        batch_size: int = DEFAULTS.batch_size,
        validation_split: float = DEFAULTS.proportion_validation,
        test_split: float = DEFAULTS.proportion_testing,
        seed: int|None = DEFAULTS.random_seed,
        num_workers: int = DEFAULTS.num_workers,
        pin_memory:bool=DEFAULTS.pin_memory,
        persistent_workers:bool=DEFAULTS.persistent_workers,
        shuffle: bool=DEFAULTS.shuffle_dataset,
        dataset_ensure_factor: int|None = DEFAULTS.ensure_factor,
        alpha_channel: bool = DEFAULTS.alpha_channel,
    ):
        super().__init__()
        # hyperparameters
        self.dataset_path = dataset_path
        self.transforms = transforms
        self.batch_size = batch_size
        self.validation_split = validation_split
        self.test_split = test_split
        self.seed = seed
        self.num_workers = num_workers
        self.pin_memory = pin_memory
        # persistent workers can only be true if workers are spawned
        self.persistent_workers = persistent_workers if self.num_workers > 0 else False
        self.shuffle = shuffle
        self.dataset_ensure_factor = dataset_ensure_factor
        self.alpha_channel = alpha_channel
        self.save_hyperparameters(ignore=("transforms",))

        # state variables
        self.train_set = None
        self.val_set = None
        self.test_set = None

    @property
    @abstractmethod
    def dataset(self) -> ds.BasicDataset[A]:
        pass
    @property
    def steps_in_epoch(self) -> int:
        if self.train_set is not None:
            sz = len(self.train_set)
        else:
            sz = len(self.dataset) * (1-self.validation_split-self.test_split)
        return math.ceil(sz/self.batch_size)

    @classmethod
    def from_configuration(cls,c: Configuration,transforms: Transform|None = None):
        return cls(c.dataset,transforms,c.batch_size,c.proportion_validation,c.proportion_testing,c.random_seed,c.num_workers,c.pin_memory,c.persistent_workers,c.shuffle_dataset,c.ensure_factor,c.alpha_channel)
            
    
    def setup(self, stage: str) -> None:
        generator = torch.Generator()
        if self.seed:
            generator.manual_seed(self.seed)
        self.train_set, self.val_set, test_set = data.random_split(self.dataset,[1-self.validation_split-self.test_split,self.validation_split,self.test_split],generator)
        if stage == "fit":
            self.test_set = test_set
        if stage == "test" and self.test_set is None:
            self.test_set = self.dataset
    
    def train_dataloader(self):
        return data.DataLoader(
            self.train_set,
            batch_size=self.batch_size,
            pin_memory=self.pin_memory,
            shuffle=self.shuffle,
            persistent_workers=self.persistent_workers,
            num_workers=self.num_workers
        )
    
    def val_dataloader(self):
        return data.DataLoader(
            self.val_set,
            batch_size=self.batch_size,
            pin_memory=self.pin_memory,
            shuffle=False,
            persistent_workers=self.persistent_workers,
            num_workers=self.num_workers
        )
    
    def test_dataloader(self):
        return data.DataLoader(
            self.test_set,
            batch_size=self.batch_size,
            pin_memory=self.pin_memory,
            shuffle=False,
            persistent_workers=self.persistent_workers,
            num_workers=self.num_workers
        )

class SegmentationDataModule(DataModule[torch.Tensor]):
    @property
    def dataset(self):
        return ds.MaskDataset(self.dataset_path,self.transforms,self.dataset_ensure_factor,self.alpha_channel)
    
class BoxDataModule(DataModule[torch.Tensor]):
    @property
    def dataset(self):
        return ds.BoxDataset(self.dataset_path,self.transforms,self.dataset_ensure_factor,self.alpha_channel)