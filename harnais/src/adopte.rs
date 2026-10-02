//! `harnais adopte` — POSER LE HARNAIS SUR UN PROJET, EN UN SEUL GESTE.
//!
//! POURQUOI CETTE SOUS-COMMANDE EXISTE. Monter un projet à la main demande
//! **une suite de gestes dont certains ne sont documentés nulle part**, et un
//! dernier invisible — rien n'avertit qu'en cours de route on vient de fabriquer
//! un projet dans l'organisation d'AVANT. Un atelier qui ne se monte que par
//! quelqu'un qui l'a déjà monté n'est pas transposable ; c'est un savoir-faire,
//! pas un outil.
//!
//! CE QU'ELLE FAIT, ET RIEN D'AUTRE :
//!
//! ```text
//!   brain/fact/base.md        le cap, et ce qu'est ce projet
//!   brain/mind/state.md       où on en est aujourd'hui
//!   brain/mind/todo.md        ce qui attend une décision
//!   .github/copilot/settings.json  marketplace locale et paquet activé
//! ```
//!
//! En équipe (`--equipe A,B,C`), un jeu d'état PAR AGENT sous
//! `brain/mind/<nom>/`, un dossier d'agent par nom, et la fiche des rôles.
//!
//! **PUREMENT ADDITIF.** Rien n'est jamais écrasé : un fichier qui existe est
//! annoncé comme déjà là et laissé tel quel. Les réglages sont FUSIONNÉS clé à
//! clé — un projet qui a déjà ses permissions les garde.
//!
//! **À BLANC PAR DÉFAUT**, `--go` pour écrire. Le témoin de ce contrat est
//! qu'après un passage à blanc, aucun des fichiers annoncés n'existe.
//!
//! **CE QU'ELLE NE FAIT PAS, ET LE DIT.** Écrire le cap à la place de
//! quelqu'un, découper des instructions existantes, trier une mémoire ancienne :
//! ce sont des jugements, ils demandent d'avoir lu le projet. La commande les
//! NOMME en fin de rapport au lieu de les deviner — un script qui décide à la
//! place de l'agent décide sans avoir lu.

use std::path::{Path, PathBuf};

use crate::memoire::{self, Forme};

const V: &str = "\x1b[32m";
const J: &str = "\x1b[33m";
const B: &str = "\x1b[1m";
const D: &str = "\x1b[2m";
const X: &str = "\x1b[0m";

/// Le dépôt du marché, tel qu'un projet doit le déclarer. Une seule copie :
/// c'est l'adresse à laquelle Copilot va chercher le paquet, et deux
/// copies qui divergent enverraient deux projets sur deux versions.
#[cfg(test)]
use crate::copilot::PAQUET;

/// La section qui garde l'adresse d'un code qui vit hors du projet. Son titre
/// porte le chemin : le briefing sert les titres des faits à chaque session.
fn section_code(code: &Path) -> String {
    let jour = chrono::Local::now().format("%d/%m/%Y");
    format!("## Le code : `{c}`\n> **dit** · {jour} — chemin donné à l'adoption\n\n\
Le code de ce projet vit hors de ce dépôt, à cet emplacement, et y reste. Ce \
dépôt porte les rôles, `brain/` et `docs/` ; on n'écrit dans le dossier du code \
que sur demande de @user. En CLI, `copilot --add-dir \"{c}\"` donne accès au code \
à une session ouverte dans ce projet.\n\n", c = code.display())
}

fn base_md(nom: &str) -> String {
    format!("---\ncap: À REMPLIR — une phrase : où va ce projet, et pour qui\n---\n\n\
# {nom}\n\n## Nature\n\nCe que ce projet EST, en trois lignes. Pas son historique.\n\n\
## Où on va\n\nLe prochain jalon, et à quoi on saura qu'il est atteint.\n\n\
## Ce que ce projet n'est pas\n\nLes confusions qui coûtent cher. Une par ligne.\n")
}

fn state_md(jour: &str) -> String {
    format!("---\nmaj: {jour}\nsante: verte\njalon: À REMPLIR — ce vers quoi on va\n---\n\n\
# État\n\n## Phase\n\nOù en est ce projet AUJOURD'HUI. Ce fichier n'énumère que\n\
des faits actuels : si on le lit, c'est que le projet est comme ça.\n")
}

