import torch
from numpy import ndarray
from ..segmentation_model import SegmentationModule
import segmentation_models_pytorch as smp
from ..level_filters import LevelFilter
from ..Datasets.dataset import to_torch,normalise,get_bbox
import numpy as np
from pathlib import Path
import copy

class _SegmentationFilter(LevelFilter):

    filter_size = (320,320)

    threshold = torch.Tensor([0.5]).cpu().detach()

    def __init__(self,ckpt_path: Path, base_model, ignore_level=False):
        super().__init__(ignore_level)
        self.lightning_module = None
        self.ckpt_path = ckpt_path
        self.base_model = base_model

    def setup(self):
        self.lightning_module = SegmentationModule.load_from_checkpoint(self.ckpt_path,model=self.base_model)
        self.lightning_module.eval()
        self.lightning_module.cpu()

    @torch.no_grad
    def filter(self, img: ndarray, scale: float) -> tuple[ndarray, float]:
        timg = to_torch(normalise(copy.copy(img)))
        timg = timg.cpu().unsqueeze(0)
        prediction = self.lightning_module.forward(timg)
        prediction = torch.sigmoid(prediction).detach()
        prediction = (prediction>=self.threshold).float().cpu().detach()
        timg = timg.squeeze()
        prediction = prediction.squeeze()

        while len(prediction.shape)<3:
            prediction = prediction.unsqueeze(0)

        img = np.array(timg)
        mask = np.array(prediction)
        mask = np.transpose(mask,[1,2,0])
        img = np.transpose(img,[1,2,0])
        
        mask = self._reduce_mask((mask.squeeze()*255).astype(np.uint8))

        mask = np.repeat(mask[:,:,np.newaxis],3,axis=2)

        #TODO change to get median height above base rather than max height above base

        if all(mask.flatten()<=0): # mask has no detections of fluid
            return img,0.0
        bbox = _median_box(mask,fmt="coco")
        liquid_volume = bbox[3]*scale
        annotated_image = self._place_mask_on_image(img,mask)
        annotated_image = self._place_bbox_on_image(img,bbox)
        if self.ignore_level:
            liquid_volume = 0.0
        return (annotated_image*255).astype(np.uint8),liquid_volume

def _median_box(mask: np.ndarray,fmt="coco") -> tuple[int,int,int,int]:
    bbox = get_bbox(mask,fmt=fmt)
    xslice = slice(bbox[0],bbox[0]+bbox[2])
    yslice = slice(bbox[1],bbox[1]+bbox[3])
    reduced_mask = mask[yslice,xslice]
    ncols = reduced_mask.shape[1]
    npixels = np.zeros((ncols,))
    for i in range(0,ncols):
        column = reduced_mask[:,i].astype(np.uint16)
        npixels[i] = np.sum(column)
    height = int(np.median(npixels))

    bbox_out = (bbox[0], bbox[1] - (bbox[3]-height),bbox[2],height)

def LinkNetFilter(ignore_level=False):
    return _SegmentationFilter(Path(__file__).parent/"linknet_320x320.ckpt",smp.Linknet(encoder_name="resnet50",encoder_weights=None),ignore_level=ignore_level)
    

        