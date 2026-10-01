//! `harnais brain-migre` — DÉPLACER LA MÉMOIRE VERS `brain/`, ET POUVOIR REVENIR.
//!
//! POURQUOI UNE SOUS-COMMANDE ET PAS UN SCRIPT. La règle qui place ces dossiers
//! vit dans `memoire.rs`. Un script séparé en serait une seconde copie, et la
//! maison a déjà payé ce prix : `carnet::amorce()` existe précisément pour que
//! la compétence qui monte une équipe n'ait pas à recopier `espace()`. Le
//! précédent exact est `equipe-amorce` — une sous-commande qui écrit, appelée
//! une fois. Et une compétence qui ne passerait pas par le résolveur
//! reconduirait le défaut. Une sous-commande, elle, EST le résolveur.
//!
//! CE QU'IL FAIT, ET RIEN D'AUTRE :
//!
//! ```text
//!   .fact/            -> brain/fact/
//!   .mind/            -> brain/mind/                (mono)
//!   memoire/.fact/    -> brain/fact/                (déportée)
//!   memoire/agents/<nom>/.mind/ -> brain/mind/<nom>/
//!   memoire/equipe/   -> brain/workspace/
//! ```
//!
//! `docs/` et `.logs/` NE BOUGENT PAS : ils sont datés, ils racontent le code,
//! et les en arracher couperait chaque trace du commit qui l'explique.
//!
//! **À BLANC PAR DÉFAUT.** Sans `--apply`, il annonce et n'écrit rien — et le
//! témoin de ce contrat est qu'après un passage à blanc, l'arbre cible n'existe
//! toujours pas. « Le blanc a écrit » est un contrôle raté, pas un détail.
//!
//! **`git mv` D'ABORD, ET IL DIT LEQUEL IL A PRIS.** Un script de migration qui
//! retombe sur un déplacement nu sans jamais dire lequel des deux chemins il a
//! emprunté est un piège. Un `git mv` qui échoue pour une
//! bonne raison — fichier non suivi — et un `git mv` qui échoue parce que
//! l'index est sale se lisent pareil, et le second perd l'historique en
//! silence. Ici chaque ligne porte son verdict.

use std::path::{Path, PathBuf};
use std::process::Command;

use crate::memoire::{self, Forme};

const V: &str = "\x1b[32m";
const R: &str = "\x1b[31m";
const J: &str = "\x1b[33m";
const D: &str = "\x1b[2m";
const X: &str = "\x1b[0m";

/// Les noms que `fact/` a le droit de porter. Le cinquième n'existe qu'en
/// équipe. **C'est ici que le plafond mord pour la première fois** : il vit
/// en prose et n'était vérifié nulle part — aucun `read_dir` du programme ne
/// portait sur ces dossiers.
// Voir `socle::FAITS_MONO`. La migration n'exige PAS `roles.md` : il n'existe
// qu'à plusieurs agents. Ce découpage est voulu — ce qui ne l'était pas, c'est
// qu'il vive dans une troisième copie de la liste.
use crate::socle::FAITS_MONO as NOMS_FACT;
use crate::socle::FAITS_EQUIPE as NOM_FACT_EQUIPE;

struct Geste {
    de: PathBuf,
    vers: PathBuf,
    /// Rempli à l'exécution : `git mv` ou `rename`. Jamais supposé.
    comment: String,
}

fn git(ou: &Path, args: &[&str]) -> (i32, String) {
    match Command::new("git").args(args).current_dir(ou).output() {
        Ok(o) => (o.status.code().unwrap_or(-1),
                  String::from_utf8_lossy(&o.stdout).trim().to_string()),
        Err(_) => (-1, String::new()),
    }
}

fn propre(depot: &Path) -> bool {
    let (rc, out) = git(depot, &["status", "--porcelain"]);
    rc == 0 && out.is_empty()
}

/// Le dépôt qui porte réellement ce dossier — le sien s'il en a un, sinon celui
/// du dessus. C'est lui qu'il faut interroger pour un `git mv`.
fn depot_porteur(p: &Path, racine: &Path) -> PathBuf {
    let mut q = p.to_path_buf();
    loop {
        if q.join(".git").exists() { return q; }
        match q.parent() { Some(x) if x.starts_with(racine) || x == racine
                                => q = x.to_path_buf(), _ => return racine.to_path_buf() }
    }
}

