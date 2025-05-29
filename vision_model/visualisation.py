import random
import torch
from segmentation_model import SegmentationModule
import segmentation_models_pytorch as smp
from Datasets.dataset import MaskDataset, to_torch, normalise
from cv2_gui.mouse_events import ImageScroller, MouseInput
from cv2_gui.cv2_multiprocessing import open_cv2_window
from pathlib import Path
from GLOBALS import Configuration
import os
from PIL import Image
import numpy as np


def save_checkpoint(model: torch.nn.Module, optimiser: torch.optim.Optimizer = None, filename="my_checkpoint.pth.tar", custom_message=None):
    state = {"state_dict": model.state_dict()}
    if optimiser:
        state = {**state, "optimizer":optimiser.state_dict()}
    print("=> Saving checkpoint" if custom_message is None else custom_message)
    torch.save(state, filename)




class LogFolder:
    def __init__(self,folder_path: Path,model: torch.nn.Module) -> None:
        if not folder_path.is_absolute():
            folder_path = folder_path.absolute()
        self.root = folder_path
        self.__configuration = Configuration.from_json(folder_path/"configuration.json",model.__class__.__name__)
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
def get_predictions():
    ckpt_path = "logs\\Linknet-320x320\\version_4\\checkpoints\\Linknet-320x320-epoch=223-mean_val_loss=8.92e-03.ckpt"
    module = smp.Linknet(encoder_name="resnet50",encoder_weights=None)
    log_folder = LogFolder(Path("logs\\Linknet-320x320\\version_4"),module)

    
    
    
    
    plmodel = SegmentationModule.load_from_checkpoint(log_folder.checkpoints[1],model=module)
    module.cpu()

    save_checkpoint(plmodel.model,filename=log_folder.root/"torch_ckpt.pth.tar")

    ds = MaskDataset("320x320")
    plmodel.eval()
    module.eval()
    indices = list(range(0,len(os.listdir("Images"))))
    random.shuffle(indices)

    mi = ImageScroller(auto_progress=True)
    window = "View Predictions"
    def loopfun(_:int, i:int):
        img = produce_image(i,ds,module)
        mi(window,img,ignore_backwards=False)
    with open_cv2_window(window):
        MouseInput.iterate(loopfun,indices)

@torch.no_grad
def produce_image(index: int,ds: MaskDataset, module: smp.Linknet):
    # inp,_ = ds[index]
    imgnames = os.listdir("Images")
    inp = np.array(Image.open(Path(__file__).parent/"Images"/imgnames[index]))
    inp = to_torch(normalise(inp))
    inp = inp.cpu().unsqueeze(0)
    prediction = module(inp)
    # generate predictions from logits
    prediction = torch.sigmoid(prediction).detach()
    threshold = torch.Tensor([0.5]).to(prediction.device).detach()
    prediction = (prediction>=threshold).float().detach()
    inp = inp.squeeze()
    prediction = prediction.squeeze()
    img_out = ds.visualise_target(inp,prediction,alpha=1)
    return img_out
    
if __name__=="__main__":
    get_predictions()
