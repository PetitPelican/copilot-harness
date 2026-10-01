param(
    [string]$PackageRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Copilot,
    [string]$Executable
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$PackageRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PackageRoot)
$exe = if ($Executable) { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Executable) } else { Join-Path $PackageRoot 'bin\harnais-windows-x86_64.exe' }
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Binaire absent : $exe" }
$testRoot = Join-Path (Split-Path $PSScriptRoot -Parent) ('.portable-smoke-' + $PID)
if (Test-Path -LiteralPath $testRoot) { throw "Dossier de test existe deja : $testRoot" }
$saved = @{}
$names = @('HOME', 'USERPROFILE', 'COPILOT_HOME', 'COPILOT_PLUGIN_ROOT',
    'PLUGIN_ROOT', 'COPILOT_PLUGIN_DATA',
    'COPILOT_PROJECT_DIR', 'HARNAIS_JUGE', 'COPILOT_CUSTOM_INSTRUCTIONS_DIRS',
    'COPILOT_AUTO_UPDATE')
foreach ($n in $names) { $saved[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Invoke-Git([string[]]$Arguments) {
    & git -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git a echoue : $Arguments" }
}
function Run([string[]]$Arguments) {
    $result = & $exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "harnais a echoue : $Arguments" }
    return ($result -join "`n")
}
function Hook([string]$Command, [object]$Payload) {
    $text = $Payload | ConvertTo-Json -Depth 20 -Compress
    $result = $text | & $exe $Command
    if ($LASTEXITCODE -ne 0) { throw "hook a echoue : $Command" }
    return ($result -join "`n")
}
function Invoke-Copilot([string[]]$Arguments) {
    $result = & $Copilot @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Copilot a echoue : $Arguments" }
    return ($result -join "`n")
}
try {
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    $env:HOME = Join-Path $testRoot 'home'
    $env:USERPROFILE = $env:HOME
    $env:COPILOT_HOME = Join-Path $env:HOME '.copilot'
    $env:COPILOT_PLUGIN_ROOT = $PackageRoot
    $env:PLUGIN_ROOT = $PackageRoot
    $env:COPILOT_PLUGIN_DATA = Join-Path $testRoot 'data'
    $env:COPILOT_AUTO_UPDATE = 'false'
    Remove-Item Env:HARNAIS_JUGE, Env:COPILOT_PROJECT_DIR -ErrorAction SilentlyContinue
    $workshop = Join-Path $testRoot 'atelier'
    Run -Arguments @('atelier-monte', '--racine', $workshop, '--utilisateur', 'Collegue') | Out-Null
    Assert (-not (Test-Path $workshop)) 'atelier a blanc a ecrit'
    Run -Arguments @('atelier-monte', '--racine', $workshop, '--utilisateur', 'Collegue', '--go') | Out-Null
    Assert (Test-Path (Join-Path $workshop 'cto\brain\fact\rules.md')) 'atelier incomplet'
    $cto = Join-Path $workshop 'cto'
    $welcomeStart = @{ hook_event_name = 'SessionStart'; session_id = 'welcome-a'; cwd = $cto }
    Assert ((Hook 'briefing' $welcomeStart) -match 'ACCUEIL CTO') 'accueil CTO absent'
    $welcomePrompt = @{ sessionId = 'welcome-a'; cwd = $cto; prompt = 'test'; transformedPrompt = 'test' }
    Assert ((Hook 'briefing' $welcomePrompt) -eq '') 'accueil CTO injecte deux fois'
    $welcomeStart.session_id = 'welcome-b'
    Assert ((Hook 'briefing' $welcomeStart) -match 'ACCUEIL CTO') 'accueil perdu avant declaration'
    [IO.File]::WriteAllText((Join-Path $cto 'docs\projects.json'),
        '{"schema":1,"projects":[{"name":"Test","path":"../projet","profiles":["PO"]}]}')
    $afterDeclaration = Hook 'briefing' $welcomeStart
    Assert ($afterDeclaration -and $afterDeclaration -notmatch 'ACCUEIL CTO') 'declaration ne ferme pas accueil dans la session'
    $welcomeStart.session_id = 'welcome-c'
    $afterRestart = Hook 'briefing' $welcomeStart
    Assert ($afterRestart -and $afterRestart -notmatch 'ACCUEIL CTO') 'accueil revient apres declaration et redemarrage'
    $env:COPILOT_CUSTOM_INSTRUCTIONS_DIRS = $workshop
    $project = Join-Path $testRoot 'projet'
    New-Item -ItemType Directory -Path $project | Out-Null
    Push-Location $project
    try {
        Invoke-Git -Arguments @('init', '-q', '-b', 'main')
        Run -Arguments @('adopte') | Out-Null
        Assert (-not (Test-Path 'brain')) 'adoption a blanc a ecrit'
        New-Item -ItemType Directory -Path 'brain\fact', 'brain\mind', '.github\copilot' | Out-Null
        [IO.File]::WriteAllText((Join-Path $project 'brain\fact\base.md'), "---`ncap: TEST-COPIE`n---`n")
        [IO.File]::WriteAllText((Join-Path $project 'brain\mind\state.md'),
            "---`nmaj: $(Get-Date -Format yyyy-MM-dd)`nsante: vert`njalon: test`n---`n")
        [IO.File]::WriteAllText((Join-Path $project 'brain\mind\todo.md'), "- [ ] initial`n")
        [IO.File]::WriteAllText((Join-Path $project '.github\copilot\settings.json'), '{"custom":"garder"}')
        Run -Arguments @('adopte', '--go') | Out-Null
        foreach ($f in @('base', 'architecture', 'stack', 'rules')) {
            Assert (Test-Path "brain\fact\$f.md") "fait absent : $f"
        }
        $before = Get-FileHash 'brain\fact\base.md', 'brain\mind\state.md', '.github\copilot\settings.json'
        Run -Arguments @('adopte', '--go') | Out-Null
        $after = Get-FileHash 'brain\fact\base.md', 'brain\mind\state.md', '.github\copilot\settings.json'
        Assert (($before.Hash -join ',') -eq ($after.Hash -join ',')) 'rerun non idempotent'
        $settings = Get-Content '.github\copilot\settings.json' -Raw | ConvertFrom-Json
        Assert ($settings.custom -eq 'garder') 'settings ecrases'
        Assert (-not (Test-Path '.claude')) 'aucun dossier .claude cree (Copilot le lirait)'
        $start = @{ hook_event_name = 'SessionStart'; session_id = 'session-a'; cwd = $project }
        $first = Hook 'briefing' $start | ConvertFrom-Json
        Assert ($first.additionalContext -match 'TEST-COPIE') 'briefing sans cap'
        $prompt = @{ sessionId = 'session-a'; cwd = $project; prompt = 'synthetique'; transformedPrompt = 'synthetique' }
        Assert ((Hook 'briefing' $prompt) -eq '') 'briefing double au premier prompt'
        Assert ((Hook 'briefing' $start) -eq '') 'SessionStart identique repete'
        [IO.File]::AppendAllText((Join-Path $project 'brain\mind\todo.md'), "- [ ] @user nouvelle decision`n")
        $refresh = Hook 'briefing' $prompt | ConvertFrom-Json
        Assert ($refresh.modifiedTransformedPrompt -match 'nouvelle decision') 'rafraichissement perdu'
        Assert ((Hook 'briefing' $prompt) -eq '') 'prompt inchange repete'
        $start.session_id = 'session-b'
        Assert ((Hook 'briefing' $start) -ne '') 'nouvelle session supprimee'
        Invoke-Git -Arguments @('add', '.')
        Invoke-Git -Arguments @('commit', '-qm', 'memoire initiale')
        [IO.File]::WriteAllText((Join-Path $project 'code.rs'), 'fn main() {}')
        Invoke-Git -Arguments @('add', 'code.rs')
        $commit = @{ cwd = $project; toolName = 'powershell'; toolArgs = @{ command = 'git commit -m code' } }
        $denied = Hook 'mind-guard' $commit | ConvertFrom-Json
        Assert ($denied.permissionDecision -eq 'deny') 'commit sans state autorise'
        $commit.toolArgs.command = 'git commit -m code # mind-ok'
        Assert ((Hook 'mind-guard' $commit) -eq '') 'exception mind-ok ignoree'
        Invoke-Git -Arguments @('commit', '-qm', 'code test')
        Hook 'journal' $commit | Out-Null
        $log = Get-ChildItem '.logs' -Filter '*.md' | Select-Object -First 1
        Assert ($null -ne $log) 'journal absent'
        $logHash = (Get-FileHash $log.FullName).Hash
        Hook 'journal' $commit | Out-Null
        Assert ((Get-FileHash $log.FullName).Hash -eq $logHash) 'journal double'
        $copy = Join-Path $testRoot 'copie'
        Invoke-Git -Arguments @('worktree', 'add', '-q', '-b', 'copie', $copy)
        [IO.File]::WriteAllText((Join-Path $copy 'brain\fact\base.md'), "---`ncap: WORKTREE-ISOLE`n---`n")
        $resolution = Run -Arguments @('resolution', $copy) | ConvertFrom-Json
        Assert ($resolution.fact -like '*copie*brain*fact') 'resolution lit le principal'
        $view = Run -Arguments @('equipe-vue', '--racine', $testRoot, '--projet', 'copie')
        Assert ($view -match 'WORKTREE-ISOLE') 'equipe-vue lit le principal'
        New-Item -ItemType Directory -Path (Join-Path $copy 'agents\QA') | Out-Null
        $fromAgent = @{ hook_event_name = 'SessionStart'; session_id = 'session-a'; cwd = (Join-Path $copy 'agents\QA') }
        $briefAgent = Hook 'briefing' $fromAgent | ConvertFrom-Json
        Assert ($briefAgent.additionalContext -match 'WORKTREE-ISOLE') 'briefing agent lit le principal'
        $agent = Join-Path $project 'agents\QA'
        $other = Join-Path $project 'agents\OPS'
        New-Item -ItemType Directory -Path (Join-Path $agent '.github\copilot'), $other | Out-Null
        [IO.File]::WriteAllText((Join-Path $agent '.github\copilot\perimetre.json'),
            (@{ deny = @($other) } | ConvertTo-Json))
        $write = @{ cwd = $agent; toolName = 'create'; toolArgs = @{ path = (Join-Path $other 'interdit.txt') } }
        Assert (((Hook 'perimetre' $write | ConvertFrom-Json).permissionDecision) -eq 'deny') 'perimetre laisse passer'
        $write.toolName = 'apply_patch'
        $write.toolArgs = "*** Begin Patch`n*** Add File: $(Join-Path $other 'interdit.txt')`n+test`n*** End Patch`n"
        Assert (((Hook 'perimetre' $write | ConvertFrom-Json).permissionDecision) -eq 'deny') 'patch FREEFORM laisse passer'
        $write.cwd = $project
        Assert ((Hook 'perimetre' $write) -eq '') 'patch sans perimetre refuse'
        Assert (-not (Test-Path (Join-Path $other 'interdit.txt'))) 'smoke a ecrit hors lot'
        # Le choix d'agent de l'app : profils poses par equipe, session a la racine
        # d'une copie de travail, agent lu dans le journal de session.
        $team = Join-Path $testRoot 'equipe'
        New-Item -ItemType Directory -Path $team | Out-Null
        Push-Location $team
        try {
            Invoke-Git -Arguments @('init', '-q', '-b', 'main')
            New-Item -ItemType Directory -Path 'brain\fact', 'brain\mind' | Out-Null
            [IO.File]::WriteAllText((Join-Path $team 'brain\fact\base.md'), "---`ncap: TEST-EQUIPE`n---`n")
            [IO.File]::WriteAllText((Join-Path $team 'brain\mind\state.md'),
                "---`nmaj: $(Get-Date -Format yyyy-MM-dd)`nsante: vert`njalon: test`n---`n")
            [IO.File]::WriteAllText((Join-Path $team 'brain\mind\todo.md'), "- [ ] initial`n")
            Run -Arguments @('equipe', '--project-root', $team, '--agents', 'OPS,QA', '--apply') | Out-Null
            Assert (Test-Path '.github\agents\ops.agent.md') 'profil ops absent'
            Assert (Test-Path '.github\agents\qa.agent.md') 'profil qa absent'
            $opsDeny = (Get-Content 'agents\OPS\.github\copilot\perimetre.json' -Raw | ConvertFrom-Json).deny
            Assert (@($opsDeny) -contains 'agents/QA') 'perimetre non relatif'
            [IO.File]::WriteAllText((Join-Path $team 'agents\OPS\AGENTS.md'), "# OPS`nROLE-OPS-TEST`n")
            [IO.File]::WriteAllText((Join-Path $team 'agents\QA\AGENTS.md'), "# QA`nROLE-QA-TEST`n")
            Invoke-Git -Arguments @('add', '-A')
            Invoke-Git -Arguments @('commit', '-qm', 'equipe')
            $profiles = Run -Arguments @('equipe', '--project-root', $team, '--profils')
            Assert ($profiles -match 'non' -and $profiles -notmatch '\+ \.github[\\/]agents') 'profils existants reecrits'
            $session = Join-Path $testRoot 'session'
            Invoke-Git -Arguments @('worktree', 'add', '-q', '-b', 'session', $session)
            $journal = Join-Path $env:COPILOT_HOME 'session-state\app-1\events.jsonl'
            New-Item -ItemType Directory -Path (Split-Path $journal) -Force | Out-Null
            [IO.File]::WriteAllText($journal, '{"type":"session.start"}' + "`n" +
                '{"type":"subagent.selected","data":{"agentName":"ops"}}' + "`n" +
                '{"type":"subagent.selected","data":{"agentName":"ops"}}' + "`n")
            $appStart = @{ hook_event_name = 'SessionStart'; session_id = 'app-1'; cwd = $session }
            $appBrief = (Hook 'briefing' $appStart | ConvertFrom-Json).additionalContext
            Assert ($appBrief -match 'agent  : OPS') 'agent du menu non reconnu'
            Assert ($appBrief -match 'ROLE-OPS-TEST') 'role non montre'
            $appWrite = @{ cwd = $session; sessionId = 'app-1'; toolName = 'create'; toolArgs = @{ path = 'agents/QA/interdit.txt' } }
            Assert (((Hook 'perimetre' $appWrite | ConvertFrom-Json).permissionDecision) -eq 'deny') 'garde de la copie laisse passer'
            $appWrite.toolArgs.path = 'agents/OPS/permis.txt'
            Assert ((Hook 'perimetre' $appWrite) -eq '') 'garde refuse le lot de l agent'
            [IO.File]::AppendAllText($journal, '{"type":"subagent.deselected","data":{}}' + "`n")
            $appPrompt = @{ sessionId = 'app-1'; cwd = $session; prompt = 'x'; transformedPrompt = 'x' }
            $defaultBrief = (Hook 'briefing' $appPrompt | ConvertFrom-Json).modifiedTransformedPrompt
            Assert ($defaultBrief -match 'agent  : QA') 'Default agent ne prend pas QA'
            Assert ($defaultBrief -match 'ROLE-QA-TEST') 'role QA non montre'
            $appWrite.toolArgs.path = 'agents/OPS/interdit.txt'
            Assert (((Hook 'perimetre' $appWrite | ConvertFrom-Json).permissionDecision) -eq 'deny') 'garde QA laisse passer'
            $probe = Run -Arguments @('agent', '--session', 'app-1', '--racine', $session)
            Assert ($probe -match 'actif   : QA') 'sonde agent incoherente'
            Invoke-Git -Arguments @('worktree', 'remove', '--force', $session)
        } finally { Pop-Location }
        if ($Copilot) {
            $instructions = Invoke-Copilot -Arguments @('instruction', 'list', '--json')
            $sources = @($instructions | ConvertFrom-Json)
            Assert (@($sources | Where-Object { $_.sourcePath -match 'copilot-instructions\.md$' }).Count -gt 0) 'methode locale non decouverte'
            Assert ((Get-Content '.github\copilot-instructions.md' -Raw) -match 'harnais:method:start') 'methode locale absente'
            $skills = Invoke-Copilot -Arguments @('--plugin-dir', $PackageRoot, 'skill', 'list')
            foreach ($s in @('agentic-adopte', 'agentic-agents', 'agentic-clean', 'agentic-init',
                'agentic-team', 'project-init', 'publish-docs', 'caveman')) {
                Assert ($skills -match $s) "skill non decouvert : $s"
            }
            Push-Location $copy
            try {
                $copyInstructions = Invoke-Copilot -Arguments @('instruction', 'list', '--json')
                Assert ($copyInstructions -match 'copilot-instructions') 'methode worktree absente'
            } finally { Pop-Location }
        }
        Invoke-Git -Arguments @('worktree', 'remove', '--force', $copy)
    } finally { Pop-Location }
    Write-Output 'PASS: atelier, accueil/declaration/restart, adoption partielle, idempotence, briefing/session/refresh, worktree/equipe-vue/agent, gardes, journal, choix d agent (menu, Default agent -> QA, copie).'
    if ($Copilot) { Write-Output 'PASS: decouverte CLI des instructions et des huit skills (sans inference).' }
} finally {
    foreach ($n in $names) { [Environment]::SetEnvironmentVariable($n, $saved[$n], 'Process') }
    if (Test-Path -LiteralPath $testRoot) { Remove-Item -LiteralPath $testRoot -Recurse -Force }
}