/// Ce qui doit bouger, et vers où. Rien n'est écrit ici.
fn gestes(r: &memoire::Resolution, racine: &Path) -> Result<Vec<Geste>, String> {
    let brain = racine.join("brain");
    let mut v = Vec::new();
    match r.forme {
        Forme::EnPlace => {
            let p = r.projet.clone().ok_or("aucun dossier de projet")?;
            v.push(Geste { de: p.join(".fact"), vers: brain.join("fact"),
                           comment: String::new() });
            // Le `.mind/` de CHAQUE agent, pas seulement celui qui parle : la
            // migration est un geste de PROJET. Le lot de l'appelant ne doit
            // pas décider de ce qui bouge.
            let ag = p.join("agents");
            let mut trouve = false;
            if ag.is_dir() {
                let mut d: Vec<PathBuf> = std::fs::read_dir(&ag).map(|it| it
                    .filter_map(|e| e.ok().map(|e| e.path())).collect()).unwrap_or_default();
                d.sort();
                for a in d {
                    if a.join(".mind").is_dir() {
                        let n = a.file_name().unwrap_or_default().to_string_lossy().to_string();
                        v.push(Geste { de: a.join(".mind"), vers: brain.join("mind").join(n),
                                       comment: String::new() });
                        trouve = true;
                    }
                }
            }
            if !trouve && p.join(".mind").is_dir() {
                v.push(Geste { de: p.join(".mind"), vers: brain.join("mind"),
                               comment: String::new() });
            }
        }
        Forme::Deportee => {
            let b = memoire::base(racine).ok_or("mémoire déportée introuvable")?;
            v.push(Geste { de: b.join(".fact"), vers: brain.join("fact"),
                           comment: String::new() });
            let ag = b.join("agents");
            if ag.is_dir() {
                let mut d: Vec<PathBuf> = std::fs::read_dir(&ag).map(|it| it
                    .filter_map(|e| e.ok().map(|e| e.path())).collect()).unwrap_or_default();
                d.sort();
                for a in d {
                    if a.join(".mind").is_dir() {
                        let n = a.file_name().unwrap_or_default().to_string_lossy().to_string();
                        v.push(Geste { de: a.join(".mind"), vers: brain.join("mind").join(n),
                                       comment: String::new() });
                    }
                }
            } else if b.join(".mind").is_dir() {
                v.push(Geste { de: b.join(".mind"), vers: brain.join("mind"),
                               comment: String::new() });
            }
            if b.join("equipe").is_dir() {
                v.push(Geste { de: b.join("equipe"), vers: brain.join("workspace"),
                               comment: String::new() });
            }
        }
        Forme::Brain => return Err("déjà en brain/".into()),
        Forme::Ambigue => return Err(
            "cet arbre porte l'ANCIEN et le NEUF à la fois — un chantier \
             interrompu. Trancher à la main avant de rejouer.".into()),
        Forme::HorsDepot | Forme::SansMemoire => return Err("ce dossier n'a pas de mémoire à déplacer".into()),
    }
    Ok(v)
}

