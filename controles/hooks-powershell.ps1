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
#   - le garde de la Production refuse `git push origin main` et l'API GitHub en
#     ecriture, sous PowerShell (TEMOIN : une branche de travail, rien) ;
#   - le garde du coffre refuse `Get-Content .env.local` et `$env:..._KEY` affiches (TEMOIN :
#     `(Get-Content .env.local).Count` passe), et son temoin signale une cle vue en clair ;
#   - la garde des sous-agents refuse un `task` qui regarde des captures d'ecran (TEMOIN : un
#     audit de code passe) ;
#   - le verrou des consignes refuse a un agent d'ecrire AGENTS.md (create, apply_patch,
#     Set-Content...) alors que le CTO l'ecrit (TEMOIN : lire, ou ecrire todo.md, passe) ;
#   - apres un commit, le journal s'ecrit (un seul processus fait journal + lecture) ;
#   - sans Python, les gardes REFUSENT (code 2) et les autres le disent (code 1) ;
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
function Hook-Command([string]$Event, [string]$Matcher, [string]$Sub = '') {
    # Plusieurs gardes partagent un filtre (`Bash`) : $Sub nomme la sous-commande voulue.
    foreach ($h in @($hooks.$Event)) {
        $m = if ($h.PSObject.Properties['matcher']) { $h.matcher } else { $null }
        if ("$m" -ne "$Matcher") { continue }
        if ($Sub -and -not $h.powershell.Contains(",'$Sub');")) { continue }
        return $h.powershell
    }
    throw "hook absent : $Event / $Matcher / $Sub"
}
function Invoke-Hook([string]$Shell, [string]$Command, [object]$Payload, [hashtable]$Env = @{}) {
    $psi = New-Object Diagnostics.ProcessStartInfo
    $psi.FileName = $Shell
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))
    $psi.Arguments = "-NoProfile -NonInteractive -EncodedCommand $enc"
    $psi.UseShellExecute = $false
    # Un hote lance le hook DANS le dossier de la session : le garde de commit
    # interroge git depuis la (comme le Rust). Sans cela, il juge le depot d'ou
    # le controle est lance, et laisse tout passer.
    $cwd = if ($Payload -isnot [string] -and $Payload.ContainsKey('cwd')) { $Payload.cwd } else { (Get-Location).Path }
    $psi.WorkingDirectory = $cwd
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
function Decision($R) {
    # La decision du hook, ou '' - jamais une erreur de propriete qui cache la sortie.
    if (-not $R.out) { return '' }
    try { $o = $R.out | ConvertFrom-Json } catch { return "illisible: $($R.out)" }
    if ($o -and $o.PSObject.Properties['permissionDecision']) { return $o.permissionDecision }
    return ''
}
function Invoke-Git([string[]]$Arguments) {
    & git -c user.name=Test -c user.email=test@example.invalid -c commit.gpgsign=false @Arguments
    if ($LASTEXITCODE -ne 0) { throw "git a echoue : $Arguments" }
}

