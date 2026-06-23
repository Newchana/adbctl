#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adbctl.py — 安卓 / VR 设备群控工具 (ADB 多设备并发)

纯开源 + 消费级设备,不依赖任何企业服务。支持普通安卓手机/平板和 VR 一体机(PICO Neo3 等)。

用法:
  python adbctl.py list                      # 列出所有在线设备(含屏幕状态/版本)
  python adbctl.py wake                      # 全部唤醒(亮屏)
  python adbctl.py sleep                     # 全部息屏(休眠)
  python adbctl.py lock                      # 全部锁屏
  python adbctl.py shutdown                  # 全部关机   (会二次确认)
  python adbctl.py reboot                    # 全部重启   (会二次确认)
  python adbctl.py open <app>                # 全部打开 app(支持别名/包名/Activity)
  python adbctl.py close <app>               # 全部强制停止 app
  python adbctl.py apps [3]                  # 列出应用包名(3=仅第三方)
  python adbctl.py temp                      # 温度监控(VR 发热必看)
  python adbctl.py battery                   # 电量监控
  python adbctl.py keepalive                 # 设置屏幕常亮(防息屏)
  python adbctl.py mirror                    # 多窗口同屏(scrcpy,自动网格布局)
  python adbctl.py mirror-stop               # 一键关闭全部投屏窗口
  python adbctl.py screenshot [dir]          # 全部截图到目录
  python adbctl.py shell "<cmd>"             # 全部执行任意 shell 命令
  python adbctl.py ping                      # 连通性自检

网络 ADB(无线群控):
  python adbctl.py wifi                      # USB 设备一键转网络 ADB,打印 IP
  python adbctl.py connect <ip[,ip2...]>     # 批量连接(支持 10.0.0.1-10 范围)
  python adbctl.py disconnect [ip]           # 断开网络设备(空=全部)

选项:
  -s SERIAL[,SERIAL2...]   只操作指定设备(默认全部在线设备)
  -y                       跳过关机/重启的二次确认
  --size <像素>            mirror 投屏最大尺寸(默认 1024)
  -r, --read-only          mirror 只看不控
  --fps <帧率>             mirror 最大帧率
  --vr {auto,on,off}       VR 投屏裁剪模式(默认 auto 自动检测)
  --crop "W:H:X:Y"         VR 自定义裁剪(覆盖预设)

app 别名(可直接写短名):
  calc/计算器  settings/设置  camera/相机  browser/浏览器
  clock/时钟  gallery/相册  music/音乐  phone/电话
  pico-home  pico-settings  pico-store  pico-video

