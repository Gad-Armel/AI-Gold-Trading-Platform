param([string]$TerminalDir = '.mt5-validation')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root $TerminalDir
$config = Join-Path $stage 'titan_test.ini'
$report = Join-Path $root 'mql5\Experts\Exness_XAUUSD_Titan\test_report.html'

@"
[Common]
Server=MetaQuotes-Demo
[Experts]
Enabled=0
AllowLiveTrading=0
AllowDllImport=0
[Tester]
Expert=Exness_XAUUSD_Titan\Exness_XAUUSD_Titan_Test.ex5
Symbol=XAUUSD
Period=M1
Model=3
ExecutionMode=150
Optimization=0
FromDate=2026.08.01
ToDate=2026.08.05
Deposit=1000
Currency=USD
Leverage=100
UseLocal=1
UseRemote=0
UseCloud=0
Visual=0
Report=$report
ReplaceReport=1
ShutdownTerminal=1
"@ | Set-Content -LiteralPath $config -Encoding Unicode

$terminal = Join-Path $stage 'terminal64.exe'
if (!(Test-Path -LiteralPath $terminal)) {
    throw "terminal64.exe missing in $stage"
}

$proc = Start-Process -FilePath $terminal -ArgumentList ('/portable /skipupdate /config:"{0}"' -f $config) -WorkingDirectory $stage -WindowStyle Hidden -PassThru
Write-Output "Launched isolated test terminal PID=$($proc.Id)"
if ($proc.WaitForExit(90000)) {
    Write-Output "Terminal exited with code $($proc.ExitCode)"
} else {
    Write-Output "Terminal timed out after 90s; stopping process."
    Stop-Process -Id $proc.Id -Force
}

$d1 = Join-Path $stage 'Tester\logs'
$d2 = Join-Path $stage 'Tester\Agent-127.0.0.1-3000\logs'
$logDirs = @($d1, $d2)

foreach ($dir in $logDirs) {
    if (Test-Path -LiteralPath $dir) {
        $latestLog = Get-ChildItem -LiteralPath $dir -Filter '*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latestLog) {
            Write-Output "=== Log: $($latestLog.FullName) ==="
            Get-Content -LiteralPath $latestLog.FullName | Select-String 'TITAN', 'TEST', 'PASSED', 'FAILED', 'result' | Select-Object -Last 30
        }
    }
}
