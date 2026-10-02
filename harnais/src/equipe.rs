//! PASSER UN PROJET EN ÉQUIPE — ou lui ajouter un agent. Écrit en Rust parce
//! que le script d'origine n'existait qu'en Python, et échouait donc en
//! silence sur un Windows sans interpréteur.
//!
//! UNE SEULE COMMANDE, DEUX COMPORTEMENTS, ET C'EST LA FORME DU PROJET QUI
//! DÉCIDE. Sur un projet mono elle convertit et crée les premiers agents ; sur
//! un projet déjà multi elle en ajoute un.
//!
//!     en `brain/`      brain/mind/{state,todo}.md -> brain/mind/<premier>/
//!                      brain/fact/roles.md, carnet dans brain/workspace/
//!     à l'ancienne     .mind/                     -> agents/<premier>/.mind/
//!                      .fact/roles.md, carnet dans equipe/
//!     dans les deux    .github/copilot/settings.json à la racine Git
//!                      .github/agents/<nom>.agent.md, le profil du menu d'agent
//!                      .github/copilot/perimetre.json pour la garde d'écriture
//!                      agents/<autres>/AGENTS.md pour le rôle
//!
//! `--profils` MET À NIVEAU un projet déjà en équipe sans lui ajouter d'agent :
//! profils manquants, périmètres réécrits en chemins relatifs.
//!
//! CE QU'ELLE NE FAIT PAS : découper le `AGENTS.md` du projet (éditorial),
//! toucher aux faits, aux traces ni au code.
//!
//! **À blanc par défaut.** `--apply` (ou `--go`) pour écrire.

use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

const GABARIT_ROLES: &str = include_str!("../../skills/agentic-agents/templates/roles.md");
const ROLE: &str = "# {} — rôle

> Le `AGENTS.md` du projet est **hérité** : il est chargé en même temps que
> celui-ci, à chaque démarrage. N'y recopier AUCUNE de ses phrases. Le test :
> si une phrase resterait vraie pour un autre agent du projet, elle est à
> l'étage au-dessus.

## Ce que cet agent tient

[LE_PÉRIMÈTRE — en dossiers, pas en intentions. « orienté produit » n'empêche
personne de toucher au backend ; la frontière qui tient est celle écrite en
le périmètre affiché par le briefing et appliqué par la garde.]

## Ce qu'il ne touche pas

[LES_AUTRES_LOTS — et qui les tient.]
";

pub(crate) fn role_qa() -> &'static str {
    "# QA — épreuve indépendante et documentation\n\n\
Auditer sans réparer le code ni la production et sans diriger les autres lots.\n\
Écrire ses plans et grilles dans ses livrables, tenir son état et sa todo.\n\
Les cinq fichiers de faits (base, stack, architecture, rules, roles) ne sont\n\
modifiables qu'après validation explicite de l'humain ; conserver cap,\n\
provenance, dates et distinction entre mesure et information rapportée.\n\
Un commit documentaire est permis dans ce périmètre : mettre son état à jour,\n\
utiliser ` # fact-ok` uniquement pour les faits autorisés, jamais ` # mind-ok`.\n\
Ne pas modifier les sources d'audit, les instructions, gardes, mémoires des\n\
pairs ou le carnet automatique. Ne pas lire ni écrire operations.md, .env\n\
ou secrets ; ne pas exécuter de pipeline ni changer une base ou un cloud.\n\
La garde de fichiers ne confine pas le shell/MCP ; elle ne prouve pas\n\
la disponibilité d'accès en lecture. Nommer l'arbre, la preuve et les limites.\n"
}

fn role(nom: &str) -> String {
    if nom.eq_ignore_ascii_case("QA") { role_qa().into() }
    else { ROLE.replacen("{}", nom, 1) }
}

pub(crate) fn allow_par_defaut(nom: &str, fact: &str, mind: &str, livrables: &str) -> Vec<String> {
    let mut allow = vec![mind.to_string(), livrables.to_string()];
    if nom.eq_ignore_ascii_case("QA") {
        allow.extend(crate::socle::faits_tous().iter().map(|f| format!("{fact}/{f}")));
    }
    allow
}

