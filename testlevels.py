from typing import Callable
import cv2
import math
import numpy as np
import copy
from support_classes.camera_interface import PygameCapture, capture, open_cv2_window
from support_classes.settings_interface import CaptureBackend
from pump_control.async_levelsensor import _get_indices, _filter, _draw_level

def morph_erode_1d(img: list[int], window_size: int = 11):
    if window_size % 2 == 0:
        raise ValueError("Even kernel size supplied to morph close")
    size_in = len(img)
    imid = math.floor(window_size/2)
    padded_data = [255]*imid + img + [0]*imid
    thresh_out = [0]*size_in

    for i in range(0,size_in):
        window = padded_data[i:i+window_size]
        set_to_full = False
        for j in range(0,window_size):
            if window[j] > 0:
                set_to_full = True
        thresh_out[i] = 255 if set_to_full else img[i]
    return thresh_out

def morph_dilate_1d(img: list[int], window_size: int = 11):
    if window_size % 2 == 0:
        raise ValueError("Even kernel size supplied to morph close")
    size_in = len(img)
    imid = math.floor(window_size/2)
    padded_data = [255]*imid + img + [0]*imid
    thresh_out = [0]*size_in
    for i in range(0,size_in):
        window = padded_data[i:i+window_size]
        set_to_zero = False
        for j in range(0,window_size):
            if window[j] == 0:
                set_to_zero = True
        thresh_out[i] = 0 if set_to_zero else img[i]
    return thresh_out

def adaptive_y_threshold(avg_list: list[int], window_size: int = 11, C: int = 0):
    if window_size % 2 == 0:
        raise ValueError("Even kernel size supplied to adaptive threshold")
    imid = math.floor(window_size/2)
    size_in = len(avg_list)
    thresh_out = [0]*size_in
    for i in range(0,size_in):
        vals_in_window = [0] * window_size
        minimum_index = i-imid
        maximum_index = i+imid


        minimum_window_index = 0
        if minimum_index < 0:
            minimum_window_index = -minimum_index
            vals_in_window[0:minimum_window_index] = [avg_list[0]]*minimum_window_index


        maximum_window_index = window_size -1
        if maximum_index > size_in -1:
            maximum_window_index = maximum_index - (size_in-1)
            vals_in_window[maximum_window_index:-1] = [avg_list[-1]]*(window_size-1-maximum_window_index)

        for jnormal in range (minimum_window_index,maximum_window_index):
            mainindex = i - imid + jnormal -1
            try:
                vals_in_window[jnormal] = avg_list[mainindex]
            except:
                print(mainindex)
                pass
        window_thresh = np.mean(vals_in_window) - C
        thresh_out[i] = 0 if avg_list[i] < window_thresh else 255
    return thresh_out

def select_final(thresh_in: list[int]):
    size_in = len(thresh_in)
    left = 0
    right = 0
    for i in range(0,size_in):
        if thresh_in[i] == 0:
            right = i
        else:
            left = i
    if right>left:
        left +=1
        thresh_in[0:left] = [255]*left
        thresh_in[left:right+1] = [0]*(right+1-left)
    return thresh_in

def meanrows(frame_in: np.ndarray,weightfun: Callable[[int],float]) -> list[int]:
    # Generate weights
    frame_in = frame_in/255
    weights = np.zeros(frame_in.shape)
    for rownum in range(0,frame_in.shape[0]):
        for colnum in range(0,frame_in.shape[1]):
            weights[rownum,colnum] = weightfun(frame_in[rownum,colnum])
   
   # Apply weighted mean to each row
    frm_rows,frm_cols = frame_in.shape
    vals_out = [0]*frm_rows
    for rownum in range(0,frm_rows):
        
        numerator = np.sum(np.multiply(weights[rownum,:],frame_in[rownum,:]))
        denominator = np.sum(weights[rownum,:])
        vals_out[rownum] = numerator/denominator * 255
    return vals_out

class Function:
    def __init__(self,*parameters,**optional_parameters):
        pass

    def solve(self,x: int) -> float:
        pass

class PowerFunction(Function):
    def __init__(self,power: float,*args,maxval: int = 255,**kwargs):
        super().__init__(*args,**kwargs)
        self.power = power
        self.maxval = maxval

    def solve(self,x: int) -> float:
        return (x/self.maxval)**self.power

