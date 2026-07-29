# H题视觉工程开发与使用说明

本目录是 H 题“车载平衡滚球运动控制系统”的正式代码目录。

当前只完成了第一步：**摄像头采集、镜头去畸变、样本图片/视频保存**。钢球检测、厘米坐标映射、卡尔曼跟踪和控制通信将在后续步骤逐步加入。

不要把“计划中的文件”误认为已经实现。本文会明确标记每一步的状态。

## 1. 总体开发大纲

| 步骤 | 内容 | 当前状态 | 本步最终输出 |
| --- | --- | --- | --- |
| 第一步 | 摄像头、120 FPS、去畸变、样本采集 | 代码已完成，等待真机验证 | 带真实厘米标签的清晰图片和滚动视频 |
| 第二步 | 钢球检测 | 未开始 | 钢球像素中心 `(u, v)` 和置信度 |
| 第三步 | 摆杆标定和厘米映射 | 未开始 | 相对 O 点的位置 `x_cm` |
| 第四步 | 一维卡尔曼跟踪和丢球保护 | 未开始 | 平滑位置、速度、检测有效状态 |
| 第五步 | 串口/控制接口 | 未开始 | 向摆杆控制器发送实时钢球状态 |
| 第六步 | 图传、录像和完整程序编排 | 未开始 | 可参赛运行的完整视觉程序 |

目前请只执行本文的“第一步”。没有采集到真实钢球图像之前，不应凭空编写和调整钢球阈值。

## 2. 最终系统会怎样工作

完整系统的数据流计划如下：

```text
摄像头原始帧
    -> 镜头去畸变
    -> 根据安装方向旋转
    -> 钢球检测，得到像素中心 (u, v)
    -> 摆杆坐标映射，得到 x_cm
    -> 一维卡尔曼滤波，得到位置和速度
    -> 控制器/串口

去畸变画面
    -> 画面标注
    -> 图传显示
    -> 测试录像
```

当前第一步已经跑通到这里：

```text
摄像头原始帧
    -> 镜头去畸变
    -> 根据安装方向旋转
    -> 预览
    -> 保存带厘米标签的图片或视频
```

## 3. 目录结构

```text
project/
├── __init__.py
├── README.md
│
├── Core/
│   ├── __init__.py
│   └── models.py
│
├── Driver/
│   ├── __init__.py
│   ├── camera.py
│   ├── my_serial.py
│   ├── configs/                       # 现有预留目录
│   └── calibration/
│       ├── __init__.py
│       ├── CameraTest_Cali_qipan.py
│       ├── camera_calibration.npz
│       └── undistorter.py
│
├── Algorithm/
│   ├── __init__.py
│   └── KalmanFilter2D.py
│
├── Services/
│   ├── __init__.py
│   └── sample_storage.py
│
├── Tools/
│   ├── __init__.py
│   └── collect_samples.py
│
├── Workbench/                       # 3D视觉教学与仿真前端
│   ├── src/
│   ├── tests/
│   ├── package.json
│   └── README.md
│
├── Test/
│   ├── __init__.py
│   ├── test_camera.py
│   ├── test_sample_storage.py
│   └── test_undistorter.py
│
└── Data/
    ├── README.md
    └── samples/                        # 运行采集工具后自动创建
```

`__init__.py` 用于让 Python 把目录识别为可以导入的包，一般不需要直接运行。

`Workbench` 是独立的浏览器教学与仿真平台。它当前使用虚拟相机数据，不改变第一步 Python 样本采集流程。启动方式见 `Workbench/README.md`。

## 4. 每个目录负责什么

### 4.1 `Core`：公共数据结构

`Core` 只定义不同模块之间交换的数据，不打开摄像头、不写文件，也不实现识别算法。

#### `Core/models.py`

目前包含两个数据结构。

`CameraConfig` 保存相机配置，默认值为：

```text
设备：0
分辨率：640×480
目标帧率：120 FPS
格式：MJPG
缓存深度：1
旋转：0°
去畸变：开启
去畸变 alpha：0
```

