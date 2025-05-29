from abc import ABC , abstractmethod
import copy
import os
from typing import Generic, TypeVar
import warnings
from PIL import Image
import numpy as np
from pathlib import Path
from vision_model.ImageTransforms import Transform, Compose, PadToSize, Crop
from vision_model.GLOBALS import get_bbox, to_torch, normalise, BBOX_FORMAT, BboxFormatException, Rect
import torch
from torch.utils.data import Dataset
import cv2
from dataclasses import dataclass, asdict
import shutil
import math
from cv2_gui.mouse_events import MouseInput, ImageScroller, BoxDrawer
from cv2_gui.cv2_multiprocessing import open_cv2_window
from pycocotools.coco import COCO
import json
import imagesize


ORIGINAL_DIR = Path(__file__).absolute().parent
ORIGINAL_IMAGES = ORIGINAL_DIR / "Images"


@dataclass
class DatasetPath:
    images: Path
    json: Path
    masks: Path

    @classmethod
    def _json_name(cls) -> str:
        return "annotations.json"
    @classmethod
    def _mask_name(cls) -> str:
        return "Masks"
    @classmethod
    def _default_images_path(cls,init_path: Path) -> str:
        return init_path/"Images"

    @classmethod
    def create(cls, root: Path|str, name: str, img_dir: Path|str|None = None):
        if isinstance(root,str):
            root = Path(__file__).parent/root
        if img_dir is None:
            img_dir = cls._default_images_path(root)
        elif isinstance(img_dir,str):
            img_dir = Path(img_dir)
        if not os.path.isdir(img_dir):
            raise OSError(f"Image directory provided does not exist: {img_dir.as_posix()}")
        
        name = name.split(".")[0] # ensure no file extensions in directory name
        ds_path = (root / name)
        if not ds_path.is_absolute():
            ds_path = ds_path.absolute()
        if name not in os.listdir(root):
            os.mkdir(ds_path)
        mask_path = ds_path / cls._mask_name()
        json_path = ds_path / cls._json_name()
        if not os.path.isdir(mask_path):
            os.mkdir(mask_path)
        return DatasetPath(img_dir,json_path,mask_path)
    
    @classmethod
    def infer(cls, ds_path: Path|str, img_dir: Path|str|None = None):
        if isinstance(ds_path,str):
            ds_path = Path(__file__).parent/ds_path
        if not ds_path.is_absolute():
            ds_path = ds_path.absolute()
        if not os.path.isdir(ds_path):
            raise OSError(f"Dataset directory provided does not exist: " + ds_path.as_posix())
        if img_dir is None:
            img_dir = cls._default_images_path(ds_path.parent)
        elif isinstance(img_dir,str):
            img_dir = Path(img_dir)
        if not os.path.isdir(img_dir):
            raise OSError(f"Image directory provided does not exist: " + img_dir.as_posix())

        mask_path = ds_path / cls._mask_name()
        json_path = ds_path / cls._json_name()
        if not os.path.isdir(mask_path):
            raise OSError("Dataset directory does not contain ./Masks: "+ ds_path.as_posix())
        if not os.path.isfile(json_path):
            raise OSError("Dataset directory does not contain ./" + cls._json_name() + ": "+ ds_path.as_posix())
        
        return DatasetPath(img_dir,json_path,mask_path)

    def copy(self, new_path: Path|str, img_extension: str = ".png"):
        if isinstance(new_path,str):
            new_path = self.images.parent/new_path
        if not new_path.is_absolute():
            new_path = new_path.absolute()
        
        try:
            target = DatasetPath.infer(new_path,img_dir=self.images)
        except OSError:
            target = DatasetPath.create(new_path.parent,new_path.parts[-1],img_dir=self.images)
        
        # copy annotations.json
        shutil.copy2(self.json,target.json)
        # copy masks
        copy_images(self.masks,target.masks,img_extension)
        return target
