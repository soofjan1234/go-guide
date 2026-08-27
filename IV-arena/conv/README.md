# 语音/视频转文字工具 (Whisper)

这个工具用于将录音或视频文件转录为带停顿标注和自动换行的文本文件，特别适合用于面试后的自我复盘。

## 核心功能
*   **多格式支持**：支持 `.m4a`, `.mp3`, `.wav`, `.mp4`, `.mov` 等音视频格式。
*   **停顿分析**：自动识别话语中的空白时间，并在文本中插入 `[...0.5s]` 标记。
*   **自动换行**：每行限制约 30 个字，使文本结构清晰。
*   **高精度**：使用 OpenAI Whisper (Base) 模型进行中文转录。

## 环境准备 (首次使用)
工具依赖 `conda` 环境和 **Homebrew 的** `ffmpeg`。macOS 上不要把 ffmpeg / llvm-openmp 装进 conda 环境，否则 Whisper 推理时容易 `Segmentation fault: 11`（exit 139）。

1.  **安装 FFmpeg**（系统级，不要用 conda 装）:
    ```bash
    brew install ffmpeg
    ```

2.  **创建 Conda 环境**:
    可以运行 `sh run_with_conda.sh` 自动初始化，或者手动创建：
    ```bash
    conda create -n iv-helper-speech python=3.10 -y
    conda activate iv-helper-speech
    conda install nomkl -y
    pip install -r requirements.txt
    ```

3.  **清掉冲突的 conda 包**（环境里如果有就卸掉；可重复执行）:
    ```bash
    conda remove -n iv-helper-speech ffmpeg llvm-openmp -y
    ```

## 使用方法

在 `IV-arena/conv` 目录下执行。macOS 每次运行前都要带上 OpenMP 相关环境变量。

### 1. 简单用法 (直接使用 Python)
如果你已经激活了环境：
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
python transcribe.py <你的文件路径>
```

### 2. 通过 Conda 运行 (推荐)
无需手动切换环境，直接执行：
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
conda run -n iv-helper-speech python transcribe.py '文件'
```

### 3. 先转 wav 再转录（推荐，尤其是长录音 / 仍崩溃时）
Whisper 内部会再采样到 16 kHz；先转成 wav 可以避开部分 AAC 解码路径：
```bash
ffmpeg -i input.m4a -vn -ar 16000 -ac 1 -y output.wav
export KMP_DUPLICATE_LIB_OK=TRUE
conda run -n iv-helper-speech python transcribe.py output.wav
```

若仍在进度条 `0%` 处 segfault，限制线程后再跑：
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
conda run -n iv-helper-speech python transcribe.py output.wav
```

## 排查：Segmentation fault: 11

崩溃发生在「正在转录」之后、进度条刚到 `0%`，并伴随 `OMP: Info #276`，通常是 conda 的 `llvm-openmp` / `ffmpeg` 和 pip 的 PyTorch OpenMP 抢同一套原生库。`KMP_DUPLICATE_LIB_OK=TRUE` 只能压住报错，挡不住 segfault。

处理顺序：

1. `conda remove -n iv-helper-speech ffmpeg llvm-openmp -y`
2. 确认 `which ffmpeg` 指向 `/opt/homebrew/bin/ffmpeg`
3. 转 wav + 上面的线程限制后再跑

不要再往该环境里 `conda install ffmpeg`。

## 输出结果说明
转录完成后，会在同一目录下生成一个同名的 `.txt` 文件：

> **示例内容：**
> 我刚才提到的那个项目 [...0.5s] 主要是在做穿透。
> 它的原理是基于 NAT 映射表的原理。
> [...1.2s] 面试官问我为什么要用这个技术...

## 配置调整 (transcribe.py)
*   **调整换行字数**：修改 `MAX_LINE_CHARS = 30`。
*   **调整停顿阈值**：修改 `if gap > 0.3:`。
*   **调整模型精度**：修改 `model = whisper.load_model("base")` (可选: `tiny`, `small`, `medium`)。
