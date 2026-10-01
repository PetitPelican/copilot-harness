//! MONTER UN ATELIER sur une machine neuve — pas un projet, la couche au-dessus.
//!
//!     <racine>/AGENTS.md      la MÉTHODE, héritée par tout agent d'un sous-dossier
//!     <racine>/<cto>/         le poste du CTO, harnais posé, dépôt git
//!
//! Deux fichiers de rôle, puis le harnais sur le poste du CTO — la seconde
//! moitié est déléguée à `adopte`, au lieu d'en écrire une seconde copie.
//!
//! POURQUOI LE SOCLE NE « PRÉVAUT » PAS. Un `AGENTS.md` parent n'écrase pas
//! celui d'un projet : les deux sont lus, le plus précis l'emporte. Le socle
//! porte l'invariant, le projet ajoute son rôle par-dessus.
//!
//! **À blanc par défaut.** `--go` pour écrire. Rien n'est jamais écrasé.

use std::path::{Path, PathBuf};

/// Les gabarits voyagent DANS le programme : un chemin vers un dossier de
/// gabarits est juste le jour où on l'écrit et faux le jour où le paquet
/// change de version — c'est exactement ce qui a tué le script d'avant.
const SOCLE: &str = include_str!("../../skills/agentic-init/templates/foundation-AGENTS.md");
const CTO: &str = include_str!("../../skills/agentic-init/templates/cto-AGENTS.md");
pub const REGISTRE: &str = "docs/projects.json";

pub fn accueil(racine: &Path) -> Result<Option<&'static str>, String> {
    let fichier = racine.join(REGISTRE);
    let texte = match std::fs::read_to_string(&fichier) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("{} : {e}", fichier.display())),
    };
    let registre: serde_json::Value = serde_json::from_str(&texte)
        .map_err(|e| format!("{} : {e}", fichier.display()))?;
    if registre.get("schema").and_then(serde_json::Value::as_u64) != Some(1) {
        return Err(format!("{} : schema doit valoir 1", fichier.display()));
    }
    let projets = registre.get("projects").and_then(serde_json::Value::as_array)
        .ok_or_else(|| format!("{} : projects doit être une liste", fichier.display()))?;
    for projet in projets {
        for champ in ["name", "path"] {
            if !projet.get(champ).and_then(serde_json::Value::as_str)
                .is_some_and(|s| !s.trim().is_empty()) {
                return Err(format!("{} : projet sans {champ}", fichier.display()));
            }
        }
        let profils = projet.get("profiles").and_then(serde_json::Value::as_array)
            .ok_or_else(|| format!("{} : projet sans liste profiles", fichier.display()))?;
        if profils.is_empty() || profils.iter().any(|p| !matches!(p.as_str(), Some("OPS" | "PO" | "QA"))) {
            return Err(format!("{} : profiles attend OPS, PO ou QA", fichier.display()));
        }
    }
    Ok(projets.is_empty().then_some(
        "ACCUEIL CTO — aucun projet déclaré dans docs/projects.json.\n\
Termine d'abord les sections À REMPLIR de la mémoire du CTO. Puis demande à\n\
l'utilisateur s'il a un projet nouveau ou existant ; demande son nom, et où est\n\
son code s'il existe, au tour suivant. Ne crée rien avant son accord explicite.\n\
Le projet agentique se crée sous la racine de l'atelier (son propre dépôt git) ;\n\
un code existant ailleurs y reste, sans rien y écrire : `harnais adopte --code\n\
\"<chemin du code>\"` depuis le dossier du projet en garde l'adresse.\n\
Présente les profils : OPS = socle (base, routes serveur, CI, déploiement, workspace) ;\n\
PO = produit (applications, logique métier, ce que voit l'utilisateur) ;\n\
QA = épreuve (lit tout, n'écrit nulle part, livre un plan ; ne répare jamais son audit).\n\
Un profil = mono-agent ; plusieurs = multi-agents après lecture de roles.md.\n\
On ne découpe pas parce que le projet est gros. Propose ensuite de personnaliser\n\
chaque profil (nom, périmètre, règles, ton), ou de garder ses valeurs par défaut.\n\
Prévisualise l'adoption et les agents ; attends l'accord avant l'écriture.\n\
Déclare le projet dans docs/projects.json seulement après l'adoption réussie."))
}

