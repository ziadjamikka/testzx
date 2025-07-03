import numpy as np
import cv2
from typing import Dict, List
from collections import OrderedDict
import sys

from utils.registry import Registry
from utils.textblock_mask import extract_ballon_mask
from utils.imgproc_utils import enlarge_window

from ..base import BaseModule, DEFAULT_DEVICE, gc_collect, DEVICE_SELECTOR, GPUINTENSIVE_SET, TORCH_DTYPE_MAP
from ..textdetector import TextBlock

INPAINTERS = Registry('inpainters')
register_inpainter = INPAINTERS.register_module


class InpainterBase(BaseModule):

    inpaint_by_block = True
    check_need_inpaint = True

    _postprocess_hooks = OrderedDict()
    _preprocess_hooks = OrderedDict()

    def __init__(self, **params) -> None:
        super().__init__(**params)
        self.name = ''
        for key in INPAINTERS.module_dict:
            if INPAINTERS.module_dict[key] == self.__class__:
                self.name = key
                break
        self.setup_inpainter()

    def setup_inpainter(self):
        raise NotImplementedError
    
    def memory_safe_inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:
        '''
        handle cuda out of memory
        '''
        try:
            return self._inpaint(img, mask, textblock_list)
        except Exception as e:
            if DEFAULT_DEVICE == 'cuda' and isinstance(e, torch.cuda.OutOfMemoryError):
                gc_collect()
                try:
                    return self._inpaint(img, mask, textblock_list)
                except Exception as ee:
                    if isinstance(ee, torch.cuda.OutOfMemoryError):
                        self.logger.warning(f'CUDA out of memory while calling {self.name}, fall back to cpu...\n\
                                            if running into it frequently, consider lowering the inpaint_size')
                        self.moveToDevice('cpu')
                        inpainted = self._inpaint(img, mask, textblock_list)
                        precision = None
                        if hasattr(self, 'precision'):
                            precision = self.precision
                        self.moveToDevice('cuda', precision)

                        return inpainted
            else:
                raise e

    def inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None, check_need_inpaint: bool = False) -> np.ndarray:
        if not self.inpaint_by_block or textblock_list is None:
            if check_need_inpaint:
                ballon_msk, non_text_msk = extract_ballon_mask(img, mask)
                if ballon_msk is not None:
                    non_text_region = np.where(non_text_msk > 0)
                    non_text_px = img[non_text_region]
                    average_bg_color = np.mean(non_text_px, axis=0)
                    std_bgr = np.std(non_text_px - average_bg_color, axis=0)
                    std_max = np.max(std_bgr)
                    inpaint_thresh = 7 if np.std(std_bgr) > 1 else 10
                    if std_max < inpaint_thresh:
                        img = img.copy()
                        img[np.where(ballon_msk > 0)] = average_bg_color
                        return img
            return self.memory_safe_inpaint(img, mask, textblock_list)
        else:
            im_h, im_w = img.shape[:2]
            inpainted = np.copy(img)
            for blk in textblock_list:
                xyxy = blk.xyxy
                xyxy_e = enlarge_window(xyxy, im_w, im_h, ratio=1.7)
                im = inpainted[xyxy_e[1]:xyxy_e[3], xyxy_e[0]:xyxy_e[2]]
                msk = mask[xyxy_e[1]:xyxy_e[3], xyxy_e[0]:xyxy_e[2]]
                need_inpaint = True
                if self.check_need_inpaint or check_need_inpaint:
                    ballon_msk, non_text_msk = extract_ballon_mask(im, msk)
                    if ballon_msk is not None:
                        non_text_region = np.where(non_text_msk > 0)
                        non_text_px = im[non_text_region]
                        average_bg_color = np.mean(non_text_px, axis=0)
                        std_bgr = np.std(non_text_px - average_bg_color, axis=0)
                        std_max = np.max(std_bgr)
                        inpaint_thresh = 7 if np.std(std_bgr) > 1 else 10
                        if std_max < inpaint_thresh:
                            need_inpaint = False
                            im[np.where(ballon_msk > 0)] = average_bg_color
                        # cv2.imshow('im', im)
                        # cv2.imshow('ballon', ballon_msk)
                        # cv2.imshow('non_text', non_text_msk)
                        # cv2.waitKey(0)
                
                if need_inpaint:
                    inpainted[xyxy_e[1]:xyxy_e[3], xyxy_e[0]:xyxy_e[2]] = self.memory_safe_inpaint(im, msk)

                mask[xyxy[1]:xyxy[3], xyxy[0]:xyxy[2]] = 0
            return inpainted

    def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:
        raise NotImplementedError
    
    def moveToDevice(self, device: str, precision: str = None):
        raise not NotImplementedError


