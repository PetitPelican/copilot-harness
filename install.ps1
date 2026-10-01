#Requires -Version 5.1
<#
.SYNOPSIS
Installs the local, prebuilt Windows harnais distribution. Dry-run by default.
.DESCRIPTION
No download, Rust build or personal paths. -Go authorizes
writes; -WhatIf still prevents them. Existing instructions and unrelated
settings are preserved. Updates replace only unchanged installer-owned files.
Uninstall removes owned registration/settings/environment entries and unchanged
payload files, but always keeps the workshop, its Git repository and memory.
Close and reopen Copilot (and the terminal for User environment changes).
.EXAMPLE
.\install.ps1 -WorkshopRoot C:\Atelier -UserName Alice -Destination C:\Tools\harnais
.EXAMPLE
.\install.ps1 -WorkshopRoot C:\Atelier -UserName Alice -Destination C:\Tools\harnais -Go
.EXAMPLE
.\install.ps1 -Action Update -Destination C:\Tools\harnais -SourcePath C:\Distribution -Go
.EXAMPLE
.\install.ps1 -Action Uninstall -Destination C:\Tools\harnais -Go
.EXAMPLE
.\install.ps1 -WorkshopRoot C:\Test\atelier -UserName Test -Destination C:\Test\paquet -CopilotHome C:\Test\config -UserHome C:\Test\home -EnvironmentScope Process -Go
.PARAMETER SourcePath
Local unpacked repository/distribution, defaulting to this script's directory.
.PARAMETER CopilotPath
Optional explicit CLI executable. Otherwise PATH, then LOCALAPPDATA SDK versions.
.PARAMETER EnvironmentScope
User (default): append to both User and Process variables. Process: never writes
User environment. None: leave environment untouched and print the required step.
.PARAMETER CopilotHome
CLI config directory. Defaults to COPILOT_HOME, otherwise UserHome\.copilot.
.PARAMETER UserHome
Optional isolated home for child commands; no changes to persistent home settings.
.PARAMETER KeepCopilotMemory
Leave Copilot Memory as it is. By default the installer sets "memory": false in
CopilotHome\settings.json so that brain/ stays the only home of project facts,
records the previous value, and restores it on uninstall if still unchanged.
#>
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Medium')]
param(
    [ValidateSet('Install', 'Update', 'Uninstall')][string]$Action = 'Install',
    [string]$SourcePath = $PSScriptRoot,
    [Parameter(Mandatory = $true)][string]$Destination,
    [string]$WorkshopRoot,
    [string]$UserName,
    [ValidatePattern('^[^\\/:*?"<>|.][^\\/:*?"<>|]*$')][string]$CtoName = 'cto',
    [string]$CopilotPath,
    [string]$CopilotHome,
    [string]$UserHome,
    [ValidateSet('User', 'Process', 'None')][string]$EnvironmentScope = 'User',
    [switch]$KeepCopilotMemory,
    [switch]$Go
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:InstallerPSCmdlet = $PSCmdlet
$script:EnvironmentName = 'COPILOT_CUSTOM_INSTRUCTIONS_DIRS'
$script:StateName = '.harnais-install.json'
$script:Marketplace = 'atelier-copilot'
$script:Plugin = 'harnais@atelier-copilot'

function Full-Path([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'An empty path is not allowed.' }
    if ($Path -match '^[a-z]+://' -or $Path.StartsWith('\\')) {
        throw "Only local filesystem paths are supported: $Path"
    }
    $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    if ($full -eq [IO.Path]::GetPathRoot($full)) { return $full }
    return $full.TrimEnd('\')
}

function Is-Inside([string]$Child, [string]$Parent) {
    return $Child.Equals($Parent, [StringComparison]::OrdinalIgnoreCase) -or
        $Child.StartsWith($Parent.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Assert-NoLinks([string]$Path) {
    $p = $Path
    while ($p) {
        if (Test-Path -LiteralPath $p) {
            $item = Get-Item -LiteralPath $p -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing a symlink/junction/reparse point: $p"
            }
        }
        $p = [IO.Path]::GetDirectoryName($p)
    }
}

function To-Map($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [System.Collections.IDictionary]) { return ,$Value }
    if ($Value -is [array]) {
        $items = @($Value | ForEach-Object { To-Map $_ })
        return ,$items
    }
    if ($Value -is [pscustomobject]) {
        $map = @{}
        foreach ($p in $Value.PSObject.Properties) { $map[$p.Name] = To-Map $p.Value }
        return ,$map
    }
    return $Value
}

function Read-Json([string]$Path) {
    $v = To-Map (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
    if ($v -isnot [System.Collections.IDictionary]) { throw "Expected a JSON object: $Path" }
    return $v
}

function Write-Json([string]$Path, $Value) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 100) + "`n",
        (New-Object Text.UTF8Encoding($false)))
}