/// LES ASSERTIONS D'AVANT. Elles refusent, et ne touchent à rien.
fn avant(r: &memoire::Resolution, racine: &Path, v: &[Geste]) -> Vec<String> {
    let mut e = Vec::new();
    let brain = racine.join("brain");

    // ① L'arbre cible ne doit pas exister — c'est l'état « à moitié migré ».
    if brain.exists() {
        e.push(format!("`{}` existe déjà : soit la migration est faite, soit \
                        elle a été interrompue. Rien ne sera écrit par-dessus.",
                       brain.display()));
    }

    // ② LE PLAFOND, ET C'EST ICI QU'IL MORD POUR LA PREMIÈRE FOIS.
    if let Some(f) = &r.fact {
        if f.is_dir() {
            let equipe = r.workspace.is_some()
                || r.projet.as_ref().map(|p| p.join("agents").is_dir()).unwrap_or(false);
            let mut attendus: Vec<&str> = NOMS_FACT.to_vec();
            if equipe { attendus.push(NOM_FACT_EQUIPE); }
            let vus: Vec<String> = std::fs::read_dir(f).map(|it| it
                .filter_map(|x| x.ok())
                .map(|x| x.file_name().to_string_lossy().to_string())
                .filter(|n| n.ends_with(".md")).collect()).unwrap_or_default();
            for n in &vus {
                if !attendus.contains(&n.as_str()) {
                    e.push(format!("`{}` porte `{}`, qui n'est pas un des {} noms \
                                    attendus. Un fichier de trop dans les faits \
                                    n'a jamais été vérifié nulle part : c'est ici \
                                    qu'on s'en aperçoit, AVANT de le déplacer.",
                                   f.display(), n, attendus.len()));
                }
            }
            for n in &attendus {
                if !vus.iter().any(|x| x == n) {
                    e.push(format!("`{}` manque dans `{}`", n, f.display()));
                }
            }
        }
    }

    // ③ RIEN EN ATTENTE **SUR CE QUI BOUGE**. Migrer par-dessus du travail non
    // enregistré rend le retour impossible — mais la question ne porte que sur
    // les dossiers déplacés.
    //
    // EXIGER UN ARBRE ENTIÈREMENT PROPRE refuserait tout projet vivant : le
    // hook de journal réécrit `.logs/<jour>.md` à chaque tour, donc un projet
    // vivant n'est JAMAIS propre. Exiger la propreté de tout l'arbre
    // reviendrait à exiger que le harnais soit à l'arrêt — une condition
    // qu'aucun projet en service ne peut tenir, et que le bac à sable ne peut
    // pas révéler.
    let mut depots = vec![racine.to_path_buf()];
    if let Some(p) = &r.projet {
        let d = depot_porteur(p, racine);
        if d != racine { depots.push(d); }
    }
    for g in v {
        let d = depot_porteur(&g.de, racine);
        let rel = g.de.strip_prefix(&d).unwrap_or(&g.de).to_string_lossy().to_string();
        let (rc, out) = git(&d, &["status", "--porcelain", "--", &rel]);
        if rc == 0 && !out.is_empty() {
            e.push(format!("`{}` a du travail non enregistré :\n        {}\n                                  Enregistre-le d'abord — sans ça, revenir en arrière \
                            ne rendrait pas l'état de départ.",
                           rel, out.lines().take(4).collect::<Vec<_>>().join("\n        ")));
        }
    }
    // Le reste de l'arbre est SIGNALÉ, jamais refusé : il ne bouge pas, et le
    // taire ferait croire qu'on a tout vérifié.
    for d in &depots {
        if !propre(d) {
            let (_, o) = git(d, &["status", "--porcelain"]);
            let n = o.lines().count();
            println!("  {}note{} {} modification(s) en attente dans `{}` — hors \
                      du périmètre, rien n'y touchera", J, X, n, d.display());
        }
    }

    // ④ LE DÉPÔT DE MÉMOIRE A-T-IL UN DISTANT ? S'il n'en a pas, la migration
    // réécrit 100 % de ses chemins sans qu'aucune copie existe ailleurs.
    for d in &depots {
        if *d == *racine { continue; }
        let (_, o) = git(d, &["remote"]);
        if o.is_empty() {
            e.push(format!("`{}` n'a AUCUN dépôt distant. Il n'y a pas de \
                            retour arrière possible hors de cette machine.",
                           d.display()));
        }
    }

    // ⑤ Chaque source doit exister, et chaque cible être libre.
    for g in v {
        if !g.de.exists() {
            e.push(format!("source absente : {}", g.de.display()));
        }
        if g.vers.exists() {
            e.push(format!("cible déjà occupée : {}", g.vers.display()));
        }
    }
    e
}

fn deplace(g: &mut Geste, racine: &Path) -> Result<(), String> {
    if let Some(p) = g.vers.parent() {
        std::fs::create_dir_all(p).map_err(|x| x.to_string())?;
    }
    let d = depot_porteur(&g.de, racine);
    let (de_r, vers_r) = (g.de.strip_prefix(&d).unwrap_or(&g.de),
                          g.vers.strip_prefix(&d).unwrap_or(&g.vers));
    let (rc, _) = git(&d, &["mv", &de_r.to_string_lossy(), &vers_r.to_string_lossy()]);
    if rc == 0 {
        g.comment = "git mv".into();
        return Ok(());
    }
    // LE REPLI DIT QU'IL EST UN REPLI. Un `git mv` qui échoue parce que le
    // fichier n'est pas suivi et un qui échoue parce que l'index est sale se
    // lisent pareil, et le second perd l'historique sans un mot.
    std::fs::rename(&g.de, &g.vers).map_err(|x| x.to_string())?;
    g.comment = "rename (git mv a refusé — historique NON suivi)".into();
    Ok(())
}

