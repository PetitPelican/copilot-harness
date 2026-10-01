//! LE RELECTEUR — un juge qui n'a pas écrit ce qu'il relit.
//!
//! Un juge du fond qui se déclenche tout seul est rare. Le principe, lui, se
//! dit facilement : le relecteur n'a jamais écrit le code qu'il relit, c'est ce
//! qui élimine le biais d'auteur — un même contexte qui se relit lui-même n'est
//! pas une relecture, c'est du biais de confirmation. Mais la doctrine est le
//! plus souvent énoncée sans être câblée : la revue relit dans le fil qui vient
//! d'écrire, ou s'appelle dans sa propre session.
//!
//! Ici la gâchette est un hook de fin de tour déterministe. Ce programme est ce
//! qu'il déclenche.
//!
//! LA BARRIÈRE N'EST PAS UNE PERMISSION, C'EST L'IGNORANCE. Le juge reçoit
//! l'affirmation, ce qui l'établit et sa vérification. Rien du raisonnement qui
//! y a mené. Il ne peut pas confirmer ce qu'il n'a pas vu.
//!
//! POURQUOI EN RUST, ET POURQUOI CELUI-CI D'ABORD. C'est du code neuf et borné :
//! il éprouve la chaîne de compilation et le portage sans risquer une seule des
//! corrections accumulées dans les hooks. Un binaire ne réclame aucun
//! interpréteur là où il tourne — c'est ce qui décide de Windows.

use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};
use crate::socle::{socle, livre};

/// Plafond journalier. Une revue qui s'appelle elle-même peut se multiplier
/// sans limite. Ici le nombre d'ouvriers lancés dans la journée est borné,
/// point.
const PLAFOND_JOUR: usize = 12;

/// Un seul ouvrier à la fois. Le verrou porte l'heure de pose : un verrou
/// oublié par un processus tué ne doit pas bloquer le dispositif pour toujours.
const VERROU_PERIME_S: u64 = 900;

fn maintenant() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn jour() -> String {
    // Pas de dépendance pour une date : le compteur journalier n'a besoin que
    // d'une clé qui change chaque jour, pas d'un calendrier.
    format!("{}", maintenant() / 86_400)
}

/// Lecture d'un fichier « clé: valeur » suivi de sections `--- nom ---`.
/// Format volontairement lisible à l'œil : une demande de relecture doit
/// pouvoir être ouverte et comprise sans outil.
fn decoupe(t: &str) -> (BTreeMap<String, String>, BTreeMap<String, String>) {
    let (mut tetes, mut sections) = (BTreeMap::new(), BTreeMap::new());
    let (mut courante, mut tampon) = (String::new(), String::new());
    for l in t.lines() {
        let n = l.trim();
        if n.starts_with("--- ") && n.ends_with(" ---") {
            if !courante.is_empty() {
                sections.insert(courante.clone(), tampon.trim().to_string());
            }
            courante = n[4..n.len() - 4].trim().to_string();
            tampon.clear();
        } else if courante.is_empty() {
            if let Some((k, v)) = n.split_once(':') {
                tetes.insert(k.trim().to_string(), v.trim().to_string());
            }
        } else {
            tampon.push_str(l);
            tampon.push('\n');
        }
    }
    if !courante.is_empty() {
        sections.insert(courante, tampon.trim().to_string());
    }
    (tetes, sections)
}

/// Le jeu fermé. Toute réponse qui n'y entre pas devient INSUFFISANT — jamais
/// CONFIRME. Un juge qu'on ne comprend pas ne vaut pas un accord.
fn normalise(sortie: &str) -> String {
    let brut = sortie.trim();
    let premiere = brut.lines().find(|l| !l.trim().is_empty()).unwrap_or("").trim();
    let haut: String = premiere.chars().map(|c| c.to_ascii_uppercase()).collect();
    // On retire les accents des trois mots attendus plutôt que d'espérer que le
    // modèle les pose : « CONFIRMÉ » et « CONFIRME » doivent valoir pareil.
    let sans = haut.replace('É', "E").replace('È', "E");
    if brut.lines().count() == 1 && sans == "CONFIRME" {
        "CONFIRME".to_string()
    } else if brut.lines().count() == 1 && sans.starts_with("CONTREDIT ") {
        format!("CONTREDIT {}", premiere[9.min(premiere.len())..].trim())
    } else if brut.lines().count() == 1 && sans.starts_with("INSUFFISANT ") {
        format!("INSUFFISANT {}", premiere[11.min(premiere.len())..].trim())
    } else {
        // LE POINT LE PLUS IMPORTANT DU PROGRAMME. Un juge muet, coupé,
        // hors-sujet ou bavard n'est PAS un accord. C'est la même règle que
        // MUET pour les vérifications : un contrôle qui n'aboutit pas ne se lit
        // jamais comme un constat confirmé.
        format!(
            "INSUFFISANT le relecteur n'a pas rendu un verdict lisible ({})",
            premiere.chars().take(80).collect::<String>()
        )
    }
}

