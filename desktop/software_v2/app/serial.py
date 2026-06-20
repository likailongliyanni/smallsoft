import re
import subprocess
import uuid


def _robust_mac() -> str:
    """本机真实网卡 MAC（12 位十六进制，无分隔符）。

    与截图软件 snap-saver 完全一致的取法：优先用 getmac 命令枚举所有网卡，
    排序取最小，保证同一台机器每次启动稳定；失败回退 uuid.getnode()。
    """
    try:
        out = subprocess.run(
            ["getmac", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=8,
            creationflags=0x08000000,  # CREATE_NO_WINDOW，不弹黑框
        ).stdout
        macs = []
        for token in re.findall(r'([0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5})', out):
            hexv = re.sub(r'[^0-9A-Fa-f]', '', token).upper()
            if len(hexv) == 12 and hexv != "000000000000":
                macs.append(hexv)
        if macs:
            return sorted(set(macs))[0]  # 排序取最小，保证同一台机器每次稳定
    except Exception:
        pass
    return f"{uuid.getnode():012X}"


def get_serial() -> str:
    """设备序列号 = 本机真实网卡 MAC，格式化为 XX-XX-XX-XX-XX-XX。

    与截图软件统一用 MAC，软件类别（自动化=auto）由登记时上报的 app 字段
    在服务器端区分，编号本身只放 MAC。这个带分隔符的格式与后台
    DesktopDeviceController.normalizeSoftwareId 的输出完全一致——
    用户首页看到的、报给客服充值的、后台账户里存的，三者一模一样。

    每次启动按本机网卡实时计算，不读配置旧值，避免软件目录被拷贝到别的
    电脑时把旧编号带过去导致多机同号。
    """
    mac = _robust_mac()
    return "-".join(mac[i:i + 2] for i in range(0, 12, 2))