@dataclass
class AnnotatedImage:
    img_name: str
    mask_names: list[str]|None = None
    bboxes: list[Rect]|None = None
    labels: list[int]|None = None
    outer_bbox: Rect|None = None

    @classmethod
    def load_json(cls, jsonpath: Path, require_masks=False, require_bboxes=False, require_ids=False, outer_bbox_shape: tuple[int,int]|None = None) -> list["AnnotatedImage"]:
        def transform_boxes(bboxes: list[list[int]]|list[int]) -> list[Rect]:
            try:
                _ = len(bboxes[0])
                out = [(0,0,0,0)]*len(bboxes)
                for i,bbox in enumerate(bboxes):
                    assert len(bbox) == 4
                    out[i] = tuple(bbox)
                return out
            except TypeError: # not list[list]]
                assert len(bboxes) == 4
                return tuple(bboxes)
        
        require_bboxes = require_bboxes or require_ids
        with open(jsonpath,"r") as jf:
            json_obj: list[dict[str|list]] = json.load(jf)
        if outer_bbox_shape is not None and (len(outer_bbox_shape) != 2 or outer_bbox_shape[0]<1 or outer_bbox_shape[1]<1):
            # soft error
            outer_bbox_shape = None
        out = []
        for info in json_obj:
            if (info["mask_names"] is None or len(info["mask_names"])<1) and require_masks:
                continue

            if info["bboxes"] is not None and len(info["bboxes"])>0:
                info["bboxes"] = transform_boxes(info["bboxes"])
            elif require_bboxes:
                continue

            if (info["labels"] is None or len(info["labels"])<1) and require_ids:
                continue
            
            if info["outer_bbox"] is not None:
                assert len(info["outer_bbox"]) == 4
                info["outer_bbox"] = tuple(info["outer_bbox"])
                if outer_bbox_shape is not None and info["outer_bbox"] != outer_bbox_shape:
                    continue
            elif outer_bbox_shape is not None:
                continue
            
            out.append(AnnotatedImage(**info))
        return out
    
    @classmethod
    def save_json(cls,anns: list["AnnotatedImage"], jsonpath: Path):
        json_obj = []
        for aimg in anns:
            d_obj = asdict(aimg)
            d_obj["bboxes"] = list(map(list,d_obj["bboxes"])) if d_obj["bboxes"] is not None else None
            d_obj["outer_bbox"] = list(d_obj["outer_bbox"]) if d_obj["outer_bbox"] is not None else None
            json_obj.append(d_obj)
        with open(jsonpath,"w") as jf:
            json.dump(json_obj,jf)

def get_subimg(r: Rect, img_path: Path, fmt=BBOX_FORMAT) -> np.ndarray:
    img = np.array(Image.open(img_path))
    if fmt == "albumentations":
        width = img.shape[1]
        height = img.shape[0]
        r = (r[0]*width,r[1]*height,r[2]*width,r[3]*height)
        fmt = "pascal_voc"
    match fmt:
        case "pascal_voc":
            slices =  (slice(r[1],r[3]),slice(r[0],r[2]))
        case "coco":
            slices = (slice(r[1],r[1]+r[3]), slice(r[0],r[0]+r[2]))
        case _:
            errstr = f"Unknown bbox format: {fmt}"
            raise NotImplementedError(errstr)
    yslice,xslice = slices
    return img[yslice,xslice]

def get_bbox_shape(r: Rect, img_path: Path,fmt: str=BBOX_FORMAT):
    if fmt == "albumentations":
        img = np.array(Image.open(img_path))
        width = img.shape[1]
        height = img.shape[0]
        r = (r[0]*width,r[1]*height,r[2]*width,r[3]*height)
        fmt = "pascal_voc"
    match fmt:
        case "pascal_voc":
            width = r[2]-r[0]
            height = r[3]-r[1]
        case "coco":
            width = r[2]
            height = r[3]
        case _:
            errstr = f"Unknown bbox format: {fmt}"
            raise NotImplementedError(errstr)
    return (height,width)


