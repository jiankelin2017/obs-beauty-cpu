// spawn_bench.cpp —— 测「创建 N 个 std::thread、跑一点活、join」的纯开销
//
// 目的：quantify 生产路径每个 runRange 调用都 new 一组线程的成本。
// surface3RgbBand 一帧要 21 次 runRange（3 个盒 × 3 次迭代 × 2 方向 + 3 次单趟），
// 8 线程时就是 ~168 次线程创建/销毁。若单次 60µs，一帧白烧 10ms。
//
// 编译：见 build_spawn_bench.bat
#define NOMINMAX
#include <windows.h>
#include <stdio.h>
#include <thread>
#include <vector>
#include <atomic>
#include <chrono>

static double now_ms()
{
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

// 模拟「每线程干 K 行」的最小活：等量于一次行循环的空转
static void work(int rows, std::atomic<int> *acc)
{
    int s = 0;
    for (int i = 0; i < rows * 64; i++) s += i & 7;
    acc->fetch_add(s, std::memory_order_relaxed);
}

int main(int argc, char **argv)
{
    const int threads = (argc > 1) ? atoi(argv[1]) : 8;
    const int iters = (argc > 2) ? atoi(argv[2]) : 500;
    std::atomic<int> acc{0};

    // 预热（OS 线程池缓存、TLS 分配）
    for (int i = 0; i < 20; i++) {
        std::vector<std::thread> v;
        for (int t = 0; t < threads; t++) v.emplace_back(work, 1, &acc);
        for (auto &th : v) th.join();
    }

    const double t0 = now_ms();
    for (int i = 0; i < iters; i++) {
        std::vector<std::thread> v;
        v.reserve(threads);
        for (int t = 0; t < threads; t++) v.emplace_back(work, 1, &acc);
        for (auto &th : v) th.join();
    }
    const double t1 = now_ms();

    const double per = (t1 - t0) / iters;
    printf("%d threads x %d iters: %.1f ms total, %.3f ms per batch, %.1f us per thread\n",
           threads, iters, t1 - t0, per, per * 1000.0 / threads);
    // 一帧 21 次 runRange 的推算
    printf("  一帧 21 次 runRange -> %.2f ms/frame\n", per * 21.0);
    return 0;
}
