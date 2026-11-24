param(
    [string]$CommonFiles = (Join-Path $env:APPDATA 'MetaQuotes\Terminal\Common\Files'),
    [switch]$Watch
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'data\runtime\gold_advisory.json'
$destination = Join-Path $CommonFiles 'GoldScalp'
New-Item -ItemType Directory -Path $destination -Force | Out-Null
$output = Join-Path $destination 'advisor1.csv'
$encoding = New-Object System.Text.UTF8Encoding($false)
do {
    try {
        # Transport the existing report only. Never import, edit or reimplement Advisor 1.
        $report = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
        $scalp = $report.horizons.SCALP
        $generated = [DateTimeOffset]::Parse($report.generated_at).ToUnixTimeSeconds()
        $valid = [DateTimeOffset]::Parse($scalp.valid_until).ToUnixTimeSeconds()
        if ($report.symbol -notmatch '^XAUUSD[^;\r\n]*$' -or $scalp.action -notin @('BUY','SELL','WAIT') -or $scalp.bias -notin @('BUY','SELL','WAIT')) { throw 'Unexpected Advisor 1 report schema.' }
        $culture = [Globalization.CultureInfo]::InvariantCulture
        $fields = @('GOLD_ADVISOR1_V1', "$generated", "$valid", $report.symbol, $scalp.action, $scalp.bias,
            ([double]$scalp.directional_score).ToString('R',$culture), ([double]$report.bid).ToString('R',$culture), ([double]$report.ask).ToString('R',$culture), 'SCALP','END')
        $temporary = "$output.$PID.tmp"
        [IO.File]::WriteAllText($temporary, ($fields -join ';') + "`r`n", $encoding)
        if (Test-Path -LiteralPath $output) {
            # Windows PowerShell 5.1 converts $null to an empty string for this
            # .NET string argument. Pass a real null to disable the backup file.
            [IO.File]::Replace($temporary,$output,[System.Management.Automation.Language.NullString]::Value)
        }
        else { [IO.File]::Move($temporary,$output) }
        if (!$Watch) { Write-Output "Advisor 1 reference published: $output (original timestamp preserved)" }
    } catch {
        if (!$Watch) { throw }
        Write-Warning $_.Exception.Message
    }
    if ($Watch) { Start-Sleep -Seconds 5 }
} while ($Watch)
