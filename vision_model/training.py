from segmentation_model import SegmentationModule
import segmentation_models_pytorch as smp
import lightning.pytorch as pl
from lightning.pytorch.tuner import Tuner
import torch
from GLOBALS import Configuration, LOG_DIR, LogFolder
import albumentations as A
import cv2
from pathlib import Path
from tensorboard_addon import tblogger
from datamodules import SegmentationDataModule,DataModule
# from torch.profiler import profile,ProfilerActivity
# from torch.utils.viz._cycles import warn_tensor_cycles

def tune(trainer: pl.Trainer,model: pl.LightningModule,datamodule: DataModule,strict=True):
    print("Tuning batch size")
    tuner = Tuner(trainer)
    tuner.scale_batch_size(model,datamodule=datamodule,steps_per_trial=2,mode="binsearch",init_val=datamodule.batch_size)
    if strict:
        # just in case, reduce batch size by 1 from its maximum value to avoid OOM
        datamodule.batch_size = max(datamodule.batch_size-1,1)

def train(
    module: torch.nn.Module,
    config_path: Path|str = "configuration.json"
):
    print("Reading Configuration")
    c = Configuration.from_json(config_path,module)
    torch.set_float32_matmul_precision(c.matmul_precision)   

    print("Configuring Data Module")
    transforms = A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.ShiftScaleRotate(shift_limit=0.1,scale_limit=0.4,rotate_limit=25,p=1,border_mode=cv2.BORDER_CONSTANT,value=0,mask_value=0),
        ]
    )
    dm = SegmentationDataModule.from_configuration(c,transforms)

    model = SegmentationModule.from_configuration(module,c)

    logger = tblogger(LOG_DIR,name=c.experiment_name,copy_path=Path(config_path))
    # prof = profile(activities=[ProfilerActivity.CPU,ProfilerActivity.CUDA],profile_memory=True,record_shapes=True)

    # warn_tensor_cycles()
    # torch.cuda.memory._record_memory_history()

    with logger as l:
        try:
            print("Initialising Trainer")
            trainer = pl.Trainer(
                callbacks=c.training_callbacks,
                logger=l,
                max_epochs=c.max_epochs,
                min_epochs=c.min_epochs,
                precision=c.precision,
                log_every_n_steps=dm.steps_in_epoch
            )

            if c.tune_batch_size:
                tune(trainer,model,dm)

            print("-----------------BEGIN TRAINING------------------")
            trainer.fit(
                model,
                datamodule=dm,
            )
            print("-----------------BEGIN TESTING------------------")
            trainer.test(
                model,
                datamodule=dm,
            )
        except RuntimeError as e: # out of memory
            print(e)
    log_folder = LogFolder(Path(l.log_dir),module)
    ckpt = sorted(log_folder.checkpoints,key = lambda name: len(name))[-1]
    print(ckpt)
    log_folder.save_pytorch_checkpoint()
    # torch.cuda.memory._dump_snapshot("my_snapshot.pickle")
    # print(prof.key_averages().table(sort_by="cuda_memory_usage"))


def main():
    print("Initialising Model")
    model = smp.UnetPlusPlus(encoder_name="resnet50",encoder_weights=None)
    train(model)

if __name__ == "__main__":
    main()