def main():
    backend = CaptureBackend.PYGAME_WINDOWS_NATIVE
    camera = 1
    capture_instance = PygameCapture(camera,backend=backend,scale_factor=1.5)
    capture_instance.open()
    power_function = PowerFunction(0)
    inp = 0
    with open_cv2_window("Window") as wind:
        while inp != ord('a'):
            img_small = capture_instance.get_image()
            original_img = copy.copy(img_small)
            img = np.concatenate((img_small,original_img),axis=1)
            roi = cv2.selectROI(wind,img)
            roi_slice = _get_indices(roi)
            frame_1 = img[roi_slice[0],roi_slice[1],:]
            frame = copy.copy(frame_1[:,:,1])
            frm_height, frm_width = np.shape(frame)
            # frame: np.ndarray = cv2.cvtColor(frame_1,cv2.COLOR_BGR2GRAY)

            avg_brightness = meanrows(frame,power_function.solve)

            for rownumber in range(0,frm_height):
                frame[rownumber,:] = avg_brightness[rownumber]
            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)
            img[roi_slice[0],roi_slice[1]] = frame
            cv2.imshow(wind,img)
            cv2.waitKey()

            kernel_size = int(math.floor(frm_height/4))
            kernel_size += kernel_size % 2 -1

            thresh_rows = adaptive_y_threshold(avg_brightness,window_size=kernel_size,C=-3)

            for rownumber in range(0,frm_height):
                frame[rownumber,:] = thresh_rows[rownumber]
            img[roi_slice[0],roi_slice[1]] = frame
            cv2.imshow(wind,img)
            cv2.waitKey()

            thresh_rows = morph_erode_1d(thresh_rows,kernel_size)
            frame: np.ndarray = cv2.cvtColor(frame_1,cv2.COLOR_BGR2GRAY)
            for rownumber in range(0,frm_height):
                frame[rownumber,:] = thresh_rows[rownumber]
            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)
            img[roi_slice[0],roi_slice[1]] = frame
            cv2.imshow(wind,img)
            cv2.waitKey()

            thresh_rows = morph_dilate_1d(thresh_rows,kernel_size)
            frame: np.ndarray = cv2.cvtColor(frame_1,cv2.COLOR_BGR2GRAY)
            for rownumber in range(0,frm_height):
                frame[rownumber,:] = thresh_rows[rownumber]
            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)

            kernel_size = int(math.floor(frm_height/8))
            kernel_size += kernel_size % 2 -1

            thresh_rows = morph_erode_1d(thresh_rows,kernel_size)
            frame: np.ndarray = cv2.cvtColor(frame_1,cv2.COLOR_BGR2GRAY)
            for rownumber in range(0,frm_height):
                frame[rownumber,:] = thresh_rows[rownumber]
            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)
            img[roi_slice[0],roi_slice[1]] = frame
            cv2.imshow(wind,img)
            cv2.waitKey()

            thresh_rows = morph_dilate_1d(thresh_rows,kernel_size)
            frame: np.ndarray = cv2.cvtColor(frame_1,cv2.COLOR_BGR2GRAY)
            for rownumber in range(0,frm_height):
                frame[rownumber,:] = thresh_rows[rownumber]
            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)



            img[roi_slice[0],roi_slice[1]] = frame
            cv2.imshow(wind,img)
            inp = cv2.waitKey()

            thresh_rows = select_final(thresh_rows)


            frame: np.ndarray = cv2.cvtColor(frame_1,cv2.COLOR_BGR2GRAY)
            for rownumber in range(0,frm_height):
                frame[rownumber,:] = thresh_rows[rownumber]

            npixels = 0
            for i in range(0,len(thresh_rows)):
                if thresh_rows[i] == 0: 
                    npixels+=1
            _draw_level(original_img[roi_slice[0],roi_slice[1]],npixels)

            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2BGR)
            img_small[roi_slice[0],roi_slice[1]] = frame
            img = np.concatenate((img_small,original_img),axis=1)
            cv2.imshow(wind,img)
            inp = cv2.waitKey()
    capture_instance.close()

            

if __name__ == "__main__":
    main()

