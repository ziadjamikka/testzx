# from https://github.com/zyddnys/manga-image-translator/blob/main/manga_translator/ocr/model_48px.py
# Roformer with Xpos and Local Attention ViT

import math
from typing import Callable, List, Optional, Tuple, Union
from collections import defaultdict
import os
import shutil
import cv2
import numpy as np
import einops

import torch
import torch.nn as nn
import torch.nn.functional as F

from .mit48px_ctc import AvgMeter, chunks, TextBlock


def fixed_pos_embedding(x):
    seq_len, dim = x.shape
    inv_freq = 1.0 / (10000 ** (torch.arange(0, dim) / dim))
    sinusoid_inp = (
        torch.einsum("i , j -> i j", torch.arange(0, seq_len, dtype=torch.float), inv_freq).to(x)
    )
    return torch.sin(sinusoid_inp), torch.cos(sinusoid_inp)

def rotate_every_two(x):
    x1 = x[:, :, ::2]
    x2 = x[:, :, 1::2]
    x = torch.stack((-x2, x1), dim=-1)
    return x.flatten(-2)  # in einsum notation: rearrange(x, '... d j -> ... (d j)')\

def duplicate_interleave(m):
    """
    A simple version of `torch.repeat_interleave` for duplicating a matrix while interleaving the copy.
    """
    dim0 = m.shape[0]
    m = m.view(-1, 1)  # flatten the matrix
    m = m.repeat(1, 2)  # repeat all elements into the 2nd dimension
    m = m.view(dim0, -1)  # reshape into a matrix, interleaving the copy
    return m

def apply_rotary_pos_emb(x, sin, cos, scale=1):
    sin, cos = map(lambda t: duplicate_interleave(t * scale), (sin, cos))
    # einsum notation for lambda t: repeat(t[offset:x.shape[1]+offset,:], "n d -> () n () (d j)", j=2)
    return (x * cos) + (rotate_every_two(x) * sin)

def apply_rotary_pos_emb2d(x, sin, cos, scale=1):
    breakpoint()
    sin, cos = map(lambda t: duplicate_interleave(t * scale), (sin, cos))
    # einsum notation for lambda t: repeat(t[offset:x.shape[1]+offset,:], "n d -> () n () (d j)", j=2)
    return (x * cos) + (rotate_every_two(x) * sin)

class XPOS(nn.Module):
    def __init__(
        self, head_dim, scale_base=512
    ):
        super().__init__()
        self.head_dim = head_dim
        self.scale_base = scale_base
        self.register_buffer(
            "scale", (torch.arange(0, head_dim, 2) + 0.4 * head_dim) / (1.4 * head_dim)
        )

    def forward(self, x, offset=0, downscale=False):
        length = x.shape[1]
        min_pos = -(length + offset) // 2
        max_pos = length + offset + min_pos
        scale = self.scale ** torch.arange(min_pos, max_pos, 1).to(self.scale).div(self.scale_base)[:, None]
        sin, cos = fixed_pos_embedding(scale)

        if scale.shape[0] > length:
            scale = scale[-length:]
            sin = sin[-length:]
            cos = cos[-length:]
        
        if downscale:
            scale = 1 / scale

        x = apply_rotary_pos_emb(x, sin, cos, scale)
        return x


