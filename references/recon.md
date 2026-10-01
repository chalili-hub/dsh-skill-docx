# 侦察：要求文档、环境、执行通道

## 1. 解析实验要求文档

要求往往分散在 docx / pptx / pdf / 图片截图里，全部要读到。

```python
# 通用：docx 段落 + 表格 -> UTF-8 文本文件
import docx, io
d = docx.Document(path)
out = io.StringIO()
for p in d.paragraphs:
    if p.text.strip():
        out.write(p.text.rstrip() + "\n")
out.write(f"=== TABLES: {len(d.tables)}\n")
for i, tb in enumerate(d.tables):
    out.write(f"--- table {i} ---\n")
    for row in tb.rows:
        out.write(" | ".join(c.text.strip() for c in row.cells) + "\n")
open("_req.txt", "w", encoding="utf-8").write(out.getvalue())
```

要点：
- **表格必须提取**。命令、源码、配置经常整段放在表格里，只读 `paragraphs` 会漏掉最关键的内容。
- **不要 print 到 Windows 控制台**，中文非 GBK 字符会抛 `UnicodeEncodeError`。写成 UTF-8 文件后用 read 工具读。
- pptx 用 `python-pptx`（遍历 shapes 的 `text_frame`）；pdf 用 `pymupdf`（`page.get_text()`）。
- 指导书类 docx 常很长（几十页）。先提取全文，再用 grep 定位关键小节（`riscv|VTile|elf2hex|参数|波形` 等）。

## 2. 从要求里抽出三样东西

1. **验收清单** —— 要求做几件事，各自的可交付形态是什么。写进 todo_write。
2. **对答案（校验基准）** —— 文档里给出的具体数值：地址、机器码、寄存器名、预期现象。
   例如"该指令对应的 PC 地址为 0x210"、"PC 的值在后续三个周期保持不变直至成功取出指令 00A00513"。
   复现后**逐条比对**；对不上说明实验没做对或版本不一致，要查清楚而不是绕过去。
3. **版本线索** —— 工具版本、源码分支、目录结构、文件名（`Tile.v` 还是 `Tile.sv`；`fe_reg` 还是 `fe_pc`）。
   这些决定了要取哪一版源码。上游仓库升级会导致命名与产物名变化，**以要求文档描述的那一版为准**。

## 3. 环境探测

**本机**：
```
pwd; Get-ChildItem -Force          # 工作目录里有什么
Get-Command python,py,pandoc,soffice,ssh,scp,plink
python -c "import docx, pptx, fitz, matplotlib; ..."   # 依赖齐不齐
```

**虚拟机 / 远程**：先确认进程与网络，再找通道。

```
Get-Process | ? { $_.ProcessName -match 'vmware|VirtualBox|qemu|vmwp' }   # 虚拟机在跑吗
Get-CimInstance Win32_Process -Filter "Name='vmware-vmx.exe'" | Select CommandLine   # 跑的是哪一个 .vmx
Get-NetIPAddress -AddressFamily IPv4
arp -a                                                                    # NAT 网段里客户机 IP
Test-NetConnection -ComputerName <ip> -Port 22
```

DHCP 租约能直接给出客户机 IP 与主机名：
`C:\ProgramData\VMware\vmnetdhcp.leases`（按 MAC 与 hostname 匹配）。

## 4. 选执行通道（按优先级）

| 通道 | 探测 | 适用 |
| --- | --- | --- |
| SSH | 22 端口开 + 有凭据 | 最理想：能跑长任务、能传文件 |
| `vmrun` Guest Operations | `vmrun list` 有在跑的 VM；VMware Tools 在客户机内运行 | SSH 未开时的主力方案 |
| 容器 | `docker ps` / `podman ps` | 环境已封装 |
| 计划任务 / 共享目录 | VMware 共享文件夹、SMB | 只能传文件，不能执行 |
| 客户机磁盘离线读取 | 关机能挂载 vmdk | 只能取证，不能执行 |

**SSH 不通不等于做不了。** 先把所有通道摸一遍再决定，不要因为 22 端口关闭就退回"只写报告"。

### vmrun 通道要点

```powershell
$vmrun = "C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
$vmx   = "<...>.vmx"

# 1) 先确认凭据与客户机可达（用户名/密码错误会明确报错）
& $vmrun -T ws -gu <user> -gp <pass> listProcessesInGuest $vmx

# 2) 传文件进去 / 跑命令 / 取文件出来
& $vmrun -T ws -gu <user> -gp <pass> copyFileFromHostToGuest  $vmx $local $guestPath
& $vmrun -T ws -gu <user> -gp <pass> runProgramInGuest        $vmx /bin/bash -c "..."
& $vmrun -T ws -gu <user> -gp <pass> copyFileFromGuestToHost  $vmx $guestPath $local
& $vmrun -T ws -gu <user> -gp <pass> captureScreen            $vmx $out.png
```

**关键：`runProgramInGuest` 不返回 stdout。** 必须让客户机把输出重定向到文件、跑完再拷回来。
推荐模式：把 bash 脚本写成主机上的文件 → 拷进 `/tmp/x.sh` → 跑
`/bin/bash -c "bash /tmp/x.sh > /tmp/x.out 2>&1; echo EXIT=$? >> /tmp/x.out"` →
轮询拷回 `/tmp/x.out` 直到见到 `EXIT=`。

**脚本换行必须是 LF。** Windows 写的 CRLF 会让客户机 bash 报 `\r: command not found`：

```powershell
[System.IO.File]::WriteAllText($f, ($text -replace "`r`n","`n"), (New-Object System.Text.UTF8Encoding($false)))
```

**客户机非交互 shell 不读 `~/.bashrc`。** Ubuntu 的 `.bashrc` 开头有
`case $- in *i*) ;; *) return;; esac`，所以往 `.bashrc` 里追加 `export PATH=...` 对
`runProgramInGuest` 完全无效。**在每个脚本开头显式 export。**

## 5. 侦察产出一张环境卡

把版本信息收集成一张表，直接进报告的"实验环境"章：

| 项目 | 版本 |
| --- | --- |
| 宿主/虚拟化 | VMware Workstation 17.6.3 |
| 客户机 | Ubuntu 22.04.3 LTS，内核 6.8.0-40 |
| 语言/构建 | JDK 11.0.32.1 / sbt 1.5.5 / Scala 2.13.7 |
| 领域工具 | Verilator 4.038、GCC 5.3.0 交叉工具链、GTKWave 3.3.104 |
| 目标工程 | ucb-bar/riscv-mini @ 3473cfd8 |
