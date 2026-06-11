# 使用项目虚拟环境运行 pytest（无需手动 activate）
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "未找到虚拟环境：$Python`n请先执行：python -m venv venv"
    exit 1
}

if ($PytestArgs.Count -eq 0) {
    $PytestArgs = @("tests/test_creativity.py", "-v")
}

& $Python -m pytest @PytestArgs
exit $LASTEXITCODE
