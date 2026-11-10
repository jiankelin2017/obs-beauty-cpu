#pragma once
// ---------------------------------------------------------------------------
// beauty_env.h —— BEAUTY_* 环境变量覆盖的唯一入口（1.0.13.10 / C-2 C-3）
//
// 为什么要有这一层：全库 116 处诊断开关（BEAUTY_ALIGN_DIFF、BEAUTY_ROLL_CHECK、
// BEAUTY_FACE_MODEL、BEAUTY_NECK_* …）原来各自直接调 getenv，于是**发布版里
// 也全部生效**。这带来两个问题：
//     文件解析入口交到"能改进程环境"的人手里；
//   · 更现实的是支持成本：用户机器上残留一个 BEAUTY_ROLL_CHECK=0，行为就和
//     文档不一致，而日志里没有任何痕迹。
//
// 现在所有覆盖都必须经过 beauty_env()。发布构建定义 BEAUTY_ENV_LOCK 之后它恒
// 返回 nullptr，调用点原有的 `if (e && *e) {...} else {默认值}` 自然落到默认
// 分支 —— 116 处**不需要改任何逻辑**，只换函数名。
//
// 两个构建（源码同一份，差一个宏）：
//   02_构建\build_1.0.13.10.bat      发布版：加锁，BEAUTY_* 全部失效
//   02_构建\build_1.0.13.10_dev.bat  诊断版：不加锁，与 1.0.13.9 行为一致
//
// 注意：加锁版不能再拿环境变量做 A/B（05_验证\ab_run.py 已加前置检查，会直接
// 报错而不是静默给出"开关无效"的结果）。要 A/B 就装诊断版，版本串相同，
// 靠日志首行的 `env override: on/off` 区分。
// ---------------------------------------------------------------------------

#include <stdlib.h>

#ifdef BEAUTY_ENV_LOCK
#define BEAUTY_ENV_ALLOWED 0
// 发布构建：所有 BEAUTY_* 覆盖失效。参数只为让调用点原样保留。
static inline const char *beauty_env(const char *) { return nullptr; }
#else
#define BEAUTY_ENV_ALLOWED 1
static inline const char *beauty_env(const char *name) { return getenv(name); }
#endif

// 供日志与台架前置检查用：发布版恒 false。
static inline bool beauty_env_enabled() { return BEAUTY_ENV_ALLOWED != 0; }
