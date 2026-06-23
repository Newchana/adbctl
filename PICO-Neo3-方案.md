# PICO Neo3 群控方案

> ⚠️ 本方案中,关机/重启/打开app/温度电量监控 已在普通安卓设备验证可用,
> **同屏能否抓到 VR 全屏画面 + 休眠命令在 VR 上的行为,必须接 PICO 真机验证**。

## 一、三个场景的实现路径

### 场景1:批量启动同一个 VR 应用
```cmd
:: ① 接上 PICO 后,先列出应用找包名(第三方应用)
python adbctl.py apps 3

:: ② 防息屏(VR 最怕跑一半黑屏)
python adbctl.py keepalive

:: ③ 并发启动同一 VR 应用(所有头显)
python adbctl.py open com.xxx.yourvrapp
```
- **注意**:VR 应用首次启动可能有权限弹窗(存储/麦克风/位置),需用 `input tap x y` 模拟点击"允许",或应用支持启动参数跳过。
- 找弹窗坐标:在单台 PICO 上 `adb shell input tap` 试,或用 scrcpy 看着点。

### 场景2:同步播放 VR 视频/内容
```cmd
:: 本地视频:先推到每台设备,再用 Intent 启动播放器
python adbctl.py shell "am start -a android.intent.action.VIEW -d file:///sdcard/video.mp4 -t video/mp4"

:: 或直接启动指定播放器并传 URI(取决于播放器是否支持 deeplink)
python adbctl.py open com.pvr.video
```
- **同步精度**:并发 ADB 下发有几十毫秒差异,基本可同步(人眼/体感难以察觉)。
- **流媒体/应用内指定内容**:若应用不支持 deeplink,需 `input tap` 模拟操作(VR 3D 界面坐标需逐台标定,较麻烦)。

### 场景3:运维监控多台画面
```cmd
:: 方案A(优先试):scrcpy 多窗口同屏
python adbctl.py mirror
python adbctl.py mirror-stop    :: 一键关闭
```
**这是最大的不确定性**。验证方法见下方第三节。

---

## 二、VR 专用注意事项(和手机不同)

| 项 | 说明 |
|---|---|
| **发热** | VR 头显发热严重,批量跑前 `python adbctl.py temp`,最高温 >50°C 建议降负 |
| **电量** | VR 耗电极快,群控建议全程接充电宝/电源 |
| **防息屏** | `python adbctl.py keepalive` 设常亮;scrcpy 也带 `--stay-awake` |
| **关机后** | ADB 无法远程唤醒关机的头显,只能按电源键或用"定时开机" |
| **休眠** | VR 亮灭屏由接近传感器(戴/摘)+电源键控制,`keyevent 223` 行为不确定;实际用 keepalive 保持运行更靠谱 |
| **控制** | scrcpy 鼠标在 PICO 2D launcher 可用;VR 应用内靠手柄/头追,鼠标基本无效 |

---

## 三、网络 ADB(无线群控,VR 头显推荐)

VR 头显戴着用,USB 线碍事;多台设备用 hub 也麻烦。**网络 ADB 让头显彻底无线化**。
adbctl 已内置完整的网络 ADB 支持(已实测验证)。

### 标准流程(首次需要 USB 引导一次)

```cmd
:: ① 头显用 USB 接上,确保连着和电脑同一个 WiFi
:: ② 一键把所有 USB 设备切到网络 ADB 模式,自动打印每台 IP
python adbctl.py wifi

::    输出示例:
::    ✓ PICO_A1 [Neo3] → 10.10.10.121:5555
::    ✓ PICO_A2 [Neo3] → 10.10.10.250:5555

:: ③ 拔掉 USB 线,用 IP 批量连接
python adbctl.py connect 10.10.10.121,10.10.10.250

::    或扫描整个网段(不知道具体 IP 时,自动展开,并发连接):
python adbctl.py connect 10.10.10.1-254

:: ④ 之后所有群控命令照常,完全无线
python adbctl.py list
python adbctl.py open <VR应用包名>
python adbctl.py mirror
python adbctl.py shutdown
```

### 网络命令一览

| 命令 | 作用 |
|---|---|
| `wifi` | USB 设备一键转网络 ADB,自动打印 IP |
| `connect <ip[,ip2...]>` | 批量连接(支持 `10.0.0.1-10` 范围语法,并发,4秒超时) |
| `connect 10.0.0.1-254` | 扫描整个 /24 网段(约30秒,自动找出在线设备) |
| `disconnect` | 断开所有网络设备(USB 不受影响) |
| `disconnect <ip:port>` | 断开指定设备 |

### 网络模式注意事项

- **首次引导**必须用 USB 接一次(执行 `wifi` / `adb tcpip 5555`);之后拔线即可。
- **重启后失效**:头显重启后 adbd 默认回到 USB 模式,需重新 USB 引导 + connect。
  (如需持久化,有 root 的设备可改 `service.adb.tcp.port` 属性。)
- **PICO Neo3 是 Android 10**:走传统 `adb tcpip 5555` 方式(Android 11+ 的"无线调试配对"不适用)。
- **USB 和网络可并存**:同一台设备插着 USB 又 connect 了网络,会显示两条。批量操作时会重复执行,
  群控时建议拔掉 USB 只用网络(用 `-s ip:port` 精确指定网络设备)。
- **同网段要求**:电脑和头显必须在同一局域网/WiFi。跨网段需要路由可达。

### 在线设备去重(USB + 网络混用时)