def _get_crop_params(bbox: Rect, img: np.ndarray, fmt: str=BBOX_FORMAT) -> dict[str,int]:
    if fmt == "augmentations":
        width = img.shape[1]
        height = img.shape[0]
        bbox = (bbox[0]*width,bbox[1]*height,bbox[2]*width,bbox[3]*height)
        fmt = "pascal_voc"
    match fmt:
        case "pascal_voc":
            return {"x_min":bbox[0],"y_min":bbox[1],"x_max":bbox[2],"y_max":bbox[3]}
        case "coco":
            return {"x_min":bbox[0],"y_min":bbox[1],"x_max":bbox[0]+bbox[2],"y_max":bbox[1]+bbox[3]}
        case _:
            raise BboxFormatException(fmt)

def _coco_to_pascal_voc(bbox_in: Rect):
     (bbox_in[0],bbox_in[1],bbox_in[0]+bbox_in[2],bbox_in[1]+bbox_in[3])


class SubImage:
    def __init__(self, img: np.ndarray, outer_box: tuple[int,int,int,int], inner_box: tuple[int,int,int,int]):
        self.image = img[outer_box[1]:outer_box[1]+outer_box[3], outer_box[0]:outer_box[0]+outer_box[2],:]
        # mask region is defined relative to whole image -> make it relative to sub image
        subregion = (inner_box[0]-outer_box[0],inner_box[1]-outer_box[1],inner_box[2],inner_box[3])
        self.mask = np.zeros(self.image.shape[:-1],dtype=np.float32)
        self.mask[subregion[1]:subregion[1]+subregion[3], subregion[0]:subregion[0]+subregion[2]] = np.ones((subregion[3],subregion[2]),dtype=np.float32)
    
    @staticmethod
    def from_csv(img_dir: Path, csv_row: list[str]):
        img_path = img_dir / csv_row[0]
        # img = cv2.imread(img_path.as_posix(),flags = cv2.IMREAD_UNCHANGED)
        # img = cv2.cvtColor(img,cv2.COLOR_BGRA2RGBA)
        img = np.array(Image.open(img_path))
        outer_1 = tuple(map(int,csv_row[1:5]))
        inner_1 = tuple(map(int,csv_row[5:9]))
        outer_2 = tuple(map(int,csv_row[9:13]))
        inner_2 = tuple(map(int,csv_row[13:]))
        return SubImage(img,outer_1,inner_1), SubImage(img,outer_2,inner_2)