fn valeur(args: &[String], cle: &str) -> Option<String> {
    let mut it = args.iter();
    while let Some(a) = it.next() {
        if a == cle { return it.next().cloned(); }
        if let Some(v) = a.strip_prefix(&format!("{}=", cle)) { return Some(v.to_string()); }
    }
    None
}

fn developpe(p: &str) -> PathBuf {
    let maison = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")).map(PathBuf::from);
    if p == "~" { if let Some(h) = maison { return h; } }
    if let Some(reste) = p.strip_prefix("~/") { if let Some(h) = maison { return h.join(reste); } }
    PathBuf::from(p)
}

/// Pose un gabarit, jamais par-dessus un fichier existant. Rend ce qui a été
/// fait ou ignoré, pour le rapport.
fn pose(texte: &str, dst: &Path, go: bool, faits: &mut Vec<String>, ignores: &mut Vec<String>) -> Result<(), String> {
    if dst.exists() {
        ignores.push(format!("Existe déjà, non écrasé : {}", dst.display()));
        return Ok(());
    }
    faits.push(format!("Créer {}", dst.display()));
    if go {
        if let Some(p) = dst.parent() {
            std::fs::create_dir_all(p).map_err(|e| format!("{} : {e}", p.display()))?;
        }
        use std::io::Write;
        std::fs::OpenOptions::new().write(true).create_new(true).open(dst)
            .and_then(|mut f| f.write_all(texte.as_bytes()))
            .map_err(|e| format!("{} : {e}", dst.display()))?;
    }
    Ok(())
}

