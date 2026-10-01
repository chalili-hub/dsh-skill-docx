# 取证：真实执行、环境搭建、数据抓取

## 1. 长任务用后台作业

构建、仿真可能几分钟到几十分钟。用 background job，然后去做别的独立工作，不要阻塞轮询。

- 每个后台作业记下 job id；结束会收到通知，不要反复 sleep 轮询。
- 交付前把所有还相关的作业 collect 掉。
- 单个命令设 timeoutMs，构建类给足（例如 40 分钟）。

## 2. 环境搭建常见坑（操作系统 / 工具链）

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| 客户机里 `which gcc` 找不到工具链 | 非交互 shell 不读 `.bashrc` | 脚本里显式 `export PATH=...` |
| 老编译器报缺少 `libmpfr.so.4` | 新版系统只有 `.so.6` | `ln -s .../libmpfr.so.6 .../libmpfr.so.4` |
| sbt 起不来 / 报 JDK 反射错误 | sbt <1.6 与 JDK 17 不兼容 | 切 JDK 11：`export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64` |
| `git clone github.com` 连接被拒 | 443 被墙/被限 | 试 `codeload.github.com`（拉 tarball）、`api.github.com`（查 repo/branches）。**分域名探测**，一个域名不通不代表全不通 |
| 上游默认分支产物名与要求不符 | 仓库已升级（`.v` → `.sv`，`fe_pc` → `fe_reg`） | 用 GitHub API 查提交历史，取要求文档描述的那个 commit 的 tarball |
| pip/apt 装不上 | 网络受限 | 先测 `repo1.maven.org`、`pypi.org`、发行版源，分别确认 |

**分域名探测模板**（在客户机里跑）：

```bash
test_url() { printf "%-90s " "$1"; timeout 25 curl -s -o /dev/null -w "%{http_code}\n" -L "$1" || echo TIMEOUT; }
test_url https://api.github.com/repos/<owner>/<repo>
test_url https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/main
test_url https://raw.githubusercontent.com/<owner>/<repo>/main/README.md
```

查默认分支：`curl -s https://api.github.com/repos/<o>/<r> | python3 -c "import json,sys;print(json.load(sys.stdin)['default_branch'])"`

## 3. 取证清单（按实验类型）

### 编译类
- 源码原文
- 编译器完整命令行 + 版本
- **警告原文**（报告里常需要解释"这个警告不用管"）
- 元数据查询输出：`readelf -h`（入口地址、架构）、`size`、`file`
- 反汇编：`objdump -d`（要地址 + 机器码 + 助记符三列）
- 目标格式转换输出（hex/coe/bin）前若干行

### 仿真 / 运行类
- 仿真器自行输出的结束状态（cycle 数、超时与否、退出码）
- **原始波形/日志文件本体**（VCD、trace、CSV）
- 从原始文件解析出的**逐周期信号表**（可复核，比截图强）
- 与要求文档"对答案"字段的一致性比对结果

### 测量类
- 原始测量数据 CSV
- 重复次数与离散度（不要只报一个"漂亮"的数）

## 4. 波形数据抓取（Verilog/VCD）

`scripts/vcd_analyze.py` 做这件事。两个必须知道的坑：

1. **Verilator 会把电气上相同的网络归并到同一个 VCD id。**
   `fe_reg_inst`、`immGen_io_inst`、`io_ctrl_inst` 可能是同一个 id。
   解析时必须建 **`id → [别名列表]`** 的一对多映射；如果反过来"一个 id 只保留最后一个名字"，
   会有信号永远读到 `x`，而且**不会报错**，静默产出错数据。这个 bug 极难发现，务必小心。
2. **采样时刻要选对。** 该测试平台在每个时钟的高、低电平各 dump 一次（`main_time` 每次 +1），
   所以偶数时间戳 = 上升沿之后的状态。取"每个时钟周期一个快照"就在偶数时间戳采样。

写输出时顺手把二进制串转成十六进制，报告里可直接用。

## 5. 关于 GUI 截图（GTKWave / ModelSim 等）

**不要承诺**能自动拿到 GUI 截图：

- GNOME Wayland 会话下，Xwayland 客户端的窗口在 `xwininfo` 里可能显示 `IsUnMapped`；
  `xdotool windowmap` 能把它变成 `IsViewable`，但 `xwd` 抓取仍返回空白/`BadMatch`。
- `vmrun captureScreen` 在客户机屏幕已熄灭或锁屏时拿到的是纯白或锁屏画面。
- `vmrun` 没有发送按键的 API，无法唤醒/解锁。

**优先级**：
1. 先用脚本从原始数据还原出精确图表（往往比截图更有说服力，还能标注周期和含义）。
2. 确实需要截图时，试 `gnome-screenshot`（Wayland 原生）或直接告诉用户"请自行截图"。
3. 在报告和答复里**说明截图未获取的原因**，并给出替代证据与用户自己复现的命令。

## 6. 数据流转

```
目标机 ──(vmrun/ssh 拷回)──> 主机本地目录 ──(python 脚本)──> 图表 / TSV / 报告
```

- 主机上单独建一个工作目录放中间产物（`_vmio/` 之类），交付前整理或清理。
- 跨机拷贝大文件（几百 MB 工具链）放后台作业。
- 最后把**原始波形文件本体**也拷回主机一份，作为可复核的证据随交付物保存。
