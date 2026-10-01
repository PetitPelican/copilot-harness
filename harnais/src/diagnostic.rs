//! `harnais diagnostic` — CE QUI EST TROUVÉ, ET CE QUI NE L'EST PAS.
//!
//! POURQUOI CETTE SOUS-COMMANDE EXISTE. Un agent qui éprouve le paquet sur un
//! poste peut conclure FAUX, et pour la même raison à chaque fois : **le
//! harnais ne fait aucun bruit quand il autorise**.
//!
//!   · `memoire` rend `null` sur un projet parfaitement en forme. C'est le
//!     comportement juste — ce module ne répond que pour une mémoire déportée —
//!     mais un `null` qui veut dire « forme en place » et un `null` qui veut
//!     dire « rien trouvé » sont indiscernables dans une sortie muette.
//!   · une garde peut laisser passer plusieurs enregistrements d'affilée. Elle
//!     n'est pas inerte : sa condition n'est pas réunie. Rien ne le dit.
//!
//! **Un silence ne prouve rien dans les deux sens.** D'où la règle de cette
//! sortie : chaque ligne dit ce qui a été CHERCHÉ, ce qui a été TROUVÉ — et
//! quand rien ne l'a été, POURQUOI. Jamais un blanc.
//!
//! Elle ne modifie rien, jamais. C'est la seule sous-commande qu'on peut
//! lancer sur un poste inconnu sans rien risquer.

use std::path::{Path, PathBuf};

fn dit(quoi: &str, trouve: Option<String>, motif: &str) {
    match trouve {
        Some(v) => println!("  {:<26} {}", quoi, v),
        None => println!("  {:<26} — {}", quoi, motif),
    }
}


fn taille(p: &Path) -> String {
    if !p.exists() { return format!("{} (absent)", p.display()); }
    match std::fs::read_dir(p) {
        Ok(it) => format!("{} ({} entrée(s))", p.display(), it.count()),
        Err(_) => format!("{} (illisible)", p.display()),
    }
}