@register_inpainter('opencv-tela')
class OpenCVInpainter(InpainterBase):

    def setup_inpainter(self):
        self.inpaint_method = lambda img, mask, *args, **kwargs: cv2.inpaint(img, mask, 3, cv2.INPAINT_NS)
    
    def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:
        return self.inpaint_method(img, mask)

    def is_computational_intensive(self) -> bool:
        return True
    
    def is_cpu_intensive(self) -> bool:
        return True


@register_inpainter('patchmatch')
class PatchmatchInpainter(InpainterBase):

    if sys.platform == 'darwin':
        download_file_list = [{
                'url': 'https://github.com/dmMaze/PyPatchMatchInpaint/releases/download/v1.0/macos_arm64_patchmatch_libs.7z',
                'sha256_pre_calculated': ['843704ab096d3afd8709abe2a2c525ce3a836bb0a629ed1ee9b8f5cee9938310', '849ca84759385d410c9587d69690e668822a3fc376ce2219e583e7e0be5b5e9a'],
                'files': ['macos_libopencv_world.4.8.0.dylib', 'macos_libpatchmatch_inpaint.dylib'],
                'save_dir': 'data/libs',
                'archived_files': 'macos_patchmatch_libs.7z',
                'archive_sha256_pre_calculated': '9f332c888be0f160dbe9f6d6887eb698a302e62f4c102a0f24359c540d5858ea'
        }]
    elif sys.platform == 'win32':
        download_file_list = [{
                'url': 'https://github.com/dmMaze/PyPatchMatchInpaint/releases/download/v1.0/windows_patchmatch_libs.7z',
                'sha256_pre_calculated': ['3b7619caa29dc3352b939de4e9981217a9585a13a756e1101a50c90c100acd8d', '0ba60cfe664c97629daa7e4d05c0888ebfe3edcb3feaf1ed5a14544079c6d7af'],
                'files': ['opencv_world455.dll', 'patchmatch_inpaint.dll'],
                'save_dir': 'data/libs',
                'archived_files': 'windows_patchmatch_libs.7z',
                'archive_sha256_pre_calculated': 'c991ff61f7cb3efaf8e75d957e62d56ba646083bc25535f913ac65775c16ca65'
        }]

    def setup_inpainter(self):
        from . import patch_match
        self.inpaint_method = lambda img, mask, *args, **kwargs: patch_match.inpaint(img, mask, patch_size=3)
    
    def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:
        return self.inpaint_method(img, mask)

    def is_computational_intensive(self) -> bool:
        return True
    
    def is_cpu_intensive(self) -> bool:
        return True


import torch
from utils.imgproc_utils import resize_keepasp
from .aot import AOTGenerator, load_aot_model
AOTMODEL: AOTGenerator = None
AOTMODEL_PATH = 'data/models/aot_inpainter.ckpt'


