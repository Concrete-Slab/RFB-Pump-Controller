from abc import ABC, abstractmethod
from typing import Callable, Iterable
import numpy as np
import random
import cv2

Rect = tuple[int,int,int,int]
"""bboxes use the format [x_min,y_min,x_max,y_max]"""

bbox = tuple[Rect,str]

def _sample_random(minmax: tuple[float,float]) -> float:
    z = random.random()
    return minmax[0] + (minmax[1]-minmax[0])*z

def _assert_fraction(val: float|int|Iterable[float|int], allow_negative = False):
    """Return if val (or all entries in val) are between 0 and 1 inclusive. If allow_negative, then allow val between -1 and 1 inclusive"""
    minimum = -1 if allow_negative else 0
    if isinstance(val, float|int):
        assert (minimum<=val and 1>=val) 
    else:
        for v in val:
            _assert_fraction(v, allow_negative=allow_negative)

class Augmentation:
    def __init__(self, image: np.ndarray, mask: np.ndarray|None = None, bboxes: list[Rect]|None = None, masks: list[np.ndarray]|None = None):
        self.__image = image
        # mask is a single mask (e.g. binary segmentation), whereas masks is a list of different masks (e.g. for multiclass segmentation)
        self.__mask = mask
        self.__masks = masks
        self.__bboxes = bboxes
    @property
    def image(self):
        return self.__image
    @property
    def mask(self):
        if self.__mask is not None:
            return self.__mask
        raise ValueError("Transformation did not return a single mask")
    @property
    def bboxes(self):
        if self.__bboxes is not None:
            return self.__bboxes
        raise ValueError("Transformation did not return any bboxes")
    @property
    def masks(self):
        if self.__masks is not None:
            return self.__masks
        raise ValueError("Transformation did not return a list of masks")

class Transform(ABC):

    assert_sizes = False

    @abstractmethod
    def _transform(self,image: np.ndarray, mask: np.ndarray|None, bboxes: list[Rect]|None, masks: list[np.ndarray]|None = None) -> Augmentation:
        raise NotImplementedError()

    def __call__(self,image: np.ndarray, mask: np.ndarray|None = None, bboxes: list[Rect]|None=None, masks: list[np.ndarray]|None = None) -> Augmentation:
        if self.assert_sizes:
            if mask:
                assert image.shape[0:2] == mask.shape[0:2]
            if masks:
                assert all([image.shape[0:2] == m.shape[0:2] for m in masks])
        return self._transform(image,mask,bboxes,masks)
    
    @classmethod
    def _apply_to_masks_inplace(cls, masks: list[np.ndarray],fn: Callable[[np.ndarray],np.ndarray]):
        for i in range(0,len(masks)):
            masks[i] = fn(masks[i])
        return masks
    
    @classmethod
    def _apply_to_bboxes_inplace(cls, bboxes: list[Rect], fn: Callable[[Rect],Rect]):
        for i in range(0,len(bboxes)):
            bboxes[i] = fn(bboxes[i])
        return bboxes

class PTransform(Transform):
    """A transform with a probability of being applied, sampled each time the transform is called"""
    def __init__(self, p: float):
        super().__init__()
        _assert_fraction(p)
        self._p = p
    
    def __call__(self, image, mask = None, bboxes = None, masks = None):
        z = random.random()
        if z>self._p:
            ## Do not perform the transform, and return the image and masks/bboxes as they were
            return Augmentation(image,mask=mask,bboxes=bboxes,masks=masks)
        ## otherwise, proceed as usual
        return super().__call__(image, mask, bboxes, masks)

class Compose(Transform):
    """Represents a transformation that applies several basic transformations one after another"""
    def __init__(self,*args: Transform):
        self._transforms = args
    
    def _transform(self, image, mask, bboxes, masks):
        """Apply the Compose's list of transforms to the image in order"""
        # The next statement deals with the case of either having or not having a mask/bbox/masks
        # "nextaug" is a variable that stores the augmentation produced by the transforms. It is initialised below to deal with the null mask/bbox/masks case.
        nextaug = Augmentation(image,mask=mask,bboxes=bboxes,masks=masks)
        

        # now successively apply each transform (using the dict from "getargs") and store its result in nextaug
        for transform in self._transforms:
            kwargs = {"mask":nextaug.mask if mask is not None else None, "bboxes":nextaug.bboxes if bboxes else None, "masks":nextaug.masks if masks is not None else None}
            nextaug = transform(nextaug.image,**kwargs)
        return nextaug

