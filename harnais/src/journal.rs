//! LE JOURNAL — hook PostToolUse (Bash), sur `git commit`.
//!
//! Écrit ce qui a été commité dans `.logs/<jour>.md`, et
//! `.logs/<jour>-<agent>.md` en multi-agents. Il répond à une question que
//! l'instantané d'état ne sait pas traiter : **qu'est-ce qui a été fait, jour
//! par jour ?** Un instantané ne dit pas ce qu'on a fait mardi ; un historique
//! ne dit pas où on en est. D'où les deux.
//!
//! POURQUOI UN HOOK ET PAS UNE COMPÉTENCE. Ce travail dépendait d'une commande
//! qu'il fallait penser à lancer. Un journal tenu quand on y pense a des trous
//! exactement les jours chargés — ceux qu'on aurait le plus besoin de relire.
//!
//! COMMENT IL SAIT QU'UN COMMIT A EU LIEU. Il ne lit pas le résultat de la
//! commande : il regarde `HEAD`. Si le commit a échoué, `HEAD` n'a pas bougé,
//! son empreinte est déjà dans le journal, et rien n'est écrit. Aucune
//! connaissance de la forme de la réponse n'est nécessaire, et un double appel
//! ne produit pas deux entrées.
//!
//! **fail-open et silencieux** : un journal est un confort, il ne doit jamais
//! empêcher de travailler.

use regex::Regex;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;

const DOSSIER: &str = ".logs";
/// Nombre de fichiers listés dans une entrée avant « … ».
const MAX_FICHIERS: usize = 40;

fn git(args: &[&str]) -> Option<String> {
    let o = Command::new("git").args(args).output().ok()?;
    if o.status.success() {
        Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
    } else {
        None
    }
}

/// Est-ce une commande de commit ? Même motif que la version Python :
/// `git` puis `commit`, aux frontières de mot.
pub fn est_un_commit(cmd: &str) -> bool {
    Regex::new(r"\bgit\b.+\bcommit\b").map(|r| r.is_match(cmd)).unwrap_or(false)
}

/// En MULTI-agents, le nom de l'agent ; sinon la chaîne vide.
///
/// Quand un agent a son propre répertoire de travail, la racine rendue par git
/// est celle DU WORKTREE : deux agents écriraient deux journaux de même chemin
/// relatif, suivis tous les deux, invisibles l'un à l'autre, et que la première
/// fusion met en collision. Un journal qui bloque une fusion a cessé d'être un
/// confort.
pub fn suffixe_agent(racine: &Path, projet: Option<&str>) -> String {
    let p = match projet {
        Some(p) if !p.is_empty() => PathBuf::from(p),
        _ => return String::new(),
    };
    let (a, b) = match (p.canonicalize(), racine.canonicalize()) {
        (Ok(a), Ok(b)) => (a, b),
        _ => (p, racine.to_path_buf()),
    };
    let rel = match a.strip_prefix(&b) {
        Ok(r) => r,
        Err(_) => return String::new(),
    };
    let parts: Vec<_> = rel.components().map(|c| c.as_os_str().to_string_lossy().to_string()).collect();
    let nom = if parts.len() == 2 && parts[0] == "agents" { &parts[1] }
        else if parts.len() == 3 && parts[0] == "brain" && parts[1] == "mind" { &parts[2] }
        else { return String::new(); };
    let mut out = String::new();
    let mut tiret = false;
    for c in nom.chars() {
        if c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-' {
            out.push(c);
            tiret = false;
        } else if !tiret {
            out.push('-');
            tiret = true;
        }
    }
    format!("-{}", out.trim_matches('-'))
}

/// L'empreinte est-elle déjà dans le journal ? Frontières de mot des deux
/// côtés, comme `\b` en Python : c'est le garde-fou contre les doublons.
pub fn deja_journalise(deja: &str, court: &str) -> bool {
    if court.is_empty() {
        return false;
    }
    let mot = |c: char| c.is_alphanumeric() || c == '_';
    let o: Vec<char> = deja.chars().collect();
    let c: Vec<char> = court.chars().collect();
    if c.len() > o.len() {
        return false;
    }
    for i in 0..=(o.len() - c.len()) {
        if o[i..i + c.len()] == c[..]
            && (i == 0 || !mot(o[i - 1]))
            && (i + c.len() == o.len() || !mot(o[i + c.len()]))
        {
            return true;
        }
    }
    false
}

/// Le bloc écrit dans le journal. Séparé pour être éprouvé sans dépôt git.
pub fn bloc(heure: &str, court: &str, branche: &str, amend: bool, sujet: &str,
            touches: &[String], auteur: &str) -> String {
    let mut l: Vec<String> = vec![
        String::new(),
        format!("## {} · `{}` · {}{}", heure, court, branche,
                if amend { " · réécriture (`--amend`)" } else { "" }),
        String::new(),
        format!("**{}**", sujet),
        String::new(),
    ];
    for f in touches.iter().take(MAX_FICHIERS) {
        l.push(format!("- `{}`", f));
    }
    if touches.len() > MAX_FICHIERS {
        l.push(format!("- … et {} autres fichiers", touches.len() - MAX_FICHIERS));
    }
    l.push(String::new());
    l.push(format!("<!-- {} -->", auteur));
    l.join("\n")
}