fn invite(criteres: &str, demande: &str) -> String {
    format!(
        "Tu es un relecteur. Tu n'as PAS écrit ce qui suit et tu n'as accès à \
rien d'autre que ce message : ni la conversation, ni le dépôt, ni le \
raisonnement qui a mené à cette affirmation.\n\n\
Tes critères, que tu ne peux pas modifier :\n\n{}\n\n\
=== CE QUE TU DOIS JUGER ===\n\n{}\n\n=== FIN ===\n\n\
Réponds par UNE SEULE LIGNE, commençant par exactement l'un de ces trois \
mots : CONFIRME, ou CONTREDIT suivi du motif en une phrase, ou INSUFFISANT \
suivi de ce qui manque. Aucun préambule, aucune explication au-delà de cette \
ligne. Dans le doute, INSUFFISANT.",
        criteres, demande
    )
}

/// Lance le juge. Rend le verdict normalisé — et jamais une erreur silencieuse :
/// un échec d'exécution est un INSUFFISANT explicite.
fn juge(invite: &str) -> String {
    let Some(exe) = crate::copilot::executable() else {
        return "INSUFFISANT CLI Copilot introuvable : poser HARNAIS_COPILOT, installer copilot dans PATH ou le SDK".into();
    };
    let mut c = Command::new(exe);
    c.args(["-p", invite, "--silent", "--no-custom-instructions", "--disable-builtin-mcps",
            "--available-tools", "--no-ask-user", "--no-auto-update", "--no-remote-export"]);
    if let Ok(modele) = std::env::var("HARNAIS_MODELE_JUGE") {
        if !modele.trim().is_empty() { c.args(["--model", modele.trim()]); }
    }
    let r = c.env("HARNAIS_JUGE", "1")
        .output();
    match r {
        Ok(o) if o.status.success() => normalise(&String::from_utf8_lossy(&o.stdout)),
        Ok(o) => format!("INSUFFISANT le relecteur n'a pas abouti (code {})", o.status.code().unwrap_or(-1)),
        Err(e) => format!("INSUFFISANT le relecteur n'a pas pu être lancé ({})", e),
    }
}