class Affine(PTransform):
    """Apply an affine transform with translation, scale, and rotation"""

    def __init__(self, p = 0.5, shift_limit: float|tuple[float,float] = 0.1, scale_limit: float|tuple[float,float] = 0.1, rotation_limit: float|tuple[float,float] = 45.0):
        super().__init__(p)
        _assert_fraction(shift_limit,allow_negative=True)
        self._shift_limit = shift_limit if isinstance(shift_limit,tuple) else (-float(shift_limit),float(shift_limit))
        self._scale_limit = scale_limit if isinstance(scale_limit,tuple) else (1/(1+float(scale_limit)),1+float(scale_limit))
        self._rotation_limit = rotation_limit if isinstance(rotation_limit,tuple) else (-float(rotation_limit),float(rotation_limit))
    
    def _transform(self, image, mask, bboxes, masks):
        imshape = image.shape

        # sample the random shifts, scale, and rotation to use
        scale = _sample_random(self._scale_limit)
        shift_x = int(_sample_random(self._shift_limit)*imshape[1])
        shift_y = int(_sample_random(self._shift_limit)*imshape[0])
        rotate = _sample_random(self._rotation_limit)

        # calculate the affine matrix associated with the transform
        center = (imshape[0]//2,imshape[1]//2)
        r_mat= np.array(cv2.getRotationMatrix2D(center,rotate,scale),dtype=np.float32) # 2x2 rotation and scale
        translate_mat = np.array([[1,0,shift_x],[0,1,shift_y]],dtype=np.float32) # 2x3 translation (when applied to [x,y,1]^T)
        affine_mat = r_mat*translate_mat # overall 2x3 affine transform matrix

        # apply the affine transform
        kwargs = {"borderMode":cv2.BORDER_CONSTANT,"borderValue":0}
        image = cv2.warpAffine(image,affine_mat,imshape,**kwargs)
        if mask is not None:
            mask = cv2.warpAffine(mask,affine_mat,imshape,**kwargs)
        if masks is not None:
            masks = Transform._apply_to_masks_inplace(masks,lambda m: cv2.warpAffine(m,affine_mat,imshape,**kwargs))
        if bboxes is not None:
            bboxes = Transform._apply_to_bboxes_inplace(bboxes, lambda bb: _warp_bbox(bb,affine_mat,imshape))
        # package into an Augmentation object
        return Augmentation(image,mask=mask,bboxes=bboxes,masks=masks)
    
def _warp_bbox(bbox: Rect, M: np.ndarray, imshape: tuple[int,int]):
    # 3x4 matrix representing the coords of the bbox corners (one for each column). The third row is for the affine offset to allow translation.
    coord_mat = np.array([[bbox[0], bbox[0], bbox[2], bbox[2]],[bbox[3], bbox[1], bbox[1], bbox[3]],[1,1,1]],dtype=np.uint32)
    # perform the affine transform by matrix multiplication with the warp matrix (2x3)
    transformed_coords = M*coord_mat

    # get the min and max coords to re-define the bbox tuple
    xmin = int(np.min(transformed_coords[0,:]))
    xmax = int(np.max(transformed_coords[0,:]))
    ymin = int(np.min(transformed_coords[1,:]))
    ymax = int(np.max(transformed_coords[1,:]))

    # crop to ensure coords are in image and return the bbox
    return _crop_bbox([xmin,ymin,xmax,ymax],0,imshape[1],0,imshape[0])

class Flip(PTransform):
    """Transformation that flips the image along the vertical (0) or horizontal axis (1)"""

    # flip functions
    _flipvert: Callable[[np.ndarray],np.ndarray] = lambda arr: arr[:0:-1,:,:] if len(arr.shape) == 3 else arr[:0:-1,:]
    _fliphor: Callable[[np.ndarray],np.ndarray] = lambda arr: arr[:,:0:-1,:] if len(arr.shape) == 3 else arr[:,:0:-1]

    _flip_bb_vert: Callable[[Rect,tuple[int,int]],Rect] = lambda bb, imshape: (bb[0], imshape[0]-bb[3], bb[2], imshape[0]-bb[1]) # note the swapping between 1 and 3, because imheight-bb[1] > imheight-bb[3] and pos 1 is reserved for y_min.
    _flip_bb_hor: Callable[[Rect,tuple[int,int]],Rect] = lambda bb, imshape: (bb[2]-imshape[1], bb[1], imshape[1]-bb[0] ,bb[3]) # similar logic here

    def __init__(self, p=0.5, axis=1):
        super().__init__(p)
        _assert_fraction(axis)
        # set the image function and bbox function attributes based on the choice of axis
        match axis:
            case 0:
                # vertical flip
                self._im_fun = Flip._flipvert
                self._bb_fun = Flip._flip_bb_vert
            case 1:
                # horizontal flip
                self._im_fun = Flip._fliphor
                self._bb_fun = Flip._flip_bb_hor
            case _:
                self._im_fun = Flip._fliphor
                self._bb_fun = Flip._flip_bb_hor

    def _transform(self, image, mask, bboxes):
        image = self._im_fun(image)
        imshape2d = image.shape[0:2]
        if mask is not None:
            mask = self._im_fun(mask)
        if masks is not None:
            masks = Transform._apply_to_masks_inplace(masks,self._im_fun)
        if bboxes is not None:
            bboxes = Transform._apply_to_bboxes_inplace(bboxes, lambda bb: self._bb_fun(bb, imshape2d))
        return Augmentation(image,mask=mask,masks=masks)

class CropToSize(Transform):
    def __init__(self,max_width: int, max_height: int):
        super().__init__()
        self._maxw = max_width
        self._maxh = max_height

    def _transform(self, image, mask, bboxes, masks):
        imshape = image.shape
        if imshape[0]<=self._maxh and imshape[1]>=self._maxw:
            # image is already below max size, so just return
            return Augmentation(image,mask=mask)
        # output image size is component-wise minimum of required maximum size and actual image size
        outsize = (min(self._maxh,imshape[0]),min(self._maxw,imshape[1]))
        # start positions for the crop ensure the image is still centered
        start_pos_y = (self._maxh-imshape[0])//2
        start_pos_x = (self._maxw-imshape[1])//2

        # apply the crop
        args = [outsize,start_pos_y,start_pos_x]
        image = self._get_cropped(image,*args)
        if mask is not None:
            mask = self._get_cropped(mask,*args)
        if masks is not None:
            masks = Transform._apply_to_masks_inplace(masks, lambda m: self._get_cropped(m,*args))
        if bboxes is not None:
            # crop bboxes
            bboxes = Transform._apply_to_bboxes_inplace(bboxes, lambda bb: _crop_bbox(bb, start_pos_x, start_pos_x+outsize[1], start_pos_y, start_pos_y+outsize[0]) )
        
        return Augmentation(image,mask=mask,bboxes=bboxes,masks=masks)
        
    @classmethod
    def _get_cropped(cls, arr: np.ndarray, outsize: tuple[int,int], start_pos_y: int, start_pos_x: int):
        if len(arr.shape) == 3:
            return arr[start_pos_y:start_pos_y+outsize[0],start_pos_x:start_pos_x+outsize[1],:]
        return arr[start_pos_y:start_pos_y+outsize[0],start_pos_x:start_pos_x+outsize[1]]

def _crop_bbox(bbox: Rect, min_x: int, max_x: int, min_y: int, max_y: int):
    """Crop bboxes by ensuring their coords are between the min and max for each axis"""
    bbox[0] = min(max_x,max(0,bbox[0]-min_x)) # take the min of 0 and the shifted bbox x value, and then take the max of that and max_x.
    bbox[1] = min(max_y,max(0,bbox[1]-min_y)) # repeat for each component of the bbox
    bbox[2] = min(max_x,max(0,bbox[2]-min_x))
    bbox[3] = min(max_y,max(0,bbox[3]-min_y))
    return bbox

class PadToSize(Transform):
    def __init__(self, min_width: int, min_height: int, border_mode = cv2.BORDER_CONSTANT, border_value = 0, mask_value = 0):
        super().__init__()
        self._minw = min_width
        self._minh = min_height
        self._border_mode = border_mode
        self._border_value = border_value
        self._mask_value = mask_value
    def _transform(self, image, mask, bboxes, masks):
        imshape = image.shape
        if imshape[1]>=self._minw or imshape[0]>=self._minh:
            # Image is already above required size
            return Augmentation(image,mask=mask)
        
        # size of the output arrays is the component-wise maximum of the input array size and the required minimum
        outsize = (max(imshape[0],self._minh),max(imshape[1],self._minw))
        # start positions are such that the image/mask is centered in the padding
        start_pos_y = (self._minh-imshape[0])//2
        start_pos_x = (self._minw-imshape[1])//2

        # perform padding on image and mask
        image = self._get_padded(image, outsize, self._border_value, start_pos_y, start_pos_x)
        if mask is not None:
            # the mask padding uses "self._mask_value" instead of "self._border_value"
            mask = self._get_padded(mask,outsize,self._mask_value,start_pos_y,start_pos_x)
        if masks is not None:
            masks = Transform._apply_to_masks_inplace(masks, lambda m: self._get_padded(m,outsize,self._mask_value,start_pos_y,start_pos_x))
        if bboxes is not None:
            bboxes = Transform._apply_to_masks_inplace(bboxes, lambda bb: (bb[0]+start_pos_x, bb[1]+ start_pos_y, bb[2]+ start_pos_x, bb[3]+ start_pos_y))
        return Augmentation(image,mask=mask,masks=masks)

    @classmethod
    def _get_padded(cls, arr: np.ndarray, sz: tuple[int,int], border_val: int, start_pos_y: int, start_pos_x: int):
        """Performs the padding by preallocating a larger section of memory and copying the image into its central pixels"""
        # the array may have an additional dimension for color, so add this in if needed
        if len(arr.shape) == 3:
            sz = (sz[0],sz[1],arr.shape[2])
            # preallocate the output
            out = np.ones(sz)*border_val
            # set the central section of the output to the image
            out[start_pos_y:start_pos_y+arr.shape[0],start_pos_x:start_pos_x+arr.shape[1],:] = arr
        else:
            # preallocate the output
            out = np.ones(sz)*border_val
            # set the central section of the output to the image
            out[start_pos_y:start_pos_y+arr.shape[0],start_pos_x:start_pos_x+arr.shape[1]] = arr
        return out
        
class Crop(Transform):
    """Crops images to a bounding box specified by minimum and maximum x/y coordinates"""
    def __init__(self, x_min = 0, y_min = 0, x_max = 256, y_max = 256):
        super().__init__()
        self._x_min = x_min
        self._x_max = x_max
        self._y_min = y_min
        self._y_max = y_max
    
    def _transform(self, image, mask, bboxes, masks):
        image = self._get_cropped(image)
        if mask is not None:
            mask = self._get_cropped(mask)
        if masks is not None:
            masks = Transform._apply_to_masks_inplace(masks, self._get_cropped)
        if bboxes is not None:
            bboxes = Transform._apply_to_bboxes_inplace(bboxes, lambda bb: _crop_bbox(bb,self._x_min,self._x_max,self._y_min,self._y_max))
        return Augmentation(image,mask=mask,bboxes=bboxes,masks=masks)

    def _get_cropped(self,arr: np.ndarray):
        if len(arr.shape) == 3:
            return arr[self._y_min:self._y_max,self._x_min:self._x_max,:]
        return arr[self._y_min:self._y_max,self._x_min:self._x_max]

