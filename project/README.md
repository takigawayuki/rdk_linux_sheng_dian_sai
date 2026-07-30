# H题视觉工程开发与使用说明

本目录是 H 题“车载平衡滚球运动控制系统”的正式代码目录。

当前已经跑通前三部分：**摄像头采集与去畸变、钢球检测、厘米映射和短时遮挡跟踪**。现阶段可以用采集视频离线验证完整视觉测量链路；实时相机服务和控制通信尚未接入。

不要把“计划中的文件”误认为已经实现。本文会明确标记每一步的状态。

## 1. 总体开发大纲

| 步骤 | 内容 | 当前状态 | 本步最终输出 |
| --- | --- | --- | --- |
| 第一步 | 摄像头、120 FPS、去畸变、样本采集 | 已完成并采集真机数据 | 带真实厘米标签的清晰图片和滚动视频 |
| 第二步 | 钢球检测 | 第一版已完成 | 钢球像素中心 `(u, v)` 和置信度 |
| 第三步 | 摆杆标定和厘米映射 | 第一版已完成 | 相对 O 点的位置 `x_cm` |
| 第四步 | 一维跟踪和丢球保护 | 第一版已完成 | 平滑位置、速度、检测有效状态 |
| 第五步 | 串口/控制接口 | 18 字节协议和实时发送入口已完成，等待真机联调 | 向摆杆控制器发送实时钢球状态 |
| 第六步 | 图传、录像和完整程序编排 | 未开始 | 可参赛运行的完整视觉程序 |

当前建议先用第 16 节的实时入口测清相机采集 FPS、视觉 FPS 和串口发送频率，再进行控制板低速联调。第一版参数是根据 `Data/samples` 中 640×480、120 FPS、已去畸变的数据确定的。

### 1.1 截至 2026-07-30 的进度快照

已经完成：

- 相机默认请求 `640×480 @ 120 FPS`，采集画面默认使用已有内参去畸变。
- 已采集空槽、`-10、-5、0、+5、+10 cm` 静态图片和钢球滚动视频。
- 钢球检测第一版已完成：窄凹槽 ROI、Hough 圆检测、半径/轨迹/预测位置筛选。
- 像素到厘米的一维线性映射已完成，五个标定点 RMSE 为 `0.0665 cm`，最大标定点残差为 `0.0890 cm`。
- alpha-beta 一维跟踪已完成：最长只允许预测 `0.12 s`，超时输出 LOST，重新捕获要求连续两帧一致。
- 滚动视频离线通路已跑通：`摄像头录像 -> 检测 -> 跟踪 -> 厘米映射 -> 标注视频/统计结果`。
- 当前共有 30 个 Python 自动化测试，全部通过。
- 视觉到控制器的固定 18 字节串口协议、CRC16、实时发送入口和下位机 C 解包说明已完成。
- PC 串口助手双向联调工具已完成，支持任意字节回显、连续 18 字节测试包和 `PING/PONG` 反向确认。

尚未完成或尚未充分验收：

- 当前映射误差是标定点残差，还没有使用独立位置测试集验证最终厘米精度。
- `20260730_074905_hand_occlusion` 中手主要在凹槽下方，钢球仍然可见，因此只验证了手部邻近干扰，没有充分验证长时间完全遮挡。
- 检测置信度平均值偏低，当前数值还不能直接解释为识别正确概率。
- 预测窗口优化后，现有滚动视频的离线算法速度约 `123.8 FPS`，已越过 120 FPS。最新无界面真机测试为 `camera=32.9 Hz、rate≈30.9 Hz`；视觉约 `2 ms`、串口约 `0.4 ms`，当前瓶颈是摄像头实际送帧速度，不是视觉或串口。
- 实时入口已经改为后台持续采集并只保留最新帧，避免视觉线程排队处理旧画面；仍需在 `/dev/video0 + /dev/ttyS1` 真机上重新测量。
- Workbench 已完成“球位置外环 + 步进电机角度位置内环 + 滚球动力学”的二维动态动画，控制与物理积分为 120 Hz，画面渲染约 30 FPS。