class DatasetHandler:

    __placeholder_name = "annotations_"

    def _get_placeholder_name(self) -> str:
        dir_numbers = [int(d.lstrip(self.__placeholder_name)) for d in os.listdir(self.imgdir) if (os.path.isdir(d) and d[0:len(self.__placeholder_name)] == self.__placeholder_name)]
        next_number = max(dir_numbers) + 1
        return self.__placeholder_name + str(next_number)
    
    @staticmethod
    def _get_mask_name(img_name: str, inst_id: int|None = None):
        suffix = "mask"
        if inst_id is not None:
            suffix += "_"+str(inst_id)
        return suffix + img_name.lstrip("img")

    def __init__(self, dataset_folder:Path=ORIGINAL_DIR, imgpath: Path|None = None, copy_files: bool=False, extension = ".png", overwrite: bool=False) -> None:
        """Class for creating and modifying the image dataset. 
        If initialised with \"imgpath\" argument, any files with \"extension\" will be considered as part of the dataset.
        If \"imgpath\" is not given, \"dataset_folder\"\\Images will be considered as the dataset images. If empty, the initialisation will complete with a warning.
        If Images exist in that directory, only those files not present will be copied.
        If \"overwrite\" is True, and imgpath is given, then the contents of \"dataset_folder\"/Images will be cleared and set to the contents of imgpath instead.

        Images will require labelling for use in the training sequence. If labels are not available upon instantiation, a prompt will be given to label the data.
        If get_directory is called when labels are not available for all data, the prompt will also be given
        """

        if not os.path.isdir(dataset_folder):
            os.mkdir(dataset_folder)

        placeholder_imgdir = DatasetPath._default_images_path(dataset_folder)
        if imgpath is None:
            self.imgdir = placeholder_imgdir
            if not os.path.isdir(placeholder_imgdir):
                os.mkdir(placeholder_imgdir)
        elif copy_files:
            if overwrite:
                shutil.rmtree(self.imgdir)
            if not os.path.isdir(placeholder_imgdir):
                os.mkdir(placeholder_imgdir)
            copy_images(imgpath,placeholder_imgdir,extension)
            self.imgdir = placeholder_imgdir
        else:
            self.imgdir = imgpath
        
        self.root = dataset_folder.absolute()

        self.n_images = len(os.listdir(self.imgdir))
        if self.n_images<1:
            warnings.warn(f"No Images available in {self.imgdir.as_posix()}. Datasets will be empty.")
        
        self.extension = extension

    def get_directories(self) -> list[Path]:
        all_dirs = [d for d in os.listdir(self.root) if d!=self.imgdir.parts[-1]]
        out_dirs = []
        for d in all_dirs:
            try:
                _ = DatasetPath.infer(self.root/d,img_dir=self.imgdir)
                out_dirs.append((self.root/d).absolute())
            except OSError:
                continue
        return out_dirs

    def new_from_coco(self,jsonpath: Path|str, new_dir_name: str|None = None) -> DatasetPath:
        if isinstance(jsonpath,str):
            jsonpath = Path(jsonpath)
        if jsonpath.is_absolute():
            pwd = jsonpath.absolute()
        else:
            pwd = self.root/jsonpath
        coco_obj = COCO(pwd)

        if new_dir_name is None:
            new_dir_name = self._get_placeholder_name()
        dsp = DatasetPath.create(self.root,new_dir_name,self.imgdir)
        
        all_images = [file for file in os.listdir(self.imgdir) if file[-len(self.extension):] == self.extension]
        annotated_images = []
        valid_imgs = [img for img in coco_obj.imgs.values() if img["file_name"] in all_images]
        for img in valid_imgs:
            aimg = self._get_anns(img, coco_obj, dsp.masks)
            annotated_images.append(aimg)
        AnnotatedImage.save_json(annotated_images,dsp.json)
        return dsp

    def add_outer_boxes(self,existing_data: Path|str, box_size: tuple[int,int], new_dir_name: str|None = None):
        """Annotate outer boxes onto already-annotated data
        if \"existing_data\" is a json file, it will be assumed to be a coco annotations file.
        In such a case, a new directory containing masks and annotations will be created under \"new_dir_name\" (or a placeholder name) with the annotations
        If \"existing_data\" points to an annotated directory (containing masks and annotations.json), then that directory will be modified with the new outer boxes unless \"new_dir_name\" is given.
        Should \"new_dir_name\" be given in this case, the annotations from \"existing_data\" will be copied to the new directory (if not already there), and from the outer boxes will be added to this new directory
        """

        assert len(box_size) == 2

        if isinstance(existing_data,Path):
            extension = existing_data.as_posix().split(".")[-1]
            if not existing_data.is_absolute():
                existing_data = self.root/existing_data
        else:
            extension = existing_data.split(".")[-1]
            existing_data = self.root/existing_data

        if extension == "json":
            try:
                self.new_from_coco(existing_data,new_dir_name=new_dir_name)
                target_dsp = DatasetPath.infer(self.root/new_dir_name)
            except AssertionError:
                raise OSError("json file provided is not in COCO format")
        else:
            initial_dsp = DatasetPath.infer(existing_data,img_dir=self.imgdir)
            if new_dir_name is not None:
                target_dsp = initial_dsp.copy(new_dir_name)
            else:
                target_dsp = initial_dsp

        # make copies of the annotated images for each instance contained within in preparation for outer box placement
        anns = AnnotatedImage.load_json(target_dsp.json)
        anns_out = []
        for ann in anns:
            nmasks = len(ann.mask_names) if ann.mask_names else 0
            nboxes = len(ann.bboxes) if ann.bboxes else 0
            nlabels = len(ann.labels) if ann.labels else 0
            n = max(nmasks,nlabels,nboxes)
            for i in range(0,n):
                anns_out.append(copy.copy(ann))
        AnnotatedImage.save_json(anns_out,target_dsp.json)
        
        self._draw_outer_boxes(target_dsp, box_size)
    
    def _draw_outer_boxes(self,dsp: DatasetPath, shp: tuple[int,int]):
        all_imgs = AnnotatedImage.load_json(dsp.json)
        candidate_images = []
        other_images = []
        for aimg in all_imgs:
            if aimg.outer_bbox is None or get_bbox_shape(aimg.outer_bbox,dsp.images/aimg.img_name) != shp:
                candidate_images.append(aimg)
            else:
                other_images.append(aimg)
        mi = BoxDrawer(shp[0],shp[1],auto_progress=True)
        window = "Draw outer boxes on images"
        def loopfun(_:int, aimg: AnnotatedImage):
            outer_box = aimg.outer_bbox
            image = np.array(Image.open(self.imgdir/aimg.img_name))
            # display already-drawn bounding boxes
            similar_imgs = list(filter(lambda ann: aimg.img_name == ann.img_name and ann.outer_bbox is not None and ann!=aimg, candidate_images))
            for simg in similar_imgs:
                similar_box = simg.outer_bbox
                #TODO make independent of bbox type
                image = cv2.rectangle(image,(similar_box[0],similar_box[1]),(similar_box[2],similar_box[3]),mi.color,thickness=1)
            outer_box = mi(window,image,ignore_backwards=False)
            #TODO make this independent of bbox type
            outer_box = (outer_box[0],outer_box[1],outer_box[0]+outer_box[2],outer_box[1]+outer_box[3])
            aimg.outer_bbox = outer_box
        with open_cv2_window(window):
            MouseInput.iterate(loopfun,candidate_images)
        all_annotations = [*candidate_images,*other_images]
        AnnotatedImage.save_json(all_annotations,dsp.json)

    def _get_anns(self,img: dict[str,str|int], coco: COCO, mask_dir: Path) -> AnnotatedImage:
        cat_ids = coco.getCatIds()
        anns_ids = coco.getAnnIds(imgIds=img["id"],catIds=cat_ids,iscrowd=False)
        anns = coco.loadAnns(anns_ids)
        mask_names = [""]*len(anns)
        bboxes = [(0,0,0,0)]*len(anns)
        labels = [0]*len(anns)
        for i,ann in enumerate(anns):
            mask = coco.annToMask(ann)
            mask_name = self._get_mask_name(img["file_name"],inst_id=i)
            Image.fromarray(mask).save(mask_dir/mask_name)
            mask_names[i] = mask_name
            bboxes[i] = get_bbox(mask)
            labels[i] = ann["category_id"]
        return AnnotatedImage(img["file_name"], mask_names=mask_names, bboxes=bboxes, labels=labels)