`FramePacket` 包装每一帧：

```python
FramePacket(
    frame=...,        # OpenCV 图像
    captured_at=...,  # time.monotonic() 单调时间戳
    sequence=...,     # 从 0 开始递增的帧序号
)
```

后续检测、滤波和控制都传递 `FramePacket`，而不是只传一张没有时间信息的图像。

### 4.2 `Driver`：硬件和底层协议

`Driver` 负责“怎样和硬件交互”，不负责判断钢球在哪里。

#### `Driver/camera.py`

这是全工程唯一的摄像头封装，主要完成：

- 使用 V4L2 打开摄像头。
- 请求 MJPG、`640×480 @ 120 FPS`。
- 将 OpenCV 缓冲深度设置为 1，减少旧帧积压。
- 设置可选的曝光、增益、白平衡和对焦参数。
- 加载 `camera_calibration.npz`。
- 对每一帧执行去畸变，然后按配置旋转。
- 给每帧添加时间戳和序号。
- 读取摄像头实际接受的分辨率、格式和 FPS。
- 退出时释放摄像头。

推荐的新代码调用方式：

```python
from project.Core.models import CameraConfig
from project.Driver.camera import Camera

config = CameraConfig(device="/dev/video0")

with Camera(config) as camera:
    packet = camera.capture_packet()
    frame = packet.frame  # 默认已经去畸变
```

为了兼容已有参考代码，下面的旧接口仍可使用：

```python
camera = Camera()
camera.open()
frame = camera.capture()
camera.close()
```

两种方式调用的是同一个 `Camera`，没有维护第二套摄像头代码。

#### `Driver/calibration/camera_calibration.npz`

这是已经生成的相机内参文件，当前记录：

```text
标定分辨率：640×480
棋盘格内角点：9×6
平均重投影误差：约 0.433 px
```

它保存的是矫正参数，不是可以直接打开的图片。`Camera` 会自动加载它。

这份参数只适用于标定时使用的同一颗摄像头、镜头状态和相同比例的画面。如果更换摄像头、镜头、焦距或安装硬件，应重新标定。

#### `Driver/calibration/undistorter.py`

`Undistorter` 负责：

1. 从 `.npz` 读取相机矩阵和畸变参数。
2. 根据当前分辨率计算矫正映射表。
3. 缓存映射表，避免每一帧重复计算。
4. 使用 `cv2.remap()` 输出无畸变画面。
5. 当前画面宽高比与标定不一致时拒绝运行。

正常使用不需要直接调用它，因为 `Camera` 已经自动调用。

#### `Driver/calibration/CameraTest_Cali_qipan.py`

这是完整的棋盘格标定工具。只有以下情况才需要重新运行：

- 更换摄像头。
- 更换镜头或重新调焦。
- 改变到不同宽高比的分辨率。
- 现有矫正结果仍有明显弯曲。

第一步普通钢球样本采集不需要重新运行它。

#### `Driver/my_serial.py`

这是从参考工程保留的串口封装，目前第一步没有调用。第五步接入控制器时会检查并改造通信协议。

### 4.3 `Algorithm`：视觉和滤波算法

#### `Algorithm/KalmanFilter2D.py`

这是参考工程留下的二维卡尔曼实现，目前没有接入第一步流程，也不是最终钢球滤波器。

第四步会针对本题新增一维状态：

```text
[钢球位置 x_cm, 钢球速度 vx_cm_s]
```

不要因为目录中存在该文件，就认为当前采集工具已经使用了卡尔曼滤波。

### 4.4 `Services`：可以复用的业务服务

#### `Services/sample_storage.py`

`SampleSession` 统一负责：

- 创建一次采集会话的目录。
- 保存 `session.json`。
- 保存无文字叠加的图片。
- 为每张图片追加一条 `samples.jsonl` 标签。
- 按需写入 `video.avi`。
- 结束时正确关闭录像文件。

采集命令不自行重复实现这些逻辑。以后调参工具也可以复用 `SampleSession`。

### 4.5 `Tools`：可以直接运行的开发工具

#### `Tools/collect_samples.py`