const TODO_MD: &str = "# À faire\n\n\
Une ligne par tâche. `@user` marque ce qui attend une décision humaine, et\n\
ces lignes-là partent en premier dans tout point d'avancement.\n\n\
- [ ] première tâche\n";

fn roles_md(agents: &[String]) -> String {
    let mut s = String::from("# Rôles\n\n\
Qui tient quoi — et SURTOUT les zones partagées. Un périmètre propre se lit\n\
dans les droits de chacun ; une zone partagée ne se lit nulle part, et c'est\n\
là que les collisions arrivent.\n\n");
    for a in agents {
        s.push_str(&format!("## {a}\n\nCe que cet agent tient, et ce qu'il ne touche pas.\n\n"));
    }
    s.push_str("## Zones partagées\n\nCe que plusieurs agents touchent, et qui prévient qui.\n");
    s
}

fn agents_md_agent(nom: &str, projet: &str) -> String {
    if nom.eq_ignore_ascii_case("QA") { return crate::equipe::role_qa().into(); }
    format!("# {nom} — {projet}\n\n\
Tu es **{nom}** sur ce projet. Ce fichier ne porte QUE ton rôle : ce qui vaut\n\
pour tout le monde vit dans `AGENTS.md` à la racine, qui est hérité.\n\n\
Contrôle de sortie : aucune phrase d'ici ne resterait vraie pour un autre agent.\n\n\
## Ce que tu tiens\n\nÀ REMPLIR.\n\n## Ce que tu ne touches pas\n\nÀ REMPLIR.\n")
}

// ── le rapport ───────────────────────────────────────────────────────────

struct Rapport {
    a_faire: Vec<(PathBuf, String)>,
    deja: Vec<PathBuf>,
    main: Vec<String>,
}

impl Rapport {
    fn neuf() -> Self {
        Rapport { a_faire: vec![], deja: vec![], main: vec![] }
    }
    /// AJOUTE UN FICHIER — ou constate qu'il est déjà là. C'est le seul endroit
    /// qui décide d'écrire, et il ne peut pas écraser : le test d'existence et
    /// la décision sont la même ligne.
    fn pose(&mut self, ou: PathBuf, quoi: &str, _contenu: &str) {
        if ou.exists() { self.deja.push(ou); } else { self.a_faire.push((ou, quoi.into())); }
    }
}

fn court(p: &Path, racine: &Path) -> String {
    p.strip_prefix(racine).unwrap_or(p).display().to_string()
}

// ── les réglages : fusionner, jamais remplacer ───────────────────────────

/// LES DEUX CLÉS QUI BRANCHENT LE PAQUET, posées dans un fichier qui existe
/// peut-être déjà et qui porte peut-être déjà des permissions.
///
/// Rend `(json à écrire, ce qui manquait)`. Si rien ne manque, la seconde
/// valeur est vide et on n'écrit pas : réécrire un fichier pour n'y rien
/// changer, c'est brouiller un `git status` pour rien.
fn reglages(f: &Path) -> Result<(String, Vec<&'static str>), String> {
    let mut v: serde_json::Value = if f.exists() {
        serde_json::from_str(&std::fs::read_to_string(f).map_err(|e| e.to_string())?)
            .map_err(|e| format!("{} : {e}", f.display()))?
    } else { serde_json::json!({}) };
    let avant = v.clone();
    crate::copilot::reglages(&mut v, &crate::copilot::paquet()?)?;
    let manque = if v == avant { vec![] } else { vec!["marketplace locale et paquet activé"] };
    Ok((serde_json::to_string_pretty(&v).map_err(|e| e.to_string())? + "\n", manque))
}

const METHODE: &str = include_str!("../../skills/agentic-init/templates/foundation-AGENTS.md");
const MARQUEUR_METHODE: &str = "<!-- harnais:method:start -->";

/// Le nom de `@user`, tel que l'initialisation l'a écrit dans la méthode de
/// l'atelier : le premier `AGENTS.md` des dossiers parents qui le porte.
fn nom_de_user(projet: &Path) -> Option<String> {
    let re = regex::Regex::new(r"`@user` désigne (.+?), l'humain qui commande l'atelier").ok()?;
    projet.ancestors().skip(1).find_map(|d| {
        let t = std::fs::read_to_string(d.join("AGENTS.md")).ok()?;
        re.captures(&t).map(|c| c[1].trim().to_string()).filter(|n| !n.is_empty() && n != "[UTILISATEUR]")
    })
}

