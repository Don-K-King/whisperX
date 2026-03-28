[CmdletBinding()]
param(
    [string]$TaskName = "EvidoX Login Autostart",
    [string]$DockerTaskName = "EvidoX Docker Desktop Login Start",
    [string]$StartScriptPath = "",
    [string]$DockerDesktopPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe",
    [string]$DockerDesktopUser = "KripoEV",
    [int]$EvidoXTaskDelaySeconds = 45,
    [int]$EvidoXRestartCount = 3,
    [int]$EvidoXRestartIntervalMinutes = 2,
    [switch]$SkipDisableDockerDesktopAutostart
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-QualifiedUser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$UserName
    )
    if ($UserName.Contains("\")) {
        return $UserName
    }
    return "$env:USERDOMAIN\$UserName"
}

function Resolve-UserSid {
    param(
        [Parameter(Mandatory = $true)]
        [string]$QualifiedUser
    )
    $account = New-Object System.Security.Principal.NTAccount($QualifiedUser)
    return $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
}

function Resolve-UserProfilePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Sid
    )
    $profile = Get-CimInstance Win32_UserProfile | Where-Object { $_.SID -eq $Sid } | Select-Object -First 1
    if ($null -eq $profile) {
        return $null
    }
    return $profile.LocalPath
}

function Disable-DockerDesktopAutostartForUser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$QualifiedUser
    )

    # Docker Desktop Autostart: best effort disable to prevent race with scheduled startup orchestration.
    Write-Host "Docker Desktop Autostart wird fuer '$QualifiedUser' deaktiviert (best effort)."
    $sid = Resolve-UserSid -QualifiedUser $QualifiedUser

    $runKeyPath = "Registry::HKEY_USERS\$sid\Software\Microsoft\Windows\CurrentVersion\Run"
    if (Test-Path -LiteralPath $runKeyPath) {
        Remove-ItemProperty -Path $runKeyPath -Name "Docker Desktop" -ErrorAction SilentlyContinue
    }

    $profilePath = Resolve-UserProfilePath -Sid $sid
    if (-not [string]::IsNullOrWhiteSpace($profilePath)) {
        $settingsStorePath = Join-Path $profilePath "AppData\Roaming\Docker\settings-store.json"
        if (Test-Path -LiteralPath $settingsStorePath) {
            try {
                $json = Get-Content -LiteralPath $settingsStorePath -Raw | ConvertFrom-Json
                if ($null -eq $json.PSObject.Properties["autoStart"]) {
                    Add-Member -InputObject $json -NotePropertyName "autoStart" -NotePropertyValue $false
                } else {
                    $json.autoStart = $false
                }
                $json | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $settingsStorePath -Encoding utf8
            } catch {
                Write-Warning "settings-store.json konnte nicht angepasst werden: $($_.Exception.Message)"
            }
        }
    }
}

if (-not (Test-IsAdmin)) {
    throw "Dieses Skript muss mit Administratorrechten ausgefuehrt werden."
}

if ([string]::IsNullOrWhiteSpace($StartScriptPath)) {
    $StartScriptPath = (Resolve-Path (Join-Path $PSScriptRoot "start-evodox.ps1")).Path
} else {
    $StartScriptPath = (Resolve-Path $StartScriptPath).Path
}
$DockerDesktopPath = (Resolve-Path $DockerDesktopPath).Path
$qualifiedDockerDesktopUser = Resolve-QualifiedUser -UserName $DockerDesktopUser

if (-not $SkipDisableDockerDesktopAutostart.IsPresent) {
    Disable-DockerDesktopAutostartForUser -QualifiedUser $qualifiedDockerDesktopUser
}

$dockerAction = New-ScheduledTaskAction -Execute $DockerDesktopPath
$dockerTrigger = New-ScheduledTaskTrigger -AtLogOn -User $qualifiedDockerDesktopUser
$dockerPrincipal = New-ScheduledTaskPrincipal -UserId $qualifiedDockerDesktopUser -LogonType Interactive -RunLevel Highest
$dockerSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $DockerTaskName `
    -Action $dockerAction `
    -Trigger $dockerTrigger `
    -Principal $dockerPrincipal `
    -Settings $dockerSettings `
    -Force | Out-Null

$startArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$StartScriptPath`""
$systemAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $startArguments
$systemTrigger = New-ScheduledTaskTrigger -AtLogOn
if ($EvidoXTaskDelaySeconds -gt 0) {
    $systemTrigger.Delay = "PT$EvidoXTaskDelaySeconds`S"
}
$systemPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$systemSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount $EvidoXRestartCount `
    -RestartInterval (New-TimeSpan -Minutes $EvidoXRestartIntervalMinutes)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $systemAction `
    -Trigger $systemTrigger `
    -Principal $systemPrincipal `
    -Settings $systemSettings `
    -Force | Out-Null

Write-Host "Task '$DockerTaskName' wurde registriert (User: $qualifiedDockerDesktopUser)."
Write-Host "Task '$TaskName' wurde registriert (SYSTEM, Delay: $EvidoXTaskDelaySeconds s, RestartCount: $EvidoXRestartCount)."
Write-Host "Startskript: $StartScriptPath"
