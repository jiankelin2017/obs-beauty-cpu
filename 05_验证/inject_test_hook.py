# -*- coding: utf-8 -*-
"""Re-inject the measurement-only test hooks into the e2e copy of the sources.

Hooks (all measurement-only, never in production source):

1. legacy_engine.cpp / LegacySelfTest - reads C:\\legacy_e2e\\panel.txt (comma
   separated panel indices) and forces skin_detect=1 to match the plugin UI
   default (精准美肤 on).

2. legacy_engine.cpp / LegacySeqTest - same panel.txt read, plus a per-frame log
   (C:\\legacy_e2e\\seq_log.txt) with faces / coverage / inferCount and the
   frame-to-frame output difference. Used for the mask-flicker diagnosis.

3. legacy_region.cpp / inferOnce - when C:\\legacy_e2e\\dump_mask.txt exists,
   dumps mask_ + maskSoft_ to C:\\legacy_e2e\\mask_dump_%03d.raw (one file per
   inference, index = inferCount_ BEFORE the increment) and appends one line
   per inference to C:\\legacy_e2e\\infer_log.txt. Frames where fuai returns no
   mask are logged too (mask=0), so path flapping is visible.

Run after every `cp` from the real source tree (sync_test_copy.py does this).
"""
import sys

SRC = r"C:/legacy_e2e/legacy_engine.cpp"

ANCHOR = "    s.panel[P_BLUR] = blur;\n    s.panel[P_WHITEN] = whiten;\n"

HOOK = r'''    s.panel[P_BLUR] = blur;
    s.panel[P_WHITEN] = whiten;
    // 与插件 UI 默认一致：精准美肤开（截图里是勾选状态）
    s.skin_detect = 1;
    // ---- measurement-only hook (NOT in production source) ----
    // panel.txt format: "idx[:value],idx[:value]"
    //   0,4        -> both driven by the `blur` argument
    //   0:75,4:50  -> each with its own value
    {
        FILE* pf = nullptr;
        if (fopen_s(&pf, "C:\\legacy_e2e\\panel.txt", "r") == 0 && pf) {
            char line[256] = {0};
            if (fgets(line, sizeof(line), pf)) {
                for (int i = 0; i < P_COUNT; i++) s.panel[i] = 0;
                char* ctx = nullptr;
                for (char* tok = strtok_s(line, ",", &ctx); tok;
                     tok = strtok_s(nullptr, ",", &ctx)) {
                    int idx = -1;
                    double val = blur;
                    char* colon = strchr(tok, ':');
                    if (colon) {
                        *colon = 0;
                        val = atof(colon + 1);
                    }
                    idx = atoi(tok);
                    if (idx >= 0 && idx < P_COUNT) s.panel[idx] = val;
                }
            }
            fclose(pf);
        }
    }
'''