### 1.2 下一步按什么顺序做

当前先验证实时通路，再允许电机动作。应按以下顺序推进：

1. **完成完全遮挡验收**：用不透明纸片从镜头视角完全盖住钢球约 `0.5 s`，验证状态能按 `DETECTED -> PREDICTED -> LOST -> DETECTED` 转换，并确认遮挡期间不会误锁手或结构件。
2. **补独立精度验证数据**：重新摆放若干没有参与拟合的位置，例如 `-8、-3、+3、+8 cm`，统计真实厘米误差，而不是继续使用原来的五个标定点自测。
3. **真机测速**：用 `--headless --log-interval 0.5` 运行实时入口，分别查看相机实测采集频率、视觉/发包频率和各阶段耗时。
4. **根据日志定位瓶颈**：若相机约 30 Hz，先处理摄像头模式；若相机约 120 Hz 而发送约 30 Hz，则查看 `vision/serial/ui` 毫秒数并优化对应阶段。
5. **联调控制器通信**：协议已定义；先用固定测试帧验证 CRC、浮点数和正负方向，再允许步进电机低速闭环动作。

完成真机测速且发送频率接近新鲜图像的采集频率后，才进入真正的车载实时闭环阶段。

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

当前离线通路已经跑通到这里：

```text
摄像头原始帧
    -> 镜头去畸变
    -> 根据安装方向旋转
    -> 钢球检测
    -> 遮挡跟踪
    -> 厘米映射
    -> 结果统计/标注视频
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
│   ├── vision_protocol.py              # 18 字节帧和 CRC16
│   ├── configs/
│   │   └── rod_calibration.json       # 像素到厘米的标定结果
│   └── calibration/
│       ├── __init__.py
│       ├── CameraTest_Cali_qipan.py
│       ├── camera_calibration.npz
│       └── undistorter.py
│
├── Algorithm/
│   ├── __init__.py
│   ├── KalmanFilter2D.py               # 旧参考代码，当前通路未使用
│   ├── ball_detector.py                # 凹槽 ROI + 圆检测
│   ├── ball_tracker.py                 # 一维跟踪和遮挡保护
│   └── rod_mapper.py                   # 像素/厘米映射
│
├── Services/
│   ├── __init__.py
│   ├── sample_storage.py
│   └── vision_pipeline.py              # 单帧检测/跟踪/映射编排
│
├── Tools/
│   ├── __init__.py
│   ├── collect_samples.py              # 真机采集
│   ├── calibrate_rod.py                # 静态样本拟合映射
│   ├── evaluate_vision.py              # 视频离线评估
│   ├── send_vision_packet.py           # 固定串口帧联调工具
│   ├── serial_duplex_test.py           # PC 串口助手双向测试
│   └── run_vision_serial.py            # 实时相机到串口入口
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
│   ├── test_ball_detector.py
│   ├── test_ball_tracker.py
│   ├── test_rod_mapper.py
│   ├── test_sample_storage.py
│   ├── test_undistorter.py
│   ├── test_vision_pipeline.py
│   └── test_vision_protocol.py
│
└── Data/
    ├── README.md
    └── samples/                        # 运行采集工具后自动创建

视觉串口18字节帧格式说明.md               # 给下位机开发人员的协议文档
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

这是 USB-TTL 串口传输封装，负责打开/关闭串口并完整发送字节包。18 字节字段定义和 CRC16 位于 `Driver/vision_protocol.py`，避免把协议编码与硬件操作混在一起。

实时入口 `Tools/run_vision_serial.py` 每处理完一帧就调用它发送钢球状态。完整帧格式、下位机 C 解包代码和固定测试向量见 `视觉串口18字节帧格式说明.md`。

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
Ran 19 tests
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

状态：**第一版已实现并通过现有样本验证**。

对应文件：

```text
Algorithm/ball_detector.py
Test/test_ball_detector.py
```

`BallDetector` 只处理凹槽附近的窄 ROI，再用圆半径、预期轨迹中心线和时间预测位置筛选候选。这样手出现在凹槽下方或侧面时，不会因为占据大量画面而主导检测。

当前固定参数以 640×480 无畸变画面为参考，其他等比例分辨率会缩放 ROI 和半径。更换相机安装角度、焦距或摆杆后必须重新检查参数。

输出结构：

```text
BallDetection(pixel_x, pixel_y, confidence, detected)
```

## 19. 第三步：摆杆标定与厘米映射

状态：**第一版线性映射已实现**。

重新从静态样本拟合标定：

```bash
python3 -m project.Tools.calibrate_rod
```

命令会自动读取 `Data/samples` 中带 `position_cm` 标签的静态样本，先检测每张图的钢球中心，再拟合：

```text
x_cm = 0.038896469 × u - 12.117028
```

并写入 `Driver/configs/rod_calibration.json`。当前五个标定点全部 20/20 检测成功，拟合 RMSE 为 0.0665 cm，最大标定点残差为 0.0890 cm。注意这只是标定点残差，不是独立测试集上的最终精度。

目前一维线性映射已经足够，不需要为了形式强行使用二维透视变换。若相机位置改变、杆在画面中明显倾斜或线性残差变大，再考虑一维射影/单应性。

第三步验收输出：

```text
钢球像素中心 (u, v) -> x_cm
```

## 20. 第四步：钢球跟踪与丢球保护

状态：**第一版 alpha-beta 跟踪和遮挡保护已实现**。

对应文件：

```text
Algorithm/ball_tracker.py
Test/test_ball_tracker.py
```

遮挡策略：

1. 手进入画面但没有盖住球：窄 ROI、圆尺寸、杆中心线和预测位置共同排除干扰。
2. 手完全盖住球：单摄像头没有真实观测，只允许最多 0.12 s 的位置/速度短时预测，置信度持续下降。
3. 超过 0.12 s：输出 `valid=False`，控制器必须进入丢球保护，不能继续使用猜测位置。
4. 重新出现：候选必须连续两帧位置一致才确认，避免单帧手指高光或螺丝被误认为钢球；确认延迟约 8.3 ms（120 FPS）。

不能承诺“手完全遮住多久都能跟踪”。要在长期完全遮挡时继续获得真值，只能增加另一视角摄像头或减少遮挡，这是可观测性的限制，不是换一种 PID 或视觉公式就能解决。

### 20.1 运行完整视频评估

```bash
python3 -m project.Tools.evaluate_vision \
  project/Data/samples/20260730_070947_rolling_ball/video.avi \
  --calibration project/Driver/configs/rod_calibration.json
