# One-command VerdictBox runner.
# Usage examples:
#   .\run_project.ps1
#   .\run_project.ps1 -TrainModels
#   .\run_project.ps1 -InitDb -SeedDb -TrainModels

param(
    [switch]$InitDb,
    [switch]$SeedDb,
    [switch]$TrainModels,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$EnvFile
    )

    if (-not (Test-Path $EnvFile)) {
        return $null
    }

    $line = Get-Content $EnvFile | Where-Object {
        $_ -match "^\s*$Key\s*="
    } | Select-Object -First 1

    if (-not $line) {
        return $null
    }

    $value = $line -replace "^\s*$Key\s*=\s*", ""
    $value = $value.Trim()

    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    return $value
}

Write-Host "[1/6] Preparing Python environment..."
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    py -3.12 -m venv venv
}

. .\venv\Scripts\Activate.ps1

if (-not $SkipInstall) {
    Write-Host "[2/6] Installing dependencies..."
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -r requirements.txt
} else {
    Write-Host "[2/6] Skipped dependency installation (-SkipInstall)."
}

$envFile = ".\config\.env"
$envExampleFile = ".\config\.env.example"

if (-not (Test-Path $envFile)) {
    if (Test-Path $envExampleFile) {
        Copy-Item $envExampleFile $envFile
        Write-Host "Created config/.env from config/.env.example. Update keys/passwords, then run again."
        exit 1
    }
    Write-Host "Missing config/.env and config/.env.example."
    exit 1
}

$dbHost = Get-DotEnvValue -Key "DB_HOST" -EnvFile $envFile
$dbPort = Get-DotEnvValue -Key "DB_PORT" -EnvFile $envFile
$dbUser = Get-DotEnvValue -Key "DB_USER" -EnvFile $envFile
$dbPass = Get-DotEnvValue -Key "DB_PASSWORD" -EnvFile $envFile
$dbName = Get-DotEnvValue -Key "DB_NAME" -EnvFile $envFile

if ($InitDb) {
    Write-Host "[3/6] Initializing database schema..."
    mysql -h $dbHost -P $dbPort -u $dbUser "-p$dbPass" -e "CREATE DATABASE IF NOT EXISTS $dbName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    Get-Content .\db\schema.sql | mysql -h $dbHost -P $dbPort -u $dbUser "-p$dbPass" $dbName

    if ($SeedDb) {
        Write-Host "[4/6] Seeding database..."
        Get-Content .\db\seed_data.sql | mysql -h $dbHost -P $dbPort -u $dbUser "-p$dbPass" $dbName
    } else {
        Write-Host "[4/6] Seeding skipped. Use -SeedDb to seed sample data."
    }
} else {
    Write-Host "[3/6] Database init skipped. Use -InitDb to initialize schema."
    Write-Host "[4/6] Database seed skipped. Use -SeedDb with -InitDb to seed data."
}

if ($TrainModels) {
    Write-Host "[5/6] Training ML models..."
    python ai\train_models.py
} else {
    Write-Host "[5/6] Model training skipped. Use -TrainModels to retrain."
}

Write-Host "[6/6] Starting Flask app..."
python app.py