pub fn main(entree: &str) {
    let d: Value = match serde_json::from_str(entree) {
        Ok(v) => v,
        Err(_) => return,
    };
    let cmd = d.get("tool_input").and_then(|o| o.get("command"))
        .and_then(|v| v.as_str()).unwrap_or("");
    if !est_un_commit(cmd) {
        return;
    }
    let racine = match git(&["rev-parse", "--show-toplevel"]) {
        Some(r) if !r.is_empty() => PathBuf::from(r),
        _ => return,
    };
    // `%x09` = tabulation : un séparateur qu'un sujet de commit ne contient pas.
    let tete = match git(&["log", "-1", "--date=short",
                           "--format=%h%x09%ad%x09%cI%x09%s%x09%an"]) {
        Some(t) => t,
        None => return,
    };
    let ch: Vec<&str> = tete.split('\t').collect();
    if ch.len() != 5 {
        return;
    }
    let (court, jour, iso, sujet, auteur) = (ch[0], ch[1], ch[2], ch[3], ch[4]);

    let fichier = racine.join(DOSSIER).join(format!(
        "{}{}.md", jour,
        suffixe_agent(&racine, std::env::var("COPILOT_PROJECT_DIR").ok().as_deref())));
    let deja = std::fs::read_to_string(&fichier).unwrap_or_default();
    if deja_journalise(&deja, court) {
        return;
    }

    let brut = git(&["show", "--name-only", "--format=", "HEAD"]).unwrap_or_default();
    // Le journal ne se journalise pas : l'entrée de la veille est commitée
    // avec le travail du jour, et se retrouverait dans la liste.
    let touches: Vec<String> = brut.lines()
        .filter(|f| !f.trim().is_empty() && !f.starts_with(&format!("{}/", DOSSIER)))
        .map(|s| s.to_string())
        .collect();

    let heure = if iso.len() >= 16 { &iso[11..16] } else { "??:??" };
    let branche = git(&["rev-parse", "--abbrev-ref", "HEAD"]).unwrap_or_else(|| "?".into());
    let corps = bloc(heure, court, &branche, cmd.contains("--amend"), sujet, &touches, auteur);

    let _ = std::fs::create_dir_all(fichier.parent().unwrap_or(&racine));
    if deja.is_empty() {
        let entete = format!(
            "# Journal — {}\n\nÉcrit par le hook `journal` à chaque commit. \
             **Append-only** : on n'y réécrit rien, on n'y compresse rien.\n", jour);
        let _ = std::fs::write(&fichier, format!("{}{}\n", entete, corps));
    } else if let Ok(mut f) = std::fs::OpenOptions::new().append(true).open(&fichier) {
        use std::io::Write;
        let _ = writeln!(f, "{}", corps);
    }
}

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn ne_reagit_qu_a_un_commit() {
        assert!(est_un_commit("git commit -m x"));
        assert!(est_un_commit("cd /tmp && git -c user.name=x commit -q -F -"));
        // TÉMOINS NÉGATIFS : tout le reste doit passer sans rien écrire.
        assert!(!est_un_commit("git status"));
        assert!(!est_un_commit("git push"));
        assert!(!est_un_commit("commit"));
        assert!(!est_un_commit(""));
        // ET SES FAUX POSITIFS, qui sont ceux de la version Python — MESURÉS,
        // pas supposés : le motif attrape aussi `git log … | grep commit`. Ils
        // sont sans effet parce que le garde suivant regarde HEAD : l'empreinte
        // est déjà journalisée, donc rien n'est écrit. Un test qui les
        // interdirait ferait DIVERGER le portage.
        assert!(est_un_commit("echo git et commit"), "faux positif partagé avec Python");
        assert!(est_un_commit("git log --format=%s | grep commit"));
    }

    #[test]
    fn l_empreinte_ferme_les_doublons() {
        assert!(deja_journalise("## 10:00 · `abc1234` · main", "abc1234"));
        assert!(!deja_journalise("## 10:00 · `abc1234` · main", "abc12"),
                "un préfixe n'est PAS l'empreinte — sinon un commit en masquerait un autre");
        assert!(!deja_journalise("", "abc1234"));
        assert!(!deja_journalise("abc", "abc1234"), "journal plus court que l'empreinte");
    }

    #[test]
    fn le_suffixe_ne_bouge_qu_en_multi_agents() {
        let r = Path::new("/tmp/projet");
        assert_eq!(suffixe_agent(r, None), "");
        assert_eq!(suffixe_agent(r, Some("/tmp/projet")), "",
                   "mono-agent : le nom de fichier ne change pas");
        assert_eq!(suffixe_agent(r, Some("/tmp/projet/agents/Projet PO")), "-Projet-PO");
        assert_eq!(suffixe_agent(r, Some("/tmp/projet/brain/mind/Projet PO")), "-Projet-PO");
        assert_eq!(suffixe_agent(r, Some("/tmp/projet/autre/chose")), "");
        assert_eq!(suffixe_agent(r, Some("/ailleurs")), "");
    }

    #[test]
    fn le_bloc_a_la_forme_attendue() {
        let f: Vec<String> = (0..45).map(|i| format!("f{}.rs", i)).collect();
        let b = bloc("10:30", "abc1234", "main", true, "Un sujet", &f, "alice");
        assert!(b.contains("## 10:30 · `abc1234` · main · réécriture (`--amend`)"));
        assert!(b.contains("**Un sujet**"));
        assert!(b.contains("- … et 5 autres fichiers"), "le plafond de 40 mord");
        assert!(b.ends_with("<!-- alice -->"));
        let court = bloc("10:30", "abc1234", "main", false, "S", &f[..2], "M");
        assert!(!court.contains("réécriture"));
        assert!(!court.contains("autres fichiers"));
    }
}
