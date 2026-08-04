# GNSS Antenna Compare

多天线 GNSS 抗干扰对比分析框架。基于北云 M21 接收机与 UG016/OEM7 协议，支持双天线同步干扰测试的自动化数据分析与 HTML 报告生成。

---

## 1. 功能概述

- **配置驱动**：通过 `config/tests.yaml` 定义测试组，无需修改代码即可添加新天线对比
- **多数据源**：同时解析 COM3 ASCII（TRACKSTAT/BESTPOS/GST/GSV）与 COM4 二进制 RANGECMP
- **标准化统计**：C/N0、Pearson/Fisher-z 相关性、Wilcoxon 符号秩检验、ETSI 1 dB 退化评估
- **卫星丢失检测**：连续丢失 ≥3 秒判定为真丢失，避免瞬态噪声误判
- **频点拆分**：按 L1/L2/L5/E1/E5a/E5b/B1/B2/B3 分析 RANGECMP 指标
- **时间追溯**：报告中完整记录原始数据时间范围、片段定义、分析窗口，支持第三方复核

---

## 2. 数据要求

### 2.1 采集设备与方法

- **接收机**：北云 M21（或兼容 UG016 协议的同系列设备）
- **天线**：两根待测 GNSS 天线，相距 30 cm 固定于同一平面
- **干扰源**：Wi-Fi 路由器（2.4 GHz）、手机（4G）、对讲机（392/409 MHz）
- **采集方式**：两台 M21 同步输出 COM3 ASCII + COM4 二进制，时间戳对齐

### 2.2 必需数据字段

| 数据源 | 消息类型 | 必需字段 | 用途 |
|---|---|---|---|
| COM3 ASCII | `TRACKSTATA` | `C/No`、`locktime`、`ch-tr-status`、`psr res`、`reject` | 核心指标：载噪比、跟踪状态、失锁检测 |
| COM3 ASCII | `BESTPOSA` | `sol stat`、`pos type`、`# sats`、`# satsln` | 定位状态、可用星数 |
| COM3 ASCII | `GPGST` | 字段 3（伪距 RMS） | 伪距退化评估 |
| COM3 ASCII | `GPGSV` | `in_view` | 可见星数统计 |
| COM4 二进制 | `RANGECMP`（ID 140） | `C/No`、`StdDev-PSR`、`StdDev-ADR`、`locktime`、`ch-tr-status` | 伪距/载波相位标准差、频点拆分 |

### 2.3 数据格式要求

- **COM3**：ASCII 文本，每行一条消息，以 `#`（自定义）或 `$`（NMEA）开头
- **COM4**：NovAtel 标准二进制，同步字 `0xAA 0x44 0x12`
- **时间戳**：FINESTEERING 格式（GPS 周 + 周内秒），两根天线必须同步

---

## 3. 安装与依赖

### 3.1 环境要求

- Python ≥ 3.9
- 依赖包：`numpy`、`pandas`、`matplotlib`、`PyYAML`

### 3.2 安装步骤

**macOS / Linux：**
```bash
# 克隆仓库
git clone https://github.com/mingzhewei/GNSS-ANTENNA-compare.git
cd GNSS-ANTENNA-compare

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install numpy pandas matplotlib pyyaml
```

**Windows：**
```cmd
# 克隆仓库
git clone https://github.com/mingzhewei/GNSS-ANTENNA-compare.git
cd GNSS-ANTENNA-compare

# 一键配置（推荐）
setup_windows.bat

# 或 PowerShell（更友好）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\setup_windows.ps1
```

详细 Windows 配置说明见 [README_WINDOWS.md](README_WINDOWS.md)。


---

## 4. 使用方法

### 4.1 配置测试组

编辑 `config/tests.yaml`，添加你的测试组：

```yaml
test_groups:
  - name: "my-test-0801"
    description: "0801 dual-antenna test: AntA vs AntB"
    data_dir: "0801"
    antennas:
      - id: "A"
        display_name: "天线A"
        com3: "A-com3.dat"
        com4: "A-com4.dat"
      - id: "B"
        display_name: "天线B"
        com3: "B-com3.dat"
        com4: "B-com4.dat"
    segments:
      - { label: "无干扰 #1", duration: 30.0 }
      - { label: "409MHz 干扰", duration: 60.0 }
      - { label: "无干扰 #2", duration: 30.0 }
      - { label: "392MHz 干扰", duration: 60.0 }
      - { label: "无干扰 #3", duration: 30.0 }
      - { label: "4G/5G 干扰", duration: 60.0 }
      - { label: "无干扰 #4", duration: 30.0 }
      - { label: "Wi-Fi 干扰", duration: 60.0 }
      - { label: "无干扰 #5", duration: 30.0 }
```