/// Combien de projets de l'atelier sont encore sur l'ancien arbre.
///
/// C'EST LE TÉMOIN QUI COMPTE. Un script qui n'a rien trouvé et un script qui a
/// tout fait rendent tous les deux zéro ; ce nombre, lui, doit descendre de un.
pub fn reste_en_v1(atelier: &Path) -> usize {
    let mut n = 0;
    if let Ok(it) = std::fs::read_dir(atelier) {
        let mut v: Vec<PathBuf> = it.filter_map(|e| e.ok().map(|e| e.path())).collect();
        v.sort();
        for d in v {
            if !d.is_dir() || !d.join(".git").exists() { continue; }
            match memoire::resous(&d).forme {
                Forme::EnPlace | Forme::Deportee => n += 1,
                _ => {}
            }
        }
    }
    n
}

pub fn main(args: &[String]) -> i32 {
    let appliquer = args.iter().any(|a| a == "--apply");
    let depart: PathBuf = args.iter().find(|a| !a.starts_with("--"))
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());

    let r = memoire::resous(&depart);
    let racine = match &r.racine {
        Some(x) => x.clone(),
        None => { println!("  {}aucun dépôt au-dessus de {}{}", R, depart.display(), X);
                  return 2; }
    };
    println!("\n  {}MIGRATION VERS `brain/`{}   {}{}{}", "\x1b[1m", X, D, racine.display(), X);
    println!("  {:<22} {}", "forme actuelle", r.forme.mot());

    let mut v = match gestes(&r, &racine) {
        Ok(v) => v,
        Err(m) => { println!("  {}rien à faire : {}{}", J, m, X); return 1; }
    };

    let ecarts = avant(&r, &racine, &v);
    if !ecarts.is_empty() {
        println!("\n  {}REFUSÉ — {} raison(s), et RIEN n'a été touché :{}", R, ecarts.len(), X);
        for e in &ecarts { println!("    · {}", e); }
        return 2;
    }

    for g in &mut v {
        if appliquer {
            if let Err(m) = deplace(g, &racine) {
                println!("  {}ÉCHEC{} {} : {}", R, X, g.de.display(), m);
                return 2;
            }
            println!("  {}→{} {:<44} {}{}{}", V, X,
                     g.de.strip_prefix(&racine).unwrap_or(&g.de).display(),
                     D, g.comment, X);
        } else {
            println!("  {}?{} {:<44} -> {}", J, X,
                     g.de.strip_prefix(&racine).unwrap_or(&g.de).display(),
                     g.vers.strip_prefix(&racine).unwrap_or(&g.vers).display());
        }
    }

    if !appliquer {
        // LE TÉMOIN DU BLANC : après cette ligne, l'arbre cible ne doit pas
        // exister. Si le blanc a écrit, le contrôle est raté, pas le détail.
        println!("\n  {} déplacement(s) À FAIRE  {}(--apply pour agir){}", v.len(), D, X);
        println!("  {}brain/ existe déjà ? {}{}", D,
                 if racine.join("brain").exists() { "OUI — ANOMALIE" } else { "non" }, X);
        return 0;
    }

    // ── LES ASSERTIONS D'APRÈS, dans la même exécution ──────────────────
    let mut mal = Vec::new();
    let apres = memoire::resous(&depart);
    if apres.forme != Forme::Brain {
        mal.push(format!("le résolveur, relancé à froid, dit `{}` et non `brain`",
                         apres.forme.mot()));
    }
    for g in &v {
        // « EXISTE ET EST VIDE » N'EST PAS « N'EXISTE PLUS ». Un dossier vide
        // se lit comme un dossier, et la détection de forme le compterait.
        if g.de.exists() {
            mal.push(format!("l'ancien dossier existe encore : {}", g.de.display()));
        }
        if !g.vers.exists() {
            mal.push(format!("le nouveau dossier manque : {}", g.vers.display()));
        }
    }
    if let Some(f) = &apres.fact {
        if !f.join("base.md").is_file() {
            mal.push("`brain/fact/base.md` est introuvable après le déplacement".into());
        }
    }

    println!();
    if mal.is_empty() {
        println!("  {}✓{} {} déplacement(s), {} assertion(s) d'après tenues",
                 V, X, v.len(), 3 + v.len() * 2);
    } else {
        println!("  {}⚠ {} assertion(s) d'après ONT ÉCHOUÉ :{}", R, mal.len(), X);
        for m in &mal { println!("    · {}", m); }
    }
    let n = reste_en_v1(&racine.parent().unwrap_or(&racine).to_path_buf());
    println!("  {}reste sur l'ancien arbre dans l'atelier : {}{}", D, n, X);
    if mal.is_empty() { 0 } else { 2 }
}
