//! L'HÔTE QUI LANCE LE HARNAIS : GitHub Copilot CLI, et lui seul.
//!
//! Les hooks du paquet sont déclarés en PascalCase (`SessionStart`,
//! `PreToolUse`…) et en camelCase (`userPromptTransformed`). Les deux formes
//! n'arrivent pas avec la même charge, et chaque écart éteint une fonction SANS
//! BRUIT :
//!
//! - `UserPromptSubmit` : Copilot JETTE la sortie d'un hook de commande. Le
//!   seul canal vers le modèle à chaque message est `userPromptTransformed`,
//!   qui réécrit le contenu envoyé (`modifiedTransformedPrompt`).
//! - Fin de tour : Copilot attend `{"decision":"block","reason":…}` sur la
//!   sortie standard, et un code 0 — un code non nul n'est qu'une panne de hook.
//! - Refus d'un outil : `permissionDecision` à la racine de l'objet.
//! - `COPILOT_PROJECT_DIR` prime sur `cwd`.
//! - Le résultat d'un outil arrive dans `tool_result`, et `view` nomme son
//!   fichier `path`.
//! - Sous Windows, les hooks tournent sous PowerShell, où `HOME` n'existe pas.
//!
//! La charge est NORMALISÉE ICI, une fois : clés en snake_case, noms d'outils
//! tels que la forme PascalCase les donne (`Bash`, `Read`, `Edit`…). Les
//! modules qui la lisent n'ont pas à connaître les deux formes ; les trois
//! SORTIES passent toutes par ce module.

use serde_json::{json, Map, Value};
use std::path::PathBuf;