def copy_images(initial_directory: Path, target_directory: Path, extension: str):
    suffix_index = -1*len(extension)
    initial_filenames = [filename for filename in os.listdir(initial_directory) if filename[suffix_index:] == extension]
    target_filenames = [filename for filename in os.listdir(target_directory) if filename[suffix_index:] == extension]
    extra_filenames = [filename for filename in initial_filenames if filename not in target_filenames]
    for file in extra_filenames:
        initpath = (initial_directory/file).as_posix()
        dstpath = (target_directory/file).as_posix()
        shutil.copy2(initpath,dstpath)

A = TypeVar("A")

class BasicDataset(Dataset,ABC,Generic[A]):

    def __len__(self):
        return len(self.annotated_images)
    
    @abstractmethod
    def __getitem__(self, index: int) -> tuple[torch.Tensor,A]:
        pass

    def __init__(
            self,
            rootpath: Path|str, 
            transform: list[Transform]|Transform|None = None, 
            ensure_factor: int|None = None, 
            alpha_channel:bool = False, 
            img_dir: Path|str|None = None,
            require_masks: bool=False,
            require_bboxes: bool=False,
            require_ids: bool = False,
            shape: tuple[int,int]|None = None,
            bbox_format: str|None = None,
    ) -> None:
        # input parsing
        ds_path = DatasetPath.infer(rootpath,img_dir=img_dir)
        
        self.img_dir = ds_path.images
        self.mask_dir = ds_path.masks
        self.annotated_images = AnnotatedImage.load_json(ds_path.json,require_masks,require_bboxes,require_ids,shape)
 
        if len(self.annotated_images)<1:
            raise OSError("No annotations in dataset path match requirements")
        
        used_imgs = [ai.img_name for ai in self.annotated_images]

        self.alpha_channel = alpha_channel
        min_shape=[1e6,1e6]

        for filename in used_imgs:
            sz = imagesize.get(self.img_dir/filename)
            sz = (sz[1],sz[0])
            min_shape[0] = min(min_shape[0],sz[0])
            min_shape[1] = min(min_shape[1],sz[1])
        min_shape = tuple(min_shape)

        if isinstance(transform,Transform):
            transform = [transform]
        elif transform is None:
            transform = []

        # self.bbox_params = A.BboxParams(bbox_format,label_fields=["label_ids"]) if bbox_format is not None else None
        
        if ensure_factor is not None:
            pad_width = math.ceil(min_shape[1]/ensure_factor) * ensure_factor
            pad_height = math.ceil(min_shape[0]/ensure_factor) * ensure_factor
            self.transform = Compose(
                *transform,
                PadToSize(min_height=pad_height,min_width=pad_width,border_mode=cv2.BORDER_CONSTANT,border_value=0,mask_value=0),
                Crop(x_max=pad_width,y_max=pad_height),
            )
            self.image_shape = (pad_height,pad_width)
        else:
            self.transform = Compose(
                *transform,
                Crop(x_max=min_shape[1],y_max=min_shape[0])
            )
            self.image_shape = min_shape

    def apply_transforms(self,image: np.ndarray, outer_bbox: Rect|None, mask: np.ndarray|None = None, bboxes: list[Rect]|None = None, masks: list[np.ndarray]|None=None):
        # first apply the transformations
        aug = self.transform(image,mask=mask,bboxes=bboxes,masks=masks)
        # now we need to crop to fit the outer bbox to obtain the final image
        if outer_bbox:
            # first get the kwargs to feed into the crop transformation (basically, do we need to also crop bboxes and a mask?)
            kwargs = {"mask":aug.mask if mask is not None else None, "bboxes":aug.bboxes if bboxes is not None else None, "masks":aug.masks if masks is not None else None}
            
            # get the crop parameters and create the crop object
            crop_params = _get_crop_params(outer_bbox,aug.image)
            cropper = Crop(**crop_params)
            
            # perform the cropping
            aug = cropper(aug.image,**kwargs)
        return aug

    @classmethod
    @abstractmethod
    def visualise_target(cls,input: torch.Tensor, output: A, **kwargs) -> np.ndarray:
        raise NotImplementedError("visualise_target is not implemented")
    def view(self,**kwargs):
        mi = ImageScroller(auto_progress=True)
        window = self.__class__.__name__ + " Viewer"
        def loopfun(_: int, i: int):
            inps,target = self[i]
            img = self.visualise_target(inps,target,**kwargs)
            mi(window,img,ignore_backwards=False)
        with open_cv2_window(window):
            MouseInput.iterate(loopfun,range(0,len(self)))