function Save-State {
    $next = $script:StatePath + '.new'
    if (Test-Path -LiteralPath $next) { throw "Unowned/stale journal staging file: $next" }
    try {
        Write-Json $next $script:State
        Move-Item -LiteralPath $next -Destination $script:StatePath -Force
    } finally {
        if (Test-Path -LiteralPath $next) { Remove-Item -LiteralPath $next -Force }
    }
}

function Find-Copilot {
    if ($CopilotPath) {
        $p = Full-Path $CopilotPath
        if (!(Test-Path -LiteralPath $p -PathType Leaf)) { throw "Copilot CLI not found: $p" }
        return $p
    }
    $command = Get-Command copilot -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($command) { return $command.Source }
    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $sdk = Join-Path $env:LOCALAPPDATA 'github-copilot-sdk\cli'
        if (Test-Path -LiteralPath $sdk -PathType Container) {
            foreach ($d in Get-ChildItem -LiteralPath $sdk -Directory) {
                $exe = Join-Path $d.FullName 'copilot.exe'
                if (Test-Path -LiteralPath $exe -PathType Leaf) {
                    $version = [version]'0.0'
                    if ($d.Name -match '^(\d+\.\d+\.\d+)(?:[-+].*)?$') {
                        $version = [version]$Matches[1]
                    }
                    $candidates += [pscustomobject]@{
                        Path = $exe; Version = $version; Stable = ($d.Name -notmatch '-')
                        Modified = $d.LastWriteTimeUtc
                    }
                }
            }
        }
    }
    $best = $candidates | Sort-Object Version, Stable, Modified -Descending | Select-Object -First 1
    if ($best) { return $best.Path }
    throw 'Copilot CLI not found. Put copilot on PATH or supply -CopilotPath. No download is attempted.'
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments, [switch]$Json) {
    $saved = @{}
    $vars = @{
        COPILOT_HOME = $CopilotHome; HOME = $UserHome; USERPROFILE = $UserHome
        COPILOT_PLUGIN_ROOT = $Destination; PLUGIN_ROOT = $Destination
    }
    $code = 0
    try {
        foreach ($key in $vars.Keys) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, $vars[$key], 'Process')
        }
        $oldPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $output = @(& $Executable @Arguments 2>&1)
        $code = $LASTEXITCODE
        $ErrorActionPreference = $oldPreference
    } finally {
        foreach ($key in $saved.Keys) {
            [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process')
        }
    }
    $text = ($output | ForEach-Object { "$_" }) -join "`n"
    if ($code -ne 0) { throw "Command failed ($code): $Executable $($Arguments -join ' ')`n$text" }
    if ($Json) {
        try {
            $parsed = To-Map (ConvertFrom-Json -InputObject $text)
            if ($null -eq $parsed) { return }
            return $parsed
        }
        catch { throw "CLI did not return valid JSON: $Executable $($Arguments -join ' ')`n$text" }
    }
    if ($text) { Write-Host $text }
}

function Get-Registrations {
    $script:Markets = @(Invoke-Checked $script:Cli @('plugin', 'marketplace', 'list', '--json') -Json)
    $script:Plugins = @(Invoke-Checked $script:Cli @('plugin', 'list', '--json') -Json)
    $script:OurMarket = @($script:Markets | Where-Object { $_.name -eq $script:Marketplace })
    $script:OurPlugin = @($script:Plugins | Where-Object {
        $_.name -eq 'harnais' -and $_.marketplace -eq $script:Marketplace
    })
}

