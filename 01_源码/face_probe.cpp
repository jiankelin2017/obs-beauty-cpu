
#include "beauty_face.h"

#include <cstdio>
#include <cstdlib>
#include <vector>

int main(int argc, char** argv) {
    if (argc < 5) {
        printf("usage: face_probe <model.onnx> <rgba.raw> <w> <h>\n");
        return 2;
    }
    const int w = atoi(argv[3]), h = atoi(argv[4]);
    FILE* f = nullptr;
    if (fopen_s(&f, argv[2], "rb") != 0 || !f) {
        printf("cannot open %s\n", argv[2]);
        return 1;
    }
    std::vector<unsigned char> rgba((size_t)w * h * 4);
    const size_t got = fread(&rgba[0], 1, rgba.size(), f);
    fclose(f);
    if (got != rgba.size()) {
        printf("short read %zu / %zu\n", got, rgba.size());
        return 1;
    }

    beautycore::FaceDetector det;
    std::string err;
    if (!det.load(argv[1], err)) {
        printf("load failed: %s\n", err.c_str());
        return 1;
    }
    std::vector<unsigned char> rgb((size_t)w * h * 3);
    for (size_t i = 0; i < (size_t)w * h; i++) {
        rgb[i * 3 + 0] = rgba[i * 4 + 0];
        rgb[i * 3 + 1] = rgba[i * 4 + 1];
        rgb[i * 3 + 2] = rgba[i * 4 + 2];
    }

    std::vector<beautycore::FaceBox> faces;
    if (!det.detect(&rgb[0], w, h, faces, err)) {
        printf("detect failed: %s\n", err.c_str());
        return 1;
    }
    printf("faces=%zu  %.1fms\n", faces.size(), det.lastMs());
    for (size_t i = 0; i < faces.size(); i++)
        printf("  [%zu] x=%.1f y=%.1f w=%.1f h=%.1f score=%.3f\n",
               i, faces[i].x, faces[i].y, faces[i].w, faces[i].h, faces[i].score);
    return 0;
}