/// `HOME`, et sous Windows hors Git Bash, `USERPROFILE`. Un `HOME` absent
/// rendait « . » : le harnais écrivait son état dans le dossier du projet.
pub fn maison() -> PathBuf {
    std::env::var_os("HOME").filter(|s| !s.is_empty())
        .or_else(|| std::env::var_os("USERPROFILE").filter(|s| !s.is_empty()))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

/// Le dossier de Copilot CLI : `COPILOT_HOME`, sinon `~/.copilot`.
pub fn maison_copilot() -> PathBuf {
    std::env::var_os("COPILOT_HOME").filter(|s| !s.is_empty()).map(PathBuf::from)
        .unwrap_or_else(|| maison().join(".copilot"))
}

fn env_non_vide(k: &str) -> Option<String> {
    std::env::var(k).ok().filter(|s| !s.trim().is_empty())
}

/// Les deux variables du paquet, posées quand l'hôte ne les donne pas — c'est
/// sous ces noms que tout le reste du programme les lit.
fn pose_variables_du_paquet() {
    if env_non_vide("COPILOT_PLUGIN_ROOT").is_none() {
        let r = env_non_vide("PLUGIN_ROOT").map(PathBuf::from)
            .or_else(|| crate::copilot::paquet().ok());
        if let Some(r) = r { std::env::set_var("COPILOT_PLUGIN_ROOT", r); }
    }
    if env_non_vide("COPILOT_PLUGIN_DATA").is_none() {
        // Un dossier qui SURVIT aux mises à jour : pas dans `installed-plugins/`,
        // que chaque mise à jour remplace.
        let d = env_non_vide("PLUGIN_DATA").map(PathBuf::from)
            .unwrap_or_else(|| maison_copilot().join("plugin-data").join("atelier-copilot").join("harnais"));
        std::env::set_var("COPILOT_PLUGIN_DATA", d);
    }
}

/// Le texte réécrit par `userPromptTransformed`, gardé pour la sortie : le
/// briefing y ajoute son contexte au lieu de le rendre à part.
static TRANSFORME: std::sync::OnceLock<String> = std::sync::OnceLock::new();

/// À appeler UNE fois, avant tout, par chaque sous-commande de hook : les
/// variables du paquet et du projet posées, et la charge normalisée.
pub fn prepare(entree: &str) -> String {
    pose_variables_du_paquet();
    let v: Value = match serde_json::from_str(entree) { Ok(v) => v, Err(_) => return entree.to_string() };
    let v = traduis(v);
    if env_non_vide("COPILOT_PROJECT_DIR").is_none() {
        if let Some(c) = v.get("cwd").and_then(|x| x.as_str()).filter(|s| !s.is_empty()) {
            std::env::set_var("COPILOT_PROJECT_DIR", c);
        }
    }
    if let Some(t) = v.get("transformedPrompt").and_then(|x| x.as_str()) {
        let _ = TRANSFORME.set(t.to_string());
    }
    v.to_string()
}

/// Les noms d'outils de la forme camelCase, ramenés à ceux que la forme
/// PascalCase donne déjà.
fn outil_pascal(n: &str) -> &str {
    match n {
        "bash" | "powershell" => "Bash",
        "view" => "Read",
        "create" => "Write",
        "edit" | "str_replace_editor" | "apply_patch" => "Edit",
        "grep" | "rg" => "Grep",
        "glob" => "Glob",
        autre => autre,
    }
}

/// LA CHARGE COPILOT, NORMALISÉE. Pure : testable sans hôte.
pub fn traduis(v: Value) -> Value {
    let mut o: Map<String, Value> = match v { Value::Object(o) => o, autre => return autre };
    for (c, s) in [("sessionId", "session_id"), ("transcriptPath", "transcript_path"),
                   ("toolArgs", "tool_input"), ("toolResult", "tool_result"),
                   ("stopReason", "stop_reason"), ("initialPrompt", "initial_prompt"),
                   ("agentId", "agent_id"), ("agentType", "agent_type")] {
        if !o.contains_key(s) {
            if let Some(x) = o.get(c).cloned() { o.insert(s.into(), x); }
        }
    }
    if !o.contains_key("tool_name") {
        if let Some(n) = o.get("toolName").and_then(|x| x.as_str()).map(String::from) {
            o.insert("tool_name".into(), Value::String(outil_pascal(&n).to_string()));
        }
    }
    // Les arguments arrivent parfois en texte JSON.
    if let Some(Value::String(s)) = o.get("tool_input").cloned() {
        if let Ok(p) = serde_json::from_str::<Value>(&s) { o.insert("tool_input".into(), p); }
    }
    if let Some(Value::Object(ti)) = o.get_mut("tool_input") {
        if !ti.contains_key("file_path") {
            if let Some(p) = ti.get("path").cloned() { ti.insert("file_path".into(), p); }
        }
    }
    if !o.contains_key("tool_response") {
        let texte = o.get("tool_result").and_then(|r| r.get("text_result_for_llm")
            .or_else(|| r.get("textResultForLlm"))).cloned();
        if let Some(t) = texte { o.insert("tool_response".into(), t); }
    }
    // `userPromptTransformed` n'a pas de nom d'événement : c'est, pour le
    // harnais, le message de l'utilisateur.
    if o.contains_key("transformedPrompt") {
        o.insert("hook_event_name".into(), json!("UserPromptSubmit"));
    }
    Value::Object(o)
}

/// Ce qui porte un contexte vers le modèle (briefing, signaux d'un message).
pub fn contexte(texte: &str) -> String {
    contexte_copilot(TRANSFORME.get().map(|s| s.as_str()), texte)
}

fn contexte_copilot(transforme: Option<&str>, texte: &str) -> String {
    match transforme {
        Some(t) => crate::socle::json_python(&json!({"modifiedTransformedPrompt": format!(
            "{t}\n\n<harnais>\nContexte ajouté par le harnais de l'atelier — ce n'est pas \
l'utilisateur qui l'a écrit.\n\n{texte}\n</harnais>")})),
        None => crate::socle::json_python(&json!({"additionalContext": texte})),
    }
}

/// Le refus d'une commande par le garde de commit.
pub fn refus(motif: &str) -> String {
    crate::socle::json_python(&json!({"permissionDecision": "deny",
                                      "permissionDecisionReason": motif}))
}

/// Renvoyer l'agent au travail en fin de tour : l'objet `block` sur la sortie
/// standard, et 0 — un code non nul n'y est qu'une panne de hook.
pub fn renvoie(message: &str) -> ! {
    println!("{}", renvoi_copilot(message));
    std::process::exit(0);
}

fn renvoi_copilot(message: &str) -> String {
    crate::socle::json_python(&json!({"decision": "block", "reason": message}))
}

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn la_forme_pascal_de_copilot_passe_presque_telle_quelle() {
        let v = traduis(json!({"hook_event_name": "PostToolUse", "session_id": "s",
            "cwd": "C:\\p", "tool_name": "Read", "tool_input": {"path": "C:\\m\\note.md"},
            "tool_result": {"result_type": "success", "text_result_for_llm": "contenu"}}));
        assert_eq!(v["tool_name"], "Read");
        assert_eq!(v["tool_input"]["file_path"], "C:\\m\\note.md");
        assert_eq!(v["tool_response"], "contenu");
        assert_eq!(v["hook_event_name"], "PostToolUse", "un nom donné n'est jamais écrasé");
    }

    #[test]
    fn la_forme_camel_est_ramenee_a_la_forme_pascal() {
        let v = traduis(json!({"sessionId": "s", "cwd": "/p", "toolName": "powershell",
            "toolArgs": "{\"command\":\"git commit -m x\"}",
            "toolResult": {"resultType": "success", "textResultForLlm": "ok"}}));
        assert_eq!(v["session_id"], "s");
        assert_eq!(v["tool_name"], "Bash", "PowerShell est le shell de Windows");
        assert_eq!(v["tool_input"]["command"], "git commit -m x");
        assert_eq!(v["tool_response"], "ok");
        // Un fichier déjà nommé `file_path` n'est pas remplacé par `path`.
        let v = traduis(json!({"tool_input": {"file_path": "/a", "path": "/b"}}));
        assert_eq!(v["tool_input"]["file_path"], "/a");
    }

    #[test]
    fn le_message_transforme_est_un_message_de_l_utilisateur() {
        let v = traduis(json!({"sessionId": "s", "cwd": "/p", "prompt": "salut",
                               "transformedPrompt": "salut (transformé)"}));
        assert_eq!(v["hook_event_name"], "UserPromptSubmit");
        assert_eq!(v["prompt"], "salut");
        // TÉMOIN : un autre événement camelCase ne devient pas un message.
        assert!(traduis(json!({"sessionId": "s"})).get("hook_event_name").is_none());
    }

    #[test]
    fn les_sorties_copilot_sont_du_json_ascii_lisible() {
        let t = "Café — à relire";
        let c: Value = serde_json::from_str(&contexte_copilot(None, t)).unwrap();
        assert_eq!(c["additionalContext"], t);
        let c = contexte_copilot(Some("la demande"), t);
        assert!(c.is_ascii(), "un octet non ASCII peut être abîmé par PowerShell : {c}");
        let c: Value = serde_json::from_str(&c).unwrap();
        let m = c["modifiedTransformedPrompt"].as_str().unwrap();
        assert!(m.starts_with("la demande"), "la demande d'abord, intacte");
        assert!(m.contains(t));
        let r: Value = serde_json::from_str(&refus("non")).unwrap();
        assert_eq!(r["permissionDecision"], "deny");
        assert_eq!(r["permissionDecisionReason"], "non");
        let b: Value = serde_json::from_str(&renvoi_copilot("reprends")).unwrap();
        assert_eq!(b["decision"], "block");
        assert_eq!(b["reason"], "reprends");
    }
}