pub fn main(args: &[String]) {
    let depart: PathBuf = args
        .first()
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());

    println!("\n  QUI TOURNE");
    println!(
        "  {:<26} {} {}",
        "version · source",
        option_env!("HARNAIS_VERSION").unwrap_or(concat!(env!("CARGO_PKG_VERSION"), "-local")),
        option_env!("HARNAIS_SOURCE").unwrap_or("local")
    );
    println!("  {:<26} {} / {}", "plateforme", std::env::consts::OS, std::env::consts::ARCH);
    dit("programme", std::env::current_exe().ok().map(|p| p.display().to_string()),
        "chemin du programme introuvable — cas très rare, à signaler");

    println!("\n  PAR QUEL SHELL");
    println!("  {:<26} {}", "hooks sur cet OS", if cfg!(windows) { "PowerShell (champ powershell)" } else { "bash (champ bash)" });
    println!("\n  VARIABLES DE L'HÔTE");
    let mut variables: Vec<(String, String)> = std::env::vars()
        .filter(|(k, _)| k.starts_with("COPILOT_") || k.starts_with("PLUGIN_"))
        .collect();
    variables.sort_by(|a, b| a.0.cmp(&b.0));
    for (k, v) in variables {
        let sensible = ["TOKEN", "SECRET", "KEY", "PASSWORD"].iter().any(|part| k.contains(part));
        dit(&k, Some(if sensible { "(masquée)".into() } else { v }), "");
    }
    println!("\n  LE PAQUET");
    dit("dossier du paquet", crate::socle::livre().map(|p| p.display().to_string()), "introuvable");
    let s = crate::socle::socle();
    dit("où l'état s'écrit", Some(taille(&s)), "");
    if !s.exists() {
        println!("  {:<26} — il n'existe pas encore ; il sera créé au premier écrit", "");
    }
    dit("ce qui est LIVRÉ", crate::socle::livre().map(|p| p.display().to_string()),
        "introuvable : les critères de relecture et la liste des rechutes \
         d'origine ne seront pas lus depuis le paquet");

    // ── CE QUI EST LIVRÉ AVEC LE PAQUET ──────────────────────────────────────
    println!("\n  LES FICHIERS QUE LE HARNAIS CHERCHE");
    for (nom, rel) in [("liste des rechutes", "rechutes.md"),
                       ("critères de relecture", "criteres-relecture.md")] {
        let mut ou = vec![s.join(rel)];
        if let Some(l) = crate::socle::livre() { ou.push(l.join(rel)); }
        let trouve = ou.iter().find(|p| p.is_file());
        dit(nom, trouve.map(|p| p.display().to_string()),
            &format!("cherché à {} — sans lui, la garde qui s'en sert ne mord pas",
                     ou.iter().map(|p| p.display().to_string())
                       .collect::<Vec<_>>().join(" puis ")));
    }

    // ── LE PROJET ────────────────────────────────────────────────────────────
    println!("\n  LE PROJET, VU DEPUIS {}", depart.display());

    // ON DEMANDE AU RÉSOLVEUR. Recomposer ses chemins depuis la racine du dépôt
    // sans jamais l'appeler annoncerait « absent » sur un projet à mémoire
    // déportée parfaitement sain — et une bascule pourrait être ANNULÉE juste à
    // cause de cette sortie, alors que le harnais sert son état complet au même
    // instant. Un instrument qui répond à une question plus petite que celle qu'on lui
    // pose coûte plus cher qu'un instrument absent — on lui obéit.
    let r = crate::memoire::resous(&depart);
    println!("  {:<26} {}", "forme du projet", r.forme.mot());
    if r.forme == crate::memoire::Forme::Ambigue {
        println!("  {:<26} — CE PROJET PORTE LES DEUX ARBRES À LA FOIS. C'est",
                 "");
        println!("  {:<26}   l'état qu'une migration interrompue laisse ; rien",
                 "");
        println!("  {:<26}   ne sera lu au hasard, mais il faut trancher.", "");
    }
    let racine = r.racine.clone();
    dit("racine du dépôt", racine.as_ref().map(|p| p.display().to_string()),
        "aucun dépôt au-dessus de ce dossier : la plupart des gardes ne \
         s'appliquent pas, et c'est voulu");
    dit("arbre de travail", r.arbre.as_ref().map(|p| p.display().to_string()),
        "aucun — hors dépôt");
    if !r.lot.is_empty() {
        println!("  {:<26} {}", "lot de cet agent", r.lot);
    }
    if let Some(rr) = &racine {
        dit("faits du projet", r.fact.as_ref().filter(|p| p.is_dir()).map(|p| taille(p)),
            &format!("cherché à {} — le projet n'a pas (encore) cette maison",
                     r.fact.as_ref().map(|p| p.display().to_string())
                      .unwrap_or_else(|| "(nulle part : forme d'avant migration)".into())));
        dit("état de l'agent", r.mind.as_ref().filter(|p| p.is_dir()).map(|p| taille(p)),
            &format!("cherché à {}",
                     r.mind.as_ref().map(|p| p.display().to_string())
                      .unwrap_or_else(|| "(nulle part)".into())));
        let d = rr.join("docs");
        dit("traces datées", if d.is_dir() { Some(taille(&d)) } else { None },
            "absent — le projet n'a pas (encore) cette maison");
        for (nom, f) in [("ce qui attend", "todo.md"), ("où on en est", "state.md")] {
            let p = r.mind.as_ref().map(|m| m.join(f));
            dit(nom, p.as_ref().filter(|p| p.is_file()).map(|p| {
                    format!("{} lignes", std::fs::read_to_string(p)
                        .map(|t| t.lines().count()).unwrap_or(0))
                }),
                &format!("cherché à {} — la garde de fin de tour le réclamera \
                          dès que du code bougera",
                         p.map(|p| p.display().to_string())
                          .unwrap_or_else(|| "(nulle part)".into())));
        }
        // LE PIÈGE NOMMÉ : ce module ne répond que pour une mémoire DÉPORTÉE.
        // Un `null` ici ne veut PAS dire « cassé ».
        dit("mémoire déportée", crate::memoire::base(&depart).map(|p| p.display().to_string()),
            "ce projet garde sa mémoire dans son dépôt — c'est la forme la plus \
             courante, et ce n'est PAS une panne");
        dit("carnet d'équipe", crate::carnet::espace(&depart, false)
                .map(|p| taille(&p)),
            "aucun : projet à un seul agent, ou équipe jamais amorcée \
             (`equipe-amorce` le crée)");
    }

    // ── LE REPLI ─────────────────────────────────────────────────────────────
    println!("\n  LE REPLI");
    println!("  {:<26} {}", "vous lisez ceci, donc",
             "le programme natif répond : le repli n'est pas employé");
    if let Some(l) = crate::socle::livre() {
        let h = l.join("hooks");
        dit("implémentation de repli", if h.is_dir() { Some(taille(&h)) } else { None },
            "absente du paquet : si le programme natif ne démarrait pas sur cette \
             machine, AUCUN hook ne partirait");
    }
    println!("\n  Rien n'a été modifié.\n");
}
