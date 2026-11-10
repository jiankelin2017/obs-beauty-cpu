//

#include "beauty_onnx.h"

#include <cstdio>
#include <vector>

int main(int argc, char** argv) {
    if (argc < 2) {
        printf("usage: onnx_probe <model.onnx>\n");
        return 2;
    }
    beautycore::OnnxModel m;
    std::string err;
    if (!m.load(argv[1], err, 1)) {
        printf("load failed: %s\n", err.c_str());
        return 1;
    }
    printf("loaded: %s\n", argv[1]);
    printf("input shape:");
    for (int64_t d : m.inputShape()) printf(" %lld", (long long)d);
    printf("\noutput count: %d\n", m.outputCount());
    for (int i = 0; i < m.outputCount(); i++)
        printf("  out[%d] name=%s\n", i, m.outputName(i));

    // （cls/obj/bbox/kps × stride 8/16/32）。
    std::vector<int64_t> shape = m.inputShape();
    for (auto& d : shape)
        if (d <= 0) d = 1;                    // 动态维兜底
    size_t elems = 1;
    for (int64_t d : shape) elems *= (size_t)d;

    std::vector<float> in;
    if (argc >= 3) {
        // 第二参数：裸 RGB float32（已归一化到 0..1），长度必须等于 elems
        FILE* f = nullptr;
        if (fopen_s(&f, argv[2], "rb") != 0 || !f) {
            printf("cannot open input: %s\n", argv[2]);
            return 1;
        }
        in.resize(elems);
        const size_t got = fread(&in[0], sizeof(float), elems, f);
        fclose(f);
        if (got != elems) {
            printf("input size mismatch: got %zu, need %zu\n", got, elems);
            return 1;
        }
    } else {
        in.assign(elems, 0.f);
    }

    std::vector<beautycore::OnnxTensor> outs;
    if (!m.run(in.data(), shape, outs, err)) {
        printf("run failed: %s\n", err.c_str());
        return 1;
    }
    for (size_t i = 0; i < outs.size(); i++) {
        float mn = 1e9f, mx = -1e9f;
        for (float v : outs[i].data) {
            if (v < mn) mn = v;
            if (v > mx) mx = v;
        }
        printf("  out[%zu] %-8s shape:", i, m.outputName((int)i));
        for (int64_t d : outs[i].shape) printf(" %lld", (long long)d);
        printf("  range=[%.3f, %.3f]\n", mn, mx);
    }
    return 0;
}