pub fn main(args: &[String]) -> i32 {
    if args.iter().any(|a| a == "-h" || a == "--help") {
        println!("harnais atelier-monte [--racine R] [--cto NOM] [--utilisateur PRÉNOM] [--go]\n\n\
Monte un atelier : la méthode à la racine, le poste du CTO avec son rôle et le\n\
harnais. À blanc par défaut ; `--go` écrit. Rien n'est jamais écrasé.");
        return 0;
    }
    let go = args.iter().any(|a| a == "--go" || a == "--apply");
    let racine = developpe(&valeur(args, "--racine").unwrap_or_else(|| "~/Agentic".into()));
    let nom_cto = valeur(args, "--cto").unwrap_or_else(|| "cto".into());
    if nom_cto.is_empty() || nom_cto == "." || nom_cto == ".." || nom_cto.contains(['/', '\\', ':']) {
        eprintln!("atelier-monte : --cto doit être un nom de dossier simple.");
        return 1;
    }
    let qui = valeur(args, "--utilisateur").map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
        .unwrap_or_else(|| "l'utilisateur".into());
    let cto = racine.join(&nom_cto);

    println!("Atelier — montage");
    println!("Racine      : {}", racine.display());
    println!("CTO         : {}", cto.display());
    println!("Mode        : {}", if go { "ÉCRITURE" } else { "À BLANC" });
    println!();

    let (mut faits, mut ignores) = (Vec::new(), Vec::new());
    if !racine.exists() {
        faits.push(format!("Créer la racine {}", racine.display()));
        if go {
            if let Err(e) = std::fs::create_dir_all(&racine) {
                eprintln!("atelier-monte : {} : {e}", racine.display());
                return 1;
            }
        }
    }
    // 1. La MÉTHODE, à la racine. C'est l'artefact portable.
    if let Err(e) = pose(&SOCLE.replace("[UTILISATEUR]", &qui), &racine.join("AGENTS.md"), go, &mut faits, &mut ignores) {
        eprintln!("atelier-monte : {e}"); return 1;
    }
    // 2. Le poste du CTO. Son rôle seulement — la méthode, il l'hérite.
    if cto.join("CLAUDE.md").exists() {
        ignores.push(format!("{} existe : ne pas créer AGENTS.md en doublon", cto.join("CLAUDE.md").display()));
    } else {
        let racine_abs = std::path::absolute(&racine).unwrap_or_else(|_| racine.clone());
        let paquet = crate::copilot::paquet().map(|p| p.display().to_string())
            .unwrap_or_else(|_| "introuvable — `harnais diagnostic` le cherche".into());
        let role = CTO.replace("[UTILISATEUR]", &qui)
            .replace("[RACINE]", &racine_abs.display().to_string())
            .replace("[PAQUET]", &paquet);
        if let Err(e) = pose(&role, &cto.join("AGENTS.md"), go, &mut faits, &mut ignores) {
            eprintln!("atelier-monte : {e}"); return 1;
        }
    }
    // 3. Un dépôt git, AVANT le harnais : `adopte` n'en crée pas, et sans lui
    //    les gardes de commit sont inertes — un garde inerte ne dit pas qu'il
    //    l'est.
    if cto.join(".git").exists() {
        ignores.push(format!("Dépôt git déjà présent dans {}", cto.display()));
    } else {
        faits.push(format!("git init dans {} (sans lui, les gardes de commit sont inertes)", cto.display()));
        if go {
            if let Err(e) = std::fs::create_dir_all(&cto) {
                eprintln!("atelier-monte : {} : {e}", cto.display()); return 1;
            }
            match std::process::Command::new("git").args(["init", "-q", "-b", "main"])
                .current_dir(&cto).output() {
                Ok(o) if o.status.success() => (),
                Ok(o) => { eprintln!("atelier-monte : git init : {}", String::from_utf8_lossy(&o.stderr)); return 1; }
                Err(e) => { eprintln!("atelier-monte : git init : {e}"); return 1; }
            }
        }
    }

    println!("Fait :");
    println!("{}", if faits.is_empty() { "- Rien".into() } else {
        faits.iter().map(|m| format!("- {}", m)).collect::<Vec<_>>().join("\n") });
    println!();
    println!("Ignorés (non écrasés) :");
    println!("{}", if ignores.is_empty() { "- Aucun".into() } else {
        ignores.iter().map(|m| format!("- {}", m)).collect::<Vec<_>>().join("\n") });
    println!();

    // 4. Le harnais sur le poste du CTO : un projet comme un autre, dont le
    //    produit se trouve être l'atelier. `adopte` pose sa mémoire et branche
    //    le paquet — à blanc s'il est à blanc.
    println!("── harnais du CTO (harnais adopte) {}", "─".repeat(30));
    if !cto.is_dir() && !go {
        println!("(le dossier n'existe pas encore : `adopte` le posera à l'écriture)");
    }
    let mut a = vec![cto.display().to_string()];
    if go { a.push("--go".into()); }
    let rc = if cto.is_dir() || go {
        crate::adopte::main(&a)
    } else { 0 };
    println!("{}", "─".repeat(65));
    println!();

    println!("À faire ensuite :");
    println!("- REMPLIR la mémoire du CTO : le cap dans `brain/fact/base.md`, l'état et ce qui \
attend dans `brain/mind/`. Tant qu'ils portent « À REMPLIR », le briefing le dit.");
    println!("- LE SOCLE de la racine ne porte QUE la méthode. Le poste (comptes, sessions, \
réseau, mémoire vive) va dans ~/.copilot/copilot-instructions.md ; le rôle et les règles métier, dans \
AGENTS.md de chaque projet.");
    println!("- La méthode est aussi dans .github/copilot-instructions.md du CTO.\n  Ajouter {} à COPILOT_CUSTOM_INSTRUCTIONS_DIRS sans remplacer les valeurs existantes\n  reste optionnel selon l'hôte ; install.ps1 le fait de façon idempotente.\n  Ouvrir une nouvelle session et contrôler /instructions.", racine.display());
    println!("- LA PREUVE : dans une session ouverte DANS le dossier du CTO, un briefing doit \
s'afficher au démarrage. Un hook qu'on n'a pas vu se déclencher n'est pas un hook vérifié.");
    println!("- LA SUITE : pour chaque projet, `harnais adopte` dans son dossier.");
    if rc == 0 {
        println!("- Registre CTO : {} (créé seulement s'il est absent).", cto.join(REGISTRE).display());
        if let Err(e) = pose("{\"schema\":1,\"projects\":[]}\n", &cto.join(REGISTRE), go, &mut faits, &mut ignores) {
            eprintln!("atelier-monte : {e}"); return 1;
        }
        if go {
            if let Err(e) = accueil(&cto) { eprintln!("atelier-monte : {e}"); return 1; }
        }
    }

    if !go {
        println!("\nÀ blanc seulement. Relancer avec --go pour écrire.");
        return rc;
    }
    if rc == 0 {
        println!("\nL'atelier est en place. Ouvrir une nouvelle session Copilot dans {} : ses réglages\ndéclarent le paquet ; il faut aussi l'installer via la marketplace. AGENTS.md porte le rôle du CTO.", cto.display());
    } else {
        eprintln!("atelier-monte : montage incomplet ; corriger l'erreur puis relancer --go.");
    }
    rc
}