/// La méthode à copier dans le projet, `@user` nommé quand l'atelier le connaît.
fn methode(projet: &Path) -> String {
    match nom_de_user(projet) {
        Some(n) => METHODE.replace("[UTILISATEUR]", &n),
        None => METHODE.replace("[UTILISATEUR], ", ""),
    }
}

fn instructions(f: &Path, projet: &Path) -> Result<Option<String>, String> {
    let avant = match std::fs::read_to_string(f) {
        Ok(t) => t,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => String::new(),
        Err(e) => return Err(format!("{} : {e}", f.display())),
    };
    if avant.contains(MARQUEUR_METHODE) { return Ok(None); }
    let separation = if avant.is_empty() { "" } else { "\n\n" };
    Ok(Some(format!("{avant}{separation}{MARQUEUR_METHODE}\n{}\n<!-- harnais:method:end -->\n",
                    methode(projet))))
}

// ── la commande ──────────────────────────────────────────────────────────

pub fn main(args: &[String]) -> i32 {
    let go = args.iter().any(|a| a == "--go" || a == "--apply");
    let demande_compact = args.iter().any(|a| a == "--compact");
    let equipe: Vec<String> = args.iter()
        .position(|a| a == "--equipe")
        .and_then(|i| args.get(i + 1))
        .map(|s| s.split(',').map(|x| x.trim().to_string())
                  .filter(|x| !x.is_empty()).collect())
        .unwrap_or_default();
    // LE CODE PEUT VIVRE AILLEURS. Un projet agentique se tient dans l'atelier ;
    // son code existant reste dans son dépôt — souvent un sous-dossier d'un dépôt
    // plus large — et n'y reçoit aucun fichier. `--code` en garde l'adresse.
    let code = args.iter().position(|a| a == "--code").and_then(|i| args.get(i + 1))
        .map(|s| std::path::absolute(s).unwrap_or_else(|_| PathBuf::from(s)));
    if let Some(c) = &code {
        if !c.is_dir() {
            eprintln!("adopte : --code {} : ce dossier n'existe pas.", c.display());
            return 1;
        }
    }
    let ou = args.iter().enumerate()
        .find(|(i, a)| !a.starts_with("--") && (*i == 0 || !["--equipe", "--code"].contains(&args[*i - 1].as_str())))
        .map(|(_, a)| PathBuf::from(a))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());

    let r = memoire::resous(&ou);
    let racine = r.racine.clone().or_else(|| ou.canonicalize().ok()).unwrap_or(ou.clone());
    let nom = racine.file_name().map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_else(|| "ce projet".into());

    println!("{B}harnais adopte{X} — poser le harnais sur ce projet\n");
    println!("  projet : {}", racine.display());
    // DEUX SITUATIONS SANS RAPPORT : pas de dépôt du tout (`HorsDepot`), et
    // dépôt sans mémoire (`SansMemoire`). Le résolveur les distingue lui-même.
    // C'est la PREMIÈRE ligne que lit qui découvre l'outil.
    let etat = match r.forme {
        Forme::SansMemoire =>
            "un dépôt git, et aucune mémoire — c'est le cas normal avant adoption",
        Forme::HorsDepot => "aucun dépôt git au-dessus — les gardes de commit ne s'appliqueront pas",
        Forme::EnPlace => "déjà une mémoire, dans la forme d'avant (`.fact/` et `.mind/`)",
        Forme::Deportee => "déjà une mémoire déportée (`memoire/`)",
        Forme::Brain => "déjà une mémoire dans la forme actuelle (`brain/`)",
        Forme::Ambigue => "À CHEVAL sur deux formes — une migration s'est arrêtée en route",
    };
    println!("  état   : {D}{etat}{X}\n");

    // UNE MIGRATION INTERROMPUE NE SE COMPLÈTE PAS À L'AVEUGLE. Poser des
    // fichiers sur un arbre à cheval, c'est choisir en silence lequel des deux
    // fera foi — exactement ce que le résolveur refuse de faire.
    if r.forme == Forme::Ambigue {
        println!("  {J}Je m'arrête ici.{X} Ce projet porte les DEUX arbres de mémoire.");
        println!("  Terminer la migration d'abord : {B}harnais brain-migre{X}");
        return 2;
    }
    if matches!(r.forme, Forme::EnPlace | Forme::Deportee) {
        eprintln!("adopte : mémoire ancienne préservée ; lancer brain-migre avant de compléter brain/.");
        return 2;
    }
    if equipe.iter().any(|a| a == "." || a == ".." || a.contains(['/', '\\', ':'])) {
        eprintln!("adopte : chaque nom d'agent doit être un nom de dossier simple.");
        return 1;
    }

    let jour = chrono::Local::now().date_naive().format("%Y-%m-%d").to_string();
    let mut rap = Rapport::neuf();
    let mut ecrits: Vec<(PathBuf, String)> = vec![];

    let fact = racine.join("brain/fact");
    let mind = racine.join("brain/mind");
    let compact = demande_compact || equipe.iter().any(|n| crate::agent::compact(&racine, n));

    let c = base_md(&nom);
    rap.pose(fact.join("base.md"), "le cap du projet, et ce qu'il est", &c);
    ecrits.push((fact.join("base.md"), c));
    for (f, titre, description) in [
        ("architecture.md", "Architecture", "composants, flux et frontières du projet"),
        ("stack.md", "Stack", "outils, versions et commandes de ce projet"),
        ("rules.md", "Règles", "invariants et limites propres au projet"),
    ] {
        let mut c = format!("# {titre}\n\n");
        if f == "architecture.md" {
            if let Some(code) = &code { c.push_str(&section_code(code)); }
        }
        c.push_str(&format!("## À REMPLIR\n\nDécrire les {description}, après lecture du projet.\n"));
        rap.pose(fact.join(f), description, &c);
        ecrits.push((fact.join(f), c));
    }
    if let Some(c) = &code {
        if fact.join("architecture.md").exists() {
            rap.main.push(format!("brain/fact/architecture.md existe : y ajouter à la main la section \
« Le code : `{}` »", c.display()));
        }
    }

    if equipe.is_empty() {
        let c = state_md(&jour);
        rap.pose(mind.join("state.md"), "où on en est aujourd'hui", &c);
        ecrits.push((mind.join("state.md"), c));
        rap.pose(mind.join("todo.md"), "ce qui attend une décision", TODO_MD);
        ecrits.push((mind.join("todo.md"), TODO_MD.into()));
    } else {
        let c = roles_md(&equipe);
        rap.pose(fact.join("roles.md"), "qui tient quoi, et les zones partagées", &c);
        ecrits.push((fact.join("roles.md"), c));
        for a in &equipe {
            let c = state_md(&jour);
            rap.pose(mind.join(a).join("state.md"), &format!("l'état de {a}"), &c);
            ecrits.push((mind.join(a).join("state.md"), c));
            rap.pose(mind.join(a).join("todo.md"), &format!("ce qui attend {a}"), TODO_MD);
            ecrits.push((mind.join(a).join("todo.md"), TODO_MD.into()));
            if compact {
                let profil = crate::agent::profil(&racine, a);
                let slug = crate::agent::nom_de_profil(a);
                if slug.is_empty() || equipe.iter().filter(|n| crate::agent::nom_de_profil(n) == slug).count() != 1 {
                    eprintln!("adopte : nom de profil vide ou en collision : {a}"); return 1;
                }
                let c = format!("---\nname: {slug}\ndescription: Agent {a} — rôle propre au projet\n---\n\
Lis brain/mind/{a}/state.md et brain/mind/{a}/todo.md à la reprise.\n\n\
<!-- harnais:role:start -->\n{}<!-- harnais:role:end -->\n", agents_md_agent(a, &nom));
                rap.pose(profil.clone(), &format!("profil et rôle uniques de {a}"), &c);
                ecrits.push((profil, c));
                let garde = crate::agent::perimetre_compact(&racine, a);
                let mut denies = vec![".github".to_string(), "brain/poids.json".into()];
                if !a.eq_ignore_ascii_case("QA") { denies.push("brain/fact".into()); }
                for n in equipe.iter().filter(|n| *n != a) {
                    denies.push(format!("brain/mind/{n}"));
                    denies.push(crate::agent::banc(n));
                }
                let allow = crate::equipe::allow_par_defaut(a, "brain/fact",
                    &format!("brain/mind/{a}"), &crate::agent::banc(a));
                let c = serde_json::json!({"allow": allow, "deny": denies}).to_string() + "\n";
                rap.pose(garde.clone(), &format!("périmètre centralisé de {a}"), &c);
                ecrits.push((garde, c));
                continue;
            }
            let d = racine.join("agents").join(a);
            let c = agents_md_agent(a, &nom);
            if d.join("CLAUDE.md").exists() {
                rap.main.push(format!("{a} : CLAUDE.md existe ; ne pas créer AGENTS.md en doublon"));
            } else {
                rap.pose(d.join("AGENTS.md"), &format!("le rôle de {a}, et lui seul"), &c);
                ecrits.push((d.join("AGENTS.md"), c));
            }
            let garde = d.join(".github/copilot/perimetre.json");
            if garde.exists() {
                if let Err(e) = crate::copilot::perimetre(&d) {
                    eprintln!("adopte : {e}"); return 1;
                }
                rap.deja.push(garde);
            } else {
                let denies: Vec<PathBuf> = equipe.iter().filter(|n| *n != a)
                    .map(|n| racine.join("agents").join(n)).collect();
                rap.a_faire.push((garde.clone(), format!("protéger le périmètre de {a}")));
                let mut v = serde_json::json!({"deny": denies});
                if a.eq_ignore_ascii_case("QA") {
                    v["allow"] = serde_json::json!(crate::equipe::allow_par_defaut(a, "brain/fact",
                        &format!("brain/mind/{a}"), &format!("agents/{a}/livrables")));
                }
                ecrits.push((garde, v.to_string() + "\n"));
            }
            crate::copilot::avertit_ancien(&d);
            crate::copilot::avertit_settings_agent(&d);
        }
    }

    crate::copilot::avertit_ancien(&racine);
    let inf = racine.join(".github/copilot-instructions.md");
    match instructions(&inf, &racine) {
        Ok(Some(texte)) => {
            rap.a_faire.push((inf.clone(), "ajouter la méthode locale, en conservant les instructions existantes".into()));
            ecrits.push((inf, texte));
        }
        Ok(None) => rap.deja.push(inf),
        Err(e) => { eprintln!("adopte : {e}"); return 1; }
    }
    let sf = crate::copilot::settings(&racine);
    let (json, manque) = match reglages(&sf) {
        Ok(v) => v, Err(e) => { eprintln!("adopte : {e}"); return 1; }
    };
    if !manque.is_empty() {
        rap.a_faire.push((sf.clone(), format!("brancher le paquet — {}", manque.join(", "))));
        ecrits.push((sf, json));
    } else { rap.deja.push(sf); }

    // ── le rapport ───────────────────────────────────────────────────────
    if rap.a_faire.is_empty() {
        println!("  {V}Ce projet est déjà au harnais.{X} Rien à poser.");
    } else {
        println!("  {B}À POSER ({}){X}", rap.a_faire.len());
        for (p, quoi) in &rap.a_faire {
            println!("    {:<34} {D}{quoi}{X}", court(p, &racine));
        }
    }
    if !rap.deja.is_empty() {
        println!("\n  {B}DÉJÀ LÀ ({}){X} {D}— jamais écrasé{X}", rap.deja.len());
        for p in &rap.deja { println!("    {}", court(p, &racine)); }
    }

    rap.main.push("remplir `cap:` — une phrase : où va ce projet, et pour qui".into());
    if !equipe.is_empty() {
        rap.main.push("découper AGENTS.md : le commun reste à la racine, le rôle \
                       descend chez chaque agent".into());
        rap.main.push("dire qui touche quoi dans les droits de chacun — les périmètres \
                       ne se devinent pas".into());
    }
    println!("\n  {B}ENSUITE, À TA MAIN{X}");
    for m in &rap.main { println!("    · {m}"); }

    if !go {
        println!("\n  {J}Rien n'a été écrit.{X} Relance avec {B}--go{X} pour appliquer.");
        return 0;
    }

    let mut poses = 0;
    for (p, contenu) in ecrits {
        let instructions = p.ends_with("copilot-instructions.md");
        if p.exists() && !p.ends_with("settings.json") && !instructions { continue; }
        if let Some(d) = p.parent() {
            if let Err(e) = std::fs::create_dir_all(d) {
                eprintln!("adopte : {} : {e}", d.display());
                return 1;
            }
        }
        use std::io::Write;
        let resultat = if instructions && p.exists() {
            std::fs::read_to_string(&p).and_then(|avant| {
                let ajout = contenu.strip_prefix(&avant).ok_or_else(|| std::io::Error::new(
                    std::io::ErrorKind::Other, "instructions modifiées depuis la prévisualisation"))?;
                std::fs::OpenOptions::new().append(true).open(&p)
                    .and_then(|mut f| f.write_all(ajout.as_bytes()))
            })
        } else if p.ends_with("settings.json") {
            std::fs::write(&p, contenu)
        } else {
            std::fs::OpenOptions::new().write(true).create_new(true).open(&p)
                .and_then(|mut f| f.write_all(contenu.as_bytes()))
        };
        match resultat {
            Ok(()) => poses += 1,
            Err(e) => { println!("  {J}échec{X} {} : {e}", court(&p, &racine)); return 1; }
        }
    }
    println!("\n  {V}{poses} fichier(s) posé(s).{X}");
    println!("  Ouvre une session dans ce dossier : le briefing d'entrée doit s'afficher.");
    0
}