```

作用：按视频原始 FPS 运行“检测 -> 遮挡跟踪 -> 厘米映射”，输出原始检测率、加入预测后的有效率、最长预测/丢失段、位置范围和离线处理速度。

当前 1132 帧视频结果：

```text
raw_detected: 1035/1132 = 91.4%
valid after tracking: 1067/1132 = 94.3%
longest prediction: 116.7 ms
lost runs >= 3 frames: 0-11, 1079-1131
processing: about 123.8 FPS on the current machine
```

尾部第 1079 帧以后钢球已经离开画面，手仍在附近，程序保持 LOST 而没有误锁到手；开头 12 帧也没有稳定钢球候选。检测器建立跟踪后只在预测位置附近执行 Hough，并只转换搜索 ROI 的灰度图；优化前后检测统计保持一致，离线速度由约 97 FPS 提升到约 123.8 FPS。

离线 123.8 FPS 不代表真机完整通路已经达到 120 Hz。最新 `run_vision_serial --headless` 实测为 `camera=32.9 Hz、rate≈30.9 Hz`，并且 `wait≈28 ms、vision≈2 ms、serial≈0.4 ms`。这说明程序大部分时间都在等待摄像头的新帧，当前应先检查摄像头支持模式、MJPG、曝光和 USB 链路。

### 20.2 生成短标注预览

```bash
python3 -m project.Tools.evaluate_vision \
  project/Data/samples/20260730_070947_rolling_ball/video.avi \
  --calibration project/Driver/configs/rod_calibration.json \
  --max-frames 300 \
  --output-video /tmp/h_ball_preview.avi
