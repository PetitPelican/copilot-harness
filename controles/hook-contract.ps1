param([Parameter(Mandatory)][string]$Copilot)
$ErrorActionPreference = 'Stop'
$root = Join-Path (Split-Path $PSScriptRoot -Parent) ('.portable-contract-' + $PID)
if (Test-Path -LiteralPath $root) { throw "Dossier existe deja : $root" }
$names = @('COPILOT_HOME', 'HOME', 'USERPROFILE', 'COPILOT_AUTO_UPDATE', 'HARNAIS_CONTRACT',
    'COPILOT_CUSTOM_INSTRUCTIONS_DIRS', 'COPILOT_PROJECT_DIR')
$saved = @{}
foreach ($n in $names) { $saved[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
try {
    New-Item -ItemType Directory -Path (Join-Path $root '.github\plugin'), (Join-Path $root 'hooks') | Out-Null
    $env:HOME = Join-Path $root 'home'
    $env:USERPROFILE = $env:HOME
    $env:COPILOT_HOME = Join-Path $env:HOME '.copilot'
    $env:COPILOT_AUTO_UPDATE = 'false'
    $env:HARNAIS_CONTRACT = Join-Path $root 'contract.jsonl'
    foreach ($n in @('COPILOT_CUSTOM_INSTRUCTIONS_DIRS', 'COPILOT_PROJECT_DIR')) {
        [Environment]::SetEnvironmentVariable($n, $null, 'Process')
    }
    [IO.File]::WriteAllText((Join-Path $root '.github\plugin\plugin.json'),
        '{"name":"contract-probe","version":"0.0.1","hooks":"hooks/contract.json"}')
    $command = @'
$v=[Console]::In.ReadToEnd()|ConvertFrom-Json
$id=if($v.PSObject.Properties['session_id']){$v.session_id}elseif($v.PSObject.Properties['sessionId']){$v.sessionId}else{''}
$hash=[Security.Cryptography.SHA256]::Create()
$pseudo=if($id){[BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($id))).Replace('-','')}else{''}
$fields=@($v.PSObject.Properties|ForEach-Object{@{name=$_.Name;type=if($null -eq $_.Value){'null'}else{$_.Value.GetType().Name}}})
[IO.File]::AppendAllText($env:HARNAIS_CONTRACT,((@{event=$env:HARNAIS_EVENT;fields=$fields;session=$pseudo}|ConvertTo-Json -Compress -Depth 6)+"`n"))
'@
    $hooks = @{
        version = 1
        hooks = @{
            SessionStart = @(@{ type = 'command'; powershell = $command; env = @{ HARNAIS_EVENT = 'SessionStart' } })
            userPromptTransformed = @(@{ type = 'command'; powershell = $command; env = @{ HARNAIS_EVENT = 'userPromptTransformed' } })
        }
    }
    [IO.File]::WriteAllText((Join-Path $root 'hooks\contract.json'), ($hooks | ConvertTo-Json -Depth 10))
    Push-Location $root
    try {
        & $Copilot --plugin-dir $root --no-auto-update --no-remote-export --disable-builtin-mcps `
            --no-custom-instructions --available-tools --no-ask-user --allow-all-tools `
            --log-level none -p 'Reply exactly OK. This is a synthetic hook contract test; do not use tools.'
        $code = $LASTEXITCODE
    } finally { Pop-Location }
    if (Test-Path -LiteralPath $env:HARNAIS_CONTRACT) {
        $records = @(Get-Content -LiteralPath $env:HARNAIS_CONTRACT | ForEach-Object { $_ | ConvertFrom-Json })
        $records | ConvertTo-Json -Depth 8
        $start = @($records | Where-Object event -eq 'SessionStart')
        $prompt = @($records | Where-Object event -eq 'userPromptTransformed')
        if ($start.Count -gt 0 -and $prompt.Count -gt 0 -and $start[0].session -and
            $start[0].session -eq $prompt[0].session) {
            Write-Output 'PASS: identifiant pseudonymise commun aux deux evenements.'
        } else { throw 'Contrat non confirme : deux evenements avec identifiant commun non observes.' }
    } else {
        throw "Aucun evenement capture (code CLI $code). Authentification ou execution non disponible dans la configuration isolee."
    }
    if ($code -ne 0) { throw "CLI a echoue (code $code) apres capture." }
} finally {
    foreach ($n in $names) { [Environment]::SetEnvironmentVariable($n, $saved[$n], 'Process') }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