class XPOS2D(nn.Module):
    def __init__(
        self, head_dim, scale_base=512
    ):
        super().__init__()
        self.xpos = XPOS(head_dim // 2, scale_base)

    def forward(self, x: torch.Tensor, offset_x = 0, offset_y = 0, downscale=False):
        """
            x: N, H, W, C
        """
        N, H, W, C = x.shape
        C = C // 2
        [dir_x, dir_y] = x.chunk(2, dim = 3)
        dir_x = einops.rearrange(dir_x, 'N H W C -> (N H) W C', N = N, H = H, W = W, C = C)
        dir_y = einops.rearrange(dir_y, 'N H W C -> (N W) H C', N = N, H = H, W = W, C = C)
        dir_x = self.xpos(dir_x, offset = offset_x, downscale = downscale)
        dir_y = self.xpos(dir_y, offset = offset_y, downscale = downscale)
        dir_x = einops.rearrange(dir_x, '(N H) W C -> N H W C', N = N, H = H, W = W, C = C)
        dir_y = einops.rearrange(dir_y, '(N W) H C -> N H W C', N = N, H = H, W = W, C = C)
        return torch.cat([dir_x, dir_y], dim = 3)


# Roformer with Xpos

class Model48pxOCR:
    _MODEL_MAPPING = {
        'model': {
            'url': 'https://huggingface.co/zyddnys/manga-image-translator/resolve/main/ocr_ar_48px.ckpt',
            'hash': '29daa46d080818bb4ab239a518a88338cbccff8f901bef8c9db191a7cb97671d',
        },
        'dict': {
            'url': 'https://huggingface.co/zyddnys/manga-image-translator/resolve/main/alphabet-all-v7.txt',
            'hash': 'f5722368146aa0fbcc9f4726866e4efc3203318ebb66c811d8cbbe915576538a',
        },
    }

    def __init__(self, model_path: str, device='cpu', max_chunk_size=16, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.device = device
        self.max_chunk_size = max_chunk_size

        with open('data/alphabet-all-v7.txt', 'r', encoding = 'utf-8') as fp:
            dictionary = [s[:-1] for s in fp.readlines()]
        self.model = OCR(dictionary, 768)
        sd = torch.load('data/models/ocr_ar_48px.ckpt', map_location='cpu')
        self.model.load_state_dict(sd)
        self.model.eval()
        if self.device != 'cpu':
            try:
                # Check if the device is actually available
                if self.device == 'cuda' and not torch.cuda.is_available():
                    self.device = 'cpu'
                    print('CUDA not available, falling back to CPU')
                elif self.device == 'mps' and not torch.backends.mps.is_available():
                    self.device = 'cpu'
                    print('MPS not available, falling back to CPU')
                self.model = self.model.to(self.device)
            except Exception as e:
                self.device = 'cpu'
                print(f'Failed to load model to {self.device}, falling back to CPU: {e}')
                self.model = self.model.to('cpu')

    def to(self, device: str) -> None:
        try:
            # Check if the device is actually available
            if device == 'cuda' and not torch.cuda.is_available():
                device = 'cpu'
                print('CUDA not available, falling back to CPU')
            elif device == 'mps' and not torch.backends.mps.is_available():
                device = 'cpu'
                print('MPS not available, falling back to CPU')
            self.model.to(device)
            self.device = device
        except Exception as e:
            print(f'Failed to load model to {device}, falling back to CPU: {e}')
            self.model.to('cpu')
            self.device = 'cpu'
    
    def __call__(self, img: np.ndarray, textblk_lst: List[TextBlock], verbose: bool = False, ignore_bubble: int = 0) -> List[TextBlock]:
        if isinstance(textblk_lst, TextBlock):
            textblk_lst = [textblk_lst]
        
        text_height = 48
        max_chunk_size = 16

        region_imgs = []
        textblk_lst_indices = []
        region_idx = 0
        for blk_idx, textblk in enumerate(textblk_lst):
            for ii in range(len(textblk)):
                textblk_lst_indices.append(blk_idx)
                region_imgs.append(textblk.get_transformed_region(img, ii, 48, maxwidth=8100))
                region_idx += 1

        perm = range(len(region_imgs))
        chunck_idx = 0
        for indices in chunks(perm, max_chunk_size):
            N = len(indices)
            widths = [region_imgs[i].shape[1] for i in indices]
            max_width = 4 * (max(widths) + 7) // 4
            region = np.zeros((N, text_height, max_width, 3), dtype = np.uint8)
            for i, idx in enumerate(indices):
                W = region_imgs[idx].shape[1]
                region[i, :, : W, :]=region_imgs[idx]

            image_tensor = (torch.from_numpy(region).float() - 127.5) / 127.5
            image_tensor = einops.rearrange(image_tensor, 'N H W C -> N C H W')
            
            if self.device != 'cpu':
                image_tensor = image_tensor.to(self.device)

            with torch.no_grad():
                ret = self.model.infer_beam_batch(image_tensor, widths, beams_k = 5, max_seq_length = 255)
            for i, (pred_chars_index, prob, fg_pred, bg_pred, fg_ind_pred, bg_ind_pred) in enumerate(ret):
                if prob < 0.2:
                    continue
                has_fg = (fg_ind_pred[:, 1] > fg_ind_pred[:, 0])
                has_bg = (bg_ind_pred[:, 1] > bg_ind_pred[:, 0])
                seq = []
                fr = AvgMeter()
                fg = AvgMeter()
                fb = AvgMeter()
                br = AvgMeter()
                bg = AvgMeter()
                bb = AvgMeter()
                for chid, c_fg, c_bg, h_fg, h_bg in zip(pred_chars_index, fg_pred, bg_pred, has_fg, has_bg) :
                    ch = self.model.dictionary[chid]
                    if ch == '<S>':
                        continue
                    if ch == '</S>':
                        break
                    if ch == '<SP>':
                        ch = ' '
                    seq.append(ch)
                    if h_fg.item() :
                        fr(int(c_fg[0] * 255))
                        fg(int(c_fg[1] * 255))
                        fb(int(c_fg[2] * 255))
                    if h_bg.item() :
                        br(int(c_bg[0] * 255))
                        bg(int(c_bg[1] * 255))
                        bb(int(c_bg[2] * 255))
                    else :
                        br(int(c_fg[0] * 255))
                        bg(int(c_fg[1] * 255))
                        bb(int(c_fg[2] * 255))
                txt = ''.join(seq)
                fr = min(max(int(fr()), 0), 255)
                fg = min(max(int(fg()), 0), 255)
                fb = min(max(int(fb()), 0), 255)
                br = min(max(int(br()), 0), 255)
                bg = min(max(int(bg()), 0), 255)
                bb = min(max(int(bb()), 0), 255)
                # self.logger.info(f'prob: {prob} {txt} fg: ({fr}, {fg}, {fb}) bg: ({br}, {bg}, {bb})')
                
                cur_region = textblk_lst[textblk_lst_indices[i+chunck_idx]]
                cur_region.text.append(txt)
                cur_region.update_font_colors(np.array([fr, fg, fb]), np.array([br, bg, bb]))

            chunck_idx += N



class ConvNeXtBlock(nn.Module):
    r""" ConvNeXt Block. There are two equivalent implementations:
    (1) DwConv -> LayerNorm (channels_first) -> 1x1 Conv -> GELU -> 1x1 Conv; all in (N, C, H, W)
    (2) DwConv -> Permute to (N, H, W, C); LayerNorm (channels_last) -> Linear -> GELU -> Linear; Permute back
    We use (2) as we find it slightly faster in PyTorch
    
    Args:
        dim (int): Number of input channels.
        drop_path (float): Stochastic depth rate. Default: 0.0
        layer_scale_init_value (float): Init value for Layer Scale. Default: 1e-6.
    """
    def __init__(self, dim, layer_scale_init_value=1e-6, ks = 7, padding = 3):
        super().__init__()
        self.dwconv = nn.Conv2d(dim, dim, kernel_size=ks, padding=padding, groups=dim) # depthwise conv
        self.norm = nn.BatchNorm2d(dim, eps=1e-6)
        self.pwconv1 = nn.Conv2d(dim, 4 * dim, 1, 1, 0) # pointwise/1x1 convs, implemented with linear layers
        self.act = nn.GELU()
        self.pwconv2 = nn.Conv2d(4 * dim, dim, 1, 1, 0)
        self.gamma = nn.Parameter(layer_scale_init_value * torch.ones(1, dim, 1, 1), 
                                    requires_grad=True) if layer_scale_init_value > 0 else None

    def forward(self, x):
        input = x
        x = self.dwconv(x)
        x = self.norm(x)
        x = self.pwconv1(x)
        x = self.act(x)
        x = self.pwconv2(x)
        if self.gamma is not None:
            x = self.gamma * x

        x = input + x
        return x

class ConvNext_FeatureExtractor(nn.Module) :
    def __init__(self, img_height = 48, in_dim = 3, dim = 512, n_layers = 12) -> None:
        super().__init__()
        base = dim // 8
        self.stem = nn.Sequential(
            nn.Conv2d(in_dim, base, kernel_size = 7, stride = 1, padding = 3),
            nn.BatchNorm2d(base),
            nn.ReLU(),
            nn.Conv2d(base, base * 2, kernel_size = 2, stride = 2, padding = 0),
            nn.BatchNorm2d(base * 2),
            nn.ReLU(),
            nn.Conv2d(base * 2, base * 2, kernel_size = 3, stride = 1, padding = 1),
            nn.BatchNorm2d(base * 2),
            nn.ReLU(),
        )
        self.block1 = self.make_layers(base * 2, 4)
        self.down1 = nn.Sequential(
            nn.Conv2d(base * 2, base * 4, kernel_size = 2, stride = 2, padding = 0),
            nn.BatchNorm2d(base * 4),
            nn.ReLU(),
        )
        self.block2 = self.make_layers(base * 4, 12)
        self.down2 = nn.Sequential(
            nn.Conv2d(base * 4, base * 8, kernel_size = (2, 1), stride = (2, 1), padding = (0, 0)),
            nn.BatchNorm2d(base * 8),
            nn.ReLU(),
        )
        self.block3 = self.make_layers(base * 8, 10, ks = 5, padding = 2)
        self.down3 = nn.Sequential(
            nn.Conv2d(base * 8, base * 8, kernel_size = (2, 1), stride = (2, 1), padding = (0, 0)),
            nn.BatchNorm2d(base * 8),
            nn.ReLU(),
        )
        self.block4 = self.make_layers(base * 8, 8, ks = 3, padding = 1)
        self.down4 = nn.Sequential(
            nn.Conv2d(base * 8, base * 8, kernel_size = (3, 1), stride = (1, 1), padding = (0, 0)),
            nn.BatchNorm2d(base * 8),
            nn.ReLU(),
        )

    def make_layers(self, dim, n, ks = 7, padding = 3) :
        layers = []
        for i in range(n) :
            layers.append(ConvNeXtBlock(dim, ks = ks, padding = padding))
        return nn.Sequential(*layers)
    
    def forward(self, x) :
        x = self.stem(x)
        # h//2, w//2
        x = self.block1(x)
        x = self.down1(x)
        # h//4, w//4
        x = self.block2(x)
        x = self.down2(x)
        # h//8, w//4
        x = self.block3(x)
        x = self.down3(x)
        # h//16, w//4
        x = self.block4(x)
        x = self.down4(x)
        return x

def transformer_encoder_forward(
    self,
    src: torch.Tensor,
    src_mask: Optional[torch.Tensor] = None,
    src_key_padding_mask: Optional[torch.Tensor] = None,
    is_causal: bool = False) -> torch.Tensor:
    x = src
    if self.norm_first:
        x = x + self._sa_block(self.norm1(x), src_mask, src_key_padding_mask, is_causal=is_causal)
        x = x + self._ff_block(self.norm2(x))
    else:
        x = self.norm1(x + self._sa_block(x, src_mask, src_key_padding_mask, is_causal=is_causal))
        x = self.norm2(x + self._ff_block(x))

    return x

class XposMultiheadAttention(nn.Module):
    def __init__(
        self,
        embed_dim,
        num_heads,
        self_attention=False,
        encoder_decoder_attention=False,
    ):
        super().__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        self.scaling = self.head_dim**-0.5

        self.self_attention = self_attention
        self.encoder_decoder_attention = encoder_decoder_attention
        assert self.self_attention ^ self.encoder_decoder_attention

        self.k_proj = nn.Linear(embed_dim, embed_dim, bias = True)
        self.v_proj = nn.Linear(embed_dim, embed_dim, bias = True)
        self.q_proj = nn.Linear(embed_dim, embed_dim, bias = True)
        self.out_proj = nn.Linear(embed_dim, embed_dim, bias = True)
        self.xpos = XPOS(self.head_dim, embed_dim)
        self.batch_first = True
        self._qkv_same_embed_dim = True

    def reset_parameters(self):
        nn.init.xavier_uniform_(self.k_proj.weight, gain=1 / math.sqrt(2))
        nn.init.xavier_uniform_(self.v_proj.weight, gain=1 / math.sqrt(2))
        nn.init.xavier_uniform_(self.q_proj.weight, gain=1 / math.sqrt(2))
        nn.init.xavier_uniform_(self.out_proj.weight)
        nn.init.constant_(self.out_proj.bias, 0.0)

    def forward(
        self,
        query,
        key,
        value,
        key_padding_mask=None,
        attn_mask=None,
        need_weights = False,
        is_causal = False,
        k_offset = 0,
        q_offset = 0
    ):
        assert not is_causal
        bsz, tgt_len, embed_dim = query.size()
        src_len = tgt_len
        assert embed_dim == self.embed_dim, f"query dim {embed_dim} != {self.embed_dim}"

        key_bsz, src_len, _ = key.size()
        assert key_bsz == bsz, f"{query.size(), key.size()}"
        assert value is not None
        assert bsz, src_len == value.shape[:2]

        q = self.q_proj(query)
        k = self.k_proj(key)
        v = self.v_proj(value)
        q *= self.scaling

        q = q.view(bsz, tgt_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(bsz, src_len, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(bsz, src_len, self.num_heads, self.head_dim).transpose(1, 2)
        q = q.reshape(bsz * self.num_heads, tgt_len, self.head_dim)
        k = k.reshape(bsz * self.num_heads, src_len, self.head_dim)
        v = v.reshape(bsz * self.num_heads, src_len, self.head_dim)

        if self.xpos is not None:
            k = self.xpos(k, offset=k_offset, downscale=True) # TODO: read paper
            q = self.xpos(q, offset=q_offset, downscale=False)

        attn_weights = torch.bmm(q, k.transpose(1, 2))

        if attn_mask is not None:
            attn_weights = torch.nan_to_num(attn_weights)
            attn_mask = attn_mask.unsqueeze(0)
            attn_weights += attn_mask

        if key_padding_mask is not None:
            attn_weights = attn_weights.view(bsz, self.num_heads, tgt_len, src_len)
            attn_weights = attn_weights.masked_fill(
                key_padding_mask.unsqueeze(1).unsqueeze(2).to(torch.bool),
                float("-inf"),
            )
            attn_weights = attn_weights.view(bsz * self.num_heads, tgt_len, src_len)

        attn_weights = F.softmax(attn_weights, dim=-1, dtype=torch.float32).type_as(
            attn_weights
        )
        attn = torch.bmm(attn_weights, v)
        attn = attn.transpose(0, 1).reshape(tgt_len, bsz, embed_dim).transpose(0, 1)

        attn = self.out_proj(attn)
        attn_weights = attn_weights.view(
            bsz, self.num_heads, tgt_len, src_len
        ).transpose(1, 0)

        if need_weights:
            return attn, attn_weights
        else :
            return attn, None

def generate_square_subsequent_mask(sz):
    mask = (torch.triu(torch.ones(sz, sz)) == 1).transpose(0, 1)
    mask = mask.float().masked_fill(mask == 0, float('-inf')).masked_fill(mask == 1, float(0.0))
    return mask

class Beam:
    def __init__(self, char_seq = [], logprobs = []):
        # L
        if isinstance(char_seq, list):
            self.chars = torch.tensor(char_seq, dtype=torch.long)
            self.logprobs = torch.tensor(logprobs, dtype=torch.float32)
        else:
            self.chars = char_seq.clone()
            self.logprobs = logprobs.clone()

    def avg_logprob(self):
        return self.logprobs.mean().item()

    def sort_key(self):
        return -self.avg_logprob()

    def seq_end(self, end_tok):
        return self.chars.view(-1)[-1] == end_tok

    def extend(self, idx, logprob):
        return Beam(
            torch.cat([self.chars, idx.unsqueeze(0)], dim = -1),
            torch.cat([self.logprobs, logprob.unsqueeze(0)], dim = -1),
        )

DECODE_BLOCK_LENGTH = 8

class Hypothesis:
    def __init__(self, device, start_tok: int, end_tok: int, padding_tok: int, memory_idx: int, num_layers: int, embd_dim: int):
        self.device = device
        self.start_tok = start_tok
        self.end_tok = end_tok
        self.padding_tok = padding_tok
        self.memory_idx = memory_idx
        self.embd_size = embd_dim
        self.num_layers = num_layers
        # 1, L, E
        self.cached_activations = [torch.zeros(1, 0, self.embd_size).to(self.device)] * (num_layers + 1)
        self.out_idx = torch.LongTensor([start_tok]).to(self.device)
        self.out_logprobs = torch.FloatTensor([0]).to(self.device)
        self.length = 0

    def seq_end(self):
        return self.out_idx.view(-1)[-1] == self.end_tok

    def logprob(self):
        return self.out_logprobs.mean().item()

    def sort_key(self):
        return -self.logprob()

    def prob(self):
        return self.out_logprobs.mean().exp().item()

    def __len__(self):
        return self.length

    def extend(self, idx, logprob):
        ret = Hypothesis(self.device, self.start_tok, self.end_tok, self.padding_tok, self.memory_idx, self.num_layers, self.embd_size)
        ret.cached_activations = [item.clone() for item in self.cached_activations]
        ret.length = self.length + 1
        ret.out_idx = torch.cat([self.out_idx, torch.LongTensor([idx]).to(self.device)], dim = 0)
        ret.out_logprobs = torch.cat([self.out_logprobs, torch.FloatTensor([logprob]).to(self.device)], dim = 0)
        return ret

    def output(self):
        return self.cached_activations[-1]

def next_token_batch(
    hyps: List[Hypothesis],
    memory: torch.Tensor, # N, H, W, C
    memory_mask: torch.BoolTensor,
    decoders: nn.ModuleList,
    embd: nn.Embedding
    ):
    layer: nn.TransformerDecoderLayer
    N = len(hyps)
    offset = len(hyps[0])

    # N
    last_toks = torch.stack([item.out_idx[-1] for item in hyps])
    # N, 1, E
    tgt: torch.FloatTensor = embd(last_toks).unsqueeze_(1)
    
    # N, L, E
    memory = torch.stack([memory[idx, :, :] for idx in [item.memory_idx for item in hyps]], dim = 0)
    for l, layer in enumerate(decoders):
        # TODO: keys and values are recomputed everytime
        # N, L - 1, E
        combined_activations = torch.cat([item.cached_activations[l] for item in hyps], dim = 0)
        # N, L, E
        combined_activations = torch.cat([combined_activations, tgt], dim = 1)
        for i in range(N):
            hyps[i].cached_activations[l] = combined_activations[i: i + 1, :, :]
        # N, 1, E
        tgt = tgt + layer.self_attn(layer.norm1(tgt), layer.norm1(combined_activations), layer.norm1(combined_activations), q_offset = offset)[0]
        tgt = tgt + layer.multihead_attn(layer.norm2(tgt), memory, memory, key_padding_mask = memory_mask, q_offset = offset)[0]
        tgt = tgt + layer._ff_block(layer.norm3(tgt))
    #print(tgt[0, 0, 0])
    for i in range(N):
        hyps[i].cached_activations[len(decoders)] = torch.cat([hyps[i].cached_activations[len(decoders)], tgt[i: i + 1, :, :]], dim = 1)
    # N, E
    return tgt.squeeze_(1)

class OCR(nn.Module):
    def __init__(self, dictionary, max_len):
        super(OCR, self).__init__()
        self.max_len = max_len
        self.dictionary = dictionary
        self.dict_size = len(dictionary)
        n_decoders = 4
        embd_dim = 320
        nhead = 4
        #self.backbone = LocalViT_FeatureExtractor(48, 3, dim = embd_dim, ff_dim = embd_dim * 4, n_layers = n_encoders)
        self.backbone = ConvNext_FeatureExtractor(48, 3, embd_dim)
        self.encoders = nn.ModuleList()
        self.decoders = nn.ModuleList()
        for i in range(4) :
            encoder = nn.TransformerEncoderLayer(embd_dim, nhead, dropout = 0, batch_first = True, norm_first = True)
            encoder.self_attn = XposMultiheadAttention(embd_dim, nhead, self_attention = True)
            encoder.forward = transformer_encoder_forward
            self.encoders.append(encoder)
        for i in range(5) :
            decoder = nn.TransformerDecoderLayer(embd_dim, nhead, dropout = 0, batch_first = True, norm_first = True)
            decoder.self_attn = XposMultiheadAttention(embd_dim, nhead, self_attention = True)
            decoder.multihead_attn = XposMultiheadAttention(embd_dim, nhead, encoder_decoder_attention = True)
            self.decoders.append(decoder)
        self.embd = nn.Embedding(self.dict_size, embd_dim)
        self.pred1 = nn.Sequential(nn.Linear(embd_dim, embd_dim), nn.GELU(), nn.Dropout(0.15))
        self.pred = nn.Linear(embd_dim, self.dict_size)
        self.pred.weight = self.embd.weight
        self.color_pred1 = nn.Sequential(nn.Linear(embd_dim, 64), nn.ReLU())
        self.color_pred_fg = nn.Linear(64, 3)
        self.color_pred_bg = nn.Linear(64, 3)
        self.color_pred_fg_ind = nn.Linear(64, 2)
        self.color_pred_bg_ind = nn.Linear(64, 2)

    def forward(self,
        img: torch.FloatTensor,
        char_idx: torch.LongTensor,
        decoder_mask: torch.BoolTensor,
        encoder_mask: torch.BoolTensor
        ):
        memory = self.backbone(img)
        memory = einops.rearrange(memory, 'N C 1 W -> N W C')
        for layer in self.encoders :
            memory = layer(memory, src_key_padding_mask = encoder_mask)
        N, L = char_idx.shape
        char_embd = self.embd(char_idx)
        # N, L, D
        casual_mask = generate_square_subsequent_mask(L).to(img.device)
        decoded = char_embd
        for layer in self.decoders :
            decoded = layer(decoded, memory, tgt_mask = casual_mask, tgt_key_padding_mask = decoder_mask, memory_key_padding_mask = encoder_mask)
        
        pred_char_logits = self.pred(self.pred1(decoded))
        color_feats = self.color_pred1(decoded)
        return pred_char_logits, \
            self.color_pred_fg(color_feats), \
            self.color_pred_bg(color_feats), \
            self.color_pred_fg_ind(color_feats), \
            self.color_pred_bg_ind(color_feats)

    def infer_beam_batch(self, img: torch.FloatTensor, img_widths: List[int], beams_k: int = 5, start_tok = 1, end_tok = 2, pad_tok = 0, max_finished_hypos: int = 2, max_seq_length = 384):
        N, C, H, W = img.shape
        assert H == 48 and C == 3
        memory = self.backbone(img)
        memory = einops.rearrange(memory, 'N C 1 W -> N W C')
        valid_feats_length = [(x + 3) // 4 + 2 for x in img_widths]
        input_mask = torch.zeros(N, memory.size(1), dtype = torch.bool).to(img.device)
        for i, l in enumerate(valid_feats_length):
            input_mask[i, l:] = True
        for layer in self.encoders :
            memory = layer(layer, src = memory, src_key_padding_mask = input_mask)
        hypos = [Hypothesis(img.device, start_tok, end_tok, pad_tok, i, len(self.decoders), 320) for i in range(N)]
        # N, E
        decoded = next_token_batch(hypos, memory, input_mask, self.decoders, self.embd)
        # N, n_chars
        pred_char_logprob = self.pred(self.pred1(decoded)).log_softmax(-1)
        # N, k
        pred_chars_values, pred_chars_index = torch.topk(pred_char_logprob, beams_k, dim = 1)
        new_hypos: List[Hypothesis] = []
        finished_hypos = defaultdict(list)
        for i in range(N):
            for k in range(beams_k):
                new_hypos.append(hypos[i].extend(pred_chars_index[i, k], pred_chars_values[i, k]))
        hypos = new_hypos
        for ixx in range(max_seq_length):
            # N * k, E
            decoded = next_token_batch(hypos, memory, torch.stack([input_mask[hyp.memory_idx] for hyp in hypos]) , self.decoders, self.embd)
            # N * k, n_chars
            pred_char_logprob = self.pred(self.pred1(decoded)).log_softmax(-1)
            # N * k, k
            pred_chars_values, pred_chars_index = torch.topk(pred_char_logprob, beams_k, dim = 1)
            hypos_per_sample = defaultdict(list)
            h: Hypothesis
            for i, h in enumerate(hypos):
                for k in range(beams_k):
                    hypos_per_sample[h.memory_idx].append(h.extend(pred_chars_index[i, k], pred_chars_values[i, k]))
            hypos = []
            # hypos_per_sample now contains N * k^2 hypos
            for i in hypos_per_sample.keys():
                cur_hypos: List[Hypothesis] = hypos_per_sample[i]
                cur_hypos = sorted(cur_hypos, key = lambda a: a.sort_key())[: beams_k + 1]
                #print(cur_hypos[0].out_idx[-1])
                to_added_hypos = []
                sample_done = False
                for h in cur_hypos:
                    if h.seq_end():
                        finished_hypos[i].append(h)
                        if len(finished_hypos[i]) >= max_finished_hypos:
                            sample_done = True
                            break
                    else:
                        if len(to_added_hypos) < beams_k:
                            to_added_hypos.append(h)
                if not sample_done:
                    hypos.extend(to_added_hypos)
            if len(hypos) == 0:
                break
        # add remaining hypos to finished
        for i in range(N):
            if i not in finished_hypos:
                cur_hypos: List[Hypothesis] = hypos_per_sample[i]
                cur_hypo = sorted(cur_hypos, key = lambda a: a.sort_key())[0]
                finished_hypos[i].append(cur_hypo)
        assert len(finished_hypos) == N
        result = []
        for i in range(N):
            cur_hypos = finished_hypos[i]
            cur_hypo = sorted(cur_hypos, key = lambda a: a.sort_key())[0]
            decoded = cur_hypo.output()
            color_feats = self.color_pred1(decoded)
            fg_pred, bg_pred, fg_ind_pred, bg_ind_pred = \
                self.color_pred_fg(color_feats), \
                self.color_pred_bg(color_feats), \
                self.color_pred_fg_ind(color_feats), \
                self.color_pred_bg_ind(color_feats)
            result.append((cur_hypo.out_idx[1:], cur_hypo.prob(), fg_pred[0], bg_pred[0], fg_ind_pred[0], bg_ind_pred[0]))
        return result

import numpy as np

def convert_pl_model(filename: str) :
    sd = torch.load(filename, map_location = 'cpu')['state_dict']
    sd2 = {}
    for k, v in sd.items() :
        k: str
        k = k.removeprefix('model.')
        sd2[k] = v
    return sd2

def test_LocalViT_FeatureExtractor() :
    net = ConvNext_FeatureExtractor(48, 3, 320)
    inp = torch.randn(2, 3, 48, 512)
    out = net(inp)
    print(out.shape)

def test_infer() :
    with open('alphabet-all-v7.txt', 'r') as fp :
        dictionary = [s[:-1] for s in fp.readlines()]
    model = OCR(dictionary, 32)
    model.eval()
    sd = convert_pl_model('epoch=0-step=13000.ckpt')
    model.load_state_dict(sd)
    model_parameters = filter(lambda p: p.requires_grad, model.parameters())
    params = sum([np.prod(p.size()) for p in model_parameters])
    print(params)

    img = cv2.cvtColor(cv2.imread('test3.png'), cv2.COLOR_BGR2RGB)
    ratio = img.shape[1] / float(img.shape[0])
    new_w = int(round(ratio * 48))
    #print(img.shape)
    img = cv2.resize(img, (new_w, 48), interpolation=cv2.INTER_AREA)

    img_torch = einops.rearrange((torch.from_numpy(img) / 127.5 - 1.0), 'h w c -> 1 c h w')

    with torch.no_grad() :
        idx, prob, fg_pred, bg_pred, fg_ind_pred, bg_ind_pred = model.infer_beam_batch(img_torch, [new_w], 5, max_seq_length = 32)[0]
        txt = ''
        for i in idx :
            txt += dictionary[i]
        print(txt, prob)
        for chid, fg, bg, fg_ind, bg_ind in zip(idx, fg_pred[0], bg_pred[0], fg_ind_pred[0], bg_ind_pred[0]) :
            has_fg = (fg_ind[1] > fg_ind[0]).item()
            has_bg = (bg_ind[1] > bg_ind[0]).item()
            if has_fg :
                fg = np.clip((fg * 255).numpy(), 0, 255)
            if has_bg :
                bg = np.clip((bg * 255).numpy(), 0, 255)
            print(f'{dictionary[chid]} {fg if has_fg else "None"} {bg if has_bg else "None"}')

if __name__ == "__main__":
    test_infer()