```

作用：只处理前 300 帧，并输出带 ROI、球心、状态、厘米位置和速度的调试视频。`DETECTED` 是当帧真实检测，`PREDICTED` 是短遮挡预测，`LOST` 表示当前结果不可用于闭环控制。

### 20.3 当前数据限制

- 画面可以先完成 `-10～+10 cm` 的通路；左右极限较紧，完整 ±12 cm 可能接近或超出画面边缘。
- 后续若题目需要可靠覆盖完整量程，应把相机稍微移远，再采集 `-12、-10、-5、0、+5、+10、+12 cm` 独立验证数据。
- 已录制 `20260730_074905_hand_occlusion`，但手主要位于凹槽下方，没有形成持续完全遮挡，仍需补录真正完全遮挡的专用视频。

### 20.4 当前手部干扰视频结果

评估命令：

```bash
python3 -m project.Tools.evaluate_vision \
  project/Data/samples/20260730_074905_hand_occlusion/video.avi \
  --calibration project/Driver/configs/rod_calibration.json \
  --output-video /tmp/hand_occlusion_result.avi
```

实测结果：

```text
frames: 1307, source FPS: 120, duration: 10.892 s
raw detected: 92.5%
valid after tracking: 99.5%
predicted: 7.3%
longest prediction: 116.7 ms
longest LOST: 16.7 ms
mean confidence: 0.535
processing with annotated-video writing: 18.1 FPS
```

当前结论：

- **已通过**：手在摆杆周围活动但没有完全挡球时，抽帧检查中绿色圆仍落在真实钢球上，没有明显误锁手指。
- **已通过**：检测短暂失败时，预测最长不超过设定的约 `120 ms`。
- **未充分测试**：超过 `120 ms` 的完全遮挡是否稳定进入 LOST，以及移开遮挡物后能否可靠重新捕获。
- `18.1 FPS` 包含 MJPEG 标注视频写入开销，不是摄像头采集 FPS，也不是纯检测速度。

下一次遮挡验收不要求人工精确控制 50 ms。直接用不透明纸片完整挡住钢球约 `0.5 s`，移开后继续录制 2 s。正确结果应该是：前 14 帧左右为黄色 PREDICTED，随后持续 LOST，纸片移开并连续确认两帧后恢复绿色 DETECTED。

## 21. 第五步：控制器通信

状态：**18 字节协议、CRC、串口封装和实时发送入口已实现，等待 USB-TTL 与控制板真机联调**。

已实现：

```text
Driver/my_serial.py
Driver/vision_protocol.py
Services/vision_pipeline.py
Tools/run_vision_serial.py
Tools/send_vision_packet.py
Tools/serial_duplex_test.py
Test/test_vision_protocol.py
Test/test_vision_pipeline.py
视觉串口18字节帧格式说明.md
```

数据包固定 18 字节，包含：

```text
0xA5 + 状态 + 偏差 cm + 位置 cm + 速度 cm/s + 帧序号 + CRC16
```

中心 O 点实时运行命令：

```bash
python3 -m project.Tools.run_vision_serial \
  --device /dev/video0 \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --target-cm 0 \
  --headless \
  --log-interval 0.5
