import torch
from numpy import ndarray
import segmentation_models_pytorch as smp
from vision_model.level_filters import LevelFilter
from vision_model.common_functions import to_torch, normalise, get_bbox, reduce_mask_numpy
import numpy as np
from pathlib import Path
import copy

class _SegmentationFilter(LevelFilter):

    filter_size = (320,320)

    def __init__(self,ckpt_path: Path, base_model: torch.nn.Module, ignore_level=False, use_cuda = True):
        super().__init__(ignore_level)
        self.ckpt_path = ckpt_path
        self.base_model = base_model
        self.device = 'cuda' if torch.cuda.is_available() and use_cuda else 'cpu'

    def setup(self):
        # load state dict from checkpoint
        map_location = {"cuda:0":"cpu"} if self.device == "cpu" else None
        checkpoint = torch.load(self.ckpt_path,map_location=map_location)
        self.base_model.load_state_dict(checkpoint["state_dict"])
        self.base_model.eval()
        self.base_model = self.base_model.to(self.device)

    @torch.no_grad
    def filter(self, img: ndarray, scale: float) -> tuple[ndarray, float]:
        timg = to_torch(normalise(copy.copy(img)),device=self.device) # convert img to tensor and send to gpu/cpu
        timg = timg.unsqueeze(0)

        prediction = self.base_model.forward(timg) # perform CNN segmentation
        mask = reduce_mask_numpy(prediction) # perform cv2 enhancements on segmentation, returns in 1-channel normalised cv2 format
        img = np.array(timg.cpu()).transpose(1,2,0) # get img as 3-channel normalised array in cv2 format
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
        column = reduced_mask[:,i,:]
        column = np.mean(column,axis=1)
        column = (column>0).astype(np.uint16)
        npixels[i] = np.sum(column)
    height = int(np.median(npixels)) if ncols>0 else 0

    bbox_out = (bbox[0], bbox[1]+bbox[3]-height, bbox[2], height)
    return bbox_out

def LinkNetFilter(ignore_level=False):
    return _SegmentationFilter(Path(__file__).parent/"linknet_320x320.pth.tar",smp.Linknet(encoder_name="resnet101",encoder_weights=None),ignore_level=ignore_level)
    

        