这是第一步主要使用的命令行入口，负责：

1. 读取命令行参数。
2. 创建 `CameraConfig`。
3. 调用统一 `Camera` 获取无畸变帧。
4. 显示预览窗口和实际 FPS。
5. 调用 `SampleSession` 保存图片、标签和录像。

工具脚本只负责把已有模块组合起来。

### 4.6 `Test`：自动化验证

- `test_camera.py`：检查 120 FPS 默认值、相机配置、帧序号、旋转、去畸变调用和旧接口兼容。
- `test_undistorter.py`：检查现有 `.npz` 能处理 `640×480` 图像，并拒绝错误宽高比。
- `test_sample_storage.py`：检查图片和厘米标签是否同步保存。

这些测试使用模拟摄像头或生成图像，不等同于真实摄像头验收。

### 4.7 `Data`：运行产生的数据

`Data/samples/` 会在第一次采集时自动创建。由于图片和录像较大，该目录已经加入 `.gitignore`。

## 5. 代码依赖方向

```text
Tools / 后续 main.py
    -> Services
    -> Algorithm
    -> Driver
    -> Core
```

需要遵守以下规则：

- `Core` 不导入其他业务层。
- `Driver` 不实现钢球检测。
- `Algorithm` 不直接打开摄像头、串口或录像文件。
- `Services` 组合底层能力。
- `Tools` 只解析参数和编排流程。
- 任何新功能都复用 `Driver/camera.py`，不要再次创建 `cv2.VideoCapture` 封装。

# 第一步：摄像头、去畸变与样本采集

## 6. 第一步的目标

第一步不是识别钢球，而是获得可靠的真实数据：

- 摄像头稳定输出完整摆杆画面。
- 摄像头请求 `640×480 @ 120 FPS`。
- 默认输出无畸变画面。
- 能采集空槽和多个已知厘米位置的钢球图片。
- 能录制钢球完整滚动视频。
- 每张图片都有正确的位置标签和时间信息。

## 7. 使用前准备

### 7.1 进入工程根目录

以下命令都应在仓库根目录执行：

```bash
cd /home/sunrise/rdk_linux_sheng_dian_sai
```

如果不在这个目录运行 `python3 -m project...`，Python 可能找不到 `project` 包。

### 7.2 确认摄像头设备

```bash
ls /dev/video*
```

作用：列出 Linux 当前识别的摄像头节点。

可能看到：

```text
/dev/video0
/dev/video1
```

通常先测试 `/dev/video0`。如果打开失败，再测试其他节点。

若已安装 `v4l2-ctl`，可查看摄像头支持的真实模式：

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
```

作用：确认该摄像头是否真的支持 `MJPG 640×480 @ 120 FPS`。

查看曝光、增益和对焦控制范围：

```bash
v4l2-ctl -d /dev/video0 --list-ctrls-menus
```

作用：为后续固定曝光、白平衡和对焦提供合法参数范围。

## 8. 先运行自动化测试

```bash
python3 -m unittest discover -s project/Test -t . -v
```

作用：在打开真实摄像头前，检查代码导入、默认配置、去畸变文件和样本存储逻辑。

正常结果应看到：

```text
Ran 9 tests
OK
```

这只能证明软件模块通过测试，不能证明真实摄像头已经达到 120 FPS。

## 9. 查看采集工具参数

```bash
python3 -m project.Tools.collect_samples --help
```

作用：查看所有可用参数，不会打开摄像头，也不会创建样本目录。

常用参数：

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `--device` | 摄像头编号或设备路径 | `0` |
| `--width` | 请求宽度 | `640` |
| `--height` | 请求高度 | `480` |
| `--fps` | 请求帧率 | `120` |
| `--rotation` | 输出旋转角度 | `0` |
| `--label` | 本次样本类别，必须填写 | 无 |
| `--position-cm` | 钢球相对 O 点的真实位置 | 未知 |
| `--count` | 保存多少张后退出 | `0`，不限数量 |
| `--record-video` | 同时保存连续录像 | 关闭 |
| `--headless` | 不显示窗口，自动保存 | 关闭 |
| `--interval` | 无窗口模式的自动保存间隔 | `0.5 s` |
| `--no-undistort` | 关闭去畸变，只用于原始标定数据 | 关闭 |

## 10. 第一次启动：采集 O 点图片

先把钢球静止放在摆杆中心 O 点，然后运行：

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm 0 \
  --count 20
```

