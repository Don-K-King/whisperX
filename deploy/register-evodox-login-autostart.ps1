[CmdletBinding()]
param(
    [string]$TaskName = "EvidoX Login Autostart",
    [string]$StartScriptPath = ""
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    throw "Dieses Skript muss mit Administratorrechten ausgefuehrt werden."
}

if ([string]::IsNullOrWhiteSpace($StartScriptPath)) {
    $StartScriptPath = (Resolve-Path (Join-Path $PSScriptRoot "start-evodox.ps1")).Path
} else {
    $StartScriptPath = (Resolve-Path $StartScriptPath).Path
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Force | Out-Null

Write-Host "Task '$TaskName' wurde registriert."
Write-Host "Startskript: $StartScriptPath"
