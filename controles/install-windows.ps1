#Requires -Version 5.1
<#
Run with powershell -NoProfile -File .\controles\install-windows.ps1 or pwsh.
All fixtures, CLI registrations and homes live under this repository and are
removed afterwards. Never writes User environment and never calls a remote.
#>
[CmdletBinding()]
param([string]$CopilotPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sandbox = Join-Path $root ('.installer-tests-' + [guid]::NewGuid().ToString('N'))
$installer = Join-Path $root 'install.ps1'
$userBefore = [Environment]::GetEnvironmentVariable('COPILOT_CUSTOM_INSTRUCTIONS_DIRS', 'User')
$processBefore = $env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS
$originalLocalAppData = $env:LOCALAPPDATA
$originalPath = $env:PATH
$passed = 0

function Assert($Condition, [string]$Message) {
    if (!$Condition) { throw "FAIL: $Message" }
    $script:passed++
    Write-Host "PASS: $Message"
}
function Fails([scriptblock]$Operation, [string]$Pattern) {
    $failure = $null
    try { & $Operation } catch { $failure = "$_" }
    Assert ($failure -and $failure -match $Pattern) "Expected refusal: $Pattern"
}
function Write-Text([string]$Path, [string]$Text) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}
# 'absent', 'true' or 'false': the Copilot Memory setting of a CLI config directory.
function Memory-Of([string]$ConfigDir) {
    $f = Join-Path $ConfigDir 'settings.json'
    if (!(Test-Path -LiteralPath $f)) { return 'absent' }
    $v = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
    if (!($v.PSObject.Properties.Name -contains 'memory')) { return 'absent' }
    return "$($v.memory)".ToLowerInvariant()
}