@register_inpainter('aot')
class AOTInpainter(InpainterBase):

    params = {
        'inpaint_size': {
            'type': 'selector',
            'options': [
                1024, 
                2048
            ], 
            'select': 2048
        }, 
        'device': DEVICE_SELECTOR(),
        'description': 'manga-image-translator inpainter'
    }

    device = DEFAULT_DEVICE
    inpaint_size = 2048
    model: AOTGenerator = None

    download_file_list = [{
            'url': 'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/inpainting.ckpt',
            'sha256_pre_calculated': '878d541c68648969bc1b042a6e997f3a58e49b6c07c5636ad55130736977149f',
            'files': 'data/models/aot_inpainter.ckpt',
    }]

    def setup_inpainter(self):
        global AOTMODEL
        self.device = self.params['device']['select']
        if AOTMODEL is None:
            self.model = AOTMODEL = load_aot_model(AOTMODEL_PATH, self.device)
        else:
            self.model = AOTMODEL
            self.model.to(self.device)
        self.inpaint_size = int(self.params['inpaint_size']['select'])

    def moveToDevice(self, device: str, precision: str = None):
        self.model.to(device)
        self.device = device

    def inpaint_preprocess(self, img: np.ndarray, mask: np.ndarray) -> np.ndarray:

        img_original = np.copy(img)
        mask_original = np.copy(mask)
        mask_original[mask_original < 127] = 0
        mask_original[mask_original >= 127] = 1
        mask_original = mask_original[:, :, None]

        new_shape = self.inpaint_size if max(img.shape[0: 2]) > self.inpaint_size else None

        img = resize_keepasp(img, new_shape, stride=None)
        mask = resize_keepasp(mask, new_shape, stride=None)

        im_h, im_w = img.shape[:2]
        pad_bottom = 128 - im_h if im_h < 128 else 0
        pad_right = 128 - im_w if im_w < 128 else 0
        mask = cv2.copyMakeBorder(mask, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT)
        img = cv2.copyMakeBorder(img, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT)

        img_torch = torch.from_numpy(img).permute(2, 0, 1).unsqueeze_(0).float() / 127.5 - 1.0
        mask_torch = torch.from_numpy(mask).unsqueeze_(0).unsqueeze_(0).float() / 255.0
        mask_torch[mask_torch < 0.5] = 0
        mask_torch[mask_torch >= 0.5] = 1

        if self.device != 'cpu':
            img_torch = img_torch.to(self.device)
            mask_torch = mask_torch.to(self.device)
        img_torch *= (1 - mask_torch)
        return img_torch, mask_torch, img_original, mask_original, pad_bottom, pad_right

    @torch.no_grad()
    def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:

        im_h, im_w = img.shape[:2]
        img_torch, mask_torch, img_original, mask_original, pad_bottom, pad_right = self.inpaint_preprocess(img, mask)
        img_inpainted_torch = self.model(img_torch, mask_torch)
        img_inpainted = ((img_inpainted_torch.cpu().squeeze_(0).permute(1, 2, 0).numpy() + 1.0) * 127.5).astype(np.uint8)
        if pad_bottom > 0:
            img_inpainted = img_inpainted[:-pad_bottom]
        if pad_right > 0:
            img_inpainted = img_inpainted[:, :-pad_right]
        new_shape = img_inpainted.shape[:2]
        if new_shape[0] != im_h or new_shape[1] != im_w :
            img_inpainted = cv2.resize(img_inpainted, (im_w, im_h), interpolation = cv2.INTER_LINEAR)
        img_inpainted = img_inpainted * mask_original + img_original * (1 - mask_original)
        
        return img_inpainted

    def updateParam(self, param_key: str, param_content):
        super().updateParam(param_key, param_content)

        if param_key == 'device':
            param_device = self.params['device']['select']
            self.model.to(param_device)
            self.device = param_device

        elif param_key == 'inpaint_size':
            self.inpaint_size = int(self.params['inpaint_size']['select'])


from .lama import LamaFourier, load_lama_mpe

