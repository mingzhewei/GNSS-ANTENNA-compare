# Windows 环境配置指南

本文档提供在 Windows 系统上运行 GNSS Antenna Compare 的**体系化配置方案**。所有配置通过统一脚本完成，无需零散操作。

---

## 1. 一键配置（推荐）

### 方式一：使用批处理脚本（CMD）

```cmd
setup_windows.bat
```

### 方式二：使用 PowerShell 脚本（推荐，更友好）

```powershell
# 如果遇到执行策略限制，先运行：
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 然后执行：
.\setup_windows.ps1
```

**脚本会自动完成：**
1. 检查 Python 和 pip 是否安装
2. 创建 `.venv` 虚拟环境
3. 激活虚拟环境
4. 升级 pip
5. 安装所有依赖（numpy、pandas、matplotlib、pyyaml）
6. 验证安装

---

## 2. 手动配置（备用方案）

如果一键脚本失败，可按以下步骤手动配置：

### 2.1 安装 Python

1. 访问 https://www.python.org/downloads/
2. 下载 Python 3.9 或更高版本
3. 安装时**务必勾选 "Add Python to PATH"**

### 2.2 创建虚拟环境

```cmd
python -m venv .venv
```

### 2.3 激活虚拟环境

**CMD：**
```cmd
.venv\Scripts\activate.bat
```

**PowerShell：**
```powershell
.venv\Scripts\Activate.ps1
```

### 2.4 安装依赖

```cmd
python -m pip install --upgrade pip
pip install numpy pandas matplotlib pyyaml
```

---

## 3. 运行分析

### 3.1 激活虚拟环境

**CMD：**
```cmd
.venv\Scripts\activate.bat
```

**PowerShell：**
```powershell
.venv\Scripts\Activate.ps1
```

### 3.2 运行分析

```cmd
python scripts\run_analysis.py
```

### 3.3 查看报告

报告生成在 `reports\` 目录下，用浏览器打开对应的 HTML 文件即可。

---

## 4. 常见问题

### Q1：PowerShell 提示"无法加载文件，因为在此系统上禁止运行脚本"

**解决方案：**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Q2：提示"Python 不是内部或外部命令"

**解决方案：**
- 重新安装 Python，勾选 "Add Python to PATH"
- 或手动添加 Python 到系统 PATH：
  1. 右键"此电脑" → 属性 → 高级系统设置 → 环境变量
  2. 在"系统变量"中找到 `Path`，点击编辑
  3. 添加 Python 安装路径（如 `C:\Python39\` 和 `C:\Python39\Scripts\`）

### Q3：pip 安装依赖失败

**解决方案：**
```cmd
python -m pip install --upgrade pip
pip install numpy pandas matplotlib pyyaml --user
```

### Q4：报告中的中文显示为方块或乱码

**解决方案：**
- Windows 上 matplotlib 默认字体可能不支持中文
- 代码已内置中文字体回退（Heiti TC、Songti SC、Arial Unicode MS）
- 如果仍乱码，请安装微软雅黑字体：
  1. 下载微软雅黑字体（msyh.ttc）
  2. 右键字体文件 → 安装
  3. 重新运行分析

---

## 5. 与 macOS 的差异说明

| 项目 | macOS | Windows |
|---|---|---|
| 路径分隔符 | `/` | `\`（代码已用 `os.path.join` 处理） |
| 虚拟环境激活 | `source .venv/bin/activate` | `.venv\Scripts\activate.bat` 或 `.venv\Scripts\Activate.ps1` |
| 默认编码 | UTF-8 | GBK（代码已显式指定 UTF-8） |
| 换行符 | LF | CRLF（不影响运行） |
| 字体 | Heiti TC、Songti SC | 微软雅黑（代码已内置回退） |

**结论**：代码本身跨平台兼容，仅需注意虚拟环境激活方式和字体显示。

---

## 6. 验证安装

运行以下命令验证环境配置是否正确：

```cmd
python -c "import numpy; import pandas; import matplotlib; import yaml; print('All dependencies OK')"
```

如果输出 `All dependencies OK`，说明环境配置成功。

---

## 7. 卸载

如果需要完全卸载：

```cmd
# 删除虚拟环境
rmdir /s /q .venv

# 删除生成的报告（可选）
rmdir /s /q reports
```