try {
    # Le paquet, recopie sous un chemin qu'un cmd.exe lirait mal.
    $paquet = Join-Path $root 'Nom (Pro) x\paquet'
    New-Item -ItemType Directory -Path $paquet | Out-Null
    foreach ($d in @('py', 'bin', 'hooks', '.github', 'skills')) {
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
        Invoke-Git @('init', '-q', '-b', 'main')
        & (Join-Path $paquet 'bin\harnais.cmd') adopte --go | Out-Null
        Assert ($LASTEXITCODE -eq 0) 'adopte par harnais.cmd a echoue'
        [IO.File]::WriteAllText((Join-Path $projet 'brain\fact\base.md'), "---`ncap: CAFE-$([char]0xE9)T$([char]0xE9)`n---`n")
        Invoke-Git @('add', '-A'); Invoke-Git @('commit', '-qm', 'memoire')

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
                Invoke-Git @('add', "code-$sh.py")
                $commit = @{ cwd = $projet; toolName = 'powershell'; toolArgs = @{ command = 'git commit -m code' } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash') $commit $env1
                Assert ($r.code -eq 0 -and (Decision $r) -eq 'deny') "[$sh] commit sans etat autorise : code $($r.code) out [$($r.out)] err [$($r.err)]"
                $commit.toolArgs.command = 'git commit -m code # mind-ok'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash') $commit $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] mind-ok refuse : $($r.out)"
                Invoke-Git @('commit', '-qm', "code $sh")
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
                Assert ((Decision $r) -eq 'deny') "[$sh] perimetre laisse passer : code $($r.code) out [$($r.out)] err [$($r.err)]"
                $ecrit.toolArgs.path = Join-Path $agent 'x.txt'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write') $ecrit $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] perimetre refuse dans le lot : $($r.out)"
                # 4 bis. Production : un projet qui ferme `main` refuse la poussee (PowerShell),
                # et laisse passer une branche de travail. Le reglage est lu dans les regles.
                $regles = Join-Path $projet 'brain\fact\rules.md'
                $avant = [IO.File]::ReadAllText($regles)
                [IO.File]::WriteAllText($regles, "---`nproduction: main`n---`n`n" + $avant)
                try {
                    $push = @{ cwd = $projet; toolName = 'powershell'; toolArgs = @{ command = 'Set-Location . ; git push origin main' } }
                    $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash' 'production') $push $env1
                    Assert ($r.code -eq 0 -and (Decision $r) -eq 'deny') "[$sh] production laisse passer la poussee : code $($r.code) out [$($r.out)] err [$($r.err)]"
                    $push.toolArgs.command = 'Invoke-RestMethod -Method Put -Uri https://api.github.com/repos/o/r/merges -Body $b'
                    $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash' 'production') $push $env1
                    Assert ((Decision $r) -eq 'deny') "[$sh] production laisse passer l'API en ecriture : out [$($r.out)] err [$($r.err)]"
                    $push.toolArgs.command = 'git push origin travail'
                    $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash' 'production') $push $env1
                    Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] production refuse une branche de travail : $($r.out)"
                } finally { [IO.File]::WriteAllText($regles, $avant) }
                # 4 ter. Coffre : aucun outil n'affiche une valeur de secret (PowerShell), et le
                # temoin d'apres signale une cle de forme connue (fabriquee ici, jamais ecrite en dur).
                $lire = @{ cwd = $projet; toolName = 'powershell'; toolArgs = @{ command = 'Get-Content .env.local' } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash|Read|Grep' 'coffre') $lire $env1
                Assert ($r.code -eq 0 -and (Decision $r) -eq 'deny') "[$sh] coffre laisse afficher .env.local : code $($r.code) out [$($r.out)] err [$($r.err)]"
                $lire.toolArgs.command = 'Write-Host $env:STRIPE_SECRET_KEY'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash|Read|Grep' 'coffre') $lire $env1
                Assert ((Decision $r) -eq 'deny') "[$sh] coffre laisse afficher une variable secrete : out [$($r.out)] err [$($r.err)]"
                $lire.toolArgs.command = '(Get-Content .env.local).Count'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash|Read|Grep' 'coffre') $lire $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] coffre refuse un compte : $($r.out)"
                $vue = @{ cwd = $projet; toolName = 'view'; toolArgs = @{ path = (Join-Path $projet '.env.local') } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Bash|Read|Grep' 'coffre') $vue $env1
                Assert ((Decision $r) -eq 'deny') "[$sh] coffre laisse ouvrir .env.local : out [$($r.out)] err [$($r.err)]"
                $fausse = 'sbp_' + ('A1b2C3d4E5f6G7h8' * 3)
                $apres = @{ cwd = $projet; toolName = 'powershell'; toolArgs = @{ command = 'cat x' }
                            toolResult = @{ resultType = 'success'; textResultForLlm = "TOKEN=$fausse" } }
                $r = Invoke-Hook $sh (Hook-Command 'PostToolUse' 'Bash') $apres $env1
                Assert ($r.code -eq 0 -and $r.out -match 'Supabase' -and $r.out -notmatch [regex]::Escape($fausse)) "[$sh] temoin du coffre : code $($r.code) out [$($r.out)] err [$($r.err)]"
                $apres.toolResult.textResultForLlm = 'rien a signaler'
                $r = Invoke-Hook $sh (Hook-Command 'PostToolUse' 'Bash') $apres $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] temoin du coffre bavard : $($r.out)"
                # 4 quater. Sous-agents : un `task` qui regarde des captures ne part pas sans accord.
                $tache = @{ cwd = $projet; toolName = 'task'; toolArgs = @{ description = 'Audit'; prompt = "Regarde chaque capture d'ecran et note les defauts" } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Task|task' 'sous-agent') $tache $env1
                Assert ($r.code -eq 0 -and (Decision $r) -eq 'deny') "[$sh] sous-agent laisse regarder des captures : code $($r.code) out [$($r.out)] err [$($r.err)]"
                $tache.toolArgs.prompt = 'Audite le depot et rends un rapport'
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Task|task' 'sous-agent') $tache $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] sous-agent refuse un audit de code : $($r.out)"
                # 4 quinquies. Consignes : un agent n'ecrit pas AGENTS.md ; le CTO, si.
                $cons = @{ cwd = $projet; toolName = 'create'; toolArgs = @{ path = (Join-Path $projet 'AGENTS.md') } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write|Bash' 'consignes') $cons $env1
                Assert ($r.code -eq 0 -and (Decision $r) -eq 'deny') "[$sh] consignes laisse ecrire AGENTS.md : code $($r.code) out [$($r.out)] err [$($r.err)]"
                $cons = @{ cwd = $projet; toolName = 'powershell'; toolArgs = @{ command = "Set-Content -Path .\AGENTS.md -Value 'x'" } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write|Bash' 'consignes') $cons $env1
                Assert ((Decision $r) -eq 'deny') "[$sh] consignes laisse Set-Content ecrire AGENTS.md : out [$($r.out)] err [$($r.err)]"
                $cons.toolArgs.command = "Add-Content -Path todo.md -Value 'voir AGENTS.md'; Get-Content AGENTS.md"
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write|Bash' 'consignes') $cons $env1
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] consignes refuse de lire ou de citer AGENTS.md : $($r.out)"
                $cto = Join-Path $root "cto-$sh"
                New-Item -ItemType Directory -Path $cto | Out-Null
                $envCto = $env1.Clone(); $envCto.COPILOT_PROJECT_DIR = $cto
                $cons = @{ cwd = $cto; toolName = 'create'; toolArgs = @{ path = (Join-Path $cto 'AGENTS.md') } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write|Bash' 'consignes') $cons $envCto
                Assert ($r.code -eq 0 -and $r.out -ne '') "[$sh] le dossier cto-$sh n'est pas le CTO et doit etre refuse"
                $cto = Join-Path $root "cto"
                if (-not (Test-Path -LiteralPath $cto)) { New-Item -ItemType Directory -Path $cto | Out-Null }
                $envCto = $env1.Clone(); $envCto.COPILOT_PROJECT_DIR = $cto
                $cons = @{ cwd = $cto; toolName = 'create'; toolArgs = @{ path = (Join-Path $cto 'AGENTS.md') } }
                $r = Invoke-Hook $sh (Hook-Command 'PreToolUse' 'Edit|Write|Bash' 'consignes') $cons $envCto
                Assert ($r.code -eq 0 -and $r.out -eq '') "[$sh] le CTO ne peut pas ecrire AGENTS.md : $($r.out)"
                # 5. fin de tour : ne casse pas
                $stop = @{ hook_event_name = 'Stop'; session_id = "s-$sh"; cwd = $projet }
                $r = Invoke-Hook $sh (Hook-Command 'Stop' $null) $stop $env1
                Assert ($r.code -eq 0) "[$sh] attente code $($r.code) : $($r.err)"
                # 6. sans Python : les gardes refusent, les autres le disent
                $sans = $env1.Clone(); $sans.HARNAIS_PYTHON = Join-Path $root 'pas-de-python.exe'
                foreach ($cas in @(@('PreToolUse', 'Bash', 2, 'mind-guard'), @('PreToolUse', 'Bash', 2, 'production'), @('PreToolUse', 'Bash|Read|Grep', 2, 'coffre'), @('PreToolUse', 'Task|task', 2, 'sous-agent'), @('PreToolUse', 'Edit|Write|Bash', 2, 'consignes'), @('PreToolUse', 'Edit|Write', 2, ''), @('SessionStart', $null, 1, ''), @('Stop', $null, 1, ''))) {
                    $r = Invoke-Hook $sh (Hook-Command $cas[0] $cas[1] $cas[3]) $start $sans
                    Assert ($r.code -eq $cas[2]) "[$sh] sans Python, $($cas[0])/$($cas[1]) rend $($r.code) au lieu de $($cas[2])"
                    Assert ($r.err -match 'Python') "[$sh] sans Python, $($cas[0]) ne le dit pas"
                }
                Write-Output "PASS [$sh] : briefing, garde de commit, journal, perimetre, production, coffre, sous-agent, consignes, fin de tour, sans Python."
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