/// LES CRITÈRES SONT LIVRÉS, JAMAIS ÉCRITS PAR L'AGENT — et il faut donc les
/// trouver là où ils sont livrés, pas là où l'agent écrit. Deux endroits, dans
/// cet ordre : le dossier du plugin quand on tourne en plugin, et **à côté du
/// programme** sinon — c'est le cas d'un poste qui appelle le binaire par son
/// chemin sans passer par le plugin. Sans cette seconde adresse, le relecteur
/// se tairait pour toujours, en annonçant « critères introuvables ».
///
/// Ce qu'on NE cherche PAS : le dossier d'état de l'agent. Y mettre les
/// critères reviendrait à laisser celui qu'on juge écrire les conditions de son
/// acceptation. La barrière n'est pas un droit de fichier — l'agent est
/// propriétaire du dépôt — c'est que les changer laisse une trace dans
/// l'historique.
fn criteres() -> String {
    let mut cands: Vec<PathBuf> = Vec::new();
    if let Some(r) = livre() {
        cands.push(r.join("criteres-relecture.md"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(bin) = exe.parent() {
            cands.push(bin.join("criteres-relecture.md"));
            if let Some(racine) = bin.parent() {
                cands.push(racine.join("criteres-relecture.md"));
            }
        }
    }
    for c in cands {
        if let Ok(t) = fs::read_to_string(&c) {
            if !t.trim().is_empty() {
                return t;
            }
        }
    }
    String::new()
}

fn compteur_jour(dossier: &Path) -> (String, usize) {
    let f = dossier.join(".compteur");
    let j = jour();
    let (mut vu, mut n) = (String::new(), 0usize);
    if let Ok(t) = fs::read_to_string(&f) {
        if let Some((a, b)) = t.trim().split_once(' ') {
            vu = a.to_string();
            n = b.parse().unwrap_or(0);
        }
    }
    if vu != j {
        n = 0;
    }
    (j, n)
}

pub fn main(args: &[String]) {
    let dossier = socle().join("relecture");
    if fs::create_dir_all(&dossier).is_err() {
        return; // fail-open : un relecteur qui empêche de travailler est pire que pas de relecteur
    }
    let sec = args.iter().any(|a| a == "--sec");

    // ── un seul ouvrier à la fois ─────────────────────────────────────────
    let verrou = dossier.join(".verrou");
    if let Ok(t) = fs::read_to_string(&verrou) {
        let pose: u64 = t.trim().parse().unwrap_or(0);
        if maintenant().saturating_sub(pose) < VERROU_PERIME_S {
            println!("un relecteur tourne déjà");
            return;
        }
    }

    let attente: Vec<PathBuf> = fs::read_dir(&dossier)
        .map(|it| {
            let mut v: Vec<PathBuf> = it
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.extension().map(|x| x == "demande").unwrap_or(false))
                .collect();
            v.sort();
            v
        })
        .unwrap_or_default();
    if attente.is_empty() {
        println!("rien à relire");
        return;
    }

    let (j, n) = compteur_jour(&dossier);
    if n >= PLAFOND_JOUR {
        println!("plafond journalier atteint ({} relectures)", n);
        return;
    }

    let criteres = criteres();
    if criteres.trim().is_empty() {
        // SANS CRITÈRES, PAS DE JUGEMENT. On ne se rabat pas sur « le bon sens
        // du modèle » : c'est précisément ce que les critères remplacent.
        println!("critères introuvables — aucune relecture (et c'est voulu)");
        return;
    }

    let _ = fs::write(&verrou, maintenant().to_string());
    let mut faits = 0usize;
    for d in attente.iter().take(PLAFOND_JOUR - n) {
        let brut = match fs::read_to_string(d) {
            Ok(t) => t,
            Err(_) => continue,
        };
        let (tetes, _) = decoupe(&brut);
        // ON NE RELIT JAMAIS UNE RELECTURE. Une demande qui porterait un verdict
        // serait une revue de revue — le chemin par lequel une revue se
        // multiplie sans fin.
        if tetes.contains_key("verdict_relecteur") {
            let _ = fs::remove_file(d);
            continue;
        }
        let verdict = if sec {
            "CONFIRME (simulation, aucun juge lancé)".to_string()
        } else {
            juge(&invite(&criteres, &brut))
        };
        let cible = d.with_extension("verdict");
        if let Ok(mut f) = fs::File::create(&cible) {
            let _ = writeln!(f, "verdict_relecteur: {}", verdict);
            let _ = writeln!(f, "rendu_le: {}", maintenant());
            let _ = writeln!(f, "sur: {}", tetes.get("id").map(|s| s.as_str()).unwrap_or("?"));
        }
        let _ = fs::remove_file(d);
        faits += 1;
        println!("{} → {}", d.file_name().map(|s| s.to_string_lossy().to_string()).unwrap_or_default(), verdict);
    }
    let _ = fs::write(dossier.join(".compteur"), format!("{} {}", j, n + faits));
    let _ = fs::remove_file(&verrou);
}

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn un_juge_bavard_ou_ambigu_ne_confirme_jamais() {
        assert_eq!(normalise("CONFIRME\n"), "CONFIRME");
        assert_eq!(normalise("CONFIRMÉ"), "CONFIRME");
        assert_eq!(normalise("CONTREDIT pas mesuré"), "CONTREDIT pas mesuré");
        for t in ["CONFIRME pas vraiment", "CONFIRME\nmais non", "CONFIRMERA", "", "CONTREDIT"] {
            assert!(normalise(t).starts_with("INSUFFISANT"), "{t}");
        }
    }
}