#[cfg(test)]
mod essais {
    use super::*;

    fn bac(nom: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("adopte-{nom}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        let _ = std::process::Command::new("git").args(["init", "-q", "-b", "main"])
            .current_dir(&d).output();
        d
    }

    #[test]
    fn adoption_compacte_additive_sans_dossier_agents() {
        let d = bac("compact");
        let args = vec![d.display().to_string(), "--equipe".into(), "OPS,PO,QA".into(), "--compact".into()];
        assert_eq!(main(&args), 0);
        assert!(!d.join("brain").exists());
        let mut args = args;
        args.push("--go".into());
        assert_eq!(main(&args), 0);
        assert!(!d.join("agents").exists());
        for n in ["OPS", "PO", "QA"] {
            let esprit = d.join("brain/mind").join(n);
            assert!(esprit.join("state.md").is_file());
            assert!(esprit.join("todo.md").is_file());
            assert!(crate::agent::profil(&d, n).is_file());
            assert!(crate::agent::perimetre_compact(&d, n).is_file());
        }
        let qa = d.join("brain/mind/QA");
        assert!(!crate::copilot::lis_deny(&qa).unwrap().contains(&PathBuf::from(".")));
        assert_eq!(crate::copilot::lis_allow(&qa).unwrap().unwrap().len(), 7);
        std::fs::write(crate::agent::profil(&d, "OPS"), "personnalisé").unwrap();
        assert_eq!(main(&args), 0);
        assert_eq!(std::fs::read_to_string(crate::agent::profil(&d, "OPS")).unwrap(), "personnalisé");
        std::fs::remove_dir_all(&d).unwrap();
    }

    /// UN CODE QUI VIT AILLEURS : son adresse entre dans les faits, rien n'entre
    /// dans son dossier, et un chemin inexistant est refusé.
    #[test]
    fn le_code_externe_est_reference_sans_y_ecrire() {
        let d = bac("code-externe");
        let code = std::env::temp_dir().join(format!("adopte-code-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&code);
        std::fs::create_dir_all(code.join("src")).unwrap();
        std::fs::write(code.join("src/main.py"), "print(1)\n").unwrap();
        assert_eq!(main(&[d.display().to_string(), "--code".into(), code.display().to_string(), "--go".into()]), 0);
        let archi = std::fs::read_to_string(d.join("brain/fact/architecture.md")).unwrap();
        assert!(archi.contains(&format!("## Le code : `{}`", code.display())), "{archi}");
        let e = crate::briefing::etablissements(&archi);
        assert!(e.iter().any(|x| x.titre.starts_with("Le code") && x.niveau == "dit"), "ligne d'établissement lisible");
        let dans_le_code: Vec<_> = walk(&code);
        assert_eq!(dans_le_code, vec![code.join("src").join("main.py")], "rien n'est écrit dans le code");
        // TÉMOIN : un dossier de code inexistant est refusé, rien n'est posé.
        let d2 = bac("code-absent");
        assert_eq!(main(&[d2.display().to_string(), "--code".into(), code.join("nulle-part").display().to_string(), "--go".into()]), 1);
        assert!(!d2.join("brain").exists());
        for x in [&d, &d2, &code] { let _ = std::fs::remove_dir_all(x); }
    }

    fn walk(d: &Path) -> Vec<PathBuf> {
        let mut out = vec![];
        for e in std::fs::read_dir(d).unwrap().flatten() {
            let p = e.path();
            if p.is_dir() { out.extend(walk(&p)); } else { out.push(p); }
        }
        out.sort();
        out
    }

    /// LA MÉTHODE COPIÉE NOMME `@user` QUAND L'ATELIER LE CONNAÎT, et ne laisse
    /// jamais le gabarit brut sinon.
    #[test]
    fn la_methode_du_projet_nomme_user_d_apres_l_atelier() {
        let atelier = std::env::temp_dir().join(format!("adopte-atelier-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&atelier);
        let projet = atelier.join("Mon projet");
        std::fs::create_dir_all(&projet).unwrap();
        std::fs::write(atelier.join("AGENTS.md"),
            METHODE.replace("[UTILISATEUR]", "Alice Martin")).unwrap();
        let m = methode(&projet);
        assert!(m.contains("`@user` désigne Alice Martin, l'humain qui commande l'atelier"), "{m}");
        assert!(!m.contains("[UTILISATEUR]"));
        // TÉMOIN : sans atelier qui le nomme, la phrase reste générale.
        std::fs::remove_file(atelier.join("AGENTS.md")).unwrap();
        let m = methode(&projet);
        assert!(m.contains("`@user` désigne l'humain qui commande l'atelier"), "{m}");
        assert!(!m.contains("[UTILISATEUR]") && !m.contains("Alice"));
        let _ = std::fs::remove_dir_all(&atelier);
    }

    /// LE BLANC N'ÉCRIT RIEN — et c'est le contrat, pas un détail. Un passage à
    /// blanc qui pose un fichier rend le geste irréversible avant d'avoir été
    /// décidé.
    #[test]
    fn le_blanc_n_ecrit_rien() {
        let d = bac("blanc");
        assert_eq!(main(&[d.display().to_string()]), 0);
        assert!(!d.join("brain/fact/base.md").exists(), "le blanc a écrit");
        assert!(!crate::copilot::settings(&d).exists(), "le blanc a écrit les réglages");
    }

    /// ET `--go` ÉCRIT VRAIMENT. Le témoin négatif du précédent : sans lui,
    /// une commande qui n'écrit JAMAIS passerait le premier essai.
    #[test]
    fn go_pose_le_cerveau_et_branche_le_paquet() {
        let d = bac("go");
        assert_eq!(main(&[d.display().to_string(), "--go".into()]), 0);
        for f in ["brain/fact/base.md", "brain/fact/architecture.md", "brain/fact/stack.md",
                  "brain/fact/rules.md", "brain/mind/state.md", "brain/mind/todo.md"] {
            assert!(d.join(f).exists(), "{f} manque");
        }
        let t = std::fs::read_to_string(crate::copilot::settings(&d)).unwrap();
        assert!(t.contains(PAQUET), "le paquet n'est pas activé");
        assert!(t.contains("\"directory\""), "la marketplace locale manque");
        let j: serde_json::Value = serde_json::from_str(&t).unwrap();
        assert_eq!(j["extraKnownMarketplaces"]["atelier-copilot"]["source"]["path"],
                   crate::copilot::paquet().unwrap().to_string_lossy().to_string());
        assert!(!d.join(".claude/settings.json").exists());
    }

    /// DEUX PASSAGES RENDENT LE MÊME ARBRE. Un outil d'installation qu'on
    /// n'ose pas relancer n'est pas un outil, c'est un pari.
    #[test]
    fn relancer_ne_change_rien() {
        let d = bac("idem");
        main(&[d.display().to_string(), "--go".into()]);
        std::fs::write(d.join("brain/fact/base.md"), "MON TEXTE À MOI\n").unwrap();
        main(&[d.display().to_string(), "--go".into()]);
        assert_eq!(std::fs::read_to_string(d.join("brain/fact/base.md")).unwrap(),
                   "MON TEXTE À MOI\n", "le second passage a écrasé un fichier du projet");
    }

    #[test]
    fn complete_une_memoire_partielle_sans_ecraser() {
        let d = bac("partiel");
        std::fs::create_dir_all(d.join("brain/fact")).unwrap();
        std::fs::create_dir_all(d.join("brain/mind")).unwrap();
        for f in ["brain/fact/base.md", "brain/mind/state.md", "brain/mind/todo.md"] {
            std::fs::write(d.join(f), "personnel\n").unwrap();
        }
        assert_eq!(main(&[d.display().to_string()]), 0);
        assert!(!d.join("brain/fact/stack.md").exists());
        assert_eq!(main(&[d.display().to_string(), "--go".into()]), 0);
        for f in crate::socle::FAITS_MONO { assert!(d.join("brain/fact").join(f).is_file()); }
        assert_eq!(std::fs::read_to_string(d.join("brain/mind/state.md")).unwrap(), "personnel\n");
        assert_eq!(main(&[d.display().to_string(), "--go".into()]), 0);
    }

    #[test]
    fn ajoute_la_methode_sans_remplacer_les_instructions_du_projet() {
        let d = bac("instructions");
        let f = d.join(".github/copilot-instructions.md");
        std::fs::create_dir_all(f.parent().unwrap()).unwrap();
        std::fs::write(&f, "# Instructions personnelles\r\nGarder ce texte.\r\n").unwrap();
        assert_eq!(main(&[d.display().to_string()]), 0);
        assert!(!std::fs::read_to_string(&f).unwrap().contains(MARQUEUR_METHODE));
        assert_eq!(main(&[d.display().to_string(), "--go".into()]), 0);
        let texte = std::fs::read_to_string(&f).unwrap();
        assert!(texte.starts_with("# Instructions personnelles\r\nGarder ce texte.\r\n"));
        assert!(texte.contains("# Atelier agentique"));
        assert_eq!(main(&[d.display().to_string(), "--go".into()]), 0);
        assert_eq!(std::fs::read_to_string(&f).unwrap(), texte);
    }

    #[test]
    fn une_erreur_de_pose_ne_reussit_pas() {
        let d = bac("echec");
        std::fs::write(d.join("brain"), "obstacle").unwrap();
        assert_eq!(main(&[d.display().to_string(), "--go".into()]), 1);
        assert!(!crate::copilot::settings(&d).exists());
    }

    /// LES RÉGLAGES SE FUSIONNENT. Un projet qui a déjà ses permissions doit les
    /// garder — les écraser couperait ses droits sans le dire.
    #[test]
    fn les_reglages_existants_survivent() {
        let d = bac("fusion");
        std::fs::create_dir_all(d.join(".github/copilot")).unwrap();
        std::fs::write(crate::copilot::settings(&d),
                       r#"{"permissions":{"deny":["Bash(rm*)"]}}"#).unwrap();
        main(&[d.display().to_string(), "--go".into()]);
        let t = std::fs::read_to_string(crate::copilot::settings(&d)).unwrap();
        assert!(t.contains("Bash(rm*)"), "les permissions du projet ont été perdues");
        assert!(t.contains(PAQUET), "le paquet n'a pas été ajouté");
    }

    #[test]
    fn le_chemin_contenant_un_nom_d_agent_reste_le_projet_cible() {
        let d = bac("Agent-A");
        assert_eq!(main(&[d.display().to_string(), "--equipe".into(), "A,B".into(), "--go".into()]), 0);
        assert!(crate::copilot::settings(&d).is_file());
        assert!(d.join("agents/A/.github/copilot/perimetre.json").is_file());
        assert!(!crate::copilot::settings(&d.join("agents/A")).exists());
    }

    /// EN ÉQUIPE, CHACUN A SON JEU D'ÉTAT — et un jeu partagé serait la panne
    /// que le multi-agents existe pour éviter.
    #[test]
    fn en_equipe_chacun_a_le_sien() {
        let d = bac("equipe");
        main(&[d.display().to_string(), "--equipe".into(), "PO,QA".into(), "--go".into()]);
        for a in ["PO", "QA"] {
            assert!(d.join("brain/mind").join(a).join("state.md").exists(), "{a} sans état");
            assert!(d.join("agents").join(a).join("AGENTS.md").exists(), "{a} sans rôle");
            assert_eq!(crate::copilot::perimetre(&d.join("agents").join(a)).unwrap().len(), 1);
            assert!(!crate::copilot::settings(&d.join("agents").join(a)).exists());
        }
        assert!(d.join("brain/fact/roles.md").exists(), "la fiche des rôles manque");
        assert!(crate::copilot::settings(&d).exists(), "réglage unique à la racine");
        assert!(!d.join("brain/mind/state.md").exists(),
                "un état de projet MONO a été posé en plus des états d'agents");
    }
}