class MaskDataset(BasicDataset[torch.Tensor]):
    def __init__(self, rootpath: Path, transform: Transform | None = None, ensure_factor: int | None = None, alpha_channel: bool = False, img_dir: Path | str | None = None, require_shape: tuple[int,int]|None = None) -> None:
        super().__init__(rootpath, transform, ensure_factor, alpha_channel, img_dir, require_masks=True, shape=require_shape)  
    def __getitem__(self, index: int):
        annotation = self.annotated_images[index]
        img_name = annotation.img_name
        image = np.array(Image.open(self.img_dir/img_name),dtype=np.uint8)
        if self.alpha_channel:
            assert image.shape[2] == 4
        else:
            image = image[:,:,:3]
        mask_names = annotation.mask_names
        if mask_names is None or len(mask_names)<1:
            raise Exception("Mask name is None or empty")
        mask = self._combine_masks(mask_names)
        if len(mask.shape)==3:
            mask = cv2.cvtColor(mask,cv2.COLOR_RGB2GRAY)


        augmentations = self.apply_transforms(image,annotation.outer_bbox,mask=mask)

        image = to_torch(normalise(augmentations.image))
        mask = to_torch(augmentations.mask)
        return image,mask
    def _combine_masks(self, mask_names: list[str]) -> np.ndarray:
        mask = np.array(Image.open(self.mask_dir/mask_names[0]),dtype=np.uint8)
        for i in range(1,len(mask_names)):
            next_mask = np.array(Image.open(self.mask_dir/mask_names[i]),dtype=np.uint8)
            mask = np.maximum(next_mask,mask,dtype=np.uint8)
        return mask
    @classmethod
    def visualise_target(cls, inp: torch.Tensor, target: torch.Tensor, alpha: float = 0.5, **kwargs):
        img = np.array(inp)
        while len(target.shape)<3:
            target = target.unsqueeze(0)
        mask = np.array(target)

        img = np.transpose(img,[1,2,0])
        mask = np.transpose(mask,[1,2,0])
        mask = np.repeat(mask,3,axis=2)
        idx = mask>0

        # Define the color to blend with (white in this case)
        blend_color = np.array([1.0, 0, 0])
        blend_mask = np.zeros_like(img)
        blend_mask[:] = blend_color
        # Create a copy of the image to overlay the mask
        image_with_transparency = img.copy()

        # Apply blending formula
        image_with_transparency[idx] = alpha*blend_mask[idx] + (1-alpha)*img[idx]
        bbox = get_bbox(mask,"coco")
        cv2.rectangle(image_with_transparency,bbox,(0,0,1),thickness=1)
        image_with_transparency = cv2.cvtColor(image_with_transparency,cv2.COLOR_RGB2BGR)
        return image_with_transparency

