# -*- coding: utf-8 -*-
"""L'HÔTE QUI LANCE LE HARNAIS : GitHub Copilot CLI, et lui seul.

Port de `harnais/src/hote.rs` (Rust, 1.3.0). Mêmes noms de fonctions.

Les hooks du paquet sont déclarés en PascalCase (`SessionStart`, `PreToolUse`…)
et en camelCase (`userPromptTransformed`). Les deux formes n'arrivent pas avec
la même charge, et chaque écart éteint une fonction SANS BRUIT :

- `UserPromptSubmit` : Copilot JETTE la sortie d'un hook de commande. Le seul
  canal vers le modèle à chaque message est `userPromptTransformed`, qui
  réécrit le contenu envoyé (`modifiedTransformedPrompt`).
- Fin de tour : Copilot attend `{"decision":"block","reason":…}` sur la sortie
  standard, et un code 0 — un code non nul n'est qu'une panne de hook.
- Refus d'un outil : `permissionDecision` à la racine de l'objet.
- `COPILOT_PROJECT_DIR` prime sur `cwd`.
- Le résultat d'un outil arrive dans `tool_result`, et `view` nomme son fichier
  `path`.
- Sous Windows, les hooks tournent sous PowerShell, où `HOME` n'existe pas.

La charge est NORMALISÉE ICI, une fois : clés en snake_case, noms d'outils tels
que la forme PascalCase les donne (`Bash`, `Read`, `Edit`…). Les modules qui la
lisent n'ont pas à connaître les deux formes ; les trois SORTIES passent toutes
par ce module.

LES SORTIES SONT EN ASCII PUR (`json.dumps` par défaut) : un octet non ASCII
peut être abîmé par PowerShell.
"""
import json
import os
import sys


def maison():
    """`HOME`, et sous Windows hors Git Bash, `USERPROFILE`. Un `HOME` absent
    rendait « . » : le harnais écrivait son état dans le dossier du projet."""
    return os.environ.get("HOME") or os.environ.get("USERPROFILE") or "."


def maison_copilot():
    """Le dossier de Copilot CLI : `COPILOT_HOME`, sinon `~/.copilot`."""
    return os.environ.get("COPILOT_HOME") or os.path.join(maison(), ".copilot")


def _env_non_vide(k):
    v = os.environ.get(k)
    return v if (v is not None and v.strip()) else None


def pose_variables_du_paquet():
    """Les deux variables du paquet, posées quand l'hôte ne les donne pas — c'est
    sous ces noms que tout le reste du programme les lit."""
    if _env_non_vide("COPILOT_PLUGIN_ROOT") is None:
        r = _env_non_vide("PLUGIN_ROOT")
        if r is None:
            import copilot
            r = copilot.paquet_ou_rien()
        if r is not None:
            os.environ["COPILOT_PLUGIN_ROOT"] = r
    if _env_non_vide("COPILOT_PLUGIN_DATA") is None:
        # Un dossier qui SURVIT aux mises à jour : pas dans `installed-plugins/`,
        # que chaque mise à jour remplace.
        d = _env_non_vide("PLUGIN_DATA") or os.path.join(
            maison_copilot(), "plugin-data", "atelier-copilot", "harnais")
        os.environ["COPILOT_PLUGIN_DATA"] = d


# Le texte réécrit par `userPromptTransformed`, gardé pour la sortie : le
# briefing y ajoute son contexte au lieu de le rendre à part.
_TRANSFORME = [None]


def prepare(entree):
    """À appeler UNE fois, avant tout, par chaque sous-commande de hook : les
    variables du paquet et du projet posées, et la charge normalisée."""
    return _prepare_avec(entree, True)


def prepare_sans_agent(entree):
    """La même, SANS lire le journal de session : pour un hook qui n'a pas besoin
    de savoir quel agent parle (les lectures de faits, communes à tous) et qui
    part à chaque lecture — le journal se lit en entier."""
    return _prepare_avec(entree, False)


def prepare_si_commit(entree):
    """Pour les deux hooks shell, qui partent à CHAQUE commande et n'agissent que
    sur un `git commit` : l'agent n'est résolu que pour un commit."""
    t = _prepare_avec(entree, False)
    try:
        v = json.loads(t)
    except ValueError:
        return t
    ti = v.get("tool_input") if isinstance(v, dict) else None
    cmd = ti.get("command") if isinstance(ti, dict) else None
    import journal
    if journal.est_un_commit(cmd if isinstance(cmd, str) else ""):
        import agent
        agent.pose(v)
    return t


def _prepare_avec(entree, avec_agent):
    pose_variables_du_paquet()
    try:
        v = json.loads(entree)
    except ValueError:
        return entree
    v = traduis(v)
    if _env_non_vide("COPILOT_PROJECT_DIR") is None and isinstance(v, dict):
        c = v.get("cwd")
        if isinstance(c, str) and c:
            os.environ["COPILOT_PROJECT_DIR"] = c
    # QUI PARLE — lu dans le journal de session, puisqu'aucun hook ne le reçoit.
    # Peut déplacer `COPILOT_PROJECT_DIR` dans le dossier de l'agent : voir `agent`.
    if avec_agent and isinstance(v, dict):
        import agent
        agent.pose(v)
    if isinstance(v, dict) and isinstance(v.get("transformedPrompt"), str) and _TRANSFORME[0] is None:
        _TRANSFORME[0] = v["transformedPrompt"]
    return json.dumps(v, ensure_ascii=False)


