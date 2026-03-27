[CmdletBinding()]
param(
    [string]$ComposeFile = "deploy/docker-compose.target.yml",
    [string]$EnvFile = ".env",
    [switch]$SkipAutoPrepare
)

$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$ComposePath,
        [Parameter(Mandatory = $true)]
        [string]$EnvPath
    )
    & docker compose --env-file $EnvPath -f $ComposePath @Arguments
    return $LASTEXITCODE
}

function Invoke-ReadinessCommand {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("check", "prepare")]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$ComposePath,
        [Parameter(Mandatory = $true)]
        [string]$EnvPath,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $raw = & docker compose --env-file $EnvPath -f $ComposePath run --rm --no-deps `
        --volume "$RepoRoot`:/workspace" `
        --workdir "/workspace" `
        worker `
        python -m evodox.runtime.offline_readiness $Command --json
    $jsonLine = $raw | Where-Object { $_ -match "^\s*\{.*\}\s*$" } | Select-Object -Last 1
    if (-not $jsonLine) {
        throw "Offline-Readiness-Ausgabe konnte nicht als JSON gelesen werden."
    }
    return ($jsonLine | ConvertFrom-Json)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composePath = (Resolve-Path (Join-Path $repoRoot $ComposeFile)).Path
$envPath = (Resolve-Path (Join-Path $repoRoot $EnvFile)).Path

Write-Host "EvidoX Bootstrap gestartet."
Write-Host "Compose: $composePath"
Write-Host "Env: $envPath"

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker ist nicht verfuegbar. Bitte Docker Desktop starten und erneut versuchen."
}

$check = Invoke-ReadinessCommand -Command "check" -ComposePath $composePath -EnvPath $envPath -RepoRoot $repoRoot
if (-not $check.ready) {
    $missing = @($check.missing) -join ", "
    Write-Host "Offline-Readiness unvollstaendig: $missing"
    if ($check.internet_available -and -not $SkipAutoPrepare) {
        Write-Host "Internet verfuegbar. Auto-Prepare wird ausgefuehrt..."
        $prepare = Invoke-ReadinessCommand -Command "prepare" -ComposePath $composePath -EnvPath $envPath -RepoRoot $repoRoot
        if (@($prepare.prepared_failures).Count -gt 0) {
            $failures = @($prepare.prepared_failures) -join "; "
            throw "Auto-Prepare fehlgeschlagen: $failures"
        }
        if (-not $prepare.ready) {
            $remaining = @($prepare.missing) -join ", "
            throw "Offline-Readiness bleibt unvollstaendig: $remaining"
        }
        Write-Host "Auto-Prepare erfolgreich."
    } else {
        throw "Offline-Readiness unvollstaendig und kein Auto-Prepare moeglich."
    }
}

$env:WORKER_OFFLINE_STRICT = "true"
$env:WORKER_HF_HUB_OFFLINE = "1"
$env:WORKER_TRANSFORMERS_OFFLINE = "1"

Write-Host "Starte Compose-Stack im offline-strict Worker-Modus..."
$upExit = Invoke-Compose -Arguments @("up", "-d") -ComposePath $composePath -EnvPath $envPath
if ($upExit -ne 0) {
    throw "docker compose up -d ist fehlgeschlagen."
}

Write-Host "EvidoX Bootstrap abgeschlossen."
