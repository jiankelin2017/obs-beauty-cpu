# -*- coding: utf-8 -*-
"""生成一个专门验证「掩码滞后」的 OBS 场景集合。

场景内容：
  * 一个 640x394 的 Browser 源，加载 move.html —— 里面的人脸以 4px/帧
    左右往返运动（30fps 下约 120 px/s，接近头部晃动速度）
  * 挂 LegacySDK Beauty 滤镜，只开美白 55，磨皮/锐化/红润全关
    → 画面上唯一会变的就是美白区域，它的位置就是掩码的位置

用法: python make_lag_scene.py
"""
import json
import os
import uuid

SCENE_DIR = os.path.join(os.path.expanduser("~"), "AppData/Roaming/obs-studio/basic/scenes")
OUT = os.path.join(SCENE_DIR, "lagtest.json")

HTML = "file:///C:/legacy_e2e/obs_move/move.html"

FILTER = {
    "prev_ver": 536936449,
    "name": "LegacySDK Beauty",
    "uuid": "b1f2c3d4-1111-4aaa-8bbb-222233334444",
    "id": "legacy_beauty_filter",
    "versioned_id": "legacy_beauty_filter",
    "settings": {
        "enabled": True,
        "skin_detect": True,
        "rotate": 0,
        "blur_level": 0.0,      # 磨皮关：只留美白，隔离变量
        "clarity": 0.0,
        "color_level": 55.0,    # 美白 55
        "red_level": 0.0,       # 红润关
        "sharpen": 0.0,         # 锐化关
        "face_threed": 0.0,
        "eye_bright": 0.0,
    },
    "mixers": 0,
    "sync": 0,
    "flags": 0,
    "volume": 1.0,
    "balance": 0.5,
    "enabled": True,
    "muted": False,
    "push-to-mute": False,
    "push-to-mute-delay": 0,
    "push-to-talk": False,
    "push-to-talk-delay": 0,
    "hotkeys": {},
    "deinterlace_mode": 0,
    "deinterlace_field_order": 0,
    "monitoring_type": 0,
    "private_settings": {},
}

BROWSER = {
    "prev_ver": 536936449,
    "name": "MovingFace",
    "uuid": "c0ffee00-5a5a-4b4b-9c9c-ddddeeeeffff",
    "id": "browser_source",
    "versioned_id": "browser_source",
    "settings": {
        "width": 640,
        "height": 394,
        "fps": 30,
        "fps_custom": True,
        "url": HTML,
        "css": "",
        "shutdown": False,
        "restart_when_inactive": False,
        "webpage_control_level": 5,
        "is_media_flag": 0,
        "reroute_audio": False,
    },
    "filters": [FILTER],
    "mixers": 0,
    "sync": 0,
    "flags": 0,
    "volume": 1.0,
    "balance": 0.5,
    "enabled": True,
    "muted": False,
    "push-to-mute": False,
    "push-to-mute-delay": 0,
    "push-to-talk": False,
    "push-to-talk-delay": 0,
    "hotkeys": {},
    "deinterlace_mode": 0,
    "deinterlace_field_order": 0,
    "monitoring_type": 0,
    "canvas_uuid": "e7d2a1f0-3c4b-4d5e-8f90-a1b2c3d4e5f6",
    "private_settings": {},
}

SCENE_ITEM = {
    "name": "MovingFace",
    "source_uuid": BROWSER["uuid"],
    "visible": True,
    "locked": False,
    "rot": 0.0,
    "scale_ref": {"x": 640.0, "y": 394.0},
    "align": 5,
    "bounds_type": 0,
    "bounds_align": 0,
    "bounds_crop": False,
    "crop_left": 0,
    "crop_top": 0,
    "crop_right": 0,
    "crop_bottom": 0,
    "id": 1,
    "group_item_backup": False,
    "pos": {"x": 0.0, "y": 0.0},
    "scale": {"x": 1.0, "y": 1.0},
    "scale_filter": "disable",
    "blending_method": "default",
    "blending_type": "normal",
    "scene_item_flags": 0,
}

SCENE = {
    "prev_ver": 536936449,
    "name": "LagTest",
    "uuid": "aabbccdd-1234-4eee-8fff-0123456789ab",
    "id": "scene",
    "versioned_id": "scene",
    "settings": {
        "id_counter": 2,
        "custom_size": False,
        "items": [SCENE_ITEM],
    },
    "mixers": 0,
    "sync": 0,
    "flags": 0,
    "volume": 1.0,
    "balance": 0.5,
    "enabled": True,
    "muted": False,
    "push-to-mute": False,
    "push-to-mute-delay": 0,
    "push-to-talk": False,
    "push-to-talk-delay": 0,
    "hotkeys": {},
    "deinterlace_mode": 0,
    "deinterlace_field_order": 0,
    "monitoring_type": 0,
    "canvas_uuid": "e7d2a1f0-3c4b-4d5e-8f90-a1b2c3d4e5f6",
    "private_settings": {},
}

COLLECTION = {
    "name": "lagtest",
    "sources": [SCENE],
    "groups": [],
    "scene_order": [{"name": "LagTest"}],
    "current_scene": "LagTest",
    "current_program_scene": "LagTest",
    "canvases": [
        {
            "uuid": "e7d2a1f0-3c4b-4d5e-8f90-a1b2c3d4e5f6",
            "width": 640,
            "height": 394,
            "background_color": 0xFF000000,
        }
    ],
    "current_transition": "Fade",
    "transition_duration": 300,
    "transitions": [],
    "quick_transitions": [],
    "saved_projectors": [],
    "preview_locked": False,
    "scaling_enabled": False,
    "scaling_level": 1.0,
    "scaling_off_x": 0.0,
    "scaling_off_y": 0.0,
    "virtual-camera": {},
    "modules": {},
    "version": 1,
}


def main():
    os.makedirs(SCENE_DIR, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(COLLECTION, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)
    print("browser url:", HTML)
    print("filter: blur=0 whiten=55 red=0 sharpen=0")


if __name__ == "__main__":
    main()
