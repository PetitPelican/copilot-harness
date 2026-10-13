# LES HOOKS TELS QUE COPILOT LES LANCE - le champ `powershell` de hooks/copilot.json,
# execute par un vrai powershell.exe (5.1) et, s'il est la, pwsh (7), charge sur
# l'entree standard, comme un hote le fait. Rien ici n'appelle le programme
# directement : c'est la commande du hook, mot pour mot, qui est jugee.
#
#   .\controles\hooks-powershell.ps1 [-PackageRoot <paquet>]
#
# Ce qu'il prouve, et le temoin de chaque preuve :
#   - le briefing sort en JSON lisible, accents compris (TEMOIN : cap absent) ;
#   - le garde de commit refuse un commit sans etat (TEMOIN : `# mind-ok` passe) ;
#   - la garde de perimetre refuse hors lot (TEMOIN : dans le lot, rien) ;
#   - apres un commit, le journal s'ecrit (un seul processus fait journal + lecture) ;
#   - sans Python, les deux gardes REFUSENT (code 2) et les autres le disent (code 1) ;
#   - depuis un paquet range sous un chemin a espaces et parentheses.
param([string]$PackageRoot = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$PackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
$hooks = (Get-Content -LiteralPath (Join-Path $PackageRoot 'hooks\copilot.json') -Raw | ConvertFrom-Json).hooks
$root = Join-Path ([IO.Path]::GetTempPath()) ('hooks-ps-' + $PID)
$shells = @('powershell.exe')
if (Get-Command pwsh -ErrorAction SilentlyContinue) { $shells += 'pwsh' }
$failures = 0

function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Hook-Command([string]$Event, [string]$Matcher) {
    foreach ($h in @($hooks.$Event)) {
        $m = if ($h.PSObject.Properties['matcher']) { $h.matcher } else { $null }
        if ($m -eq $Matcher) { return $h.powershell }
    }
    throw "hook absent : $Event / $Matcher"
}
function Invoke-Hook([string]$Shell, [string]$Command, [object]$Payload, [hashtable]$Env = @{}) {
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $Shell
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
    $psi.Arguments = "-NoProfile -NonInteractive -EncodedCommand $enc"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    foreach ($k in $Env.Keys) {
        if ($null -eq $Env[$k]) { $psi.EnvironmentVariables.Remove($k) } else { $psi.EnvironmentVariables[$k] = $Env[$k] }
    }
    $p = [Diagnostics.Process]::Start($psi)
    $err = $p.StandardError.ReadToEndAsync()
    $text = if ($Payload -is [string]) { $Payload } else { $Payload | ConvertTo-Json -Depth 20 -Compress }
    $bytes = [Text.Encoding]::UTF8.GetBytes($text)
    $p.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    $p.StandardInput.Close()
    $out = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit()
    return @{ code = $p.ExitCode; out = $out.Trim(); err = $err.Result }
}
function Invoke-Git([string[]]$Arguments) {
    & git -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git a echoue : $Arguments" }
}

try {
    # Le paquet, recopie sous un chemin qu'un cmd.exe lirait mal.
    $paquet = Join-Path $root 'Jean (Pro) x\paquet'
    New-Item -ItemType Directory -Path $paquet | Out-Null
    foreach ($d in @('py', 'bin', 'hooks', '.github')) {
        Copy-Item -LiteralPath (Join-Path $PackageRoot $d) -Destination $paquet -Recurse
    }
    $home2 = Join-Path $root 'maison'
    $base = @{ COPILOT_PLUGIN_ROOT = $paquet; PLUGIN_ROOT = $null; HOME = $home2; USERPROFILE = $home2;
               COPILOT_HOME = (Join-Path $home2 '.copilot'); COPILOT_PLUGIN_DATA = (Join-Path $root 'data');
               COPILOT_PROJECT_DIR = $null; HARNAIS_JUGE = $null }
    $projet = Join-Path $root 'projet'
    New-Item -ItemType Directory -Path $projet | Out-Null
    Push-Location $projet
    try {
        Git @('init', '-q', '-b', 'main')
        & (Join-Path $paquet 'bin\harnais.cmd') adopte --go | Out-Null
        Assert ($LASTEXITCODE -eq 0) 'adopte par harnais.cmd a echoue'
        [IO.File]::WriteAllText((Join-Path $projet 'brain\fact\base.md'), "---`ncap: CAFE-$([char]0xE9)T$([char]0xE9)`n---`n")
        Git @('add', '-A'); Git @('commit', '-qm', 'memoire')

        foreach ($sh in $shells) {
            try {
                $env1 = $base.Clone()
                $env1.COPILOT_PLUGIN_DATA = Join-Path $root "data-$sh"
                # 1. briefing, accents compris
                $start = @{ hook_event_name = 'SessionStart'; session_id = "s-$sh"; cwd = $projet }
                $r = Invoke-Hook $sh (Hook-Command 'SessionStart' $null) $start $env1
                Assert ($r.code -eq 0) "[$sh] briefing code $($r.code) : $($r.err)"
                $ctx = ($r.out | ConvertFrom-Json).additionalContext
                Assert ($ctx -match "CAFE-$([char]0xE9)T$([char]0xE9)") "[$sh] briefing sans cap accentue"
                # 2. garde de commit, et son temoin
                [IO.File]::WriteAllText((Join-Path $projet "code-$sh.py"), 'x = 1')
                Git @('add', "code-$sh.py")
                $commit = @{ cwd = $projet; toolName = 'powershell'; toolArgs = @{ command = 'git commit -m code' } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash') $commit $env1
                Assert ($r.code -eq 0 -and ($r.out | ConvertFrom-Json).permissionDecision -eq 'deny') "[$sh] commit sans etat autorise : $($r.out) $($r.err)"
                $commit.toolArgs.command = 'git commit -m code # mind-ok'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash') $commit $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] mind-ok refuse : $($r.out)"
                Git @('commit', '-qm', "code $sh")
                # 3. apres le commit : journal (et lecture) en un processus
                $r = Invoke-Hook $sh (Hook-Command 'PostToolUse' 'Bash') $commit $env1
                Assert ($r.code -eq 0) "[$sh] apres-bash code $($r.code) : $($r.err)"
                $log = Get-ChildItem (Join-Path $projet '.logs') -Filter '*.md' | Select-Object -First 1
                Assert ($null -ne $log -and (Get-Content $log.FullName -Raw) -match "code $sh") "[$sh] journal absent"
                # 4. perimetre : refuse hors lot, temoin dans le lot
                $agent = Join-Path $projet 'agents\QA'; $autre = Join-Path $projet 'agents\OPS'
                New-Item -ItemType Directory -Path (Join-Path $agent '.github\copilot'), $autre -Force | Out-Null
                [IO.File]::WriteAllText((Join-Path $agent '.github\copilot\perimetre.json'), (@{ deny = @($autre) } | ConvertTo-Json))
                $ecrit = @{ cwd = $agent; toolName = 'create'; toolArgs = @{ path = (Join-Path $autre 'x.txt') } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write') $ecrit $env1
                Assert (($r.out | ConvertFrom-Json).permissionDecision -eq 'deny') "[$sh] perimetre laisse passer : $($r.out) $($r.err)"
                $ecrit.toolArgs.path = Join-Path $agent 'x.txt'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write') $ecrit $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] perimetre refuse dans le lot : $($r.out)"
                # 5. fin de tour : ne casse pas
                $stop = @{ hook_event_name = 'Stop'; session_id = "s-$sh"; cwd = $projet }
                $r = Invoke-Hook $sh (Hook-Command 'Stop' $null) $stop $env1
                Assert ($r.code -eq 0) "[$sh] attente code $($r.code) : $($r.err)"
                # 6. sans Python : les gardes refusent, les autres le disent
                $sans = $env1.Clone(); $sans.HARNAIS_PYTHON = Join-Path $root 'pas-de-python.exe'
                foreach ($cas in @(@('PreToolUse', 'Bash', 2), @('PreToolUse', 'Edit|Write', 2), @('SessionStart', $null, 1), @('Stop', $null, 1))) {
                    $r = Invoke-Hook $sh (Hook-Command $cas[0] $cas[1]) $start $sans
                    Assert ($r.code -eq $cas[2]) "[$sh] sans Python, $($cas[0])/$($cas[1]) rend $($r.code) au lieu de $($cas[2])"
                    Assert ($r.err -match 'Python') "[$sh] sans Python, $($cas[0]) ne le dit pas"
                }
                Write-Output "PASS [$sh] : briefing, garde de commit, journal, perimetre, fin de tour, sans Python."
            } catch {
                $failures++
                Write-Output "FAIL [$sh] : $($_.Exception.Message)"
            }
        }
    } finally { Pop-Location }
} finally {
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
if ($failures) { exit 1 }
