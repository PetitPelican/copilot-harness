#Requires -Version 5.1
<#
L'ATELIER DÉPLACÉ — `install.ps1 -Action Update` ne recrée plus un atelier fantôme.

Relevé sur un poste le 21/10/2026 : l'atelier avait changé de dossier ; l'Update
relisait l'ancien chemin dans le journal d'installation et y relançait
`atelier-monte --go`, et `-WorkshopRoot` était refusé (« differs from the
ownership journal »). Ce contrôle joue la prévisualisation (sans -Go), avec un
faux CLI : rien n'est enregistré, rien ne sort du bac à sable.

Run with powershell -NoProfile -File .\controles\atelier-deplace.ps1 or pwsh.
#>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$sandbox = Join-Path $root ('.atelier-deplace-' + [guid]::NewGuid().ToString('N'))
$installer = Join-Path $root 'install.ps1'
$passed = 0

function Assert($Condition, [string]$Message) {
    if (!$Condition) { throw "FAIL: $Message" }
    $script:passed++
    Write-Host "PASS: $Message"
}
function Fails([scriptblock]$Operation, [string]$Pattern) {
    $failure = $null
    try { & $Operation 6>&1 | Out-Null } catch { $failure = "$_" }
    if (!($failure -and $failure -match $Pattern)) { Write-Host "got: $failure" }
    Assert ($failure -and $failure -match $Pattern) "Expected refusal: $Pattern"
}
function Write-Text([string]$Path, [string]$Text) {
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}

try {
    [IO.Directory]::CreateDirectory($sandbox) | Out-Null
    $source = Join-Path $sandbox 'source'
    foreach ($name in @('.github\plugin', 'bin', 'py', 'hooks', 'skills',
        'criteres-passe.md', 'criteres-relecture.md', 'rechutes.md')) {
        $to = Join-Path $source $name
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($to)) | Out-Null
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $to -Recurse
    }
    $cli = Join-Path $sandbox 'cli\copilot.cmd'
    Write-Text $cli '@exit /b 0'
    $destination = Join-Path $sandbox 'plugin'
    $old = Join-Path $sandbox 'Documents\AGENTIC'
    $new = Join-Path $sandbox 'Documents\COPILOT'
    $config = Join-Path $sandbox 'config'
    $testHome = Join-Path $sandbox 'home'
    [IO.Directory]::CreateDirectory((Join-Path $new 'cto')) | Out-Null
    [IO.Directory]::CreateDirectory($config) | Out-Null
    [IO.Directory]::CreateDirectory($testHome) | Out-Null
    $journal = Join-Path $destination '.harnais-install.json'
    Write-Text $journal ((@{
        schema = 1; destination = $destination; WorkshopRoot = $old
        UserName = 'u'; CtoName = 'cto'; CopilotHome = $config
        UserHome = $testHome; EnvironmentScope = 'None'
        files = @{}; environment = @{}; settings = $null; cliSettings = $null
        marketplaceOwned = $false; pluginOwned = $false
    } | ConvertTo-Json -Depth 10) + "`n")
    $before = (Get-FileHash -LiteralPath $journal).Hash
    $base = @{ Action = 'Update'; Destination = $destination; SourcePath = $source; CopilotPath = $cli }

    # 1. Ancien atelier disparu, aucun -WorkshopRoot : refus, rien recréé.
    Fails { & $installer @base } 'no longer exists'
    Assert (!(Test-Path -LiteralPath $old)) 'the old workshop is not recreated'

    # 2. -WorkshopRoot vers l'atelier déplacé : la prévisualisation le suit.
    $out = & $installer @base -WorkshopRoot $new 6>&1 | Out-String -Width 10000
    Assert ($out.Contains("Workshop moved: $old -> $new")) 'the dry run names the move'
    Assert ($out.Contains("Workshop: $new |")) 'the dry run works on the new workshop'
    Assert ($out.Contains('DRY RUN')) 'nothing applied without -Go'
    Assert (!(Test-Path -LiteralPath $old)) 'the old workshop is still not recreated'
    Assert ((Get-FileHash -LiteralPath $journal).Hash -eq $before) 'the dry run leaves the journal untouched'

    # 3. Témoin : un -WorkshopRoot qui ne porte pas le CTO n'est pas un atelier déplacé.
    $empty = Join-Path $sandbox 'vide'
    [IO.Directory]::CreateDirectory($empty) | Out-Null
    Fails { & $installer @base -WorkshopRoot $empty } 'must be the moved workshop'

    # 4. Témoin : l'ancien atelier existe encore ; un autre chemin reste refusé.
    [IO.Directory]::CreateDirectory((Join-Path $old 'cto')) | Out-Null
    Fails { & $installer @base -WorkshopRoot $new } 'differs from the ownership journal'
    $out = & $installer @base 6>&1 | Out-String -Width 10000
    Assert ($out.Contains("Workshop: $old |") -and !$out.Contains('Workshop moved')) 'an existing workshop is used as recorded'

    Write-Host "atelier-deplace: $passed PASS"
} finally {
    if (Test-Path -LiteralPath $sandbox) { Remove-Item -LiteralPath $sandbox -Recurse -Force }
}