也可直接写包名(com.xx)或完整 Activity(com.xx/.MainActivity)。
"""

import os
import re
import sys
import time
import shutil
import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------- ADB 路径自动探测 ----------
def find_adb():
    adb = shutil.which("adb") or shutil.which("adb.exe")
    if adb:
        return adb
    candidates = [
        r"C:\Users\j1352\AppData\Local\Android\Sdk\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\Android\Sdk\platform-tools\adb.exe",
        "/c/Users/j1352/AppData/Local/Android/Sdk/platform-tools/adb.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "adb"  # 退回 PATH

ADB = find_adb()

# ---------- scrcpy 路径自动探测 ----------
def find_scrcpy():
    import glob
    s = shutil.which("scrcpy") or shutil.which("scrcpy.exe")
    if s:
        return s
    pats = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Genymobile.scrcpy_*\scrcpy-win64-*\scrcpy.exe"),
        r"C:\Program Files\scrcpy\scrcpy.exe",
        r"C:\tools\scrcpy\scrcpy.exe",
    ]
    for pat in pats:
        for m in glob.glob(pat):
            if os.path.exists(m):
                return m
    return None

SCRCPY = find_scrcpy()

# ---------- app 别名表 ----------
APP_ALIASES = {
    "calc": "com.android.calculator2",
    "计算器": "com.android.calculator2",
    "settings": "com.android.settings",
    "设置": "com.android.settings",
    "camera": "com.fih.camera",
    "相机": "com.fih.camera",
    "browser": "com.android.browser",
    "浏览器": "com.android.browser",
    "clock": "com.android.deskclock",
    "时钟": "com.android.deskclock",
    "gallery": "com.android.gallery3d",
    "相册": "com.android.gallery3d",
    "music": "com.android.music",
    "音乐": "com.android.music",
    "phone": "com.android.dialer",
    "电话": "com.android.dialer",
    # ---- PICO Neo3 VR 应用(包名因 PICO OS 版本而异,接真机后用 'apps' 命令核对)----
    "pico-home": "com.pvr.android.products",   # PICO Launcher
    "pico-settings": "com.pvr.android.settings",
    "pico-store": "com.pico.store",
    "pico-video": "com.pvr.video",
}

# ---------- 颜色 ----------
class C:
    G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[96m"
    D = "\033[90m"; BOLD = "\033[1m"; END = "\033[0m"
def color(s, c): return f"{c}{s}{C.END}" if sys.stdin.isatty() else s

# ---------- 设备发现 ----------
def list_devices():
    out = run([ADB, "devices", "-l"])
    devs = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            info = {"serial": serial, "product": "", "model": ""}
            for p in parts[2:]:
                if ":" in p:
                    k, v = p.split(":", 1)
                    info[k] = v
            devs.append(info)
    return devs

def run(cmd, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return "<TIMEOUT>"
    except Exception as e:
        return f"<ERROR: {e}>"

def adb_shell(serial, script, timeout=30, su=False):
    if su:
        # 通过 su 提权执行(magisk 兼容)
        script = f"su -c {shellquote(script)}"
    return run([ADB, "-s", serial, "shell", script], timeout=timeout).strip()

def shellquote(s):
    return "'" + s.replace("'", "'\\''") + "'"

# ---------- 设备显示名 ----------
def dev_label(d):
    m = d.get("model") or d.get("product") or ""
    return f"{d['serial']}" + (f" [{m}]" if m else "")

# ---------- 对单台设备执行一个动作,返回 (serial, ok, msg) ----------
def exec_action(d, action, arg):
    s = d["serial"]
    try:
        if action == "wake":
            adb_shell(s, "input keyevent 224")  # WAKEUP
            return s, True, "已唤醒"
        if action == "sleep":
            adb_shell(s, "input keyevent 223")  # SLEEP
            return s, True, "已息屏"
        if action == "lock":
            adb_shell(s, "input keyevent 223")
            return s, True, "已锁屏/息屏"
        if action == "shutdown":
            return _do_reboot(s, "-p", "关机")
        if action == "reboot":
            return _do_reboot(s, "", "重启")
        if action == "open":
            target = resolve_app(arg)
            if not target:
                return s, False, f"无法识别 app: {arg}"
            if "/" in target or "." in target and target.startswith("com."):
                # 可能带 Activity 或纯包名
                out = adb_shell(s, monkey_or_am(target))
            else:
                out = adb_shell(s, monkey_or_am(target))
            if "Error" in out or "error" in out:
                return s, False, out[:200]
            return s, True, f"已打开 {target}"
        if action == "close":
            pkg = resolve_app(arg) if arg else ""
            if not pkg:
                return s, False, "缺少包名"
            adb_shell(s, f"am force-stop {pkg}")
            return s, True, f"已停止 {pkg}"
        if action == "uninstall":
            pkg = resolve_app(arg) if arg else ""
            if not pkg:
                return s, False, "缺少包名"
            out = run([ADB, "-s", s, "uninstall", pkg])
            return s, "Success" in out, out.strip()[:200]
        if action == "screenshot":
            return screenshot(s, arg)
        if action == "shell":
            out = adb_shell(s, arg, timeout=60)
            return s, True, out
        if action == "ping":
            out = adb_shell(s, "echo OK")
            return s, out.strip() == "OK", out.strip()
        if action == "temp":
            # VR 头显发热严重,批量跑必须监控温度(毫℃→℃)
            out = adb_shell(s, "cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null")
            temps = []
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit() or (line.startswith("-") and line[1:].isdigit()):
                    temps.append(int(line) / 1000.0)
            cpu_out = adb_shell(s, "dumpsys cpuinfo 2>/dev/null | head -1")
            if temps:
                return s, True, f"温度 {max(temps):.1f}°C (共{len(temps)}个传感器,最高) | CPU:{cpu_out.strip()[:30]}"
            return s, False, "读取温度失败"
        if action == "battery":
            out = adb_shell(s, "dumpsys battery")
            level = "?"; status = "?"; temp = "?"
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("level:"): level = line.split(":", 1)[1].strip()
                elif line.startswith("status:"): status = {"2":"充电中","3":"放电中","4":"未充电","5":"充满"}.get(line.split(":",1)[1].strip(), line.split(":",1)[1].strip())
                elif line.startswith("temperature:"):
                    t = line.split(":", 1)[1].strip()
                    temp = f"{int(t)/10:.1f}°C" if t.isdigit() else t
            return s, True, f"电量 {level}% | {status} | 电池{temp}"
        if action == "keepalive":
            # VR 群控最怕中途息屏,设置屏幕常亮
            adb_shell(s, "settings put system screen_off_timeout 2147483647")
            adb_shell(s, "svc power stayon true")
            return s, True, "已设为屏幕常亮(防息屏)"
        if action == "apps":
            # 列出第三方/所有包名 — 用来找 VR 应用包名
            flag = "-3" if (arg and arg == "3") else ""
            out = adb_shell(s, f"pm list packages {flag}".strip())
            pkgs = [l.replace("package:", "").strip() for l in out.splitlines() if l.startswith("package:")]
            return s, True, f"共{len(pkgs)}个应用: " + ", ".join(pkgs[:40]) + (" ..." if len(pkgs) > 40 else "")
        return s, False, f"未知动作: {action}"
    except Exception as e:
        return s, False, f"异常: {e}"

def _has_root(serial):
    """检测设备是否可 su 提权(不执行危险动作)"""
    try:
        out = adb_shell(serial, "su -c id", timeout=4)
        return "uid=0" in out
    except Exception:
        return False

def _do_reboot(serial, flag, label):
    """关机/重启:有 root 用 su;无 root 试普通 reboot。flag='' 重启,'-p' 关机"""
    cmd_core = "reboot" + ((" " + flag) if flag else "")
    if _has_root(serial):
        adb_shell(serial, cmd_core, su=True, timeout=8)
        return serial, True, f"已{label} (root: su {cmd_core})"
    # 无 root:尝试普通 reboot(部分固件允许 shell 用户调用)
    out = adb_shell(serial, cmd_core, timeout=8)
    low = (out or "").lower()
    # reboot 成功时设备会立即断开,命令通常无输出或连接中断(也属成功)
    if any(k in low for k in ("not permitted", "denied", "permission denied", "operation not permitted")):
        return serial, False, f"无 root 且系统拒绝 {cmd_core}，需 root 或手动{label}"
    return serial, True, f"已{label} (非root: {cmd_core})"

def resolve_app(name):
    if not name:
        return ""
    name = name.strip()
    if name in APP_ALIASES:
        return APP_ALIASES[name]
    return name

def monkey_or_am(target):
    """纯包名用 monkey 启动更稳;带 / 用 am start -n"""
    if "/" in target:
        return f"am start -n {target}"
    return f"monkey -p {target} -c android.intent.category.LAUNCHER 1"

def screenshot(serial, outdir):
    outdir = outdir or "."
    os.makedirs(outdir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_serial = re.sub(r"[^\w\-.]", "_", serial)   # 网络设备 ip:port 的冒号在 Windows/Android 均非法
    remote = f"/sdcard/_shot_{safe_serial}_{ts}.png"   # 远端也用安全名(Android fs 同样禁冒号)
    local = os.path.join(outdir, f"{safe_serial}_{ts}.png")
    adb_shell(serial, f"screencap -p {remote}")
    run([ADB, "-s", serial, "pull", remote, local])
    adb_shell(serial, f"rm {remote}")
    if os.path.exists(local):
        return serial, True, f"截图: {os.path.abspath(local)}"
    return serial, False, "截图失败"

# ---------- 并发执行 ----------
def run_all(devices, action, arg=None, confirm_msg=None, assume_yes=False):
    if confirm_msg and not assume_yes:
        print(color(f"\n⚠ {confirm_msg}\n即将对 {len(devices)} 台设备执行,输入 y 继续: ", C.Y),
              end="", flush=True)
        if input().strip().lower() not in ("y", "yes"):
            print("已取消。")
            return
    print(color(f"\n▶ 对 {len(devices)} 台设备并发执行 [{action}] …", C.B))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=min(16, max(1, len(devices)))) as ex:
        futs = {ex.submit(exec_action, d, action, arg): d for d in devices}
        for f in as_completed(futs):
            serial, ok, msg = f.result()
            tag = color("✓", C.G) if ok else color("✗", C.R)
            print(f"  {tag} {color(serial, C.BOLD)} {color(msg, C.D if ok else C.R)}")
    print(color(f"  done in {time.time()-t0:.2f}s\n", C.D))

# ---------- 同屏 (scrcpy 多窗口) ----------
# VR 头显双眼合图裁剪参数(宽度:高度:偏移X:偏移Y),参考 scrcpy 官方 VR issue
# PICO Neo3 实际分辨率约 4K 宽双眼,单眼约一半;接真机后需标定微调
VR_CROP_PRESETS = {
    # 默认双眼合图裁出单眼,render-fit=stretched 拉满显示
    "default": "--crop 1920:1920:0:0 --render-fit=stretched",
    "neo3":    "--crop 1920:1920:0:0 --render-fit=stretched",
    "quest2":  "--crop 1832:1920:0:0 --render-fit=stretched",
    "quest3":  "--crop 2064:2208:0:0 --render-fit=stretched",
}

def _is_vr_device(d):
    """检测是否为 VR 头显(PICO/Meta Quest 等)"""
    m = (d.get("model", "") + " " + d.get("product", "")).lower()
    return any(k in m for k in ("neo3", "pico", "quest", "oculus", "vr"))

def cmd_mirror(devs, max_size=1024, read_only=False, fps=0, vr_mode="auto", vr_crop=None):
    if not SCRCPY:
        print(color("✗ 未找到 scrcpy。请先安装: winget install Genymobile.scrcpy", C.R))
        return
    n = len(devs)
    if n == 0:
        print(color("没有在线设备。", C.R)); return
    import math
    try:
        import ctypes
        user32 = ctypes.windll.user32
        try: user32.SetProcessDPIAware()
        except Exception: pass
        sw = user32.GetSystemMetrics(0)   # 屏幕宽(逻辑像素)
        sh = user32.GetSystemMetrics(1)   # 屏幕高
    except Exception:
        sw, sh = 1920, 1080

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    cell_w = sw // cols
    cell_h = (sh - 60) // rows            # 底部留任务栏

    env = os.environ.copy()
    env["ADB"] = ADB                       # 关键:复用同一个 adb server
    print(color(f"\n▶ 启动 {n} 个 scrcpy 窗口(网格 {rows}x{cols}, 屏幕 {sw}x{sh})…", C.B))
    def _start(scrcpy_cmd):
        """启动一个 scrcpy,带 1 次重试(避免并发 push scrcpy-server 冲突)"""
        for attempt in range(2):
            try:
                p = subprocess.Popen(scrcpy_cmd, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            except Exception as e:
                return None, str(e)
            time.sleep(0.8)              # 等 server 推送 + 稳定
            if p.poll() is None:
                return p, None
            time.sleep(0.4)              # 失败则稍等后重试
        return p, "启动后立即退出(adb server 可能瞬时繁忙)"

    launched = 0
    for i, d in enumerate(devs):
        r, c = divmod(i, cols)
        x = c * cell_w + 8
        y = 60 + r * cell_h + 8
        w = cell_w - 16
        h = cell_h - 16
        title = f"{d.get('model') or d['serial']} · {d['serial'][:12]}"
        cmd = [SCRCPY, "-s", d["serial"], "--window-title", title,
               "--window-x", str(x), "--window-y", str(y),
               "--window-width", str(w), "--window-height", str(h),
               "--max-size", str(max_size), "--stay-awake"]
        if read_only:
            cmd.append("--no-control")
        if fps:
            cmd += ["--max-fps", str(fps)]

        # VR 裁剪模式:auto=自动检测VR设备;on=强制VR;off=强制普通
        use_vr = False
        if vr_mode == "on":
            use_vr = True
        elif vr_mode == "auto":
            use_vr = _is_vr_device(d)
        if use_vr:
            crop_args = vr_crop if vr_crop else VR_CROP_PRESETS.get("neo3", VR_CROP_PRESETS["default"])
            cmd += crop_args.split()
            title = "[VR] " + title

        p, err = _start(cmd)
        if p is not None and p.poll() is None:
            launched += 1
            vr_tag = color(" (VR裁剪)", C.Y) if use_vr else ""
            print(f"  {color('✓', C.G)} {color(d['serial'], C.BOLD)}  pid={p.pid}  →  {title}{vr_tag}")
        else:
            print(f"  {color('✗', C.R)} {d['serial']} 启动失败: {err}")
    print(color(f"\n已启动 {launched}/{n} 个窗口。", C.BOLD))
    print(color("  关闭窗口即可停止;或运行 'python adbctl.py mirror-stop' 一键关闭全部。", C.D))

def cmd_mirror_stop():
    r = subprocess.run(["taskkill", "/IM", "scrcpy.exe", "/F"],
                       capture_output=True)
    try:
        out = r.stdout.decode("gbk", "replace") + r.stderr.decode("gbk", "replace")
    except Exception:
        out = ""
    n = out.count("PID") if r.returncode == 0 else 0
    print(color(f"已发送关闭指令(taskkill)。{('已终止 ' + str(n) + ' 个进程') if n else '(无运行中的 scrcpy)'}", C.B))

# ---------- 网络 ADB (wifi) ----------
def parse_hosts(spec, default_port=5555):
    """解析 IP 列表:支持 'a,b,c' / 'a-b' 范围 / 'ip:port' / 'ip' """
    hosts = []
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        # 范围 10.0.0.250-252
        m = re.match(r"^(\d+\.\d+\.\d+\.)(\d+)-(\d+)(?::(\d+))?$", part)
        if m:
            prefix, start, end, port = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            port = int(port) if port else default_port
            for i in range(start, end + 1):
                hosts.append(f"{prefix}{i}:{port}")
            continue
        # 单个 ip[:port]
        if ":" not in part.split(".")[-1]:   # 没带端口(纯 IPv4)
            hosts.append(f"{part}:{default_port}")
        else:
            hosts.append(part)
    return hosts

def cmd_wifi(port=5555):
    """把当前所有 USB 设备切到网络 ADB 模式,并打印每台 IP(方便拔线后 connect)"""
    devs = list_devices()
    usb_devs = [d for d in devs if ":" not in d["serial"]]   # 排除已是网络的
    if not usb_devs:
        print(color("没有 USB 连接的设备(网络设备无需此操作)。", C.Y))
        return
    print(color(f"\n▶ 将 {len(usb_devs)} 台 USB 设备切换到网络 ADB(端口 {port})…", C.B))
    results = []
    for d in usb_devs:
        s = d["serial"]
        # 1) 切 tcpip 模式
        out = run([ADB, "-s", s, "tcpip", str(port)], timeout=10)
        ok_tcp = "restarting" in out or "Restarting" in out
        # 2) 轮询等待 USB 连接恢复(adbd 重启会断开 2-3 秒),最多等 6 秒
        ip = ""
        for _ in range(6):
            time.sleep(1)
            if run([ADB, "-s", s, "get-state"], timeout=3).strip() == "device":
                ip = adb_shell(s, "ip -f inet addr show wlan0 2>/dev/null | grep 'inet ' | awk '{print $2}'", timeout=4)
                ip = ip.split("/")[0].strip() if "/" in ip else ""
                if not ip:   # fallback: 接口名不一定是 wlan0(部分设备用 wlan1/eth0)
                    ip = adb_shell(s, "ip -f inet addr 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | awk '{print $2}' | head -1", timeout=4)
                    ip = ip.split("/")[0].strip() if "/" in ip else ""
                if ip:
                    break
        if ok_tcp and ip:
            host = f"{ip}:{port}"
            results.append((s, d.get("model",""), host))
            print(f"  {color('✓', C.G)} {color(s, C.BOLD)} [{d.get('model','?')}] → {color(host, C.G)}")
        else:
            print(f"  {color('✗', C.R)} {s} 切换失败(ip={ip or '无'}, out={out.strip()[:60]})")
    if results:
        ips = ",".join(h for _, _, h in results)
        print(color(f"\n✅ 切换完成。拔线后执行以下命令连接:", C.BOLD))
        print(color(f"   python adbctl.py connect {ips}", C.G))
        print(color(f"   (或在同网段直接 connect 各设备 IP)", C.D))

def cmd_connect(spec):
    """批量连接网络设备(并发,适合扫描网段)"""
    hosts = parse_hosts(spec)
    if not hosts:
        print(color("用法: adbctl.py connect <ip[:port][,ip2...]或范围 10.0.0.1-10>", C.R))
        return
    print(color(f"\n▶ 并发连接 {len(hosts)} 台网络设备(超时4s)…", C.B))
    def _try(h):
        out = run([ADB, "connect", h], timeout=4)
        if "connected" in out and "cannot" not in out:
            return h, "ok"
        if "already connected" in out:
            return h, "dup"
        return h, "fail:" + out.strip().replace("\n"," ")[:60]
    ok = 0
    with ThreadPoolExecutor(max_workers=min(32, len(hosts))) as ex:
        futs = {ex.submit(_try, h): h for h in hosts}
        for f in as_completed(futs):
            h, status = f.result()
            if status == "ok":
                ok += 1; print(f"  {color('✓', C.G)} {color(h, C.BOLD)} 已连接")
            elif status == "dup":
                ok += 1; print(f"  {color('•', C.Y)} {color(h, C.BOLD)} 已是连接状态")
            else:
                short = h if len(hosts) > 6 else f"{h} {color(status, C.D)}"
                print(f"  {color('✗', C.R)} {short}")
    print(color(f"\n连接成功 {ok}/{len(hosts)}。运行 'python adbctl.py list' 查看。", C.BOLD))

def cmd_disconnect(spec=None):
    """断开网络设备(无参数=断开所有网络设备)"""
    if spec:
        hosts = parse_hosts(spec)
        print(color(f"\n▶ 断开 {len(hosts)} 台…", C.B))
        for h in hosts:
            run([ADB, "disconnect", h], timeout=5)
            print(f"  {color('✓', C.G)} {h} 已断开")
    else:
        run([ADB, "disconnect"], timeout=5)
        print(color("已断开所有网络设备(USB 设备不受影响)。", C.B))

# ---------- 主入口 ----------
def main():
    ap = argparse.ArgumentParser(description="安卓机群控工具", formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("-s", "--serial", help="只操作指定设备(逗号分隔)")
    ap.add_argument("-y", action="store_true", help="跳过危险操作确认")
    ap.add_argument("--size", type=int, default=1024, help="scrcpy 投屏最大尺寸(默认 1024)")
    ap.add_argument("-r", "--read-only", action="store_true", help="mirror 时只看不控")
    ap.add_argument("--fps", type=int, default=0, help="mirror 最大帧率(0=不限)")
    ap.add_argument("--vr", choices=["auto", "on", "off"], default="auto",
                    help="VR 投屏裁剪模式:auto=自动检测VR头显,on=强制VR裁剪,off=强制普通(默认auto)")
    ap.add_argument("--crop", default=None, help="VR 自定义裁剪,如 '1920:1920:0:0'(覆盖预设)")
    ap.add_argument("cmd", help="list|wake|sleep|lock|shutdown|reboot|open|close|uninstall|screenshot|shell|ping|mirror|mirror-stop")
    ap.add_argument("arg", nargs="?", help="命令参数(app/包名/shell 命令)")
    args = ap.parse_args()

    cmd = args.cmd.lower()

    if cmd == "list":
        devs = list_devices()
        if not devs:
            print(color("没有在线设备。", C.R))
            return
        print(color(f"\n在线设备 {len(devs)} 台:", C.B))
        for d in devs:
            # 顺带取一下屏幕状态
            wake = adb_shell(d["serial"], "dumpsys power | grep mWakefulness=")
            wake = wake.split("=")[-1].strip() if "=" in wake else "?"
            android = adb_shell(d["serial"], "getprop ro.build.version.release")
            print(f"  • {color(d['serial'], C.BOLD)}  model={d.get('model','?')}"
                  f"  android={android}  屏幕={wake}")
        print()
        return

    if cmd in ("mirror-stop", "unmirror", "stop-mirror"):
        cmd_mirror_stop()
        return

    if cmd == "connect":
        if not args.arg:
            print(color("用法: adbctl.py connect <ip[:port][,ip2...]或范围 10.0.0.1-10>", C.R)); return
        cmd_connect(args.arg)
        return
    if cmd in ("disconnect", "dc"):
        cmd_disconnect(args.arg)   # arg 可为空=断开所有
        return
    if cmd in ("wifi", "tcpip"):
        cmd_wifi(port=5555)
        return

    # 其余命令需要设备列表
    all_devs = list_devices()
    if not all_devs:
        print(color("没有在线设备。", C.R))
        return
    if args.serial:
        want = set(x.strip() for x in args.serial.split(","))
        devs = [d for d in all_devs if d["serial"] in want]
        if not devs:
            print(color(f"未找到指定设备: {args.serial}", C.R))
            return
    else:
        devs = all_devs

    if cmd == "wake":
        run_all(devs, "wake")
    elif cmd in ("sleep", "休眠"):
        run_all(devs, "sleep")
    elif cmd == "lock":
        run_all(devs, "lock")
    elif cmd in ("shutdown", "poweroff", "关机"):
        run_all(devs, "shutdown", confirm_msg="关机后需手动开机!", assume_yes=args.y)
    elif cmd in ("reboot", "重启"):
        run_all(devs, "reboot", confirm_msg="将重启所有设备", assume_yes=args.y)
    elif cmd in ("open", "打开", "start"):
        if not args.arg:
            print(color("用法: adbctl.py open <app|包名|别名>", C.R)); return
        run_all(devs, "open", args.arg)
    elif cmd in ("close", "stop", "关闭"):
        if not args.arg:
            print(color("用法: adbctl.py close <app|包名>", C.R)); return
        run_all(devs, "close", args.arg)
    elif cmd == "uninstall":
        if not args.arg:
            print(color("用法: adbctl.py uninstall <包名>", C.R)); return
        run_all(devs, "uninstall", args.arg, confirm_msg=f"卸载 {args.arg}", assume_yes=args.y)
    elif cmd in ("screenshot", "shot", "截图"):
        run_all(devs, "screenshot", args.arg)
    elif cmd == "shell":
        if not args.arg:
            print(color("用法: adbctl.py shell \"<命令>\"", C.R)); return
        run_all(devs, "shell", args.arg)
    elif cmd == "ping":
        run_all(devs, "ping")
    elif cmd in ("temp", "温度"):
        run_all(devs, "temp")
    elif cmd in ("battery", "电量", "bat"):
        run_all(devs, "battery")
    elif cmd in ("keepalive", "常亮", "防息屏"):
        run_all(devs, "keepalive")
    elif cmd in ("apps", "应用列表"):
        run_all(devs, "apps", args.arg)
    elif cmd in ("mirror", "同屏", "screen", "投屏"):
        cmd_mirror(devs, max_size=args.size, read_only=args.read_only,
                   fps=args.fps, vr_mode=args.vr, vr_crop=args.crop)
    else:
        print(color(f"未知命令: {cmd}", C.R))
        print(__doc__)

if __name__ == "__main__":
    main()