**字段说明**：
- `name`：测试组唯一标识，用于输出目录命名
- `data_dir`：数据文件所在目录（相对于项目根目录）
- `antennas`：天线列表，目前支持 2 根天线对比
- `id`：天线内部标识（用于 CSV 文件名）
- `display_name`：报告显示名称
- `segments`：测试片段定义，`label` 为显示名称，`duration` 为秒数

### 4.2 运行分析

```bash
python scripts/run_analysis.py
```

输出：
- 每根天线：`reports/{test_name}/antenna_{test_name}_{display_name}_report.html`
- 对比报告：`reports/{test_name}/antenna_{name1}_vs_{name2}_{test_name}_report.html`
- CSV 数据：`reports/{test_name}/*.csv`

### 4.3 查看报告

用浏览器打开生成的 HTML 文件。报告包含：

1. **数据时间范围与片段追溯**：原始数据 GPS 周/周内秒、片段定义、分析窗口
2. **整体指标对比**：C/N0、PLL 锁定率、跟踪星数、参与解算星数
3. **逐星 C/N0 统计**：最高/最低/25/75 分位、中位数
4. **相关性分析**：Pearson r、Fisher-z 平均、按系统分组
5. **显著性检验**：Wilcoxon 符号秩检验（p < 0.05）
6. **卫星丢失情况**：连续丢失 ≥3 秒的卫星名单
7. **ETSI 退化评估**：ΔC/N0 ≤ 1 dB 行业参考线
8. **RANGECMP 分析**：StdDev-PSR、StdDev-ADR、按频点拆分
9. **联合失锁分析**：TRACKSTAT + RANGECMP 联合判定
10. **综合结论**：绝对接收能力、相对抗干扰能力、总体性能判定

---

## 5. 核心算法与标准

### 5.1 统计口径

| 指标 | 方法 | 标准 |
|---|---|---|
| C/N0 | TRACKSTATA `C/No` 字段（dB-Hz） | UG016 §4.2.26 |
| 相关性 | 同一卫星多频点先按历元取中位数聚合，再按同一 sow 配对，逐星 Pearson r | 统计学标准 |
| 相关性合并 | Fisher z-transform 平均 | meta-analysis 标准 |
| 显著性 | Wilcoxon 符号秩检验，p < 0.05 | 非参数统计标准 |
| 退化评估 | 干扰段 − 前基线 ΔC/N0 中位数 | ETSI EN 303 413（1 dB 参考线） |
| 卫星丢失 | 连续丢失 ≥3 秒（按数据实际采样间隔判定） | 工程惯例 |
| 最小样本量 | 相关性 ≥30 共同历元；Wilcoxon/ETSI 每星 ≥5 历元 | 统计稳健性要求 |

### 5.2 报告结论维度

- **绝对接收能力**：基线 C/No 差值、干扰段 C/No 差值
- **相对抗干扰能力**：各干扰场景 ΔC/N0 退化量对比
- **总体性能判定**：综合绝对和相对两个维度给出明确结论

---

## 6. 项目结构

```
GNSS-ANTENNA-compare/
├── config/
│   └── tests.yaml          # 测试组配置
├── scripts/
│   ├── gnss_config.py      # 配置加载与片段构建
│   ├── gnss_parser.py      # COM3/COM4 解析
│   ├── gnss_analyzer.py    # 统计计算
│   ├── gnss_reporter.py    # HTML 报告生成
│   └── run_analysis.py     # 主入口
├── reports/                # 输出报告（HTML + CSV）
├── 0718/ 0719/ 0721/ ...   # 示例数据
├── M21_双天线抗干扰对比测试_采集与判定方案.html
├── UG016_数据通信接口协议_北云科技.pdf
├── OEM7_Commands_Logs_Manual.pdf
└── README.md
```

---

## 7. 注意事项

1. **M21 内置抗干扰算法**：UG016 协议未提供关闭开关，对比结果为"天线 + M21 算法"的系统级结论，非天线单独性能
2. **干扰源功率波动**：手机/路由器发射功率随业务动态变化，建议固定型号/姿态/业务状态，每场景复测 ≥2 轮
3. **15 cm 近场几何**：干扰源距天线 15 cm 处于近场区，场强空间梯度大，建议交换复测消除几何误差
4. **COM4 格式差异**：部分天线 COM4 可能为非标准格式，报告会自动检测并标注

---

## 8. 参考文档

- 【P】《UG016 数据通信接口协议》（北云科技）
- 【M】《OEM7 Commands and Logs Reference Manual v11》（NovAtel）
- 【ETSI】ETSI EN 303 413：GNSS 接收机阻塞测试，ΔC/N0 ≤ 1 dB
- 【JRC】EC JRC《Compatibility between amateur and Galileo》：抗干扰评估三大指标

---

## 9. 许可证

内部测试工具，仅供学习与研究使用。