```

第一次测 120 Hz 必须先使用 `--headless`，排除绘图和桌面显示的影响。确认通路速度后再去掉它，并用 `--preview-fps 30` 观察画面。

`--log-interval 0.5` 表示终端每 0.5 秒打印一次发送摘要，并在视觉状态进入或退出 LOST 时立即打印。示例：

```text
camera device=/dev/video0 mode=640x480 fourcc=MJPG fps=120.00 undistorted=True
TX seq=00120 status=DETECTED position= +2.35cm error= -2.35cm velocity= -8.20cm/s confidence=0.87 sent=121 rate=112.4Hz camera=119.8Hz skipped=7 ms[wait=0.7 vision=7.1 serial=0.2 ui=0.0]
```

第一行 `fps` 是摄像头驱动协商后报告的模式，不等于实际送帧速度。TX 行中 `camera` 才是后台采集线程按真实到帧时间测出的采集 FPS，`rate` 是处理新图像并成功发包的频率，`skipped` 是处理期间被较新图像覆盖的累计帧数。

`ms[wait/vision/serial/ui]` 分别表示等待新帧、视觉算法、串口写入和界面的平均耗时。判断规则如下：

- `fps≈30、camera≈30、rate≈30`：摄像头实际只输出 30 FPS，应先检查 MJPG、分辨率、USB 带宽和驱动支持模式。
- `fps≈120、camera≈120、rate≈30、vision≈30 ms`：相机正常，视觉处理是瓶颈。
- `camera≈120、rate≈120`：采集和串口通路达到目标；少量 `skipped` 表示始终使用最新帧，不会积累旧画面延迟。
- `serial` 明显变大：检查串口驱动是否阻塞；115200 波特率发送 18 字节的线速约需 `1.56 ms`，理论最高约 `641 包/s`，本身足够承载 120 Hz。

设置 `--log-interval 0` 可以关闭周期日志；不建议每帧打印，否则终端输出会降低实时速度。

`--preview-fps 30` 只限制调试窗口刷新率，不限制视觉检测和串口发送；程序不再每处理一帧都复制并绘制预览图。追求最高实时速度时添加 `--headless` 完全关闭预览。

此命令会真实打开电机控制器串口并持续发包。第一次联调必须先限制步进电机速度/角度或断开电机动力，只验证接收数据，确认误差正负方向后再闭环。

待真机完成：

1. 下位机用固定测试帧验证 CRC16 和小端 float 解包。
2. 验证 `error_cm = target_position_cm - position_cm` 的正负方向与电机机构方向。
3. 验证 DETECTED、PREDICTED、LOST 三种状态下的安全行为。
4. 测量实际发包率、丢包率和端到端延迟。

与 PC 串口助手联调时，先运行双向回显模式：

```bash
python3 -m project.Tools.serial_duplex_test \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --mode echo
```

PC 应收到 `RDK_READY`；PC 发送的任意字节应被原样回显。完整接线、HEX 连续包测试和注意事项见 `视觉串口18字节帧格式说明.md` 第 10 节。

## 22. 第六步：图传、录像和正式入口

状态：**未实现**。

计划新增：

```text
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

## 23. 新增串口代码速查

### 23.1 文件分别负责什么

| 文件 | 作用 |
| --- | --- |
| `Driver/vision_protocol.py` | 定义固定 18 字节帧、三种视觉状态、CRC16 组包和解包 |
| `Driver/my_serial.py` | 打开/关闭串口，发送完整视觉帧，读取当前收到的串口字节 |
| `Services/vision_pipeline.py` | 组合检测、跟踪和厘米映射，生成串口需要的位置、速度与偏差 |
| `Services/latest_frame_capture.py` | 后台持续采集和去畸变，只保留最新帧并测量真实采集 FPS |
| `Tools/send_vision_packet.py` | 不开摄像头，打印或发送一包固定测试数据 |
| `Tools/serial_duplex_test.py` | 与 PC 串口助手进行回显、连续视觉包和 `PING/PONG` 双向测试 |
| `Tools/run_vision_serial.py` | 正式运行实时摄像头视觉，并在每帧处理完成后发送 18 字节数据 |
| `Test/test_vision_protocol.py` | 验证 CRC、帧长度、字段解包、LOST 数据和串口接收 |
| `Test/test_vision_pipeline.py` | 验证像素位置/速度映射和 `目标 - 实测` 偏差计算 |
| `Test/test_latest_frame_capture.py` | 验证最新帧覆盖、无旧帧排队和采集异常传递 |
| `视觉串口18字节帧格式说明.md` | 提供给下位机人员的完整协议、C 解包代码和联调步骤 |

