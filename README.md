# 健康助手 · 桌面宠物提醒

一个基于 Python + Tkinter 的 Windows 桌面健康提醒工具。支持喝水、站立、护眼、运动提醒，并集成桌面宠物、宠物图鉴、番茄时钟、免打扰和局域网好友提醒。

## 功能概览

- 健康提醒：喝水、站立、护眼、运动四类定时提醒。
- 答题关闭：可选开启，定时健康提醒需要输入简单算术题答案才能关闭。
- 临时免打扰：可设置 30 分钟、1 小时、2 小时或当天自定义恢复时间。
- 桌面宠物：支持透明背景宠物、抽卡、命名、互动、图鉴、心情、生命天数。
- 宠物番茄时钟：右键宠物开启 25 分钟专注倒计时；专注期间不弹健康提醒、不霸屏、不切换宠物对话。
- 护眼训练：可从主界面或提醒入口打开护眼训练页面，训练超过 1 分钟后可自动统计。
- 好友功能：局域网发现好友、发送提醒、查看好友健康数据。
- 打包发布：提供 PyInstaller 单文件 exe 打包配置。

## 运行环境

- Windows 10/11
- Python 3.7+

安装依赖：

```powershell
pip install -r requirements.txt
```

运行源码：

```powershell
python drink_water_reminder.py
```

## 常用操作

### 设置提醒

打开应用后进入“设置”，可以调整：

- 昵称
- 提醒间隔
- 休眠时段
- 是否关闭提醒时需要答题
- 是否启动应用时自动召唤桌面宠物
- 主题颜色

### 使用桌面宠物

主界面点击“召唤宠物”，或在设置中开启“启动应用时自动打开桌面宠物”。

宠物右键菜单支持：

- 开始番茄时钟
- 查看今日进度
- 记录喝水
- 开始护眼
- 设置免打扰
- 修改名称
- 重新抽宠物
- 宠物图鉴
- 关闭宠物

### 自定义宠物图片

宠物资源目录：

```text
assets/desktop_pets/
```

每只宠物一个独立文件夹。推荐命名：

```text
idle_0.png      默认展示
idle_1.png      普通互动动作
idle_2.png      普通互动动作
happy.png       正向反馈
unhappy.png     负向/关心提醒
sleep.png       休息/夜间状态，可选
drink.png       喝水提醒专用，可选
eye.png         护眼提醒专用，可选
stand.png       站立提醒专用，可选
sport.png       运动提醒专用，可选
```

图片建议使用透明背景 PNG。

## 测试

当前项目保留了轻量回归检查脚本：

```powershell
python test_dashboard_ui.py
python test_reminder_challenge.py
python test_protocol_and_config.py
```

## 打包 exe

推荐使用项目内的单文件版 spec：

```powershell
$env:TEMP='E:\course\drink_water_reminder\tmp_build'
$env:TMP='E:\course\drink_water_reminder\tmp_build'
$env:PYINSTALLER_CONFIG_DIR='E:\course\drink_water_reminder\tmp_pyinstaller_cache'
pyinstaller --clean --noconfirm '健康助手单文件版.spec'
```

打包产物默认输出到：

```text
dist/健康助手单文件版.exe
```

对外分享时，建议把 exe 上传到 GitHub Releases，不要直接提交到仓库。

## GitHub 发布建议

源码仓库建议提交：

- `*.py`
- `assets/`
- `护眼/`
- `*.spec`
- `README.md`
- `CHANGELOG.md`
- `requirements.txt`
- `test_*.py`

不要提交：

- `build/`
- `dist/`
- `发布版/`
- `archive/`
- `tmp_build/`
- `tmp_pyinstaller_cache/`
- 用户数据 JSON
- 日志文件
- exe 文件

## 数据与隐私

应用会在本地生成配置、健康记录、好友数据和日志文件。默认 `.gitignore` 已排除这些文件，避免误传个人数据。

## 许可证

如果要公开给其他用户使用，建议补充开源许可证，例如 MIT License。许可证会影响别人是否可以复制、修改和二次分发代码。
