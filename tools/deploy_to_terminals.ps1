# Deploy Exness XAUUSD Titan EA to all detected MetaTrader 5 terminal instances
$root = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $root 'mql5\Experts\Exness_XAUUSD_Titan'

if (!(Test-Path -LiteralPath $sourceDir)) {
    throw "Source directory missing: $sourceDir"
}

Write-Output "Source directory: $sourceDir"

$terminalDirs = @()
$appDataTerminal = Join-Path $env:APPDATA 'MetaQuotes\Terminal'

if (Test-Path -LiteralPath $appDataTerminal) {
    Get-ChildItem -LiteralPath $appDataTerminal -Directory | ForEach-Object {
        if ($_.Name -notin @('Common', 'Community')) {
            $terminalDirs += $_.FullName
        }
    }
}

$validationTerminal = Join-Path $root '.mt5-validation'
if (Test-Path -LiteralPath $validationTerminal) {
    $terminalDirs += $validationTerminal
}

Write-Output "Found $($terminalDirs.Count) terminal instance candidate(s)."

$deployedList = @()

foreach ($t in $terminalDirs) {
    try {
        $originFile = Join-Path $t 'origin.txt'
        $originName = if (Test-Path -LiteralPath $originFile) { Get-Content -LiteralPath $originFile -Raw } else { $t }
        $originName = $originName.Trim()

        $targetExperts = Join-Path $t 'MQL5\Experts\Exness_XAUUSD_Titan'
        $targetTester = Join-Path $t 'MQL5\Profiles\Tester'
        $targetFiles = Join-Path $t 'MQL5\Files'

        New-Item -ItemType Directory -Path $targetExperts -Force -ErrorAction Stop | Out-Null
        New-Item -ItemType Directory -Path $targetTester -Force -ErrorAction SilentlyContinue | Out-Null
        New-Item -ItemType Directory -Path $targetFiles -Force -ErrorAction SilentlyContinue | Out-Null

        # Copy all files
        Get-ChildItem -LiteralPath $sourceDir -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $targetExperts -Force
        }

        # Copy .set files to MQL5\Profiles\Tester
        Get-ChildItem -LiteralPath $sourceDir -Filter '*.set' | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $targetTester -Force
        }

        Write-Output "-> Successfully deployed to: $originName"
        Write-Output "   Target: $targetExperts"
        $deployedList += $targetExperts
    }
    catch {
        Write-Output "-> Skipped/Notice for $t : $($_.Exception.Message)"
    }
}

Write-Output ""
Write-Output "DEPLOYMENT SUMMARY: Deployed to $($deployedList.Count) terminal instance(s)."