function Assert-Registrations {
    if ($script:OurMarket.Count) {
        if (!$script:State.marketplaceOwned -or
            $script:OurMarket[0].source -ne "Local: $Destination") {
            throw 'Existing atelier-copilot registration is not owned by this installation; refusing to replace/remove it.'
        }
    }
    if ($script:OurPlugin.Count) {
        if (!$script:State.pluginOwned -or
            $script:OurPlugin[0].installedFrom -ne $Destination) {
            throw 'Existing harnais registration is not owned by this installation; refusing to replace/remove it.'
        }
    }
}

function Has-Token([string]$Value, [string]$Token) {
    foreach ($part in ($Value -split ',')) {
        if ($part.Trim().TrimEnd('\').Equals($Token.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Add-Environment {
    if ($EnvironmentScope -eq 'None') { return }
    $scopes = @('Process')
    if ($EnvironmentScope -eq 'User') { $scopes = @('User', 'Process') }
    foreach ($scope in $scopes) {
        $before = [Environment]::GetEnvironmentVariable($script:EnvironmentName, $scope)
        if (!(Has-Token $before $WorkshopRoot)) {
            $after = if ([string]::IsNullOrEmpty($before)) { $WorkshopRoot } else { "$before,$WorkshopRoot" }
            if (!$script:State.environment.ContainsKey($scope)) {
                $script:State.environment[$scope] = @{ before = $before; after = $after }
                Save-State
            }
            [Environment]::SetEnvironmentVariable($script:EnvironmentName, $after, $scope)
        }
    }
}

function Remove-Environment {
    foreach ($scope in @($script:State.environment.Keys)) {
        $entry = $script:State.environment[$scope]
        $current = [Environment]::GetEnvironmentVariable($script:EnvironmentName, $scope)
        if ($current -ceq $entry.after) { $new = $entry.before }
        else {
            $new = (@($current -split ',' | Where-Object {
                !($_.Trim().TrimEnd('\').Equals($WorkshopRoot.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase))
            })) -join ','
        }
        [Environment]::SetEnvironmentVariable($script:EnvironmentName, $new, $scope)
        $script:State.environment.Remove($scope)
        Save-State
    }
}

function Settings-Plan([string]$Path = (Join-Path (Join-Path $WorkshopRoot $CtoName) '.github\copilot\settings.json')) {
    Assert-NoLinks $path
    $settings = if (Test-Path -LiteralPath $path) { Read-Json $path } else { @{} }
    foreach ($key in @('extraKnownMarketplaces', 'enabledPlugins')) {
        if ($settings.ContainsKey($key) -and $settings[$key] -isnot [System.Collections.IDictionary]) {
            throw "$key must be an object in $path"
        }
    }
    $mkPresent = $settings.ContainsKey('extraKnownMarketplaces') -and
        $settings.extraKnownMarketplaces.ContainsKey($script:Marketplace)
    $epPresent = $settings.ContainsKey('enabledPlugins') -and
        $settings.enabledPlugins.ContainsKey($script:Plugin)
    if ($mkPresent) {
        $value = $settings.extraKnownMarketplaces[$script:Marketplace]
        if ($value -isnot [System.Collections.IDictionary] -or !$value.ContainsKey('source') -or
            $value.source -isnot [System.Collections.IDictionary] -or
            !$value.source.ContainsKey('source') -or !$value.source.ContainsKey('path') -or
            $value.source.source -ne 'directory' -or $value.source.path -ne $Destination) {
            throw "Conflicting workshop marketplace settings: $path"
        }
    }
    if ($epPresent -and $settings.enabledPlugins[$script:Plugin] -isnot [bool]) {
        throw "Workshop plugin flag must be a boolean: $path"
    }
    if ($epPresent -and $settings.enabledPlugins[$script:Plugin] -ne $true) {
        throw "Workshop explicitly disables harnais; refusing to overwrite: $path"
    }
    return @{ path = $path; marketplaceAdded = !$mkPresent; pluginAdded = !$epPresent }
}

function Remove-OwnedSettings($Plan, [bool]$PluginValue = $true) {
    if (!$Plan -or !(Test-Path -LiteralPath $Plan.path)) { return }
    Assert-NoLinks $plan.path
    $v = Read-Json $plan.path
    $changed = $false
    if ($plan.pluginAdded -and $v.ContainsKey('enabledPlugins') -and
        $v.enabledPlugins -is [System.Collections.IDictionary] -and
        $v.enabledPlugins.ContainsKey($script:Plugin) -and $v.enabledPlugins[$script:Plugin] -is [bool] -and
        $v.enabledPlugins[$script:Plugin] -eq $PluginValue) {
        $v.enabledPlugins.Remove($script:Plugin)
        $changed = $true
    }
    if ($plan.marketplaceAdded -and $v.ContainsKey('extraKnownMarketplaces') -and
        $v.extraKnownMarketplaces -is [System.Collections.IDictionary] -and
        $v.extraKnownMarketplaces.ContainsKey($script:Marketplace)) {
        $m = $v.extraKnownMarketplaces[$script:Marketplace]
        if ($m -is [System.Collections.IDictionary] -and $m.ContainsKey('source') -and
            $m.source -is [System.Collections.IDictionary] -and
            $m.source.ContainsKey('source') -and $m.source.ContainsKey('path') -and
            $m.source.source -eq 'directory' -and $m.source.path -eq $Destination) {
            $v.extraKnownMarketplaces.Remove($script:Marketplace)
            $changed = $true
        }
    }
    if ($changed) { Write-Json $plan.path $v }
}

# Copilot Memory: "memory" in the CLI user settings, true when absent (CLI 1.0.90-0).
function Memory-Plan([string]$Path) {
    Assert-NoLinks $Path
    $settings = if (Test-Path -LiteralPath $Path) { Read-Json $Path } else { @{} }
    if (!$settings.ContainsKey('memory')) { return @{ path = $Path; previous = 'absent' } }
    if ($settings.memory -isnot [bool]) { throw "Copilot setting memory must be a boolean: $Path" }
    return @{ path = $Path; previous = $(if ($settings.memory) { 'true' } else { 'false' }) }
}

function Set-MemoryOff([string]$Path) {
    Assert-NoLinks $Path
    $v = if (Test-Path -LiteralPath $Path) { Read-Json $Path } else { @{} }
    $v['memory'] = $false
    Write-Json $Path $v
}

function Restore-Memory($Owned) {
    if (!$Owned -or !(Test-Path -LiteralPath $Owned.path)) { return }
    Assert-NoLinks $Owned.path
    $v = Read-Json $Owned.path
    # Changed by the user since installation: their choice, not ours.
    if (!$v.ContainsKey('memory') -or $v.memory -isnot [bool] -or $v.memory) { return }
    if ($Owned.previous -eq 'absent') { $v.Remove('memory') } else { $v['memory'] = $true }
    Write-Json $Owned.path $v
}

$Destination = Full-Path $Destination
Assert-NoLinks $Destination
$script:StatePath = Join-Path $Destination $script:StateName
Assert-NoLinks $script:StatePath
$existingState = Test-Path -LiteralPath $script:StatePath -PathType Leaf
if ($existingState) {
    $script:State = Read-Json $script:StatePath
    if ($script:State.schema -ne 1 -or $script:State.destination -ne $Destination) {
        throw 'Invalid ownership journal; refusing to continue.'
    }
    foreach ($key in @('WorkshopRoot', 'UserName', 'CtoName', 'CopilotHome', 'UserHome', 'EnvironmentScope')) {
        if ($PSBoundParameters.ContainsKey($key) -and (Get-Variable $key -ValueOnly) -ne $script:State[$key]) {
            throw "$key differs from the ownership journal. Use another destination."
        }
        Set-Variable -Name $key -Value $script:State[$key]
    }
} elseif ($Action -ne 'Install') {
    throw "$Action requires an installer-owned destination ($script:StateName)."
}
if (!$WorkshopRoot -or [string]::IsNullOrWhiteSpace($UserName)) {
    throw 'Install requires -WorkshopRoot and -UserName; no personal/default workshop is assumed.'
}
$WorkshopRoot = Full-Path $WorkshopRoot
if ($WorkshopRoot.Contains(',')) { throw 'WorkshopRoot cannot contain a comma (instructions directories use commas).' }
if ($CtoName -in @('.', '..') -or $CtoName.EndsWith('.') -or $CtoName.EndsWith(' ')) { throw 'Invalid CTO directory name.' }
if (!$UserHome) { $UserHome = $env:USERPROFILE }
$UserHome = Full-Path $UserHome
if (!$CopilotHome) {
    $CopilotHome = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $UserHome '.copilot' }
}
$CopilotHome = Full-Path $CopilotHome
Assert-NoLinks $WorkshopRoot
Assert-NoLinks $CopilotHome
if ((Is-Inside $Destination $WorkshopRoot) -or (Is-Inside $WorkshopRoot $Destination)) {
    throw 'Destination and workshop must be separate, non-nested directories.'
}
if ((Is-Inside $Destination $CopilotHome) -or (Is-Inside $CopilotHome $Destination)) {
    throw 'Destination and CopilotHome must be separate, non-nested directories.'
}
$script:Cli = Find-Copilot
$payload = @{}
if ($Action -ne 'Uninstall') {
    $SourcePath = Full-Path $SourcePath
    Assert-NoLinks $SourcePath
    if ((Is-Inside $Destination $SourcePath) -or (Is-Inside $SourcePath $Destination)) {
        throw 'Source and destination must be separate, non-nested directories.'
    }
    if ((Is-Inside $CopilotHome $SourcePath) -or
        (Is-Inside (Join-Path $WorkshopRoot $CtoName) $SourcePath) -or $WorkshopRoot -eq $SourcePath) {
        throw 'Config and workshop writes must not modify the source distribution.'
    }
    $marketFile = Join-Path $SourcePath '.github\plugin\marketplace.json'
    $pluginFile = Join-Path $SourcePath '.github\plugin\plugin.json'
    $market = Read-Json $marketFile
    $pluginManifest = Read-Json $pluginFile
    $entry = @($market.plugins | Where-Object { $_.name -eq 'harnais' })
    if ($market.name -ne $script:Marketplace -or $entry.Count -ne 1 -or
        $entry[0].source -notin @('./', '.') -or $pluginManifest.name -ne 'harnais' -or
        $pluginManifest.hooks -ne 'hooks/copilot.json') {
        throw 'Unsupported distribution: expected atelier-copilot/harnais at local source "./" with hooks/copilot.json.'
    }
    foreach ($required in @('bin\harnais-windows-x86_64.exe', 'hooks\copilot.json', 'skills')) {
        if (!(Test-Path -LiteralPath (Join-Path $SourcePath $required))) { throw "Distribution missing $required" }
    }
    foreach ($relative in @('.github\plugin', 'bin', 'hooks', 'skills',
        'criteres-passe.md', 'criteres-relecture.md', 'rechutes.md')) {
        $path = Join-Path $SourcePath $relative
        if (!(Test-Path -LiteralPath $path)) { continue }
        Assert-NoLinks $path
        $items = if (Test-Path -LiteralPath $path -PathType Container) {
            @(Get-ChildItem -LiteralPath $path -Recurse -Force)
        } else { @(Get-Item -LiteralPath $path) }
        foreach ($item in $items) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Distribution contains a reparse point: $($item.FullName)" }
            if (!$item.PSIsContainer) {
                $rel = $item.FullName.Substring($SourcePath.Length + 1)
                $payload[$rel] = @{ source = $item.FullName; hash = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash }
            }
        }
    }
    if (!(Get-Command git -CommandType Application -ErrorAction SilentlyContinue)) { throw 'git is required by atelier-monte (Rust is not).' }
}
if (!$existingState) {
    $script:State = @{
        schema = 1; destination = $Destination; WorkshopRoot = $WorkshopRoot
        UserName = $UserName; CtoName = $CtoName; CopilotHome = $CopilotHome
        UserHome = $UserHome; EnvironmentScope = $EnvironmentScope
        files = @{}; environment = @{}; settings = $null; cliSettings = $null
        marketplaceOwned = $false; pluginOwned = $false
    }
}
foreach ($rel in @($script:State.files.Keys)) {
    $path = Full-Path (Join-Path $Destination $rel)
    if (!(Is-Inside $path $Destination) -or $path -eq $Destination -or $rel -eq $script:StateName) {
        throw "Unsafe path in ownership journal: $rel"
    }
    Assert-NoLinks $path
    if ($Action -ne 'Uninstall' -and (Test-Path -LiteralPath $path)) {
        if (!(Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $script:State.files[$rel]) {
            throw "Modified owned file; preserve it and resolve before updating: $path"
        }
    }
}
foreach ($rel in $payload.Keys) {
    $target = Join-Path $Destination $rel
    Assert-NoLinks $target
    if (Test-Path -LiteralPath $target) {
        if (!(Test-Path -LiteralPath $target -PathType Leaf)) { throw "File/directory conflict: $target" }
        $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($script:State.files.ContainsKey($rel)) {
            if ($hash -ne $script:State.files[$rel]) { throw "Modified owned file; preserve it and resolve before updating: $target" }
        } elseif ($hash -ne $payload[$rel].hash) { throw "Unowned destination file; refusing to overwrite: $target" }
    }
}
if ($Action -ne 'Uninstall') {
    $settingsPlan = Settings-Plan
    $cliSettingsPlan = Settings-Plan (Join-Path $CopilotHome 'settings.json')
    if (!$existingState -and (!$cliSettingsPlan.pluginAdded -or !$cliSettingsPlan.marketplaceAdded)) {
        throw 'Existing global harnais configuration is unowned; refusing to replace it.'
    }
    $binary = Join-Path $SourcePath 'bin\harnais-windows-x86_64.exe'
    Invoke-Checked $binary @('version')
    $memoryPlan = Memory-Plan (Join-Path $CopilotHome 'settings.json')
}
Write-Host "$Action | source: $SourcePath | destination: $Destination"
Write-Host "CLI: $script:Cli | config: $CopilotHome"
Write-Host "Workshop: $WorkshopRoot | CTO: $CtoName | user: $UserName | environment: $EnvironmentScope"
$memoryOwned = $script:State.ContainsKey('memory') -and $script:State.memory
if ($Action -eq 'Uninstall') {
    if ($memoryOwned) { Write-Host "Copilot Memory: restore previous value ($($script:State.memory.previous)) if still off." }
} elseif ($KeepCopilotMemory) {
    Write-Host 'Copilot Memory: left as is (-KeepCopilotMemory).'
} elseif ($memoryPlan.previous -eq 'false') {
    Write-Host 'Copilot Memory: already off.'
} elseif ($memoryOwned) {
    Write-Warning "Copilot Memory was turned back on after installation; left on. Turn it off with /memory off."
} else {
    Write-Host "Copilot Memory: currently $($memoryPlan.previous) in $($memoryPlan.path); will set `"memory`": false so brain/ stays the only home of facts (restored on uninstall; -KeepCopilotMemory to skip)."
}
if (!$Go -or !$script:InstallerPSCmdlet.ShouldProcess($Destination, "$Action harnais and its owned registration")) {
    Write-Host 'DRY RUN: no files, registrations or environment values changed. Use -Go to apply.'
    if ($Action -eq 'Uninstall') {
        Write-Host "Remove owned registration with: copilot plugin uninstall $script:Plugin; copilot plugin marketplace remove $script:Marketplace (never --force)"
        Write-Host 'Keep workshop, memory, Git history and all modified/unowned files.'
    } else {
        Write-Host "Install/update runs: copilot plugin marketplace add `"$Destination`"; copilot plugin install $script:Plugin"
        Write-Host "Workshop command: harnais atelier-monte --racine `"$WorkshopRoot`" --cto `"$CtoName`" --utilisateur `"$UserName`" --go"
    }
    return
}

[IO.Directory]::CreateDirectory($Destination) | Out-Null
$lockPath = Join-Path $Destination '.harnais-install.lock'
$lock = $null
try {
    $lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    Get-Registrations
    Assert-Registrations
    if ($Action -eq 'Uninstall') {
        if ($script:State.pluginOwned -and $script:OurPlugin.Count) {
            Invoke-Checked $script:Cli @('plugin', 'uninstall', $script:Plugin)
        }
        $script:State.pluginOwned = $false
        Save-State
        if ($script:State.marketplaceOwned -and $script:OurMarket.Count) {
            Invoke-Checked $script:Cli @('plugin', 'marketplace', 'remove', $script:Marketplace)
        }
        $script:State.marketplaceOwned = $false
        Save-State
        Remove-OwnedSettings $script:State.settings
        Remove-OwnedSettings $script:State.cliSettings $false
        if ($memoryOwned) { Restore-Memory $script:State.memory }
        Remove-Environment
        foreach ($rel in @($script:State.files.Keys)) {
            $path = Join-Path $Destination $rel
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -eq $script:State.files[$rel]) {
                    Remove-Item -LiteralPath $path -Force
                } else { Write-Warning "Kept modified file: $path" }
            }
            $script:State.files.Remove($rel)
        }
        Remove-Item -LiteralPath $script:StatePath -Force
        Write-Host 'Uninstalled owned integration. Workshop, Git history, memory, changed/unowned files and unrelated settings remain.'
    } else {
        if (!$script:State.settings) { $script:State.settings = $settingsPlan }
        if (!$script:State.cliSettings) { $script:State.cliSettings = $cliSettingsPlan }
        Save-State
        foreach ($rel in $payload.Keys) {
            $path = Join-Path $Destination $rel
            $owned = $script:State.files.ContainsKey($rel)
            if ($owned -or !(Test-Path -LiteralPath $path)) {
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path)) | Out-Null
                $script:State.files[$rel] = $payload[$rel].hash
                Save-State
                Copy-Item -LiteralPath $payload[$rel].source -Destination $path -Force
            }
        }
        foreach ($rel in @($script:State.files.Keys)) {
            if (!$payload.ContainsKey($rel)) {
                $path = Join-Path $Destination $rel
                if (Test-Path -LiteralPath $path -PathType Leaf) {
                    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $script:State.files[$rel]) {
                        throw "Modified obsolete owned file; refusing to remove: $path"
                    }
                    Remove-Item -LiteralPath $path -Force
                }
                $script:State.files.Remove($rel)
                Save-State
            }
        }
        if (!$script:OurMarket.Count) {
            $script:State.marketplaceOwned = $true
            Save-State
            Invoke-Checked $script:Cli @('plugin', 'marketplace', 'add', $Destination)
        }
        if (!$script:OurPlugin.Count) {
            $script:State.pluginOwned = $true
            Save-State
            Invoke-Checked $script:Cli @('plugin', 'install', $script:Plugin)
        }
        Get-Registrations
        Assert-Registrations
        if (!$script:OurMarket.Count -or !$script:OurPlugin.Count) { throw 'CLI reported success but registration is absent.' }
        # After the CLI registration, which rewrites the same settings file.
        $memoryPlan = Memory-Plan (Join-Path $CopilotHome 'settings.json')
        if (!$KeepCopilotMemory -and !$memoryOwned -and $memoryPlan.previous -ne 'false') {
            $script:State.memory = $memoryPlan
            Save-State
            Set-MemoryOff $memoryPlan.path
        }
        $atelierArgs = @('atelier-monte', '--racine', $WorkshopRoot, '--cto', $CtoName,
            '--utilisateur', $UserName, '--go')
        Invoke-Checked (Join-Path $Destination 'bin\harnais-windows-x86_64.exe') $atelierArgs
        $cto = Join-Path $WorkshopRoot $CtoName
        $gitRoot = (& git -C $cto rev-parse --show-toplevel 2>&1) -join ''
        if ($LASTEXITCODE -ne 0 -or (Full-Path $gitRoot) -ne $cto) { throw "CTO must have its own Git root: $cto" }
        foreach ($rel in @('AGENTS.md', "$CtoName\brain\fact\base.md",
            "$CtoName\brain\mind\state.md", "$CtoName\brain\mind\todo.md",
            "$CtoName\.github\copilot\settings.json")) {
            if (!(Test-Path -LiteralPath (Join-Path $WorkshopRoot $rel) -PathType Leaf)) {
                throw "atelier-monte did not create the required workshop file: $rel"
            }
        }
        Add-Environment
        Write-Host "Installed. Fill CTO memory, then open a NEW Copilot session in $cto."
    }
    if ($EnvironmentScope -eq 'User') {
        Write-Host 'Restart the terminal/application to inherit the User environment; then restart Copilot.'
    } elseif ($EnvironmentScope -eq 'Process') {
        Write-Host 'Process-only environment: start the next Copilot session from THIS PowerShell process.'
    } else {
        Write-Host "Environment unchanged. Preserve existing comma-separated values and add $WorkshopRoot to $script:EnvironmentName before starting Copilot."
    }
    Write-Host 'Hooks are not proven until a briefing is observed in that new session.'
} finally {
    if ($null -ne $lock) {
        $lock.Dispose()
        Remove-Item -LiteralPath $lockPath -Force
    }
}