fn profil_role(p: &Path, n: &str, appliquer: bool, rap: &mut Vec<(String, String)>) -> Result<(), String> {
    let f = crate::agent::profil(p, n);
    if f.exists() {
        return Err(format!("{} existe déjà ; réconcilier le rôle avant de créer cet agent", f.display()));
    }
    rap.push(("+".into(), format!("{} — profil et rôle uniques ; livrables dans docs/livrables/{n}/", rel(p, &f))));
    if appliquer {
        let texte = format!("---\nname: {}\ndescription: Agent {n} — rôle propre au projet\n---\n\
Lis brain/mind/{n}/state.md et brain/mind/{n}/todo.md à la reprise. \
Le harnais applique .github/copilot/perimetres/{}.json.\n\n\
<!-- harnais:role:start -->\n{}<!-- harnais:role:end -->\n",
            crate::agent::nom_de_profil(n), crate::agent::nom_de_profil(n), role(n));
        std::fs::create_dir_all(f.parent().unwrap()).map_err(|e| e.to_string())?;
        std::fs::write(f, texte).map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Tout ce qui n'est pas alphanumérique devient un tiret, et une suite de tels
/// caractères UN SEUL : deux noms d'agents qui donnent la même clé auraient les
/// mêmes dossiers d'état.
pub(crate) fn slug(p: &str) -> String {
    let mut out = String::new();
    let mut dans = false;
    for c in p.chars() {
        if c.is_ascii_alphanumeric() { out.push(c); dans = false; }
        else if !dans { out.push('-'); dans = true; }
    }
    out
}

fn git(p: &Path, a: &[&str]) -> bool {
    Command::new("git").arg("-C").arg(p).args(a).output().map(|o| o.status.success()).unwrap_or(false)
}

fn rel(racine: &Path, p: &Path) -> String {
    p.strip_prefix(racine).unwrap_or(p).components()
        .map(|c| c.as_os_str().to_string_lossy().to_string()).collect::<Vec<_>>().join("/")
}

/// OÙ VIVENT LES FAITS ET LES ESPRITS — la seule chose qui change entre les
/// deux organisations. En `brain/`, l'esprit d'un agent vit dans le CERVEAU,
/// rangé par nom : `agents/<nom>/` ne porte plus que le rôle et les réglages.
struct Disposition { racine: PathBuf, cerveau: bool, faits: PathBuf }
impl Disposition {
    fn esprit(&self, nom: &str) -> PathBuf {
        if self.cerveau { self.racine.join("brain/mind").join(nom) }
        else { self.racine.join("agents").join(nom).join(".mind") }
    }
    fn esprit_mono(&self) -> PathBuf {
        if self.cerveau { self.racine.join("brain/mind") } else { self.racine.join(".mind") }
    }
    fn etiquette_faits(&self) -> &'static str { if self.cerveau { "brain/fact" } else { ".fact" } }
    fn rel(&self, p: &Path) -> String { rel(&self.racine, p) }
}

fn trie(d: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(d).map(|it| it.flatten().map(|e| e.path()).collect())
        .unwrap_or_default();
    v.sort();
    v
}

fn nom(p: &Path) -> String { p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default() }

/// La forme du projet. MULTI se reconnaît à un esprit PAR AGENT, et l'endroit
/// où le chercher dépend de l'organisation — chercher au seul ancien endroit
/// déclarait « mono » un projet `brain/` déjà converti.
fn forme(p: &Path) -> (&'static str, Vec<String>, Disposition) {
    let cerveau = p.join("brain/fact").is_dir();
    let disp = Disposition {
        racine: p.to_path_buf(), cerveau,
        faits: p.join(if cerveau { "brain/fact" } else { ".fact" }),
    };
    let etats: Vec<String> = if cerveau {
        trie(&p.join("brain/mind")).into_iter()
            .filter(|d| d.is_dir() && d.join("state.md").is_file()).map(|d| nom(&d)).collect()
    } else {
        trie(&p.join("agents")).into_iter().filter(|d| d.join(".mind").is_dir()).map(|d| nom(&d)).collect()
    };
    if !etats.is_empty() { return ("multi", etats, disp); }
    if cerveau || p.join(".fact").is_dir() { return ("mono", vec![], disp); }
    ("ancienne", vec![], disp)
}

/// Le JSON tel que `json.dumps(indent=2, ensure_ascii=False)` l'écrit.
fn json_indent2(v: &Value) -> String { serde_json::to_string_pretty(v).unwrap_or_default() }

/// Le plugin est déclaré une fois à la racine Git ; chaque agent garde son périmètre local.
fn reglages_racine(projet: &Path, appliquer: bool, rap: &mut Vec<(String, String)>) -> Result<(), String> {
    let racine = crate::copilot::racine_git(projet)?;
    let cible = crate::copilot::settings(&racine);
    let mut d: Value = if cible.is_file() {
        serde_json::from_str(&std::fs::read_to_string(&cible).map_err(|e| e.to_string())?)
            .map_err(|e| format!("{} : {e}", cible.display()))?
    } else { json!({}) };
    let avant = d.clone();
    crate::copilot::reglages(&mut d, &crate::copilot::paquet()?)?;
    if d != avant {
        rap.push(("+".into(), format!("{} — déclaration Copilot unique à la racine Git", rel(projet, &cible))));
        if appliquer {
            std::fs::create_dir_all(cible.parent().unwrap()).map_err(|e| e.to_string())?;
            std::fs::write(&cible, json_indent2(&d) + "\n").map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// LE PÉRIMÈTRE D'UN AGENT, EN CHEMINS RELATIFS À LA RACINE DU PROJET.
///
/// Jusqu'en 0.15.0 il était écrit en ABSOLU, donc vers le dossier principal :
/// dans une copie de travail de l'app, aucune écriture n'y tombait et la garde
/// laissait tout passer. Relatif, il se pose sur la copie où l'on travaille.
/// Les entrées existantes sous le projet sont réécrites en relatif ; celles
/// qui visent un dossier hors du projet restent telles quelles.
fn perimetre_agent(cible: &Path, projet: &Path, autres: &[String],
                   appliquer: bool, rap: &mut Vec<(String, String)>) -> Result<(), String> {
    crate::copilot::avertit_settings_agent(cible);
    let mut denies: Vec<String> = autres.iter().map(|a| format!("agents/{a}")).collect();
    let est_compact = cible.parent().is_some_and(|p| p == projet.join("brain/mind"));
    let perimetre = if est_compact {
        for a in autres {
            denies.push(format!("brain/mind/{a}"));
            denies.push(format!("docs/livrables/{a}"));
        }
        denies.extend([".github", "brain/poids.json"].map(String::from));
        if !nom(cible).eq_ignore_ascii_case("QA") { denies.push("brain/fact".into()); }
        crate::agent::perimetre_compact(projet, &nom(cible))
    } else { cible.join(".github/copilot/perimetre.json") };
    let nouveau = !perimetre.exists();
    if !est_compact && nouveau && nom(cible).eq_ignore_ascii_case("QA") {
        denies.extend([".github", "brain/poids.json"].map(String::from));
        for a in autres {
            denies.push(format!("brain/mind/{a}"));
            denies.push(format!("docs/livrables/{a}"));
        }
    }
    if perimetre.exists() {
        if est_compact { crate::copilot::lis_allow(cible)?; }
        let base = projet.canonicalize().unwrap_or_else(|_| projet.to_path_buf());
        for chemin in crate::copilot::lis_deny(cible)? {
            // `\\x` sous Windows n'a pas de lecteur mais a une racine : il n'est
            // PAS relatif au projet, il reste tel qu'écrit.
            let ecrit = if chemin.is_relative() && !chemin.has_root() { rel(Path::new(""), &chemin) }
                        else if chemin.is_relative() { chemin.to_string_lossy().to_string() } else {
                let c = chemin.canonicalize().unwrap_or_else(|_| chemin.clone());
                if c == base { ".".into() }
                else if c.starts_with(&base) { rel(&base, &c) } else { chemin.to_string_lossy().to_string() }
            };
            if !ecrit.is_empty() && !denies.contains(&ecrit) { denies.push(ecrit); }
        }
    }
    rap.push(("+".into(), format!("{} — {} dossier(s) interdits par la garde Edit|Write",
        rel(projet, &perimetre), denies.len())));
    if appliquer {
        std::fs::create_dir_all(perimetre.parent().unwrap()).map_err(|e| e.to_string())?;
        let mut garde: Value = if perimetre.exists() {
            serde_json::from_str(&std::fs::read_to_string(&perimetre).map_err(|e| e.to_string())?)
                .map_err(|e| e.to_string())?
        } else { json!({}) };
        let avant = garde.clone();
        garde["deny"] = json!(denies);
        if (est_compact || (nouveau && nom(cible).eq_ignore_ascii_case("QA"))) && garde.get("allow").is_none() {
            let n = nom(cible);
            let cerveau = projet.join("brain/fact").is_dir();
            let fact = if cerveau { "brain/fact" } else { ".fact" };
            let mind = if cerveau { format!("brain/mind/{n}") } else { format!("agents/{n}/.mind") };
            let livrables = if est_compact { format!("docs/livrables/{n}") } else { format!("agents/{n}/livrables") };
            garde["allow"] = json!(allow_par_defaut(&n, fact, &mind, &livrables));
        }
        if !perimetre.exists() || garde != avant {
            std::fs::write(perimetre, json_indent2(&garde) + "\n").map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// LE PROFIL DU MENU D'AGENT — `.github/agents/<nom>.agent.md`, à la racine Git.
///
/// L'app Copilot lance chaque conversation à la racine d'une copie de travail :
/// le dossier `agents/<nom>/` ne dit plus qui parle. Ce profil fait apparaître
/// l'agent dans le menu du champ de saisie ; le harnais lit ensuite le choix
/// dans le journal de session et sert le rôle, l'état et le périmètre (voir
/// `agent`). Le profil reste COURT : il ne recopie pas le rôle, qui n'a qu'une
/// maison. Sa dernière phrase est le secours d'une session sans harnais.
/// Jamais écrasé : un profil existant est peut-être déjà ajusté à la main.
fn profil(racine_git: &Path, projet: &Path, n: &str, esprit: &Path, appliquer: bool,
          rap: &mut Vec<(String, String)>) {
    let nom_profil = crate::agent::nom_de_profil(n);
    if nom_profil.is_empty() {
        rap.push(("⚠".into(), format!("agent {n} : aucun nom de profil possible — profil non écrit")));
        return;
    }
    let f = racine_git.join(".github/agents").join(format!("{nom_profil}.agent.md"));
    if f.exists() {
        rap.push(("·".into(), format!("{} existe : non écrasé", rel(projet, &f))));
        return;
    }
    rap.push(("+".into(), format!("{} — l'agent {n} dans le menu d'agent de l'app", rel(projet, &f))));
    if appliquer {
        let role = format!("agents/{n}/AGENTS.md");
        let etat = rel(projet, esprit);
        let texte = format!("---\nname: {nom_profil}\ndescription: Agent {n} de {projet_nom} — son rôle est dans {role}\n---\n\
Tu es l'agent {n} de ce projet. À chaque ouverture, le harnais te sert ton rôle ({role}), \
ton état ({etat}/) et ton périmètre d'écriture.\n\n\
S'il ne te les a pas montrés, lis d'abord {role}, puis {etat}/state.md et {etat}/todo.md, avant toute réponse.\n",
            projet_nom = nom(projet));
        if let Some(d) = f.parent() { let _ = std::fs::create_dir_all(d); }
        let _ = std::fs::write(&f, texte);
    }
}

/// Deux agents dont les profils porteraient le même nom : le menu n'en
/// montrerait qu'un, et le choix désignerait le mauvais dossier.
fn profils_en_collision(tous: &[String]) -> Option<String> {
    for (i, a) in tous.iter().enumerate() {
        for b in &tous[i + 1..] {
            if crate::agent::nom_de_profil(a) == crate::agent::nom_de_profil(b) {
                return Some(format!("{a} et {b} donnent le même profil « {} »", crate::agent::nom_de_profil(a)));
            }
        }
    }
    None
}

/// `--profils` : un projet DÉJÀ en équipe, mis à niveau sans nouvel agent.
fn mise_a_niveau(p: &Path, appliquer: bool) -> i32 {
    let (f, existants, disp) = forme(p);
    if f != "multi" {
        eprintln!("equipe --profils : ce projet n'est pas en équipe ({f}) — rien à mettre à niveau. \
Pour le passer en équipe : `harnais equipe --agents A,B`.");
        return 1;
    }
    if let Some(c) = profils_en_collision(&existants) { eprintln!("equipe --profils : {c} ; rien n'est écrit"); return 1; }
    if existants.iter().any(|n| crate::agent::compact(p, n)) {
        return crate::compact::main(p, appliquer);
    }
    let racine = match crate::copilot::racine_git(p) { Ok(r) => r, Err(e) => { eprintln!("equipe : {e}"); return 1; } };
    let mut rap: Vec<(String, String)> = vec![];
    for n in &existants {
        let d = p.join("agents").join(n);
        let autres: Vec<String> = existants.iter().filter(|x| *x != n).cloned().collect();
        if let Err(e) = perimetre_agent(&d, p, &autres, appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
        profil(&racine, p, n, &disp.esprit(n), appliquer, &mut rap);
    }
    println!("── profils — {} ({}){}", nom(p), existants.join(", "), if appliquer { "" } else { "  [DRY-RUN]" });
    for (signe, ligne) in &rap { println!("  {} {}", signe, ligne); }
    println!("\n── À reprendre à la main");
    println!("  · {}", a_commiter(&existants));
    if !appliquer { println!("\nDry-run. Relancer avec --apply pour écrire."); }
    0
}

/// La dernière consigne, la même pour les deux chemins.
fn a_commiter(tous: &[String]) -> String {
    format!("COMMITER `.github/agents/` et les périmètres : une nouvelle conversation de l'app part de \
l'état COMMITÉ, un profil non commité n'apparaît pas dans le menu. Ensuite, choisir l'agent dans le menu \
d'agent du champ de saisie ({}) ; dans le CLI, `copilot --agent <nom>` ou une session lancée dans \
`agents/<nom>/` pour la forme historique. En compact : `copilot --agent <nom>` \
depuis la racine. Sans agent choisi, {} tient la session s'il existe — le briefing le dit.",
        tous.iter().map(|n| crate::agent::nom_de_profil(n)).collect::<Vec<_>>().join(", "),
        crate::agent::DEFAUT)
}

/// Le serveur MCP du projet peut être propre à un agent : copier uniquement .mcp.json.
fn porte_les_non_herites(projet: &Path, cible: &Path, appliquer: bool, rap: &mut Vec<(String, String)>) {
    for r in [".mcp.json"] {
        let src = projet.join(r);
        if !src.is_file() { continue; }
        rap.push(("+".into(), format!("{}/{} — copié depuis la racine (ne s'hérite pas)", rel(projet, cible), r)));
        if appliquer {
            let dst = cible.join(r);
            if dst.exists() { rap.push(("·".into(), format!("{} existe : non écrasé", dst.display()))); continue; }
            if let Some(p) = dst.parent() { let _ = std::fs::create_dir_all(p); }
            let _ = std::fs::copy(&src, &dst);
        }
    }
}

fn valeur(args: &[String], cle: &str) -> Option<String> {
    let mut it = args.iter();
    while let Some(a) = it.next() {
        if a == cle { return it.next().cloned(); }
        if let Some(v) = a.strip_prefix(&format!("{}=", cle)) { return Some(v.to_string()); }
    }
    None
}

pub fn main(args: &[String]) -> i32 {
    if args.iter().any(|a| a == "-h" || a == "--help") {
        println!("harnais equipe --agents A,B[,C] [--project-root P] [--apply]\n\
harnais equipe --profils [--project-root P] [--apply]\n\
harnais equipe --compact [--agents A,B] [--project-root P] [--apply]\n\n\
Passe un projet mono en équipe (le PREMIER nommé hérite de l'état existant),\n\
ou ajoute des agents à un projet déjà en équipe. Chaque agent reçoit son profil\n\
`.github/agents/<nom>.agent.md`, qui le fait apparaître dans le menu d'agent de l'app.\n\
`--profils` met à niveau un projet déjà en équipe : profils manquants, périmètres\n\
en chemins relatifs. `--compact` exporte une équipe existante vers les profils-rôles\n\
et périmètres centralisés, ou crée les agents demandés sous cette forme.\n\
Les anciens dossiers et livrables ne sont jamais supprimés. À blanc par défaut.");
        return 0;
    }
    if args.iter().any(|a| a == "--compact") && !args.iter().any(|a| a == "--agents" || a.starts_with("--agents=")) {
        let p = PathBuf::from(valeur(args, "--project-root").unwrap_or_else(|| ".".into()));
        return crate::compact::main(&p, args.iter().any(|a| a == "--apply" || a == "--go"));
    }
    if args.iter().any(|a| a == "--profils") {
        let p0 = PathBuf::from(valeur(args, "--project-root").unwrap_or_else(|| ".".into()));
        let p = p0.canonicalize().unwrap_or(p0);
        return mise_a_niveau(&p, args.iter().any(|a| a == "--apply" || a == "--go"));
    }
    let Some(liste) = valeur(args, "--agents") else {
        eprintln!("harnais equipe : --agents est requis (noms séparés par des virgules ; \
le PREMIER hérite de l'état existant)");
        return 2;
    };
    let appliquer = args.iter().any(|a| a == "--apply" || a == "--go");
    let p0 = PathBuf::from(valeur(args, "--project-root").unwrap_or_else(|| ".".into()));
    let p = p0.canonicalize().unwrap_or(p0);
    let noms: Vec<String> = liste.split(',').map(|x| x.trim().to_string()).filter(|x| !x.is_empty()).collect();
    let (mut rap, mut reste): (Vec<(String, String)>, Vec<String>) = (vec![], vec![]);

    let (f, existants, disp) = forme(&p);
    let compact = args.iter().any(|a| a == "--compact")
        || existants.iter().any(|n| crate::agent::compact(&p, n));
    if compact && !disp.cerveau {
        eprintln!("equipe : l'architecture compacte exige brain/ ; migrer la mémoire d'abord");
        return 1;
    }
    if compact && f == "mono" && ["state.md", "todo.md"].iter()
        .any(|n| !disp.esprit_mono().join(n).is_file()) {
        eprintln!("equipe : mémoire mono incomplète ; compléter avant la conversion compacte");
        return 1;
    }
    crate::copilot::avertit_ancien(&p);
    if f == "ancienne" {
        println!("Ce projet n'a de faits ni dans `brain/fact/` ni dans `.fact/`. \
Lancer d'abord la migration de mémoire, puis revenir.");
        return 1;
    }
    if noms.is_empty() || noms.iter().any(|n| existants.contains(n)) {
        eprintln!("equipe : liste vide ou agent déjà présent ; aucun fichier n'a été écrasé");
        return 1;
    }
    if noms.iter().any(|n| n == "." || n == ".." || n.contains(['/', '\\', ':'])
        || crate::agent::nom_de_profil(n).is_empty()) {
        eprintln!("equipe : nom d'agent invalide ; aucune écriture");
        return 1;
    }
    if compact && f == "multi" && existants.iter().any(|n| !crate::agent::compact(&p, n)) {
        eprintln!("equipe : exporter toute l'équipe avec --compact avant d'ajouter un agent compact ; aucune écriture");
        return 1;
    }
    if compact && noms.iter().any(|n| crate::agent::profil(&p, n).exists()) {
        eprintln!("equipe : un profil demandé existe déjà ; réconcilier avant de créer l'agent");
        return 1;
    }
    let tous_prevus: Vec<String> = existants.iter().chain(noms.iter()).cloned().collect();
    if let Some(c) = profils_en_collision(&tous_prevus) {
        eprintln!("equipe : {c} — le menu d'agent n'en montrerait qu'un ; aucun fichier n'a été écrit");
        return 1;
    }
    let racine = match crate::copilot::racine_git(&p) { Ok(r) => r, Err(e) => { eprintln!("equipe : {e}"); return 1; } };
    if let Err(e) = reglages_racine(&p, appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
    let (neufs, tous): (Vec<String>, Vec<String>);
    if f == "mono" {
        let premier = noms[0].clone();
        let cible = if compact { disp.esprit(&premier) } else { p.join("agents").join(&premier) };
        let (src, dst) = (disp.esprit_mono(), disp.esprit(&premier));
        // Cerveau : `brain/mind/` NE bouge PAS, ce sont ses FICHIERS qui
        // descendent d'un cran. Ancienne forme : le dossier descend en entier.
        rap.push(("→".into(), format!("{} -> {} (l'agent qui était là garde sa mémoire)", disp.rel(&src), disp.rel(&dst))));
        if appliquer {
            if disp.cerveau {
                let _ = std::fs::create_dir_all(&dst);
                for fic in trie(&src) {
                    if fic.is_file() {
                        let cible_f = dst.join(nom(&fic));
                        if !git(&p, &["mv", &disp.rel(&fic), &disp.rel(&cible_f)]) {
                            let _ = std::fs::rename(&fic, &cible_f);
                        }
                    }
                }
            } else {
                if let Some(pp) = dst.parent() { let _ = std::fs::create_dir_all(pp); }
                if !git(&p, &["mv", &disp.rel(&src), &disp.rel(&dst)]) { let _ = std::fs::rename(&src, &dst); }
            }
        }
        if let Err(e) = perimetre_agent(&cible, &p, &noms[1..], appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
        if !compact { porte_les_non_herites(&p, &cible, appliquer, &mut rap); }

        // Le premier agent hérite de l'état, pas d'un rôle : il lui faut le sien.
        if compact {
            if let Err(e) = profil_role(&p, &premier, appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
        }
        else if cible.join("CLAUDE.md").exists() { rap.push(("⚠".into(), format!("agents/{premier}/CLAUDE.md existe : ne pas doubler le rôle"))); }
        else {
            rap.push(("+".into(), format!("agents/{premier}/AGENTS.md — rôle à remplir")));
            if appliquer && !cible.join("AGENTS.md").exists() { let _ = std::fs::write(cible.join("AGENTS.md"), role(&premier)); }
        }
        neufs = noms[1..].to_vec();
        tous = noms.clone();

    } else {
        neufs = noms.clone();
        tous = existants.iter().chain(noms.iter()).cloned().collect();

    }

    if f == "multi" {
        for ancien in &existants {
            let d = crate::agent::contexte(&p, ancien);
            let autres: Vec<String> = tous.iter().filter(|n| *n != ancien).cloned().collect();
            if let Err(e) = perimetre_agent(&d, &p, &autres, appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
        }
    }

    let jour = chrono::Local::now().format("%Y-%m-%d").to_string();
    for n in &neufs {
        let d = if compact { disp.esprit(n) } else { p.join("agents").join(n) };
        let esprit = disp.esprit(n);
        rap.push(("+".into(), format!("{} — esprit neuf ; rôle et périmètre {}", disp.rel(&esprit),
            if compact { "centralisés" } else { "dans agents/" })));
        if appliquer {
            let _ = std::fs::create_dir_all(&esprit);
            let _ = std::fs::create_dir_all(&d);
            if !compact && !d.join("CLAUDE.md").exists() && !d.join("AGENTS.md").exists() { let _ = std::fs::write(d.join("AGENTS.md"), role(n)); }
            let _ = std::fs::write(esprit.join("state.md"), format!(
                "---\nmaj: {}\nsante: vert\njalon: [LE_PROCHAIN_CAILLOU de ce lot]\n---\n\n# État — {}\n\n[où en est CET agent]\n", jour, n));
            let _ = std::fs::write(esprit.join("todo.md"), format!("# À faire — {}\n\n- [ ] [première tâche de ce lot]\n", n));
        }
        if compact {
            if let Err(e) = profil_role(&p, n, appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
        }
        let autres: Vec<String> = tous.iter().filter(|x| *x != n).cloned().collect();
        crate::copilot::avertit_ancien(&d);
        if let Err(e) = perimetre_agent(&d, &p, &autres, appliquer, &mut rap) { eprintln!("equipe : {e}"); return 1; }
        if !compact { porte_les_non_herites(&p, &d, appliquer, &mut rap); }
    }

    // LES PROFILS DU MENU D'AGENT — tous, anciens compris : un projet converti
    // avant 0.16.0 n'en a aucun.
    if !compact { for n in &tous { profil(&racine, &p, n, &disp.esprit(n), appliquer, &mut rap); } }

    // LE CARNET D'ÉQUIPE — LU partout, il ne serait CRÉÉ nulle part sans cet
    // appel. On appelle la règle qui le place, on ne la recopie pas.
    if appliquer {
        match crate::carnet::amorce(&p) {
            Some(e) => rap.push(("+".into(), format!("carnet d'équipe amorcé : {}", rel(&p, &e)))),
            None => rap.push(("⚠".into(), "carnet d'équipe NON amorcé : le programme n'a rien rendu".into())),
        }
    } else {
        rap.push(("+".into(), "carnet d'équipe à amorcer (créé à l'application)".into()));
    }

    // Le cinquième fichier, qui n'existe qu'en équipe : chacun connaît sa
    // frontière et ignore celle des autres — ici, chacun lit TOUT le découpage.
    let fichier_roles = disp.faits.join("roles.md");
    if disp.faits.is_dir() && !fichier_roles.exists() {
        rap.push(("+".into(), format!("{}/roles.md — qui tient quoi, à remplir", disp.etiquette_faits())));
        if appliquer {
            // La maison des faits est NOMMÉE, jamais écrite en dur : le gabarit
            // sert les deux organisations. Écrire `.fact/` en dur le poserait
            // aussi dans un projet en `brain/`.
            let mut texte = GABARIT_ROLES.replace("[PROJECT_NAME]", &nom(&p))
                .replace("[FAITS]", disp.etiquette_faits());
            for (i, n) in tous.iter().enumerate() {
                texte = texte.replace(&format!("`<agent-{}>`", i + 1), &format!("`{}`", n));
            }
            let _ = std::fs::write(&fichier_roles, texte);
        }
        reste.push(format!("REMPLIR {}/roles.md — qui tient quoi, et surtout LES ZONES PARTAGÉES. Un \
périmètre propre se lit dans la garde Copilot ; une zone partagée ne se lit nulle part, et c'est là que les \
collisions arrivent. Ce sont des FAITS : ça s'écrit à la demande de @user (` # fact-ok` au commit).",
            disp.etiquette_faits()));
    }
    reste.push(format!("DÉCOUPER AGENTS.md — le commun reste à la racine, le rôle descend dans {}. \
Contrôle de sortie : aucune phrase du bas ne resterait vraie pour un autre agent.",
        if compact { ".github/agents/<nom>.agent.md" } else { "agents/<nom>/AGENTS.md" }));
    reste.push("ÉCRIRE LES PÉRIMÈTRES en dossiers dans chaque perimetre.json : les dossiers interdits ne couvrent \
que les dossiers d'agents. Le code, lui, n'est pas partagé au hasard — dire qui tient quoi.".into());
    reste.push(a_commiter(&tous));

    println!("── agents — {} ({}){}", nom(&p), f, if appliquer { "" } else { "  [DRY-RUN]" });
    for (signe, ligne) in &rap { println!("  {} {}", signe, ligne); }
    println!("\n── À reprendre à la main");
    for r in &reste { println!("  · {}", r); }
    if !appliquer { println!("\nDry-run. Relancer avec --apply pour écrire."); }
    0
}

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn qa_historique_a_un_allow_documentaire_et_conserve_les_restrictions() {
        for cerveau in [false, true] {
            let p = std::env::temp_dir().join(format!("equipe-qa-historique-{cerveau}-{}", std::process::id()));
            std::fs::create_dir_all(p.join(if cerveau { "brain/fact" } else { ".fact" })).unwrap();
            let d = p.join("agents/QA");
            std::fs::create_dir_all(&d).unwrap();
            assert!(Command::new("git").args(["init", "-q"]).current_dir(&p).status().unwrap().success());
            assert!(perimetre_agent(&d, &p, &["OPS".into()], true, &mut vec![]).is_ok());
            let ecrit = |f: &str| crate::copilot::decision(&json!({"tool_name":"Write","tool_input":{"file_path":p.join(f)}}), &d);
            let fact = if cerveau { "brain/fact/base.md" } else { ".fact/base.md" };
            let mind = if cerveau { "brain/mind/QA/todo.md" } else { "agents/QA/.mind/todo.md" };
            for f in [fact, mind, "agents/QA/livrables/plan.md"] {
                assert!(ecrit(f).unwrap().is_none(), "{f}");
            }
            for f in ["src/code.py", ".env", "docs/audit/source.md", "agents/OPS/livrables/a.md"] {
                assert!(ecrit(f).unwrap().is_some(), "{f}");
            }
            assert!(std::fs::read_to_string(d.join(".github/copilot/perimetre.json")).unwrap().contains("allow"));
            std::fs::write(d.join(".github/copilot/perimetre.json"), r#"{"allow":[],"deny":["."]}"#).unwrap();
            assert!(perimetre_agent(&d, &p, &["OPS".into()], true, &mut vec![]).is_ok());
            assert!(ecrit(fact).unwrap().is_some(), "mise à niveau ne lève pas un refus existant");
            std::fs::remove_dir_all(&p).unwrap();
        }
    }

    #[test]
    fn creation_et_ajout_compacts_sans_dossiers_agents() {
        let p = std::env::temp_dir().join(format!("equipe-compact-{}", std::process::id()));
        std::fs::create_dir_all(p.join("brain/fact")).unwrap();
        std::fs::create_dir_all(p.join("brain/mind")).unwrap();
        std::fs::write(p.join("brain/mind/state.md"), "état mono").unwrap();
        std::fs::write(p.join("brain/mind/todo.md"), "todo mono").unwrap();
        assert!(Command::new("git").args(["init", "-q"]).current_dir(&p).status().unwrap().success());
        let p = p.canonicalize().unwrap();
        let args = vec!["--project-root".into(), p.display().to_string(), "--agents".into(),
            "OPS,QA".into(), "--compact".into()];
        assert_eq!(main(&args), 0);
        assert!(!p.join(".github").exists(), "dry-run sans écriture");
        let mut args = args;
        args.push("--apply".into());
        assert_eq!(main(&args), 0);
        assert!(!p.join("agents").exists());
        assert!(crate::agent::profil(&p, "OPS").is_file());
        let qa = p.join("brain/mind/QA");
        assert!(!crate::copilot::lis_deny(&qa).unwrap().contains(&PathBuf::from(".")));
        for f in ["brain/fact/base.md", "brain/mind/QA/todo.md", "docs/livrables/QA/plan.md"] {
            assert!(crate::copilot::decision(&json!({"tool_name":"Write","tool_input":{"file_path":p.join(f)}}), &qa).unwrap().is_none(), "{f}");
        }
        for f in ["brain/fact/autre.md", "brain/fact/base.md/code.py", "brain/mind/OPS/todo.md", "docs/audit/a.md", "src/a.rs", ".env", ".github/agents/qa.agent.md"] {
            assert!(crate::copilot::decision(&json!({"tool_name":"Write","tool_input":{"file_path":p.join(f)}}), &qa).unwrap().is_some(), "{f}");
        }
        assert_eq!(main(&["--project-root".into(), p.display().to_string(), "--agents".into(),
            "PO".into(), "--apply".into()]), 0);
        assert!(!p.join("agents").exists(), "ajout conserve la forme compacte");
        assert!(crate::agent::profil(&p, "PO").is_file());
        assert!(crate::copilot::lis_deny(&p.join("brain/mind/OPS")).unwrap().contains(&PathBuf::from("docs/livrables/PO")));
        std::fs::remove_dir_all(&p).unwrap();
    }

    /// UN PROJET CONVERTI AVANT 0.16.0 : périmètres absolus vers le dossier
    /// principal, pas de profils, un profil écrit à la main. `--profils` le met à
    /// niveau sans rien écraser.
    #[test]
    fn la_mise_a_niveau_ecrit_les_profils_et_des_perimetres_relatifs() {
        let d = std::env::temp_dir().join(format!("equipe-profils-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join(".github/agents")).unwrap();
        assert!(Command::new("git").args(["init", "-q"]).current_dir(&d).status().unwrap().success());
        let d = d.canonicalize().unwrap();
        // Un absolu HORS du projet, sur cette plateforme : `/x` n'en est pas un sous Windows.
        let dehors = std::env::temp_dir().join(format!("hors-projet-{}", std::process::id()));
        let dehors = dehors.to_string_lossy().to_string();
        std::fs::create_dir_all(d.join("brain/fact")).unwrap();
        for a in ["OPS", "Projet QA"] {
            std::fs::create_dir_all(d.join("brain/mind").join(a)).unwrap();
            std::fs::write(d.join("brain/mind").join(a).join("state.md"), "---\nmaj: 2026-10-01\n---\n").unwrap();
            std::fs::create_dir_all(d.join("agents").join(a).join(".github/copilot")).unwrap();
        }
        std::fs::write(d.join("agents/OPS/.github/copilot/perimetre.json"),
            json!({"deny": [d.join("agents/Projet QA"), dehors]}).to_string()).unwrap();
        std::fs::write(d.join(".github/agents/ops.agent.md"), "à la main\n").unwrap();

        assert_eq!(mise_a_niveau(&d, true), 0);
        let v: Value = serde_json::from_str(&std::fs::read_to_string(
            d.join("agents/OPS/.github/copilot/perimetre.json")).unwrap()).unwrap();
        assert_eq!(v["deny"], json!(["agents/Projet QA", dehors]), "relatif sous le projet, absolu hors");
        assert_eq!(std::fs::read_to_string(d.join(".github/agents/ops.agent.md")).unwrap(), "à la main\n",
                   "un profil existant n'est jamais écrasé");
        let qa = std::fs::read_to_string(d.join(".github/agents/projet-qa.agent.md")).unwrap();
        assert!(qa.starts_with("---\nname: projet-qa\n"), "{qa}");
        assert!(qa.contains("agents/Projet QA/AGENTS.md") && qa.contains("brain/mind/Projet QA/state.md"));
        assert_eq!(crate::agent::correspond("projet-qa", &["OPS".into(), "Projet QA".into()]).as_deref(),
                   Some("Projet QA"), "le nom écrit dans le profil désigne bien le dossier");
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn deux_agents_au_meme_profil_sont_refuses() {
        assert!(profils_en_collision(&["QA".into(), "qa".into()]).is_some());
        assert!(profils_en_collision(&["Q A".into(), "Q-A".into()]).is_some());
        assert!(profils_en_collision(&["OPS".into(), "PO".into(), "QA".into()]).is_none());
    }

    #[test]
    fn conversion_du_deny_racine_ne_le_supprime_pas() {
        let p = std::env::temp_dir().join(format!("equipe-deny-racine-{}", std::process::id()));
        let d = p.join("agents/QA");
        std::fs::create_dir_all(d.join(".github/copilot")).unwrap();
        assert!(Command::new("git").args(["init", "-q"]).current_dir(&p).status().unwrap().success());
        let p = p.canonicalize().unwrap();
        std::fs::write(d.join(".github/copilot/perimetre.json"), json!({"deny":[p]}).to_string()).unwrap();
        assert!(perimetre_agent(&d, &p, &["OPS".into()], true, &mut vec![]).is_ok());
        assert!(crate::copilot::lis_deny(&d).unwrap().contains(&PathBuf::from(".")));
        std::fs::remove_dir_all(&p).unwrap();
    }

    #[test]
    fn deux_noms_qui_donnent_la_meme_cle_se_voient() {
        assert_eq!(slug("/Users/x/Projet Studio"), "-Users-x-Projet-Studio");
        assert_eq!(slug("Q A"), slug("Q-A"), "deux noms, une adresse : la collision que le refus attrape");
    }
}