如果同时插着 USB 又连了网络,`list` 会显示同一台设备两次。精确控制用:
```cmd
python adbctl.py -s 10.10.10.250:5555 battery     :: 只操作这一台的网络通道
```

---

## 四、真机验证清单(接上 PICO Neo3 后按顺序跑)

### 第1步:设备识别(必做)
```cmd
python adbctl.py list       :: 看 PICO 是否出现,brand 应该是 pvr/PICO,model 类似 Neo3
```
> PICO Neo3 系统基于 Android 10,brand 一般是 `pvr`,model 可能含 `Neo3`。

### 第2步:基础能力(基本能过)
```cmd
python adbctl.py ping       :: 连通
python adbctl.py temp       :: 温度
python adbctl.py battery    :: 电量
python adbctl.py apps 3     :: 列第三方应用,记下目标 VR 应用包名
python adbctl.py open pico-home   :: 启动 PICO Launcher 测试
```

### 第3步:关机/重启(验证关机命令)
```cmd
python adbctl.py reboot -y  :: 先试重启(比关机安全,能自动回来)
:: 重启回来后:
python adbctl.py shutdown -y :: 再试关机(确认 reboot -p 在 PICO 上可用)
```
> PICO OS 通常给 shell 放权,`reboot -p` 大概率可用(类似已验证的安全手机)。

### 第4步:同屏 ⭐ 最关键,决定方案可行性
```cmd
python adbctl.py mirror     :: 启动 scrcpy 多窗口
```
**然后依次观察**(在每个 scrcpy 窗口里):
- [ ] **能看到 PICO Launcher / 2D 设置界面?** → 能 = scrcpy 基础可用
- [ ] **手动启动一个 VR 全屏应用后,窗口里还有画面?**
  - 有画面(单眼合成)→ ✅ **scrcpy 完全可用**,群控同屏搞定
  - 黑屏 → ❌ scrcpy 抓不到 VR 画面,需走备选方案(见下)
  - 只有一只眼/扭曲 → ⚠️ 可用但画质差,考虑备选

### 第5步:VR 应用批量启动
```cmd
python adbctl.py open <第2步找到的VR应用包名>
```
- 观察:所有头显是否同时进入同一应用?
- 若有权限弹窗:记录坐标,用 `python adbctl.py shell "input tap x y"` 统一点"允许"。

---

## 四、同屏的备选方案(若 scrcpy 抓不到 VR 画面)

> **重要更新(基于 scrcpy 官方 issue 调研)**:scrcpy **明确支持 VR 头显投屏**
> (Meta Quest 2/3 在 Win10 上有大量成功案例)。VR 头显渲染的是双眼合图,
> 需要 `--crop` 裁出单眼 + `--render-fit=stretched` 拉伸。
> `adbctl` 已内置此能力(`--vr auto` 自动检测 VR 设备并裁剪)。
> **PICO Neo3 同为 Android-based VR,机制相同,大概率可用,接真机验证即可。**

若 `python adbctl.py mirror` 仍出现黑屏/闪烁,按以下顺序排查:

1. **画面黑屏(系统UI正常,VR应用黑)**:VR 应用可能用了独立渲染层。
   尝试加 `--display-buffer 50` 或换 `--video-source=camera`(部分设备有效)。
2. **画面闪烁**:scrcpy 3.x 老问题,4.0 已修复;确认用的是 4.0+(`scrcpy --version`)。
3. **画面是一半/双眼合图**:VR 裁剪参数不准。单台调试:
   ```cmd
   python adbctl.py -s <PICO序列号> mirror --vr off --size 1920
   :: 看清双眼合图实际尺寸后,自定义裁剪:
   python adbctl.py -s <PICO序列号> mirror --crop "1920:1920:0:0" --size 1920
   ```
4. **裁剪报错 "exceeds input area"**:crop 的宽高+偏移超过了头显实际分辨率。
   先 `python adbctl.py shell "wm size"` 看真实分辨率,再调 crop。

---

## 五、消费级方案的边界(诚实说明)

本方案**完全基于开源工具 + 普通消费级 PICO Neo3**,不依赖任何企业服务。能可靠实现:
- ✅ 关机/重启(`reboot -p`)
- ✅ 打开 VR 应用(`am start`/`monkey -p`,需先 `apps 3` 找包名)
- ✅ 防息屏(`keepalive`)
- ✅ 温度/电量监控(`temp`/`battery`)
- ✅ 多窗口同屏(scrcpy + VR 裁剪,接真机验证裁剪参数即可)
- ⚠️ "休眠":VR 概念不同,实际用 `keepalive` 保持运行 + `sleep` 尝试息屏

**消费级方案做不到的**(需要企业服务才能做的):
- ❌ 关机后远程唤醒(关机=断电,企业 MDM 也是通过预装 agent 在开机后回连,本质一样)
- ❌ 一对多实时广播级同步投屏(消费级 scrcpy 是一对一窗口,企业 vrCast 是专用 cast server 做合成广播)
- ❌ 集中管理后台/Web 控制台(消费级用命令行脚本,企业级有 GUI/云后台)

---

## 五、针对 PICO 的已知命令(待真机确认)

PICO OS 除标准 Android 命令外,部分版本有 `pvr` 系统工具(用于系统级控制):
```cmd
python adbctl.py shell "pvr"          :: 看 pvr 是否存在及子命令
python adbctl.py shell "getprop | grep -i pvr"   :: 看 PICO 专有属性
python adbctl.py shell "pm list packages | grep -i pvr"  :: 找 PICO 系统应用包名
```
