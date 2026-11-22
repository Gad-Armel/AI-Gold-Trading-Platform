param([string]$PythonPath = '', [ValidateSet('M1','S30','S15','S5','S1','AUTO','MICRO')][string]$ScalpTimeframe = 'M1', [switch]$AllowProvisionalCosts)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (!$PythonPath) { $PythonPath = Join-Path $projectRoot '.venv-audit\Scripts\python.exe' }
if (!(Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Specify an installed Python interpreter with -PythonPath.' }
if ($ScalpTimeframe -in @('S30','S15','S5','S1','AUTO','MICRO')) {
    if ($AllowProvisionalCosts) {
        & $PythonPath -B -c "import time,json; import MetaTrader5 as m; from services.research.gold_s30_execution import load_costs; p=json.load(open('data/runtime/s5_provisional_demo_costs.json')).get('terminal_path'); assert m.initialize(*([p] if p else []),timeout=10000); load_costs('data/runtime/s5_provisional_demo_costs.json',now=time.time(),allow_provisional=True,account=m.account_info()); m.shutdown(); print('Account-bound provisional demo costs verified')"
    } else {
        & $PythonPath -B -c "import time; from services.research.gold_s30_execution import load_costs; load_costs('data/research/goldhft_20261020/s30_execution_costs.json',now=time.time()); print('Measured cost evidence verified')"
    }
    if ($LASTEXITCODE -ne 0) { throw 'S30 preflight failed; existing bot left running' }
}
& $PythonPath -c "import MetaTrader5 as m,json; p=json.load(open('data/runtime/s5_provisional_demo_costs.json')).get('terminal_path') if '$AllowProvisionalCosts'=='True' else None; assert m.initialize(*([p] if p else []),timeout=10000), m.last_error(); a=m.account_info(); assert a and a.trade_mode==m.ACCOUNT_TRADE_MODE_DEMO; ps=m.positions_get(symbol='XAUUSD'); assert ps is not None; owned=[p for p in ps if p.magic in (631005,631011,631012,631013)]; assert all(p.sl>0 for p in owned), 'Unprotected position: restart aborted'; print('Demo verified; broker-protected controlled positions:',len(owned)); m.shutdown()"
if ($LASTEXITCODE -ne 0) { throw 'Pre-restart MT5 validation failed' }
$matches = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like 'python*' -and $_.CommandLine -like "*$projectRoot*" -and $_.CommandLine -match '(?:^|[\\\s"''])run_gold_consensus_bot\.py(?:[\s"'']|$)'
})
$parentIds = @($matches | ForEach-Object { $_.ParentProcessId })
$worker = @($matches | Where-Object { $_.ProcessId -notin $parentIds })
if ($worker.Count -ne 1) { throw 'Expected exactly one verified main worker process tree.' }
$allowedIds = @([int]$worker[0].ProcessId, [int]$worker[0].ParentProcessId)
if (@($matches | Where-Object { $_.ProcessId -notin $allowedIds }).Count) { throw 'Another main instance was found; restart aborted.' }
# Only the verified main process is replaced; existing broker SLs remain active.
Stop-Process -Id $worker[0].ProcessId -Force
Wait-Process -Id $worker[0].ProcessId -ErrorAction SilentlyContinue
$runner = Join-Path $projectRoot 'run_gold_consensus_bot.py'
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$outPath = Join-Path $projectRoot ('logs\monitored-main-' + $stamp + '.stdout.log')
$errPath = Join-Path $projectRoot ('logs\monitored-main-' + $stamp + '.stderr.log')
$launchArguments = @(
    '-u', '-B', ('"' + $runner + '"'), '--mode', 'demo', '--confirm',
    'I_ACCEPT_DEMO_SCALPING_RISK', '--max-minutes', '0', '--scalp-timeframe', $ScalpTimeframe
)
if ($AllowProvisionalCosts) { $launchArguments += @('--allow-provisional-costs', '--s30-cost-report', 'data/runtime/s5_provisional_demo_costs.json') }
$launched = Start-Process -FilePath $PythonPath -ArgumentList $launchArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outPath -RedirectStandardError $errPath -PassThru
Write-Output ('Main launcher PID: ' + $launched.Id)
Write-Output ('Logs: ' + $outPath)