class BoxDataset(BasicDataset[torch.Tensor]):
    def __init__(self, rootpath: Path, transform: Transform | None = None, ensure_factor: int | None = None, alpha_channel: bool = False, img_dir: Path | str | None = None, require_shape: tuple[int,int]|None = None) -> None:
        super().__init__(rootpath, transform, ensure_factor, alpha_channel, img_dir, require_bboxes=True,bbox_format=BBOX_FORMAT, shape=require_shape)
    def __getitem__(self, index: int) -> tuple[torch.Tensor,torch.Tensor]:
        annotations = self.annotated_images[index]
        img_name = annotations.img_name
        image = np.array(Image.open(self.img_dir/img_name))
        bboxes = annotations.bboxes
        if bboxes is None:
            raise Exception("BBoxes is None")
        labels = annotations.labels
        if labels is None or len(labels) != len(bboxes):
            labels = [1]*len(bboxes)

        augmentations = self.apply_transforms(image,annotations.outer_bbox,bboxes=bboxes)
        bboxes = augmentations.bboxes
        image = augmentations.image

        image = to_torch(normalise(image))
        bbox = torch.Tensor(bbox).float()
        return image,bbox

class MaskRCNNDataset(BasicDataset[dict[str,torch.Tensor]]):
    def __init__(self, rootpath: Path | str, transform: Transform | None = None, ensure_factor: int | None = None, alpha_channel: bool = False, img_dir: Path | str | None = None, require_shape: tuple[int,int]|None = None) -> None:
        super().__init__(rootpath, transform, ensure_factor, alpha_channel, img_dir, require_masks=True, require_bboxes=True, require_ids=True, bbox_format=BBOX_FORMAT, shape=require_shape)
    def __getitem__(self, index: int):
        annotation = self.annotated_images[index]
        img_name = annotation.img_name
        image = np.array(Image.open(self.img_dir/img_name),dtype=np.uint8)
        if self.alpha_channel:
            assert image.shape[2] == 4
        else:
            image = image[:,:,:3]
        mask_names = annotation.mask_names
        if mask_names is None or len(mask_names)<1:
            raise Exception("Mask names are None empty")
        bboxes = annotation.bboxes
        if bboxes is None or len(bboxes)<1:
            raise Exception("BBoxes are None or empty")
        
        for bb in bboxes:
            bb = _coco_to_pascal_voc(bb)

        labels = annotation.labels
        if labels is None or len(labels)<1:
            raise Exception("Labels is None or Empty")
        assert len(bboxes) == len(mask_names)
        assert len(bboxes) == len(labels)

        masks = []
        for mask_name in mask_names:
            next_mask = np.array(Image.open(self.mask_dir/mask_name))
            masks.append(next_mask)

        bboxes = list(map(list,bboxes))
        augmentations = self.apply_transforms(image,annotation.outer_bbox,masks=masks,bboxes=bboxes)

        # augmentations = self.apply_transforms(image,None,masks=masks,bboxes=bboxes)


        image = to_torch(normalise(augmentations.image))
        masks = list(map(to_torch,augmentations.masks))
        masks = torch.stack(masks)
        bboxes = torch.Tensor(augmentations.bboxes)
        labels = torch.Tensor(labels)
        dict_out = {"masks":masks,"bboxes":bboxes,"labels":labels}
        return image,dict_out
    @classmethod
    def visualise_target(cls,img: torch.Tensor, targets: dict[str,torch.Tensor], alpha=0.5):
        def cycle(my_list: list, start_at=None):
            start_at = 0 if start_at is None else my_list.index(start_at)
            while True:
                yield my_list[start_at]
                start_at = (start_at + 1) % len(my_list)
        
        img: np.ndarray = np.array(img)
        img = np.transpose(img,[1,2,0])
        img = cv2.cvtColor(img,cv2.COLOR_RGB2BGR)
        masks = targets["masks"]
        colors = cycle([np.array([1,0,0]),np.array([0,1,0]),np.array([0,0,1])])
        bboxes = np.array(targets["bboxes"])
        big_mask = np.zeros((img.shape[0],img.shape[1],3),dtype=np.float64)
        for i,mask in enumerate(masks):
            mask = np.array(mask)
            mask = np.transpose(mask,[1,2,0])
            mask = np.repeat(mask,3,axis=2)
            idx = mask>0
            next_color = next(colors)
            blend = np.zeros_like(mask)
            blend[:]=next_color
            mask[idx] = blend[idx]
            big_mask += mask
            #TODO make independent of bbox type
            try:
                pt1 = (int(bboxes[i][0]),int(bboxes[i][1]))
                pt2 = (int(bboxes[i][2]),int(bboxes[i][3]))
                img = cv2.rectangle(img,pt1,pt2,tuple([int(x) for x in next_color]),thickness=1)
            except IndexError:
                pass
        idx = big_mask>0
        blend = np.zeros_like(img)
        image_with_transparency = img.copy()
        image_with_transparency[idx] = alpha*big_mask[idx] + (1-alpha)*img[idx]
        return image_with_transparency