try {
    [IO.Directory]::CreateDirectory($sandbox) | Out-Null
    $source = Join-Path $sandbox 'source'
    [IO.Directory]::CreateDirectory($source) | Out-Null
    foreach ($name in @('.github\plugin', 'bin', 'hooks', 'skills',
        'criteres-passe.md', 'criteres-relecture.md', 'rechutes.md')) {
        $from = Join-Path $root $name
        $to = Join-Path $source $name
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to)) | Out-Null
        Copy-Item -LiteralPath $from -Destination $to -Recurse
    }
    $destination = Join-Path $sandbox 'copied plugin with spaces'
    $workshop = Join-Path $sandbox 'workshop with spaces'
    $testHome = Join-Path $sandbox 'home'
    $config = Join-Path $sandbox 'copilot'
    $params = @{
        SourcePath = $source; Destination = $destination; WorkshopRoot = $workshop
        UserName = 'Test Alice'; CopilotHome = $config; UserHome = $testHome
        EnvironmentScope = 'Process'
    }
    $cliParams = @{}
    if ($CopilotPath) { $cliParams.CopilotPath = $CopilotPath; $params.CopilotPath = $CopilotPath }
    $env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS = 'C:\existing-one, C:\existing-two '
    $dryOutput = (& $installer @params 6>&1 | Out-String -Width 10000)
    Write-Host $dryOutput
    $resolvedCli = [regex]::Match($dryOutput, 'CLI: (.+?) \| config:').Groups[1].Value
    Assert ((Test-Path -LiteralPath $resolvedCli -PathType Leaf)) 'CLI discovery resolves a real executable'
    Assert (!(Test-Path -LiteralPath $destination)) 'Dry-run creates no destination'
    Assert (!(Test-Path -LiteralPath $workshop)) 'Dry-run creates no workshop'
    Assert (!(Test-Path -LiteralPath $config)) 'Dry-run creates no CLI config'
    Assert ($env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS -ceq 'C:\existing-one, C:\existing-two ') 'Dry-run preserves Process environment exactly'
    Push-Location $sandbox
    try {
        $relative = $params.Clone()
        $relative.SourcePath = '.\source'
        $relative.Destination = '.\relative destination'
        $relative.WorkshopRoot = '.\relative workshop'
        $relative.CopilotHome = '.\relative config'
        $relative.UserHome = '.\relative home'
        $relativeOutput = & $installer @relative 6>&1 | Out-String -Width 10000
        Assert ($relativeOutput.Contains("destination: $(Join-Path $sandbox 'relative destination')")) 'Relative paths follow PowerShell location'
        Assert (!(Test-Path -LiteralPath (Join-Path $sandbox 'relative destination'))) 'Relative dry-run does not write'
    } finally { Pop-Location }
    & $installer @params -Go -WhatIf
    Assert (!(Test-Path -LiteralPath $destination)) '-Go -WhatIf still does not write'

    $fakeLocal = Join-Path $sandbox 'localappdata'
    foreach ($version in @('1.9.9', '1.10.0-0', '99.0.0')) {
        $dir = Join-Path $fakeLocal "github-copilot-sdk\cli\$version"
        [IO.Directory]::CreateDirectory($dir) | Out-Null
        if ($version -ne '99.0.0') { Write-Text (Join-Path $dir 'copilot.exe') 'not executed in dry run' }
    }
    $fakePath = Join-Path $sandbox 'path-bin'
    [IO.Directory]::CreateDirectory($fakePath) | Out-Null
    Write-Text (Join-Path $fakePath 'copilot.cmd') '@exit /b 0'
    $env:LOCALAPPDATA = $fakeLocal
    $env:PATH = "$fakePath;$originalPath"
    $discovery = $params.Clone()
    $discovery.Remove('CopilotPath')
    $detected = & $installer @discovery 6>&1 | Out-String -Width 10000
    if (!$detected.Contains("CLI: $(Join-Path $fakePath 'copilot.cmd')")) { Write-Host $detected }
    Assert ($detected.Contains("CLI: $(Join-Path $fakePath 'copilot.cmd')")) 'PATH takes precedence over SDK'
    $env:PATH = @($originalPath -split ';' | Where-Object {
        $p = $_.Trim('"')
        !(Test-Path -LiteralPath (Join-Path $p 'copilot.exe') -PathType Leaf) -and
        !(Test-Path -LiteralPath (Join-Path $p 'copilot.cmd') -PathType Leaf)
    }) -join ';'
    $detected = & $installer @discovery 6>&1 | Out-String -Width 10000
    Assert ($detected.Contains("CLI: $(Join-Path $fakeLocal 'github-copilot-sdk\cli\1.10.0-0\copilot.exe')")) 'SDK versions sorted numerically, missing executables skipped'
    $env:LOCALAPPDATA = $originalLocalAppData
    $env:PATH = $originalPath

    $emptyWorkshop = Join-Path $sandbox 'empty workshop'
    $emptyCto = Join-Path $emptyWorkshop 'CTO'
    [IO.Directory]::CreateDirectory($emptyCto) | Out-Null
    $emptyParams = @{
        SourcePath = $source; Destination = (Join-Path $sandbox 'empty plugin')
        WorkshopRoot = $emptyWorkshop; CtoName = 'CTO'; UserName = 'Test Alice'
        CopilotHome = (Join-Path $sandbox 'empty config')
        UserHome = (Join-Path $sandbox 'empty home'); EnvironmentScope = 'Process'
    }
    if ($CopilotPath) { $emptyParams.CopilotPath = $CopilotPath }
    Push-Location $emptyCto
    try {
        & $installer @emptyParams
        Assert (@(Get-ChildItem -LiteralPath $emptyCto -Force).Count -eq 0) 'Existing empty current CTO preserved by dry-run'
        & $installer @emptyParams -KeepCopilotMemory -Go
        Assert ((Memory-Of $emptyParams.CopilotHome) -eq 'absent') '-KeepCopilotMemory leaves Copilot Memory untouched'
        Assert ((Get-Location).Path -eq $emptyCto) 'Installation keeps current CTO working directory'
        Assert ((Test-Path -LiteralPath (Join-Path $emptyCto '.git'))) 'Existing current CTO initialized as its own repository'
        Assert ((Test-Path -LiteralPath (Join-Path $emptyCto 'docs\projects.json'))) 'Current CTO has an explicit empty project registry'
        Assert ((Test-Path -LiteralPath (Join-Path $emptyCto '.github\copilot-instructions.md'))) 'Current CTO has repository-local method instructions'
    } finally { Pop-Location }
    & $installer -Action Uninstall -Destination $emptyParams.Destination -Go @cliParams

    $settingsPath = Join-Path $workshop 'cto\.github\copilot\settings.json'
    Write-Text (Join-Path $workshop 'AGENTS.md') 'MY EXISTING METHOD'
    Write-Text (Join-Path $workshop 'cto\AGENTS.md') 'MY EXISTING CTO ROLE'
    Write-Text (Join-Path $workshop 'cto\brain\fact\base.md') 'MY EXISTING MEMORY'
    Write-Text $settingsPath '{"permissions":{"allow":["keep"]},"enabledPlugins":{"other@market":true},"extraKnownMarketplaces":{"other":{"source":{"source":"directory","path":"C:\\other"}}}}'
    Write-Text (Join-Path $testHome '.copilot\copilot-instructions.md') 'PRIVATE EXISTING USER INSTRUCTIONS'
    Write-Text (Join-Path $config 'settings.json') '{"customUnrelatedSetting":"global-keep","enabledPlugins":{"existing@other":false}}'
    $memoryDry = (& $installer @params 6>&1 | Out-String -Width 10000)
    Assert ($memoryDry -match 'Copilot Memory: currently absent' -and (Memory-Of $config) -eq 'absent') 'Dry-run announces Copilot Memory change without writing it'
    & $installer @params -Go
    Assert ((Memory-Of $config) -eq 'false') 'Install turns Copilot Memory off'
    Assert ((Get-Content -LiteralPath (Join-Path $config 'settings.json') -Raw | ConvertFrom-Json).customUnrelatedSetting -eq 'global-keep') 'Copilot Memory change keeps unrelated global settings'
    Assert ((Get-Content -LiteralPath (Join-Path $workshop 'AGENTS.md') -Raw) -ceq 'MY EXISTING METHOD') 'Existing workshop method preserved'
    Assert ((Get-Content -LiteralPath (Join-Path $workshop 'cto\AGENTS.md') -Raw) -ceq 'MY EXISTING CTO ROLE') 'Existing CTO role preserved'
    Assert ((Get-Content -LiteralPath (Join-Path $workshop 'cto\brain\fact\base.md') -Raw) -ceq 'MY EXISTING MEMORY') 'Existing workshop memory preserved'
    Assert ((Get-Content -LiteralPath (Join-Path $testHome '.copilot\copilot-instructions.md') -Raw) -ceq 'PRIVATE EXISTING USER INSTRUCTIONS') 'Existing user instructions preserved'
    $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    Assert ($settings.permissions.allow[0] -eq 'keep' -and $settings.enabledPlugins.'other@market') 'Unrelated settings preserved'
    Assert ($settings.extraKnownMarketplaces.'atelier-copilot'.source.path -eq $destination) 'Workshop points at copied, not source, payload'
    Assert ($env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS -ceq "C:\existing-one, C:\existing-two ,$workshop") 'Comma-separated Process environment appended without rewriting values'
    Assert (!(Test-Path -LiteralPath (Join-Path $workshop 'cto\.claude'))) 'No .claude directory created (Copilot would read it)'
    Assert ((Test-Path -LiteralPath (Join-Path $destination '.github\plugin\marketplace.json'))) 'Copied self-contained marketplace'
    $beforeSettings = Get-FileHash -LiteralPath $settingsPath
    & $installer @params -Go
    Assert ((Get-FileHash -LiteralPath $settingsPath).Hash -eq $beforeSettings.Hash) 'Repeat installation does not rewrite settings'
    Assert (@($env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS -split ',' | Where-Object { $_ -eq $workshop }).Count -eq 1) 'Repeat installation does not duplicate environment token'

    $sourceCriterion = Join-Path $source 'criteres-passe.md'
    Write-Text $sourceCriterion 'NEW DISTRIBUTION VERSION'
    $obsolete = Join-Path $source 'skills\obsolete-test\SKILL.md'
    Write-Text $obsolete 'OBSOLETE SKILL'
    & $installer -Action Update -Destination $destination -SourcePath $source -Go @cliParams
    Remove-Item -LiteralPath (Split-Path $obsolete -Parent) -Recurse -Force
    & $installer -Action Update -Destination $destination -SourcePath $source -Go @cliParams
    Assert ((Get-Content -LiteralPath (Join-Path $destination 'criteres-passe.md') -Raw) -eq 'NEW DISTRIBUTION VERSION') 'Update replaces unchanged owned payload'
    Assert (!(Test-Path -LiteralPath (Join-Path $destination 'skills\obsolete-test\SKILL.md'))) 'Update removes obsolete unchanged owned files'
    Write-Text (Join-Path $destination 'criteres-relecture.md') 'LOCAL EDIT'
    Fails { & $installer -Action Update -Destination $destination -SourcePath $source -Go @cliParams } 'Modified owned file'
    Write-Text (Join-Path $destination 'unowned.txt') 'USER FILE'
    $settings.enabledPlugins | Add-Member -NotePropertyName 'new@other' -NotePropertyValue $true
    Write-Text $settingsPath ($settings | ConvertTo-Json -Depth 20)
    $env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS += ',C:\added-later'
    & $installer -Action Uninstall -Destination $destination -Go @cliParams
    Assert (!(Test-Path -LiteralPath (Join-Path $destination 'bin\harnais-windows-x86_64.exe'))) 'Uninstall removes unchanged owned binary'
    Assert ((Get-Content -LiteralPath (Join-Path $destination 'criteres-relecture.md') -Raw) -eq 'LOCAL EDIT') 'Uninstall keeps edited owned files'
    Assert ((Get-Content -LiteralPath (Join-Path $destination 'unowned.txt') -Raw) -eq 'USER FILE') 'Uninstall keeps unowned files'
    Assert ((Test-Path -LiteralPath (Join-Path $workshop 'cto\brain\fact\base.md'))) 'Uninstall retains workshop and memory'
    $remaining = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    Assert ($remaining.enabledPlugins.'new@other' -and $remaining.enabledPlugins.'other@market') 'Uninstall preserves original and subsequently added settings'
    Assert (!($remaining.enabledPlugins.PSObject.Properties.Name -contains 'harnais@atelier-copilot')) 'Uninstall removes only owned plugin key'
    Assert ($env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS -ceq 'C:\existing-one, C:\existing-two ,C:\added-later') 'Uninstall removes only owned environment token'
    $globalRemaining = Get-Content -LiteralPath (Join-Path $config 'settings.json') -Raw | ConvertFrom-Json
    Assert ($globalRemaining.customUnrelatedSetting -eq 'global-keep' -and $globalRemaining.enabledPlugins.'existing@other' -eq $false) 'CLI uninstall preserves unrelated global configuration'
    Assert (!($globalRemaining.enabledPlugins.PSObject.Properties.Name -contains 'harnais@atelier-copilot')) 'Uninstall removes owned global disable tombstone'
    Assert ((Memory-Of $config) -eq 'absent') 'Uninstall restores an absent Copilot Memory setting'

    $memoryOn = $params.Clone()
    $memoryOn.Destination = Join-Path $sandbox 'memory on plugin'
    $memoryOn.WorkshopRoot = Join-Path $sandbox 'memory on workshop'
    $memoryOn.CopilotHome = Join-Path $sandbox 'memory on config'
    Write-Text (Join-Path $memoryOn.CopilotHome 'settings.json') '{"memory":true}'
    & $installer @memoryOn -Go
    Assert ((Memory-Of $memoryOn.CopilotHome) -eq 'false') 'Install turns an explicit Copilot Memory off'
    & $installer -Action Uninstall -Destination $memoryOn.Destination -Go @cliParams
    Assert ((Memory-Of $memoryOn.CopilotHome) -eq 'true') 'Uninstall restores an explicit previous Copilot Memory value'

    $memoryBack = $params.Clone()
    $memoryBack.Destination = Join-Path $sandbox 'memory back plugin'
    $memoryBack.WorkshopRoot = Join-Path $sandbox 'memory back workshop'
    $memoryBack.CopilotHome = Join-Path $sandbox 'memory back config'
    & $installer @memoryBack -Go
    $back = Get-Content -LiteralPath (Join-Path $memoryBack.CopilotHome 'settings.json') -Raw | ConvertFrom-Json
    $back.memory = $true
    Write-Text (Join-Path $memoryBack.CopilotHome 'settings.json') ($back | ConvertTo-Json -Depth 20)
    & $installer -Action Update -Destination $memoryBack.Destination -SourcePath $source -Go @cliParams
    Assert ((Memory-Of $memoryBack.CopilotHome) -eq 'true') 'Update respects Copilot Memory turned back on by the user'
    & $installer -Action Uninstall -Destination $memoryBack.Destination -Go @cliParams
    Assert ((Memory-Of $memoryBack.CopilotHome) -eq 'true') 'Uninstall keeps the user choice made after installation'

    $conflictParams = $params.Clone()
    $conflictParams.Destination = Join-Path $sandbox 'conflicting destination'
    $conflictParams.WorkshopRoot = Join-Path $sandbox 'conflicting workshop'
    $conflictParams.CopilotHome = Join-Path $sandbox 'conflicting config'
    Write-Text (Join-Path $conflictParams.Destination 'criteres-passe.md') 'NOT OWNED'
    Fails { & $installer @conflictParams -Go } 'Unowned destination file'
    Assert (!(Test-Path -LiteralPath $conflictParams.CopilotHome)) 'Conflict rejected before touching CLI config'
    Fails { & $installer -Action Uninstall -Destination $conflictParams.Destination -Go } 'requires an installer-owned'
    $failingCli = Join-Path $sandbox 'failing-cli.cmd'
    Write-Text $failingCli "@echo off`r`nif `"%1 %2 %3`"==`"plugin marketplace add`" (`r`n echo simulated registration failure 1>&2`r`n exit /b 37`r`n)`r`n`"$resolvedCli`" %*`r`nexit /b %errorlevel%`r`n"
    $failureParams = $params.Clone()
    $failureParams.Destination = Join-Path $sandbox 'failed install'
    $failureParams.WorkshopRoot = Join-Path $sandbox 'failed workshop'
    $failureParams.CopilotHome = Join-Path $sandbox 'failed config'
    $failureParams.CopilotPath = $failingCli
    Fails { & $installer @failureParams -Go } 'Command failed \(37\).*plugin marketplace add'
    Assert (!(Test-Path -LiteralPath $failureParams.WorkshopRoot)) 'Registration failure prevents workshop and environment changes'
    & $installer -Action Uninstall -Destination $failureParams.Destination -CopilotPath $resolvedCli -Go
    Assert (!(Test-Path -LiteralPath (Join-Path $failureParams.Destination 'bin\harnais-windows-x86_64.exe'))) 'Partial failed installation safely removable'
    $globalConflict = $params.Clone()
    $globalConflict.Destination = Join-Path $sandbox 'unowned registration destination'
    $globalConflict.WorkshopRoot = Join-Path $sandbox 'unowned registration workshop'
    $globalConflict.CopilotHome = Join-Path $sandbox 'unowned registration config'
    Write-Text (Join-Path $globalConflict.CopilotHome 'settings.json') '{"enabledPlugins":{"harnais@atelier-copilot":true}}'
    Fails { & $installer @globalConflict -Go } 'Existing global harnais configuration is unowned'
    Assert (!(Test-Path -LiteralPath $globalConflict.Destination)) 'Unowned global integration rejected without payload writes'
    Assert ([Environment]::GetEnvironmentVariable('COPILOT_CUSTOM_INSTRUCTIONS_DIRS', 'User') -ceq $userBefore) 'Actual User environment unchanged'
    Write-Host "$passed installer checks passed."
} finally {
    $env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS = $processBefore
    $env:LOCALAPPDATA = $originalLocalAppData
    $env:PATH = $originalPath
    if (Test-Path -LiteralPath $sandbox) { Remove-Item -LiteralPath $sandbox -Recurse -Force }
}