### 23.2 发送的主要数据

```text
error_cm = target_position_cm - position_cm
```

实时视觉入口统一采用以下控制坐标：

```text
小球向右运动：position_cm > 0，velocity_cm_s > 0
目标在中心：target_position_cm = 0
小球位于右侧：error_cm = 0 - position_cm < 0
```

标定文件原始方向与机构控制方向相反，因此程序默认使用 `BALL_VISION_DIRECTION = -1.0`。方向系数会同时作用于位置和速度，然后才计算误差，不能只反转 `position_cm`。

18 字节依次包含：

```text
0xA5、状态、偏差 cm、位置 cm、速度 cm/s、帧序号、CRC16
```

状态包括：

- `0x20 DETECTED`：当前帧真实检测到钢球。
- `0x21 PREDICTED`：短时间遮挡，使用不超过约 0.12 s 的预测值。
- `0x00 LOST`：没有可信位置，下位机不能继续使用位置环积分。

### 23.3 常用测试和正式发送命令

只打印固定 18 字节包，不打开串口：

```bash
python3 -m project.Tools.send_vision_packet \
  --status detected \
  --error-cm -2 \
  --position-cm 3 \
  --velocity-cm-s -2 \
  --sequence 9 \
  --print-only
```

与 PC 串口助手进行双向回显：

```bash
python3 -m project.Tools.serial_duplex_test \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --mode echo
```

#### 23.3.1 无界面高速发送给电机控制器

这是当前测速和正式控制联调优先使用的命令：

```bash
python3 -m project.Tools.run_vision_serial \
  --device /dev/video0 \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --target-cm 0 \
  --position-direction -1 \
  --headless \
  --log-interval 0.5
```

程序每处理完一张**新的摄像头图像**就发送一个 18 字节包，不会重复旧数据伪造 120 Hz。`--target-cm 0` 表示目标为中心 O 点；若题目要求稳定在右侧 `+5 cm`，改成 `--target-cm 5`。

`--position-direction -1` 是当前实测方向；它也是代码默认值，可以省略。启动后终端会打印：

```text
coordinates right-positive direction=-1 scale=1 error=target-position
```

把球手动向右移动时，确认 TX 日志中的 `position` 变为正数；向左移动时应变为负数。如果结果相反，临时改用 `--position-direction 1`，不要同时修改下位机误差符号或 `Kp` 符号。

终端重点看：

```text
camera=32.9Hz rate=30.9Hz skipped=0 ms[wait=28.0 vision=2.1 serial=0.3 ui=0.0]
```

- `camera`：后台采集线程实际取得新图像的频率。
- `rate`：视觉处理完成并成功向电机控制器发包的累计平均频率，启动后会缓慢趋于稳定。
- `skipped`：视觉处理期间被更新图像覆盖的帧数；为 0 表示视觉没有跟不上相机。
- `wait/vision/serial/ui`：等待相机、视觉、串口写入、界面显示的平均毫秒数。

最新实测 `camera=32.9 Hz、rate≈30.9 Hz`，而 `vision≈2 ms、serial≈0.4 ms`，所以当前约 30 Hz 是摄像头送帧限制，不是串口限制。

#### 23.3.2 带画面预览并发送给电机控制器

需要观察检测圆是否套住钢球时使用：

```bash
python3 -m project.Tools.run_vision_serial \
  --device /dev/video0 \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --target-cm 0 \
  --position-direction -1 \
  --preview-fps 30 \
  --log-interval 0.5
```

`--preview-fps 30` 只限制窗口绘制速度，视觉和串口仍按新图像尽可能快地运行。按 `q` 或 `Ctrl+C` 退出。追求最高速度时必须改用上一条 `--headless` 命令。

