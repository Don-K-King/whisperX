[CmdletBinding()]
param(
    [string]$ComposeFile = "deploy/docker-compose.target.yml",
    [string]$EnvFile = ".env",
    [switch]$SkipAutoPrepare,
    [int]$DockerReadyTimeoutSeconds = 180,
    [int]$DockerReadyPollIntervalSeconds = 5,
    [string]$ImageArchivePath = "C:\ProgramData\EvidoX\images\evodox-local-dev.tar",
    [switch]$SkipImageAutoLoad
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-OutputPreview {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$OutputLines
    )
    $lines = @($OutputLines | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($lines.Count -eq 0) {
        return "<keine Ausgabe>"
    }
    return ($lines | Select-Object -First 30) -join " | "
}

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$ComposePath,
        [Parameter(Mandatory = $true)]
        [string]$EnvPath
    )
    $nativeVar = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ($null -ne $nativeVar) {
        $previous = [bool]$nativeVar.Value
        Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $false -Scope Script
    }
    try {
        & docker compose --env-file $EnvPath -f $ComposePath @Arguments
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($null -ne $nativeVar) {
            Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $previous -Scope Script
        }
    }
}

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

function Resolve-EvidoXImageName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvPath
    )

    if (-not [string]::IsNullOrWhiteSpace($env:EVODOX_IMAGE)) {
        return $env:EVODOX_IMAGE.Trim()
    }

    $fromFile = Get-EnvValueFromFile -Path $EnvPath -Key "EVODOX_IMAGE"
    if (-not [string]::IsNullOrWhiteSpace($fromFile)) {
        return $fromFile
    }

    return "evodox-local:dev"
}

function Test-LocalImagePresent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ImageName
    )
    return (Invoke-DockerStatus -Arguments @("image", "inspect", $ImageName)) -eq 0
}

function Ensure-LocalRuntimeImage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ImageName,
        [Parameter(Mandatory = $true)]
        [string]$ArchivePath,
        [Parameter(Mandatory = $true)]
        [bool]$AutoLoadEnabled
    )

    if (Test-LocalImagePresent -ImageName $ImageName) {
        Write-Host "Lokales Runtime-Image vorhanden: $ImageName"
        return
    }

    Write-Host "Lokales Runtime-Image fehlt: $ImageName"
    Write-Host "Offline-Archivpfad: $ArchivePath"
    if ($AutoLoadEnabled -and (Test-Path -LiteralPath $ArchivePath)) {
        Write-Host "Image-Archiv gefunden. Fuehre docker load aus..."
        & docker load -i $ArchivePath
        if ($LASTEXITCODE -ne 0) {
            throw "docker load ist fehlgeschlagen fuer '$ArchivePath'."
        }
    } elseif (-not $AutoLoadEnabled) {
        Write-Host "Auto-Load ist deaktiviert (SkipImageAutoLoad=true)."
    } else {
        Write-Host "Kein lokales Image-Archiv gefunden."
    }

    if (-not (Test-LocalImagePresent -ImageName $ImageName)) {
        throw (
            "Lokales Runtime-Image '$ImageName' ist nicht vorhanden. " +
            "Offline-Start bricht fail-fast ab, da kein Registry-Pull im Offline-Modus moeglich ist. " +
            "Bitte zuerst online preloaden (z. B. deploy/preload-offline-runtime-image.ps1)."
        )
    }
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

    if ($TimeoutSeconds -le 0) {
        throw "DockerReadyTimeoutSeconds muss > 0 sein."
    }
    if ($PollIntervalSeconds -le 0) {
        throw "DockerReadyPollIntervalSeconds muss > 0 sein."
    }

    Write-Host "Docker-Backend-Readiness wird geprueft..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Invoke-DockerStatus -Arguments @("info")) -eq 0) {
            if ((Invoke-DockerStatus -Arguments @("version")) -eq 0) {
                Write-Host "Docker-Backend ist bereit."
                return
            }
        }
        Start-Sleep -Seconds $PollIntervalSeconds
    }
    throw "Docker-Backend war nach $TimeoutSeconds Sekunden nicht bereit."
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

    $nativeVar = Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ($null -ne $nativeVar) {
        $previous = [bool]$nativeVar.Value
        Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $false -Scope Script
    }
    try {
        $raw = & docker compose --env-file $EnvPath -f $ComposePath run --rm --no-deps `
            --volume "$RepoRoot`:/workspace" `
            --workdir "/workspace" `
            worker `
            python -m evodox.runtime.offline_readiness $Command --json 2>&1
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($null -ne $nativeVar) {
            Set-Variable -Name PSNativeCommandUseErrorActionPreference -Value $previous -Scope Script
        }
    }
    $exitCode = $LASTEXITCODE
    $allowedExitCodes = if ($Command -eq "check") { @(0, 1) } else { @(0, 2) }
    if ($allowedExitCodes -notcontains $exitCode) {
        $preview = Get-OutputPreview -OutputLines @($raw)
        throw "Offline-Readiness-Befehl '$Command' fehlgeschlagen (ExitCode=$exitCode). Ausgabe: $preview"
    }
    $jsonLine = $raw | Where-Object { $_ -match "^\s*\{.*\}\s*$" } | Select-Object -Last 1
    if (-not $jsonLine) {
        $preview = Get-OutputPreview -OutputLines @($raw)
        throw "Offline-Readiness-Befehl '$Command' lieferte kein parsebares JSON. Ausgabe: $preview"
    }
    try {
        return ($jsonLine | ConvertFrom-Json)
    } catch {
        $preview = Get-OutputPreview -OutputLines @($raw)
        throw "Offline-Readiness-JSON konnte nicht gelesen werden. Ausgabe: $preview"
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composePath = (Resolve-Path (Join-Path $repoRoot $ComposeFile)).Path
$envPath = (Resolve-Path (Join-Path $repoRoot $EnvFile)).Path

Write-Host "EvidoX Bootstrap gestartet."
Write-Host "Compose: $composePath"
Write-Host "Env: $envPath"
Write-Host "Offline-Image-Archiv: $ImageArchivePath"

Wait-ForDockerBackendReady -TimeoutSeconds $DockerReadyTimeoutSeconds -PollIntervalSeconds $DockerReadyPollIntervalSeconds

$requiredImage = Resolve-EvidoXImageName -EnvPath $envPath
Write-Host "Erwartetes Runtime-Image: $requiredImage"
Ensure-LocalRuntimeImage -ImageName $requiredImage -ArchivePath $ImageArchivePath -AutoLoadEnabled (-not $SkipImageAutoLoad.IsPresent)

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
