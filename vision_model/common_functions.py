"""This module contains functions used by both the training code and the main application. This is the only crossover between the two codes, and therefore reduces the size of each when compiled."""
import numpy as np
import torch
import cv2

def to_torch(npimg: np.ndarray, device: str|None = None) -> torch.Tensor:
    # add a channel dimension to image if it doesnt exist
    if len(npimg.shape) == 2:
        npimg = np.expand_dims(npimg,2)
    # torch uses CHW format, image supplied from PIL is in HWC format
    npimg = npimg.transpose(2,0,1)
    # convert numpy array to torch tensor
    if device is None:
        return torch.from_numpy(npimg).float()
    return torch.from_numpy(npimg).float().to(device=device)

def normalise(img: np.ndarray, max_pixel_value=255) -> np.ndarray:
    # Reduce image range to [0,1]
    img = img / max_pixel_value
    # # Normalise the image
    # mean = np.mean(img)
    # std = np.std(img)
    # img = (img-mean)/std
    # # image now has 0.5 mean and range [0,1]
    return img

BBOX_FORMAT = "pascal_voc"
Rect = tuple[int,int,int,int]
class BboxFormatException(NotImplementedError):
    def __init__(self, fmt: str) -> None:
        str_out = f"Unknown bbox format: {fmt}"
        super().__init__(str_out)

def get_bbox(img: np.ndarray,fmt: str=BBOX_FORMAT) -> Rect:
    nrows = img.shape[0]
    ncols = img.shape[1]
    rows = np.any(img>0, axis=1)
    cols = np.any(img>0, axis=0)
    try:
        rmin, rmax = np.where(rows)[0][[0, -1]]
        cmin, cmax = np.where(cols)[0][[0, -1]]
    except IndexError:
        # mask doesnt exist or is too thin
        rmin, rmax, cmin, cmax = (0,0,0,0)
    # calculate median height
    
    match fmt:
        case "coco":
            return int(cmin), int(rmin), int(cmax-cmin), int(rmax-rmin)
        case "pascal_voc":
            return int(cmin),int(rmin),int(cmax),int(rmax)
        case "albumentations":
            return int(cmin)/ncols,int(rmin)/nrows,int(cmax)/ncols,int(rmax)/nrows
        case _:
            raise BboxFormatException(fmt)

def reduce_mask_numpy(prediction: torch.Tensor, kernel_size=(10,10), threshold_value = 0.5):
    # generate predictions from logits
    prediction = torch.sigmoid(prediction).detach()
    threshold = torch.Tensor([0.5]).to(prediction.device).detach()
    
    prediction = (prediction>=threshold).float().cpu()
    
    # convert to numpy array
    while len(prediction.shape)>3:
        prediction = prediction.squeeze() # remove any additional dimensions of size 1 (e.g. batch index)
    while len(prediction.shape)<3:
        prediction = prediction.unsqueeze(0)
    mask = np.array(prediction)
    mask = np.transpose(mask,[1,2,0])
    # morph close to remove smaller blobs more efficiently
    kernel = np.ones(kernel_size)*255
    thresh= cv2.morphologyEx(mask,cv2.MORPH_OPEN,kernel)
    thresh = np.multiply(thresh,255).astype(np.uint8) # convert from 0<thresh<1 to 0<thresh<255 and ensure uint8 datatype
    # find the contours around all remaining activations
    contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]
    # select the contour with the maximum area
    if len(contours)>0:
        max_contour = max(contours,key=cv2.contourArea)
        mask_out = np.zeros_like(mask,dtype=np.uint8)
        cv2.drawContours(mask_out,[max_contour],-1,255,thickness=cv2.FILLED)
        # mask_out = mask_out.transpose(2,0,1)
    else:
        mask_out = thresh[:,:,np.newaxis]
    return mask_out.astype(np.float32)/255

def reduce_mask(prediction: torch.Tensor, kernel_size=(10,10)):
    original_device = prediction.device
    original_size = len(prediction.shape)

    mask_array = reduce_mask_numpy(prediction,kernel_size=kernel_size)
    mask_array = mask_array.transpose(2,0,1) # torch uses channels,height,width instead of cv2's height,width,channel
    mask_tensor = torch.from_numpy(mask_array).float().cpu() # convert to Tensor

    while len(mask_tensor.shape)<original_size:
        mask_tensor = mask_tensor.unsqueeze(0)
    while len(mask_tensor.shape)>original_size:
        mask_tensor = mask_tensor.squeeze()
    mask_tensor = mask_tensor.to(original_device)
    one = torch.Tensor([1]).to(original_device).detach()
    mask_tensor = torch.log(mask_tensor/(one-mask_tensor)) # convert mask back from probability into logits
    return mask_tensor