第一次联调不要直接使能步进电机闭环。先用 PC 串口助手或断开电机动力验证帧内容、CRC 和正负方向；同一个串口也不能被两个程序同时打开。

本项目目标板的 UART1 按 `/dev/ttyS1` 使用，注意设备名不是 `tty/s1`。如果以后改用插在 RDK USB 口上的 USB-TTL，设备名才通常是 `/dev/ttyUSB0`，应以目标板执行 `ls -l /dev/ttyS* /dev/ttyUSB*` 的结果为准。

### 23.4 PC 串口助手回显测试怎么使用

回显测试的数据流是：

```text
PC 发送 -> RDK UART1 接收 -> RDK 原样返回 -> PC 接收
```

它只用于验证串口接线、波特率和双向收发，不会运行视觉算法，也不应该在测试时使能电机。

#### 23.4.1 接线

```text
PC USB-TTL TX  -> RDK UART1 RX
PC USB-TTL RX  <- RDK UART1 TX
PC USB-TTL GND -- RDK GND
```

确认 USB-TTL 使用 `3.3V TTL` 电平。TX 和 RX 必须交叉，双方必须共地，不要连接 VCC。

#### 23.4.2 PC 串口助手设置

在 PC 设备管理器中找到 USB-TTL 对应的 COM 口，然后设置：

```text
波特率：115200
数据位：8
停止位：1
校验位：None
流控：None
接收显示：第一次先使用 ASCII
```

先在 PC 串口助手中打开 COM 口，再启动 RDK 程序，因为 `RDK_READY` 只在程序启动时发送一次。

#### 23.4.3 启动双向回显

在 RDK 执行：

```bash
cd /home/sunrise/rdk_linux_sheng_dian_sai

python3 -m project.Tools.serial_duplex_test \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --mode echo
```

RDK 应显示：

```text
串口 /dev/ttyS1 打开成功
mode=echo port=/dev/ttyS1 baudrate=115200
TX ASCII: RDK_READY
```

PC 应收到：

```text
RDK_READY
```

PC 使用 ASCII 发送 `hello`，应原样收到 `hello`。RDK 会显示：

```text
RX HEX: 68 65 6C 6C 6F
RX TXT: hello
TX ECHO: 68 65 6C 6C 6F
```

然后将 PC 串口助手切换为 HEX 发送，发送：

```text
01 A5 7F
```

PC 应原样收到 `01 A5 7F`。这两项都通过，才能说明 PC->RDK 和 RDK->PC 两个方向均正常。

#### 23.4.4 测试连续 18 字节视觉包

先在 RDK 按 `Ctrl+C` 结束 echo 模式，再运行：

```bash
python3 -m project.Tools.serial_duplex_test \
  --serial-port /dev/ttyS1 \
  --baudrate 115200 \
  --mode packet \
  --interval 0.5
```

PC 切换为 HEX 接收，应每隔 `0.5 s` 收到一个以 `A5 20` 开头的固定 18 字节包。帧序号每包递增，因此最后两个 CRC 字节也会变化。

PC 使用 ASCII 发送 `PING`，RDK 应回复 `PONG`，用于确认发送视觉二进制包时反向链路仍然正常。测试完成后在 RDK 按 `Ctrl+C`。

#### 23.4.5 常见问题

- `/dev/ttyS1` 不存在：执行 `ls -l /dev/ttyS*`，检查 UART1 是否在设备树中启用。
- 打开串口提示权限不足：检查当前用户是否属于串口设备对应的用户组。
- PC 收不到 `RDK_READY`：先打开 PC COM 口，再重新启动 RDK 回显程序。
- 收到乱码：确认两端都是 `115200、8N1、无校验、无流控`。
- 只能单向通信：重点检查 TX/RX 是否交叉以及 GND 是否相连。
- 串口被占用：同一时间只能运行 `serial_duplex_test`、`send_vision_packet`、`run_vision_serial` 中的一个程序，并检查 UART1 是否被系统调试终端占用。
