param(
    [Parameter(Mandatory)][string]$Copilot,
    [string]$PackageRoot = (Split-Path $PSScriptRoot -Parent)
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$PackageRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PackageRoot)
$root = Join-Path (Split-Path $PSScriptRoot -Parent) ('.cto-start-' + $PID)
if (Test-Path -LiteralPath $root) { throw "Fixture already exists: $root" }
$names = @('HOME', 'USERPROFILE', 'COPILOT_HOME', 'COPILOT_AUTO_UPDATE',
    'COPILOT_CUSTOM_INSTRUCTIONS_DIRS', 'HARNAIS_CTO_PROBE',
    'HARNAIS_CTO_BINARY', 'COPILOT_PROJECT_DIR')
$saved = @{}
foreach ($n in $names) { $saved[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
function Assert([bool]$Condition, [string]$Message) {
    if (!$Condition) { throw $Message }
    Write-Output "PASS: $Message"
}
function Invoke-Cli([string[]]$Arguments) {
    $result = & $Copilot @Arguments
    if ($LASTEXITCODE -ne 0) { throw "CLI failure: $Arguments" }
    return ($result -join "`n")
}
try {
    $source = Join-Path $root 'source'
    $destination = Join-Path $root 'plugin'
    $workshop = Join-Path $root 'Agentic'
    $cto = Join-Path $workshop 'CTO'
    New-Item -ItemType Directory $source, $cto | Out-Null
    foreach ($relative in @('.github\plugin', 'bin', 'hooks', 'skills',
        'criteres-passe.md', 'criteres-relecture.md', 'rechutes.md')) {
        $to = Join-Path $source $relative
        [IO.Directory]::CreateDirectory((Split-Path $to -Parent)) | Out-Null
        Copy-Item -LiteralPath (Join-Path $PackageRoot $relative) -Destination $to -Recurse
    }
    $env:HOME = Join-Path $root 'home'
    $env:USERPROFILE = $env:HOME
    $env:COPILOT_HOME = Join-Path $root 'config'
    $env:COPILOT_AUTO_UPDATE = 'false'
    foreach ($n in @('COPILOT_PROJECT_DIR')) {
        [Environment]::SetEnvironmentVariable($n, $null, 'Process')
    }
    $params = @{
        SourcePath = $source; Destination = $destination
        WorkshopRoot = $workshop; CtoName = 'CTO'; UserName = 'Synthetic User'
        CopilotPath = $Copilot; CopilotHome = $env:COPILOT_HOME
        UserHome = $env:HOME; EnvironmentScope = 'Process'
    }
    Push-Location $cto
    try {
        & (Join-Path $PackageRoot 'install.ps1') @params
        Assert (@(Get-ChildItem -Force).Count -eq 0) 'dry-run preserves the already open empty CTO'
        & (Join-Path $PackageRoot 'install.ps1') @params -Go
        $instructions = @(Invoke-Cli -Arguments @('instruction', 'list', '--json') | ConvertFrom-Json)
        Assert (@($instructions | Where-Object { $_.sourcePath -match 'copilot-instructions\.md$' }).Count -gt 0) 'restarted CLI discovers the local method'
        Assert (@($instructions | Where-Object { $_.sourcePath -eq 'AGENTS.md' }).Count -gt 0) 'restarted CLI discovers the CTO role'
        $skills = Invoke-Cli -Arguments @('skill', 'list')
        foreach ($skill in @('agentic-adopte', 'agentic-agents', 'agentic-clean', 'agentic-init',
            'agentic-team', 'project-init', 'publish-docs', 'caveman')) {
            Assert ($skills -match $skill) "installed skill available: $skill"
        }

        # Observe only the two briefing hooks. Synthetic prompts have no tools;
        # Stop checks and the full conversational onboarding are not measured here.
        $env:HARNAIS_CTO_BINARY = Join-Path $destination 'bin\harnais-windows-x86_64.exe'
        $probe = @'
$inputText=[Console]::In.ReadToEnd()
$output=($inputText | & $env:HARNAIS_CTO_BINARY briefing) -join "`n"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
$record=@{briefing=($output -match 'Briefing');welcome=($output -match 'ACCUEIL CTO')}
[IO.File]::AppendAllText($env:HARNAIS_CTO_PROBE,(($record|ConvertTo-Json -Compress)+"`n"))
if($output){[Console]::WriteLine($output)}
'@
        $hooks = @{
            version = 1
            hooks = @{
                SessionStart = @(@{type = 'command'; powershell = $probe})
                userPromptTransformed = @(@{type = 'command'; powershell = $probe})
            }
        }
        [IO.File]::WriteAllText((Join-Path $destination 'hooks\copilot.json'), ($hooks | ConvertTo-Json -Depth 8))
        $args = @('--silent', '--no-auto-update', '--no-remote-export', '--disable-builtin-mcps',
            '--available-tools', '--no-ask-user', '--log-level', 'none',
            '-p', 'Synthetic startup observation only. Do not use tools. Reply briefly.')
        $env:HARNAIS_CTO_PROBE = Join-Path $root 'before.jsonl'
        Invoke-Cli -Arguments $args | Out-Null
        $before = @(Get-Content $env:HARNAIS_CTO_PROBE | ForEach-Object { $_ | ConvertFrom-Json })
        Assert (@($before | Where-Object briefing).Count -eq 1) 'live CLI receives one briefing before declaration'
        Assert (@($before | Where-Object welcome).Count -eq 1) 'live CLI receives the welcome exactly once'
        [IO.File]::WriteAllText((Join-Path $cto 'docs\projects.json'),
            '{"schema":1,"projects":[{"name":"Synthetic project","path":"../Project","profiles":["PO"]}]}')
        $env:HARNAIS_CTO_PROBE = Join-Path $root 'after.jsonl'
        Invoke-Cli -Arguments $args | Out-Null
        $after = @(Get-Content $env:HARNAIS_CTO_PROBE | ForEach-Object { $_ | ConvertFrom-Json })
        Assert (@($after | Where-Object briefing).Count -eq 1) 'live CLI still receives briefing after declaration'
        Assert (@($after | Where-Object welcome).Count -eq 0) 'live restarted CLI does not welcome again after declaration'
    } finally { Pop-Location }
} finally {
    foreach ($n in $names) { [Environment]::SetEnvironmentVariable($n, $saved[$n], 'Process') }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