def main():
    print("Done labelling, displaying results")
    ds = MaskDataset("320x320")
    ds.view()

if __name__ == "__main__":

    # dh = DatasetHandler()
    # dh.add_outer_boxes("fluid_polygons.json",(320,320),"320x320")
    print("Done labelling, displaying results")
    ds = MaskDataset("320x320")
    ds.view()
    # files = [file for file in os.listdir(ORIGINAL_IMAGES) if file[-4:]==".png"]
    # with open(ORIGINAL_DIR/"labelled_images.csv","r",newline="") as f:
    #     csv_info = [row for row in csv.reader(f)]
    # with open(ORIGINAL_DIR/"labelled_images_2","a+",newline="") as f:
    #     writer = csv.writer(f)
    #     for row in csv_info:
    #         filename = row[0]
    #         img = np.array(Image.open(ORIGINAL_IMAGES/filename))
    #         mask = np.zeros(img.shape,dtype=np.uint8)
    #         box1 = get_slice_from_bbox(tuple(map(int,row[5:9])))
    #         box2 = get_slice_from_bbox(tuple(map(int,row[13:])))
    #         mask[box1[0],box1[1]] = 1
    #         mask[box2[0],box2[1]] = 1
    #         maskname = "mask"+filename.lstrip("img")
    #         Image.fromarray(mask).save(ORIGINAL_DIR/"Masks"/maskname)
    #         writer.writerow([filename,maskname])
    