LAMA_MPE: LamaFourier = None
@register_inpainter('lama_mpe')
class LamaInpainterMPE(InpainterBase):

    params = {
        'inpaint_size': {
            'type': 'selector',
            'options': [
                1024, 
                2048
            ], 
            'select': 2048
        }, 
        'device': DEVICE_SELECTOR()
    }
    precision = 'fp32'

    device = DEFAULT_DEVICE
    inpaint_size = 2048

    download_file_list = [{
            'url': 'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/inpainting_lama_mpe.ckpt',
            'sha256_pre_calculated': 'd625aa1b3e0d0408acfd6928aa84f005867aa8dbb9162480346a4e20660786cc',
            'files': 'data/models/lama_mpe.ckpt',
    }]

    def setup_inpainter(self):
        global LAMA_MPE

        self.device = self.params['device']['select']
        if LAMA_MPE is None:
            self.model = LAMA_MPE = load_lama_mpe(r'data/models/lama_mpe.ckpt', self.device)
        else:
            self.model = LAMA_MPE
            self.model.to(self.device)
        self.inpaint_size = int(self.params['inpaint_size']['select'])

    def inpaint_preprocess(self, img: np.ndarray, mask: np.ndarray) -> np.ndarray:

        img_original = np.copy(img)
        mask_original = np.copy(mask)
        mask_original[mask_original < 127] = 0
        mask_original[mask_original >= 127] = 1
        mask_original = mask_original[:, :, None]

        new_shape = self.inpaint_size if max(img.shape[0: 2]) > self.inpaint_size else None
        # high resolution input could produce cloudy artifacts
        img = resize_keepasp(img, new_shape, stride=64)
        mask = resize_keepasp(mask, new_shape, stride=64)

        im_h, im_w = img.shape[:2]
        longer = max(im_h, im_w)
        pad_bottom = longer - im_h if im_h < longer else 0
        pad_right = longer - im_w if im_w < longer else 0
        mask = cv2.copyMakeBorder(mask, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT)
        img = cv2.copyMakeBorder(img, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT)

        img_torch = torch.from_numpy(img).permute(2, 0, 1).unsqueeze_(0).float() / 255.0
        mask_torch = torch.from_numpy(mask).unsqueeze_(0).unsqueeze_(0).float() / 255.0
        mask_torch[mask_torch < 0.5] = 0
        mask_torch[mask_torch >= 0.5] = 1
        rel_pos, _, direct = self.model.load_masked_position_encoding(mask_torch[0][0].numpy())
        rel_pos = torch.LongTensor(rel_pos).unsqueeze_(0)
        direct = torch.LongTensor(direct).unsqueeze_(0)

        if self.device != 'cpu':
            img_torch = img_torch.to(self.device)
            mask_torch = mask_torch.to(self.device)
            rel_pos = rel_pos.to(self.device)
            direct = direct.to(self.device)
        img_torch *= (1 - mask_torch)
        return img_torch, mask_torch, rel_pos, direct, img_original, mask_original, pad_bottom, pad_right

    @torch.no_grad()
    def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:

        im_h, im_w = img.shape[:2]
        img_torch, mask_torch, rel_pos, direct, img_original, mask_original, pad_bottom, pad_right = self.inpaint_preprocess(img, mask)
        
        precision = TORCH_DTYPE_MAP[self.precision]
        if self.device in {'cuda'}:
            try:
                with torch.autocast(device_type=self.device, dtype=precision):
                    img_inpainted_torch = self.model(img_torch, mask_torch, rel_pos, direct)
            except Exception as e:
                self.logger.error(e)
                self.logger.error(f'{precision} inference is not supported for this device, use fp32 instead.')
                img_inpainted_torch = self.model(img_torch, mask_torch, rel_pos, direct)
        else:
            img_inpainted_torch = self.model(img_torch, mask_torch, rel_pos, direct)

        img_inpainted = (img_inpainted_torch.to(device='cpu', dtype=torch.float32).squeeze_(0).permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        if pad_bottom > 0:
            img_inpainted = img_inpainted[:-pad_bottom]
        if pad_right > 0:
            img_inpainted = img_inpainted[:, :-pad_right]
        new_shape = img_inpainted.shape[:2]
        if new_shape[0] != im_h or new_shape[1] != im_w :
            img_inpainted = cv2.resize(img_inpainted, (im_w, im_h), interpolation = cv2.INTER_LINEAR)
        img_inpainted = img_inpainted * mask_original + img_original * (1 - mask_original)
        
        return img_inpainted

    def updateParam(self, param_key: str, param_content):
        super().updateParam(param_key, param_content)

        if param_key == 'device':
            param_device = self.params['device']['select']
            
            # Check if the device is actually available
            if param_device == 'cuda' and not torch.cuda.is_available():
                param_device = 'cpu'
                self.logger.warning('CUDA not available, falling back to CPU')
            elif param_device == 'mps' and not torch.backends.mps.is_available():
                param_device = 'cpu'
                self.logger.warning('MPS not available, falling back to CPU')
                
            self.model.to(param_device)
            self.device = param_device

        elif param_key == 'inpaint_size':
            self.inpaint_size = int(self.params['inpaint_size']['select'])

        elif param_key == 'precision':
            precision = self.params['precision']['select']
            self.precision = precision

    def moveToDevice(self, device: str, precision: str = None):
        try:
            # Check if the device is actually available
            if device == 'cuda' and not torch.cuda.is_available():
                device = 'cpu'
                self.logger.warning('CUDA not available, falling back to CPU')
            elif device == 'mps' and not torch.backends.mps.is_available():
                device = 'cpu'
                self.logger.warning('MPS not available, falling back to CPU')
            self.model.to(device)
            self.device = device
            if precision is not None:
                self.precision = precision
        except Exception as e:
            self.logger.warning(f'Failed to load model to {device}, falling back to CPU: {e}')
            self.model.to('cpu')
            self.device = 'cpu'
            if precision is not None:
                self.precision = 'fp32'  # Use fp32 for CPU

LAMA_LARGE: LamaFourier = None
@register_inpainter('lama_large_512px')
class LamaLarge(LamaInpainterMPE):

    params = {
        'inpaint_size': {
            'type': 'selector',
            'options': [
                512,
                768,
                1024,
                1536, 
                2048
            ], 
            'select': 1536,
        }, 
        'device': DEVICE_SELECTOR(),
        'precision': {
            'type': 'selector',
            'options': [
                'fp32',
                'bf16'
            ], 
            'select': 'bf16' if DEFAULT_DEVICE == 'cuda' else 'fp32'
        }, 
    }

    download_file_list = [{
            'url': 'https://huggingface.co/dreMaz/AnimeMangaInpainting/resolve/main/lama_large_512px.ckpt',
            'sha256_pre_calculated': '11d30fbb3000fb2eceae318b75d9ced9229d99ae990a7f8b3ac35c8d31f2c935',
            'files': 'data/models/lama_large_512px.ckpt',
    }]

    device = DEFAULT_DEVICE
    inpaint_size = 1024

    def setup_inpainter(self):
        global LAMA_LARGE

        device = self.params['device']['select']
        self.inpaint_size = int(self.params['inpaint_size']['select'])
        precision = self.params['precision']['select']

        # Check if the device is actually available
        if device == 'cuda' and not torch.cuda.is_available():
            device = 'cpu'
            self.logger.warning('CUDA not available, falling back to CPU')
        elif device == 'mps' and not torch.backends.mps.is_available():
            device = 'cpu'
            self.logger.warning('MPS not available, falling back to CPU')

        if LAMA_LARGE is None:
            self.model = LAMA_LARGE = load_lama_mpe(r'data/models/lama_large_512px.ckpt', device='cpu', use_mpe=False, large_arch=True)
        else:
            self.model = LAMA_LARGE
        self.moveToDevice(device, precision=precision)


# LAMA_ORI: LamaFourier = None
# @register_inpainter('lama_ori')
# class LamaInpainterORI(InpainterBase):

#     params = {
#         'inpaint_size': {
#             'type': 'selector',
#             'options': [
#                 1024, 
#                 2048
#             ], 
#             'select': 2048
#         }, 
#         'device': {
#             'type': 'selector',
#             'options': [
#                 'cpu',
#                 'cuda'
#             ],
#             'select': DEFAULT_DEVICE
#         }
#     }

#     device = DEFAULT_DEVICE
#     inpaint_size = 2048

#     def setup_inpainter(self):
#         global LAMA_ORI

#         self.device = self.params['device']['select']
#         if LAMA_ORI is None:
#             self.model = LAMA_ORI = load_lama_mpe(r'data/models/lama_org.ckpt', self.device, False)
#         else:
#             self.model = LAMA_ORI
#             self.model.to(self.device)
#         self.inpaint_by_block = True if self.device == 'cuda' else False
#         self.inpaint_size = int(self.params['inpaint_size']['select'])

#     def inpaint_preprocess(self, img: np.ndarray, mask: np.ndarray) -> np.ndarray:

#         img_original = np.copy(img)
#         mask_original = np.copy(mask)
#         mask_original[mask_original < 127] = 0
#         mask_original[mask_original >= 127] = 1
#         mask_original = mask_original[:, :, None]

#         new_shape = self.inpaint_size if max(img.shape[0: 2]) > self.inpaint_size else None
#         # high resolution input could produce cloudy artifacts
#         img = resize_keepasp(img, new_shape, stride=64)
#         mask = resize_keepasp(mask, new_shape, stride=64)

#         im_h, im_w = img.shape[:2]
#         longer = max(im_h, im_w)
#         pad_bottom = longer - im_h if im_h < longer else 0
#         pad_right = longer - im_w if im_w < longer else 0
#         mask = cv2.copyMakeBorder(mask, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT)
#         img = cv2.copyMakeBorder(img, 0, pad_bottom, 0, pad_right, cv2.BORDER_REFLECT)

#         img_torch = torch.from_numpy(img).permute(2, 0, 1).unsqueeze_(0).float() / 255.0
#         mask_torch = torch.from_numpy(mask).unsqueeze_(0).unsqueeze_(0).float() / 255.0
#         mask_torch[mask_torch < 0.5] = 0
#         mask_torch[mask_torch >= 0.5] = 1
#         rel_pos, _, direct = self.model.load_masked_position_encoding(mask_torch[0][0].numpy())
#         rel_pos = torch.LongTensor(rel_pos).unsqueeze_(0)
#         direct = torch.LongTensor(direct).unsqueeze_(0)

#         if self.device == 'cuda':
#             img_torch = img_torch.cuda()
#             mask_torch = mask_torch.cuda()
#             rel_pos = rel_pos.cuda()
#             direct = direct.cuda()
#         img_torch *= (1 - mask_torch)
#         return img_torch, mask_torch, rel_pos, direct, img_original, mask_original, pad_bottom, pad_right

#     @torch.no_grad()
#     def _inpaint(self, img: np.ndarray, mask: np.ndarray, textblock_list: List[TextBlock] = None) -> np.ndarray:

#         im_h, im_w = img.shape[:2]
#         img_torch, mask_torch, rel_pos, direct, img_original, mask_original, pad_bottom, pad_right = self.inpaint_preprocess(img, mask)
#         img_inpainted_torch = self.model(img_torch, mask_torch, rel_pos, direct)
        
#         img_inpainted = (img_inpainted_torch.cpu().squeeze_(0).permute(1, 2, 0).numpy() * 255).astype(np.uint8)
#         if pad_bottom > 0:
#             img_inpainted = img_inpainted[:-pad_bottom]
#         if pad_right > 0:
#             img_inpainted = img_inpainted[:, :-pad_right]
#         new_shape = img_inpainted.shape[:2]
#         if new_shape[0] != im_h or new_shape[1] != im_w :
#             img_inpainted = cv2.resize(img_inpainted, (im_w, im_h), interpolation = cv2.INTER_LINEAR)
#         img_inpainted = img_inpainted * mask_original + img_original * (1 - mask_original)
        
#         return img_inpainted

#     def updateParam(self, param_key: str, param_content):
#         super().updateParam(param_key, param_content)

#         if param_key == 'device':
#             param_device = self.params['device']['select']
#             self.model.to(param_device)
#             self.device = param_device
#             if param_device == 'cuda':
#                 self.inpaint_by_block = False
#             else:
#                 self.inpaint_by_block = True

#         elif param_key == 'inpaint_size':
#             self.inpaint_size = int(self.params['inpaint_size']['select'])