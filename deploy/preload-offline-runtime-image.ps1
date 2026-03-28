[CmdletBinding()]
param(
    [string]$EnvFile = ".env",
    [string]$DockerfilePath = "deploy/Dockerfile.runtime",
    [string]$ImageName = "",
    [string]$ImageArchivePath = "C:\ProgramData\EvidoX\images\evodox-local-dev.tar",
    [switch]$ForceBuild,
    [switch]$SkipArchive,
    [int]$DockerReadyTimeoutSeconds = 180,
    [int]$DockerReadyPollIntervalSeconds = 5
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-DockerStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )
    $nativeVar = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ($null -ne $nativeVar) {
        $previous = [bool]$nativeVar.Value
        Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $false -Scope Script
    }
    try {
        try {
            & docker @Arguments 1>$null 2>$null
        } catch {
            # ExitCode is evaluated below; stderr in probe mode is expected.
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($null -ne $nativeVar) {
            Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $previous -Scope Script
        }
    }
}

function Get-EnvValueFromFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $escapedKey = [Regex]::Escape($Key)
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = [string]$rawLine
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line.TrimStart().StartsWith("#")) {
            continue
        }
        if ($line -notmatch "^\s*$escapedKey\s*=") {
            continue
        }
        $value = $line -replace "^\s*$escapedKey\s*=\s*", ""
        $value = $value.Trim()
        if (((($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) -and $value.Length -ge 2)) {
            $value = $value.Substring(1, $value.Length - 2)
        } else {
            $value = ($value -split "\s+#", 2)[0].Trim()
        }
        return $value
    }
    return $null
}

function Wait-ForDockerBackendReady {
    param(
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [int]$PollIntervalSeconds
    )

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI wurde nicht gefunden. Bitte Docker Desktop korrekt installieren."
    }
    Write-Host "Pruefe Docker-Backend-Readiness..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Invoke-DockerStatus -Arguments @("info")) -eq 0) {
            Write-Host "Docker-Backend ist bereit."
            return
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
    throw "Docker-Backend war nach $TimeoutSeconds Sekunden nicht bereit."
}

function Test-LocalImagePresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ImageToCheck
    )
    return (Invoke-DockerStatus -Arguments @("image", "inspect", $ImageToCheck)) -eq 0
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = (Resolve-Path (Join-Path $repoRoot $EnvFile)).Path
$dockerfile = (Resolve-Path (Join-Path $repoRoot $DockerfilePath)).Path

if ([string]::IsNullOrWhiteSpace($ImageName)) {
    $ImageName = Get-EnvValueFromFile -Path $envPath -Key "EVODOX_IMAGE"
}
if ([string]::IsNullOrWhiteSpace($ImageName)) {
    $ImageName = "evodox-local:dev"
}

Write-Host "EvidoX Offline-Image-Preload gestartet."
Write-Host "Repo: $repoRoot"
Write-Host "Dockerfile: $dockerfile"
Write-Host "Image: $ImageName"
Write-Host "Archive-Ziel: $ImageArchivePath"

Wait-ForDockerBackendReady -TimeoutSeconds $DockerReadyTimeoutSeconds -PollIntervalSeconds $DockerReadyPollIntervalSeconds

$needsBuild = $ForceBuild.IsPresent -or -not (Test-LocalImagePresent -ImageToCheck $ImageName)
if ($needsBuild) {
    if ($ImageName.StartsWith("evodox-local:") -or $ForceBuild.IsPresent) {
        Write-Host "Baue Runtime-Image lokal..."
        & docker build -f $dockerfile -t $ImageName $repoRoot
        if ($LASTEXITCODE -ne 0) {
            throw "docker build ist fehlgeschlagen."
        }
    } else {
        Write-Host "Lade Runtime-Image aus Registry..."
        & docker pull $ImageName
        if ($LASTEXITCODE -ne 0) {
            throw "docker pull ist fehlgeschlagen fuer '$ImageName'."
        }
    }
} else {
    Write-Host "Image ist bereits lokal vorhanden."
}

if (-not (Test-LocalImagePresent -ImageToCheck $ImageName)) {
    throw "Runtime-Image '$ImageName' ist nach Preload nicht lokal verfuegbar."
}

if (-not $SkipArchive.IsPresent) {
    $archiveDir = Split-Path -Path $ImageArchivePath -Parent
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    Write-Host "Erzeuge Offline-Archiv..."
    & docker save -o $ImageArchivePath $ImageName
    if ($LASTEXITCODE -ne 0) {
        throw "docker save ist fehlgeschlagen fuer '$ImageName'."
    }
}

Write-Host "EvidoX Offline-Image-Preload abgeschlossen."
