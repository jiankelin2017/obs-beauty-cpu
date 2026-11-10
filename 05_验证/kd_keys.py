# -*- coding: utf-8 -*-
"""提取候选参数 key：对照面板字符串 + Nama 经典参数名。"""
import re
import os

THEIRS = os.path.join(os.path.expanduser("~"), "AppData/Roaming/obsplus/plugins/obs-cam-beauty/bin/64bit")
FILES = ['obs-cam-beauty_qt6.dll', 'obs-cam-beauty.dll', 'beauty.exe']


def strings_of(path, minlen=3, maxlen=64):
    data = open(path, 'rb').read()
    out = set()
    for m in re.finditer(rb'[ -~]{%d,%d}' % (minlen, maxlen), data):
        out.add(m.group().decode('ascii'))
    return out


# 已知的 Nama SDK 经典参数（官方文档 + 我们源码已在用）
CLASSIC = [
    'blur_level', 'color_level', 'red_level', 'sharpen', 'face_threed',
    'eye_bright', 'remove_pouch_strength', 'remove_nasolabial_folds_strength',
    'clarity', 'delspot_level', 'blur_type', 'skin_detect', 'heavy_blur',
    'color_level_type', 'use_new_whiten', 'whiten_v2', 'beauty_mask_v',
    'filter_name', 'filter_level', 'filter_type', 'filter_list',
    'face_shape', 'face_shape_level', 'eye_enlarging', 'cheek_thinning',
    'cheek_v', 'cheek_narrow', 'cheek_small', 'intensity_chin',
    'intensity_forehead', 'intensity_nose', 'intensity_mouth',
    'intensity_eye_circle', 'intensity_eye_height', 'intensity_eye_lid',
    'intensity_eye_rotate', 'intensity_eye_space', 'eye_enlarge_level',
    'tooth_whiten', 'brightness', 'saturation', 'contrast',
    'background_blur', 'background_blur_value', 'body_shape',
    'skin_dect_en', 'disable_skinseg', 'enable_skinseg',
    'face_landmark_quality', 'base_beauty', 'adv_beauty',
    'change_frames', 'use_uniform_buffer', 'is_beauty',
    'enable_lip_color', 'lip_color_level', 'blusher_level',
    'eye_shadow_level', 'eyelash_level', 'pupil_level', 'eyebrow_level',
    'hair_color_level', 'makeup_level', 'makeup_intensity',
    'clear_smooth', 'fine_smooth', 'balance_smooth', 'hazy_smooth',
    'smooth_level', 'smooth_mode', 'smooth_type', 'beauty_level',
    'debug_log', 'enable_debug', 'manual_scale', 'is_debug',
]

cands = set(CLASSIC)
for f in FILES:
    p = os.path.join(THEIRS, f)
    if not os.path.exists(p):
        continue
    for s in strings_of(p):
        if re.fullmatch(r'[a-z][a-z0-9_]{2,30}', s):
            if re.search(r'blur|smooth|skin|beaut|whiten|color|red|sharpen|'
                         r'filter|shape|threed|eye|pouch|nasolabial|level|'
                         r'clean|clear|fine|balance|hazy|strength|intensity|'
                         r'tooth|bright|satur|contrast|dect|seg|landmark|'
                         r'mask|scale|debug|texture|detail', s):
                cands.add(s)

order = [k for k in CLASSIC if k in cands] + sorted(cands - set(CLASSIC))
print('候选总数', len(order))
for k in order:
    print(k)
open(r'C:\legacy_e2e\kd_keys.txt', 'w').write('\n'.join(order))