# ---- 第二个钩子：逐帧转储掩码（注入 legacy_region.cpp 的 inferOnce）------------
# flag 文件 C:\legacy_e2e\dump_mask.txt 存在时，每次推理把 mask_（fuai 原始）和
# maskSoft_（软化后）落盘到 C:\legacy_e2e\mask_dump_%03d.raw（编号 = inferCount_，
# 即本次推理前的计数值，0 起），同时往 C:\legacy_e2e\infer_log.txt 追一行状态。
# 用途：帧间对比掩码，区分「掩码本身在抖」和「上采样/施加环节在抖」。
REG_SRC = r"C:/legacy_e2e/legacy_region.cpp"
REG_ANCHOR = "    softenMask();\n    temporalSmooth();\n    coverage_ = 0.0;\n"
REG_HOOK = r'''    softenMask();
    temporalSmooth();
    coverage_ = 0.0;
    // ---- measurement-only hook: per-frame mask dump (NOT in production) ----
    {
        FILE* kf = nullptr;
        if (fopen_s(&kf, "C:\\legacy_e2e\\dump_mask.txt", "r") == 0 && kf) {
            fclose(kf);
            char mp[160];
            sprintf_s(mp, "C:\\legacy_e2e\\mask_dump_%03d.raw", (int)inferCount_);
            FILE* mf = nullptr;
            if (fopen_s(&mf, mp, "wb") == 0 && mf) {
                int hdr[2] = { mw_, mh_ };
                fwrite(hdr, sizeof(int), 2, mf);
                fwrite(&mask_[0], 1, npx, mf);
                fwrite(&maskSoft_[0], 1, npx, mf);
                // 3.0.4 追加：rawTmp_ 是**真正未处理**的 fuai 原始掩码（mask_
                // 自 3.0.4 起已被时域中值就地改写）。老分析脚本按 npx 偏移读
                // 前两块，追加第三块不影响它们。
                if (rawTmp_.size() >= npx)
                    fwrite(&rawTmp_[0], 1, npx, mf);
                fclose(mf);
            }
            FILE* lf = nullptr;
            if (fopen_s(&lf, "C:\\legacy_e2e\\infer_log.txt", "a") == 0 && lf) {
                fprintf(lf, "frame=%d mask=1 mw=%d mh=%d cov=%.4f\n",
                        (int)inferCount_, mw_, mh_, coverage_);
                fclose(lf);
            }
        }
    }
'''

# ---- 第三个钩子：fuai 返回「无掩码」的帧也要留痕 ---------------------------
# 这一帧走的是 r==2 / 空指针提前返回，hasMask_ 置 false。若这种帧和正常帧
# 交替出现，渲染层就会在「语义掩码路径」和「颜色启发式路径」之间反复横跳 —
# 整幅画面的美白风格会变，是最典型的「遮罩屏闪」。
REG2_ANCHOR = "        hasMask_ = false;\n        coverage_ = 0.0;\n"
REG2_HOOK = r'''        hasMask_ = false;
        coverage_ = 0.0;
        // ---- measurement-only hook: log no-mask frames (NOT in production) ----
        {
            FILE* kf = nullptr;
            if (fopen_s(&kf, "C:\\legacy_e2e\\dump_mask.txt", "r") == 0 && kf) {
                fclose(kf);
                FILE* lf = nullptr;
                if (fopen_s(&lf, "C:\\legacy_e2e\\infer_log.txt", "a") == 0 && lf) {
                    fprintf(lf, "frame=%d mask=0 mw=0 mh=0 cov=0.0000\n",
                            (int)inferCount_);
                    fclose(lf);
                }
            }
        }
'''


def inject_region():
    try:
        d = open(REG_SRC, "rb").read().decode("utf-8")
    except FileNotFoundError:
        print("region hook: file missing")
        return 1
    if "measurement-only hook: per-frame mask dump" in d:
        print("region hook already present")
    else:
        if REG_ANCHOR not in d:
            print("region ANCHOR not found - source changed?")
            return 1
        d = d.replace(REG_ANCHOR, REG_HOOK, 1)
        open(REG_SRC, "wb").write(d.encode("utf-8"))
        print("region hook injected")

    if "measurement-only hook: log no-mask frames" in d:
        pass
    else:
        d = open(REG_SRC, "rb").read().decode("utf-8")
        if REG2_ANCHOR not in d:
            print("region2 ANCHOR not found - source changed?")
            return 1
        d = d.replace(REG2_ANCHOR, REG2_HOOK, 1)
        open(REG_SRC, "wb").write(d.encode("utf-8"))
        print("region2 hook injected")
    return 0


def main():
    d = open(SRC, "rb").read().decode("utf-8")
    if "measurement-only hook" in d:
        print("hook already present")
    else:
        if ANCHOR not in d:
            print("ANCHOR not found - source changed?")
            return 1
        d = d.replace(ANCHOR, HOOK, 1)
        open(SRC, "wb").write(d.encode("utf-8"))
        print("hook injected")
    return inject_region()


if __name__ == "__main__":
    sys.exit(main())
