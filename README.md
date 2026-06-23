# adbctl — 安卓 / VR 设备群控工具

基于 ADB 的多设备并发群控工具,**纯开源 + 消费级设备**,不依赖任何企业服务。
支持普通安卓手机/平板,以及基于 Android 的 VR 一体机(如 PICO Neo3)。

> 在 4 台普通安卓设备(含无 root 设备)上实测通过:关机、休眠、打开 App、同屏、网络 ADB 全部可用。

## 特性

- 🖥️ **多设备并发** —— 线程池并发,设备越多越省时(4 台耗时 ≈ 1 台)
- 🔌 **USB + 网络 ADB 混合** —— 支持 wifi/tcpip 无线群控,VR 头显彻底无线化
- 📱 **手机 + VR 自适应** —— 同屏自动检测 VR 设备,双眼合图自动裁剪单眼显示
- 🔋 **运维监控** —— 温度 / 电量 / 防息屏,VR 发热监控必备
- 🚫 **无 root 也能关机** —— 已验证多款设备 `reboot -p` 无需 root 可用
- 🎯 **零外部依赖** —— 纯 Python 标准库,Windows 开箱即用

## 依赖

| 组件 | 用途 | 安装 |
|---|---|---|
| Python 3.7+ | 运行本工具 | 已有 |
| ADB (platform-tools) | 设备通信 | 脚本自动探测 Android Studio 路径 |
| scrcpy 4.0+ | 同屏投屏 | `winget install Genymobile.scrcpy` |

## 快速开始

```cmd
cd android-fleet

:: 查看所有在线设备
python adbctl.py list

:: 全部亮屏 / 息屏
python adbctl.py wake
python adbctl.py sleep

:: 全部打开指定应用(支持别名或包名)
python adbctl.py open calc
python adbctl.py open com.tencent.mm

:: 全部关机(会二次确认)
python adbctl.py shutdown
python adbctl.py shutdown -y     :: 跳过确认

:: 多窗口同屏(scrcpy,自动网格布局)
python adbctl.py mirror
python adbctl.py mirror-stop     :: 一键关闭全部投屏窗口

:: 只控部分设备
python adbctl.py -s 序列号1,序列号2 sleep
```

## 命令一览

| 命令 | 作用 |
|---|---|
| `list` | 列出所有在线设备(含屏幕状态 / Android 版本) |
| `wake` / `sleep` / `lock` | 全部唤醒 / 息屏 / 锁屏 |
| `open <app>` / `close <app>` | 打开 / 关闭应用(支持别名或包名) |
| `shutdown` / `reboot` | 全部关机 / 重启(带二次确认) |
| `mirror` / `mirror-stop` | scrcpy 多窗口同屏 / 一键关闭 |
| `apps [3]` | 列出应用包名(`3` = 仅第三方,用于找 VR 应用包名) |
| `temp` / `battery` | 温度监控(VR 发热必看) / 电量 |
| `keepalive` | 设置屏幕常亮(防息屏) |
| `screenshot [dir]` | 全部截图到目录 |
| `shell "<cmd>"` | 全部执行任意 shell 命令 |
| `ping` | 连通性自检 |
| `wifi` | USB 设备一键转网络 ADB,自动打印 IP |
| `connect <ip>` | 批量连接网络设备(支持 `10.0.0.1-10` 范围语法) |
| `disconnect` | 断开网络设备 |

### 选项

```
-s, --serial <序列号>     只操作指定设备(逗号分隔)
-y                        跳过关机/重启确认
--size <像素>             mirror 投屏最大尺寸(默认 1024)
-r, --read-only           mirror 只看不控
--fps <帧率>              mirror 最大帧率
--vr {auto,on,off}        VR 投屏裁剪模式(默认 auto 自动检测)
--crop "W:H:X:Y"          VR 自定义裁剪(覆盖预设)
```

## 网络 ADB(无线群控)

VR 头显戴着用 USB 线碍事;多台用 hub 也麻烦。网络 ADB 让设备彻底无线化:

```cmd
:: ① 头显 USB 接一次,确保连着同一 WiFi
:: ② 一键转网络 ADB,自动打印每台 IP
python adbctl.py wifi

:: ③ 拔掉 USB,用 IP 批量连接
python adbctl.py connect 10.10.10.121,10.10.10.250

::    或扫描整个网段(自动找出在线设备):
python adbctl.py connect 10.10.10.1-254

:: ④ 之后完全无线,所有命令照常
python adbctl.py list / open <app> / mirror / shutdown
```

> **注意**:首次必须 USB 引导一次;设备重启后 adbd 回到 USB 模式,需重新引导 + connect。

## VR 设备同屏(PICO Neo3 / Quest)

VR 头显渲染双眼合图,scrcpy 需要 `--crop` 裁出单眼。本工具已内置(`mirror` 默认 `--vr auto` 自动检测):

```cmd
python adbctl.py mirror                    :: 自动检测 VR 设备并裁剪
python adbctl.py mirror --vr on            :: 强制 VR 模式
python adbctl.py mirror --crop "1920:1920:0:0"  :: 自定义裁剪
```

VR 裁剪参数因头显分辨率而异,接真机后用 `python adbctl.py shell "wm size"` 查看实际分辨率再微调。
详细方案见 [`PICO-Neo3-方案.md`](./PICO-Neo3-方案.md)。

## App 别名表

`open` 命令支持短名:`calc` `settings` `camera` `browser` `clock` `gallery` `music` `phone`,
以及 PICO 应用:`pico-home` `pico-settings` `pico-store` `pico-video`。
也可直接传包名(`com.xxx.yy`)或完整 Activity(`com.xx/.MainActivity`)。
扩展别名编辑 `adbctl.py` 的 `APP_ALIASES` 字典。

## 许可证

MIT