#[cfg(test)]
mod essais {
    use super::*;

    fn bac(nom: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("atelier-{}-{}", nom, std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        d
    }

    #[test]
    fn a_blanc_rien_ne_s_ecrit() {
        let d = bac("blanc");
        main(&["--racine".into(), d.display().to_string()]);
        assert!(!d.exists(), "à blanc, pas même la racine");
    }

    #[test]
    fn ecrit_puis_n_ecrase_rien() {
        let d = bac("ecrit");
        main(&["--racine".into(), d.display().to_string(), "--utilisateur".into(), "alice".into(), "--go".into()]);
        let socle = std::fs::read_to_string(d.join("AGENTS.md")).unwrap();
        let role = std::fs::read_to_string(d.join("cto/AGENTS.md")).unwrap();
        assert_eq!(socle, SOCLE.replace("[UTILISATEUR]", "alice"));
        assert!(socle.contains("`@user` désigne alice"), "la méthode nomme @user");
        assert!(role.contains("alice") && !role.contains("[UTILISATEUR]"));
        // LE RÔLE DIT OÙ SONT LES CHOSES : la racine en absolu, le paquet, et
        // aucun gabarit laissé brut.
        assert!(role.contains(&format!("Racine de l'atelier : `{}`", d.display())), "{role}");
        assert!(!role.contains("[RACINE]") && !role.contains("[PAQUET]"));
        assert!(d.join("cto/brain/fact/base.md").is_file(), "le harnais est posé par adopte");
        assert!(d.join("cto/.git").exists(), "et son dépôt");
        // relancer ne change rien
        std::fs::write(d.join("AGENTS.md"), "à moi").unwrap();
        main(&["--racine".into(), d.display().to_string(), "--go".into()]);
        assert_eq!(std::fs::read_to_string(d.join("AGENTS.md")).unwrap(), "à moi");
        let _ = std::fs::remove_dir_all(&d);
    }

    #[test]
    fn accueil_seulement_pour_un_cto_sans_projet_declare() {
        let d = bac("accueil");
        assert_eq!(accueil(&d).unwrap(), None);
        std::fs::create_dir_all(d.join("docs")).unwrap();
        let fichier = d.join(REGISTRE);
        std::fs::write(&fichier, r#"{"schema":1,"projects":[]}"#).unwrap();
        assert!(accueil(&d).unwrap().unwrap().contains("ACCUEIL CTO"));
        std::fs::write(&fichier, r#"{"schema":1,"projects":[{"name":"Test","path":"../Test","profiles":["PO"]}]}"#).unwrap();
        assert_eq!(accueil(&d).unwrap(), None);
        std::fs::write(&fichier, r#"{"schema":1,"projects":[{}]}"#).unwrap();
        assert!(accueil(&d).is_err());
        std::fs::write(&fichier, "cassé").unwrap();
        assert!(accueil(&d).is_err());
        std::fs::remove_dir_all(&d).unwrap();
    }
}