_OUTILS = {
    "bash": "Bash", "powershell": "Bash",
    "view": "Read",
    "create": "Write",
    "edit": "Edit", "str_replace_editor": "Edit", "apply_patch": "Edit",
    "grep": "Grep", "rg": "Grep",
    "glob": "Glob",
    # L'outil des sous-agents de Copilot (COMMENT-CA-MARCHE.md, « Qui parle » ;
    # py/agent.py) : la garde des sous-agents le juge sous ce nom.
    "task": "Task",
}


def outil_pascal(n):
    """Les noms d'outils de la forme camelCase, ramenés à ceux que la forme
    PascalCase donne déjà."""
    return _OUTILS.get(n, n)


_CLES = [("sessionId", "session_id"), ("transcriptPath", "transcript_path"),
         ("toolArgs", "tool_input"), ("toolResult", "tool_result"),
         ("stopReason", "stop_reason"), ("initialPrompt", "initial_prompt"),
         ("agentId", "agent_id"), ("agentType", "agent_type")]


def traduis(v):
    """LA CHARGE COPILOT, NORMALISÉE. Pure : testable sans hôte."""
    if not isinstance(v, dict):
        return v
    o = dict(v)
    for c, s in _CLES:
        if s not in o and c in o:
            o[s] = o[c]
    if "tool_name" not in o and isinstance(o.get("toolName"), str):
        o["tool_name"] = outil_pascal(o["toolName"])
    # Les arguments arrivent parfois en texte JSON.
    if isinstance(o.get("tool_input"), str):
        try:
            o["tool_input"] = json.loads(o["tool_input"])
        except ValueError:
            pass
    ti = o.get("tool_input")
    if isinstance(ti, dict) and "file_path" not in ti and "path" in ti:
        ti = dict(ti)
        ti["file_path"] = ti["path"]
        o["tool_input"] = ti
    if "tool_response" not in o:
        r = o.get("tool_result")
        if isinstance(r, dict):
            if "text_result_for_llm" in r:
                o["tool_response"] = r["text_result_for_llm"]
            elif "textResultForLlm" in r:
                o["tool_response"] = r["textResultForLlm"]
    # `userPromptTransformed` n'a pas de nom d'événement : c'est, pour le
    # harnais, le message de l'utilisateur.
    if "transformedPrompt" in o:
        o["hook_event_name"] = "UserPromptSubmit"
    return o


def _noms_outil(d):
    out = []
    if isinstance(d, dict):
        for k in ("toolName", "tool_name"):
            if isinstance(d.get(k), str):
                out.append(d[k].strip().lower())
    return out


def est_powershell(d):
    """La commande part-elle dans PowerShell ? `traduis` ramène `powershell` à
    `Bash`, mais garde le nom d'origine dans `toolName` : c'est lui qui dit quel
    shell lira la ligne (ni `\\` ni `&&` n'y veulent dire la même chose)."""
    return "powershell" in _noms_outil(d)


def est_shell(d):
    """Une commande shell, bash comme PowerShell. Le nom `powershell` reste
    accepté tel quel : la forme PascalCase pourrait le donner sans le ramener à
    `Bash` (pas mesuré)."""
    return any(n in ("bash", "powershell") for n in _noms_outil(d))


def est_sous_agent(d):
    """L'outil `task`, qui lance un sous-agent."""
    return "task" in _noms_outil(d)


def json_ascii(v):
    """`json.dumps(x)` : séparateurs `, ` et `: `, tout le non-ASCII en `\\uXXXX`."""
    return json.dumps(v)


def contexte(texte):
    """Ce qui porte un contexte vers le modèle (briefing, signaux d'un message)."""
    return contexte_copilot(_TRANSFORME[0], texte)


def contexte_copilot(transforme, texte):
    if transforme is not None:
        return json_ascii({"modifiedTransformedPrompt": (
            "%s\n\n<harnais>\nContexte ajouté par le harnais de l'atelier — ce n'est pas "
            "l'utilisateur qui l'a écrit.\n\n%s\n</harnais>" % (transforme, texte))})
    return json_ascii({"additionalContext": texte})


def refus(motif):
    """Le refus d'une commande par un garde (commit, périmètre)."""
    return json_ascii({"permissionDecision": "deny", "permissionDecisionReason": motif})


def renvoi_copilot(message):
    return json_ascii({"decision": "block", "reason": message})


def renvoie(message):
    """Renvoyer l'agent au travail en fin de tour : l'objet `block` sur la sortie
    standard, et 0 — un code non nul n'y est qu'une panne de hook."""
    sys.stdout.write(renvoi_copilot(message) + "\n")
    sys.stdout.flush()
    sys.exit(0)