这条命令表示：

```text
使用 /dev/video0
使用默认 640×480 @ 120 FPS
使用默认 camera_calibration.npz 去畸变
本次图片标签为 static_ball
钢球真实位置为 0 cm
保存满 20 张后退出
```

窗口打开后的按键：

```text
s：保存当前画面
q：结束本次采集
```

`--count 20` 不表示程序立即自动保存 20 张。交互模式下需要按 20 次 `s`；保存达到 20 张后程序自动退出。

预览窗口应显示：

```text
label: static_ball
position: +0.00 cm
saved: 已保存数量
fps: 当前程序实际读取帧率
undistorted: YES
```

如果显示 `undistorted: YES`，说明当前输出已经经过 `camera_calibration.npz` 矫正。

## 11. 按顺序采集完整样本

每个静止位置建议至少采集 20 张：

```text
-10 cm
-5 cm
0 cm
+5 cm
+10 cm
```

每次移动钢球后，都要确认实际刻度，再修改 `--position-cm`。

### 11.1 空槽

取出钢球后运行：

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label empty \
  --count 20
```

作用：为后续背景差分提供没有钢球的参考画面。空槽没有钢球位置，因此不填写 `--position-cm`。

### 11.2 `-10 cm`

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm -10 \
  --count 20
```

### 11.3 `-5 cm`

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm -5 \
  --count 20
```

### 11.4 `0 cm`

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm 0 \
  --count 20
```

### 11.5 `+5 cm`

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm 5 \
  --count 20
```

### 11.6 `+10 cm`

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm 10 \
  --count 20
```

## 12. 采集钢球滚动视频

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label rolling_ball \
  --record-video
```

作用：记录钢球从一端滚到另一端的连续无畸变画面。

滚动过程中位置不断变化，因此不填写固定的 `--position-cm`。录制完成后按 `q`，程序会正确关闭 `video.avi`。

## 13. 无显示器自动采集

例如自动采集 30 张 O 点图片，每 0.2 秒一张：

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label static_ball \
  --position-cm 0 \
  --headless \
  --count 30 \
  --interval 0.2
```

作用：适用于没有桌面窗口或通过 SSH 运行的设备。

注意：无窗口模式无法人工逐张确认清晰度，第一次采集优先使用交互模式。

## 14. 什么时候使用 `--no-undistort`

正常钢球图片、滚动视频和后续识别都不要添加这个参数。

只有重新采集棋盘格原始图、准备重新计算相机内参时才关闭矫正：

```bash
python3 -m project.Tools.collect_samples \
  --device /dev/video0 \
  --label checkerboard_raw \
  --no-undistort \
  --count 20
```

添加后，预览会显示：

```text
undistorted: NO
```

这不是运行故障，而是明确要求保存原始畸变画面。

## 15. 样本保存在哪里

每次执行采集命令都会创建一个独立目录：

```text
project/Data/samples/20260729_123000_static_ball/
├── session.json
├── samples.jsonl
├── frame_0000_seq_00000123.jpg
├── frame_0001_seq_00000180.jpg
└── video.avi
```

各文件含义：

- `session.json`：本次标签、真实位置、请求相机参数、实际相机参数、标定文件和是否去畸变。
- `samples.jsonl`：每张图片一行，记录文件名、位置、帧序号、时间戳和尺寸。
- `frame_*.jpg`：无文字叠加的默认无畸变图片。
- `video.avi`：只有添加 `--record-video` 时才存在。

预览窗口中的黄色文字不会写入图片，因此不会干扰后续钢球检测。

## 16. 如何确认 120 FPS 是否生效

程序“请求 120 FPS”不等于硬件一定输出 120 FPS。

