# Runtime Data

`samples/` 由 `project.Tools.collect_samples` 自动创建，用来保存默认已去畸变的图片、标签元数据和可选录像。该目录已加入 `.gitignore`，避免大量采集数据进入源码版本管理。重新做相机内参标定时可使用 `--no-undistort` 保存原始畸变画面。

需要长期保留的小型标定配置应放在明确命名的配置目录中；不要把唯一一份标定结果只留在临时样本会话里。
