# ==================================================
# 身份证 1:1 透视校正工具 - 自动打包 EXE 脚本 (PATH兼容版)
# ==================================================

$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  身份证 1:1 透视校正工具 - 自动打包 EXE 脚本" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 切换工作目录至脚本所在目录
$scriptDir = $PSScriptRoot
Set-Location $scriptDir

$pyFile = "core.py"

# 1. 检查核心 Python 文件是否存在
if (-not (Test-Path $pyFile)) {
    Write-Host ""
    Write-Host "[ERROR] 未在当前目录下找到 $pyFile 文件！" -ForegroundColor Red
    Write-Host "请确保本 ps1 脚本与 $pyFile 处于同一目录下。" -ForegroundColor Red
    Write-Host ""
    Read-Host "按回车键退出..."
    exit
}

# 2. 检查并安装打包所需依赖
Write-Host ""
Write-Host "[1/3] 正在检查并准备 Python 依赖环境..." -ForegroundColor Yellow
python -m pip install --upgrade pyinstaller opencv-python numpy Pillow reportlab

# 3. 清理历史构建垃圾文件
Write-Host ""
Write-Host "[2/3] 正在清理上一次打包产生的缓存..." -ForegroundColor Yellow
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "core.spec") { Remove-Item -Force "core.spec" }

# 4. 执行 PyInstaller 打包 (使用 python -m PyInstaller 避开环境变量 PATH 缺失问题)
Write-Host ""
Write-Host "[3/3] 正在开始打包 (生成单文件、无黑框命令行)..." -ForegroundColor Yellow
python -m PyInstaller --noconsole --onefile --clean $pyFile

# 5. 校验结果
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Green
    Write-Host "  [OK] 打包成功！" -ForegroundColor Green
    Write-Host "  [路径] 可执行文件位于: $scriptDir\dist\core.exe" -ForegroundColor Green
    Write-Host "  [提示] 你可以将 dist\core.exe 发送到任何 Windows 电脑直接运行" -ForegroundColor Green
    Write-Host "==================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ERROR] 打包失败，请检查上方的错误信息。" -ForegroundColor Red
}

Read-Host "按回车键关闭窗口..."