启动时终端会打印类似：

```text
Camera: {"width": 640, "height": 480, "fps": 120.0, ...}
```

需要同时检查：

1. `fps` 是否接近 `120.0`。
2. 是否出现 `camera reports ... requested 120.00` 警告。
3. 预览窗口 FPS 是否长期稳定。
4. 运行一段时间后延迟是否持续增加。

如果摄像头实际只支持 60 FPS，程序会给出警告。不要通过修改日志或忽略警告假装达到 120 FPS，应先检查摄像头支持模式、USB 带宽和 MJPG 设置。

## 17. 第一步验收清单

- [ ] `python3 -m unittest ...` 显示全部测试通过。
- [ ] 摄像头画面覆盖完整 25 cm 摆杆。
- [ ] 预览显示 `undistorted: YES`。
- [ ] 硬件实际 FPS 接近 120，或已明确记录硬件限制。
- [ ] 空槽至少保存 20 张。
- [ ] `-10、-5、0、+5、+10 cm` 每个位置至少保存 20 张。
- [ ] 图片焦点清晰，钢球和刻度可辨认。
- [ ] 至少有一段完整滚动视频。
- [ ] `session.json` 中 `images_are_undistorted` 为 `true`。
- [ ] `samples.jsonl` 中的位置标签和实际摆放位置一致。
- [ ] 连续运行时没有不断累积延迟。

完成以上检查后，第一步才算结束。

# 后续步骤大纲

## 18. 第二步：钢球检测

状态：**未实现**。

计划新增：

```text
Algorithm/BallDetector.py
Tools/tune_ball_detector.py
Test/test_ball_detector.py
```

主要工作：

1. 读取第一步采集的空槽和钢球图片。
2. 确定摆杆 ROI。
3. 使用背景差分、轮廓面积、圆度和尺寸筛选钢球。
4. 输出像素中心 `(u, v)`、置信度和检测状态。
5. 使用固定样本建立回归测试。

第二步验收输出：

```text
BallDetection(pixel_x, pixel_y, confidence, detected)
```

## 19. 第三步：摆杆标定与厘米映射

状态：**未实现**。

计划新增：

```text
Algorithm/RodMapper.py
Tools/calibrate_rod.py
Driver/configs/rod_calibration.json
Test/test_rod_mapper.py
```

主要工作：

1. 使用第一步的 `-10、-5、0、+5、+10 cm` 样本建立对应点。
2. 先验证一维线性映射。
3. 误差不满足时再使用一维射影或二维单应性。
4. 输出相对于 O 点的 `x_cm`。
5. 统计最大绝对误差和均方误差。

第三步验收输出：

```text
钢球像素中心 (u, v) -> x_cm
```

## 20. 第四步：钢球跟踪与丢球保护

状态：**未实现**。

计划新增：

```text
Algorithm/BallTracker.py
Core/ball_state.py
Test/test_ball_tracker.py
```

主要工作：

1. 建立一维状态 `[x_cm, vx_cm_s]`。
2. 使用真实帧时间戳更新 `dt`。
3. 短时丢球允许有限预测并降低置信度。
4. 超时后将状态标记为无效。

## 21. 第五步：控制器通信

状态：**未实现**。

计划改造：

```text
Driver/my_serial.py
Services/ball_state_publisher.py
```

主要工作：

1. 定义钢球位置、速度、置信度、序号和状态位协议。
2. 加入 CRC 和接收超时判断。
3. 独立线程发送最新状态，禁止积压旧状态。

## 22. 第六步：图传、录像和正式入口

状态：**未实现**。

计划新增：

```text
Services/vision_pipeline.py
Services/video_recorder.py
Services/web_streamer.py
main.py
```

主要工作：

1. 编排采集、检测、映射、跟踪和控制线程。
2. 推送原图/结果图双路画面。
3. 按测试开始和结束保存完整录像。
4. 处理摄像头断开、丢球、网络断开和安全退出。

后续每完成一步，再把对应章节从“未实现”改为“已实现”，并补充实际运行命令和验收结果。
