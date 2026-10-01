//! LA VUE D'ÉQUIPE — lit la mémoire de tous les projets d'un atelier et en rend
//! deux vues : le rapport terminal (le DIAGNOSTIC) et une page autonome (la VUE).
//! Porté de `agentic-team.py`, à l'octet : il rend ce que rendait le script sur
//! l'atelier fabriqué de `controles/vue-equipe.sh`, témoin figé AVANT le
//! retrait du script.
//!
//!     harnais equipe-vue                     le rapport terminal
//!     harnais equipe-vue --html team.html    une page autonome
//!     harnais equipe-vue --projet <nom>      un seul projet
//!
//! **Une seule lecture, deux sorties** : deux analyseurs se désaccorderaient
//! sans que personne le voie. **Strictement en lecture** : n'écrit que la page
//! demandée. La page est **autonome** — ni serveur, ni ressource externe.
//!
//! LA LECTURE A ÉTÉ REFAITE, et c'est dit : le script lisait l'organisation
//! d'avant, et des réglages qui ne veulent plus rien dire depuis le paquet. Le
//! garder à l'octet classerait des projets « aucune mémoire » alors qu'ils sont
//! servis, et donnerait des conseils qui renvoient à deux compétences
//! disparues (la mise à niveau et la synchronisation d'avant le paquet). Un
//! tableau de bord qui désigne presque tout l'atelier comme à refaire est pire
//! qu'aucun tableau : on apprend à ne plus le lire.
//!
//! CE QU'IL LIT DÉSORMAIS, et d'où :
//! · la mémoire, PAR LE RÉSOLVEUR — la même règle que le briefing, toutes les
//!   formes, jamais un chemin recomposé ;
//! · le PAQUET, dans le dossier d'où chaque agent se LANCE : la racine en mono,
//!   `agents/<nom>` à plusieurs — les réglages de la racine y sont inertes ;
//! · trois choses séparées, parce que chacune peut manquer seule et en silence :
//!   le paquet DÉCLARÉ, la marketplace INSCRITE (sans quoi Copilot ne le
//!   charge pas), et la TRACE D'ENTRÉE qui prouve qu'il a servi, avec la
//!   version qui l'a écrite — toutes copies de travail confondues : un agent
//!   peut se lancer depuis une copie, et l'arbre principal n'a alors de lui
//!   qu'une trace ancienne.

use fancy_regex::Regex as FRegex;
use regex::Regex;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

const CHAMPS: &[&str] = &["maj", "cap", "sante", "jalon", "balle", "depuis", "attente", "suivant"];
const MIND_ATTENDU: &[&str] = &["state.md", "todo.md"];
/// La taxonomie d'avant, rangée dans `.memory/`.
const ANCIENS: &[&str] = &["charter.md", "business.md", "clients.md", "overview.md"];
const MONTENT: &[&str] = &["state.md", "rules.md", "architecture.md"];
/// `copilot-harness` est la SOURCE du paquet, pas un agent : lui conseiller
/// `harnais adopte`, ce serait brancher le paquet sur son propre code.
const IGNORE: &[&str] = &["copilot-harness"];
const DEHORS: &str = "dehors";
const TIEDE_JOURS: i64 = 7;
const PERIME_JOURS: i64 = 28;

fn re(s: &'static str, c: &'static OnceLock<Regex>) -> &'static Regex { c.get_or_init(|| Regex::new(s).unwrap()) }
fn entete_re() -> &'static Regex { static C: OnceLock<Regex> = OnceLock::new(); re(r"(?s)\A\s*---\s*\n(.*?)\n---\s*(\n|$)", &C) }
fn tache_re() -> &'static Regex { static C: OnceLock<Regex> = OnceLock::new(); re(r"^\s*[-*]\s*\[( |x|X|>|~)\]\s+(.+?)\s*$", &C) }
fn prio_re() -> &'static Regex { static C: OnceLock<Regex> = OnceLock::new(); re(r"!(haut|moyen|bas)\b", &C) }
fn chantiers_re() -> &'static Regex { static C: OnceLock<Regex> = OnceLock::new(); re(r"(?im)^#{1,3}\s*chantiers\b.*$", &C) }
fn import_re() -> &'static Regex { static C: OnceLock<Regex> = OnceLock::new(); re(r"(?m)^@(\S+)", &C) }
/// Le `@` doit ouvrir un mot — sinon `root@serveur` serait lu comme un
/// destinataire nommé « serveur ».
fn qui_re() -> &'static FRegex {
    static C: OnceLock<FRegex> = OnceLock::new();
    C.get_or_init(|| FRegex::new(r"(?:^|(?<=\s))@([A-Za-zÀ-ÿ][\w-]*)\b").unwrap())
}

fn lis(p: &Path) -> String { std::fs::read(p).map(|o| String::from_utf8_lossy(&o).to_string()).unwrap_or_default() }
fn nom(p: &Path) -> String { p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default() }
fn trie(d: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(d).map(|it| it.flatten().map(|e| e.path()).collect()).unwrap_or_default();
    v.sort();
    v
}
fn md_de(d: &Path, ext: &str) -> Vec<String> {
    let mut v: Vec<String> = trie(d).iter()
        .filter(|p| p.extension().map(|e| e == ext).unwrap_or(false)).map(|p| nom(p)).collect();
    v.sort();
    v
}
/// Tranche en CARACTÈRES, comme `s[:n]` en Python — jamais au milieu d'un octet.
fn coupe(s: &str, n: usize) -> String { s.chars().take(n).collect() }
fn gauche(s: &str, n: usize) -> String {
    let l = s.chars().count();
    if l >= n { s.to_string() } else { format!("{}{}", s, " ".repeat(n - l)) }
}

type Entete = Vec<(String, String)>;
fn get<'a>(e: &'a Entete, k: &str) -> Option<&'a str> { e.iter().find(|(x, _)| x == k).map(|(_, v)| v.as_str()) }
fn set(e: &mut Entete, k: &str, v: String) {
    match e.iter_mut().find(|(x, _)| x == k) { Some(p) => p.1 = v, None => e.push((k.into(), v)) }
}

fn entete(texte: &str) -> Entete {
    let Some(m) = entete_re().captures(texte) else { return vec![] };
    let mut d = vec![];
    for ligne in m.get(1).map(|x| x.as_str()).unwrap_or("").lines() {
        if let Some((k, v)) = ligne.split_once(':') {
            let k = k.trim().to_lowercase();
            if CHAMPS.contains(&k.as_str()) { set(&mut d, &k, v.trim().to_string()); }
        }
    }
    d
}

#[derive(Clone)]
struct Tache { etat: &'static str, titre: String, prio: String, qui: String }

/// Le fichier ENTIER, toutes sections confondues : une version antérieure ne
/// lisait que la section « Chantiers » et rendait zéro tâche sur des fichiers
/// pleins. Le titre reste reconnu, pour les anciens fichiers qui la bornaient.
fn taches(texte: &str) -> Vec<Tache> {
    if texte.is_empty() { return vec![]; }
    let ms: Vec<_> = chantiers_re().find_iter(texte).collect();
    let corps = match ms.first() {
        Some(m) => &texte[m.end()..ms.get(1).map(|n| n.start()).unwrap_or(texte.len())],
        None => texte,
    };
    let mut out = vec![];
    for ligne in corps.lines() {
        let Some(t) = tache_re().captures(ligne) else { continue };
        let titre = t.get(2).unwrap().as_str();
        let prio = prio_re().captures(titre).map(|c| c[1].to_string()).unwrap_or_default();
        let qui = qui_re().captures(titre).ok().flatten()
            .and_then(|c| c.get(1).map(|x| x.as_str().to_string())).unwrap_or_default();
        let sans_qui = qui_re().replace_all(titre, "").to_string();
        let net = prio_re().replace_all(&sans_qui, "").to_string();
        let net = net.trim_matches(|c| c == ' ' || c == '-' || c == '—' || c == '·').to_string();
        let etat = match &t[1] { "x" | "X" => "fait", ">" | "~" => "encours", _ => "afaire" };
        out.push(Tache { etat, titre: net, prio, qui });
    }
    out
}

fn fraicheur(maj: &str, aujourdhui: chrono::NaiveDate) -> (&'static str, Option<i64>) {
    let d = chrono::NaiveDate::parse_from_str(maj, "%Y-%m-%d")
        .or_else(|_| chrono::NaiveDate::parse_from_str(maj, "%Y%m%d"));
    let Ok(d) = d else { return ("illisible", None) };
    let j = (aujourdhui - d).num_days();
    if j > PERIME_JOURS { ("perime", Some(j)) } else if j > TIEDE_JOURS { ("tiede", Some(j)) } else { ("frais", Some(j)) }
}

/// Un dossier d'où un agent se LANCE — la racine en mono, `agents/<nom>` à
/// plusieurs. Ses réglages et sa trace d'entrée vivent là.
struct Lancement {
    nom: Option<String>,
    /// `paquet` · `hooks` (l'ancien câblage local) · `non`
    declare: &'static str,
    /// `None` : les inscriptions n'ont pas pu être lues — on ne conclut rien.
    inscrit: Option<bool>,
    /// La version que cette inscription chargera au prochain démarrage.
    inscrite: Option<String>,
    /// La plus récente, toutes copies de travail confondues : (version, instant).
    /// Une trace sans version a été écrite avant la 0.10.0.
    trace: Option<(Option<String>, f64)>,
    deny: Option<usize>,
}

struct Harnais {
    git: bool,
    /// Le résolveur a trouvé un dépôt : sans lui, il ne cherche aucune mémoire.
    depot: bool,
    /// `brain` · `en-place` · `deportee` · `ambigue` · `ancienne` · `mind-seul` · `aucune`
    forme: &'static str,
    fact_dir: Option<PathBuf>, fact: Vec<String>,
    minds: Vec<PathBuf>, mind: Vec<String>,
    manque: Vec<String>, surplus: Vec<String>, anciens: Vec<String>,
    lancements: Vec<Lancement>, oriente: bool, logs: usize,
}

/// Les inscriptions au paquet, lues UNE fois par relevé. SURCHARGEABLE, et
/// uniquement pour le mesurer : sans elle, le contrôle jugerait l'état de la
/// machine qui l'exécute au lieu de son atelier fabriqué.
enum Inscriptions { Illisibles, Toutes(Option<String>), Chemins(Vec<(PathBuf, Option<String>)>) }

fn inscriptions() -> Inscriptions {
    let f = crate::hote::maison_copilot().join("settings.json");
    if !f.exists() { return Inscriptions::Chemins(vec![]); }
    let Ok(v) = serde_json::from_str::<Value>(&lis(&f)) else { return Inscriptions::Illisibles };
    let actif = v.get("enabledPlugins").and_then(|e| e.get(crate::copilot::PAQUET))
        .and_then(Value::as_bool) == Some(true);
    if actif && resolu(&v) { Inscriptions::Toutes(None) } else { Inscriptions::Chemins(vec![]) }
}

fn resolu(v: &Value) -> bool {
    let local = v.get("extraKnownMarketplaces").and_then(|m| m.get(crate::copilot::MARCHE))
        .and_then(|m| m.get("source"))
        .filter(|s| s.get("source").and_then(Value::as_str) == Some("directory"))
        .and_then(|s| s.get("path")).and_then(Value::as_str)
        .is_some_and(|p| Path::new(p).join(".github/plugin/plugin.json").is_file());
    local || crate::hote::maison_copilot().join("installed-plugins/atelier-copilot/harnais").is_dir()
}

/// Les copies de travail du dépôt qui porte `p`, `p` compris.
///
/// Un agent peut se lancer depuis une copie de travail (par exemple
/// `.worktrees/<nom>`) ; l'arbre principal n'a alors de lui qu'une trace
/// ancienne. Ne lire que l'arbre principal, ce serait crier « jamais servi »
/// sur un agent qui tourne.
fn copies(p: &Path) -> Vec<PathBuf> {
    let mut v = vec![p.to_path_buf()];
    let Ok(o) = std::process::Command::new("git").args(["worktree", "list", "--porcelain"])
        .current_dir(p).output() else { return v };
    if !o.status.success() { return v; }
    for l in String::from_utf8_lossy(&o.stdout).lines() {
        if let Some(w) = l.strip_prefix("worktree ") {
            let w = PathBuf::from(w);
            let w = w.canonicalize().unwrap_or(w);
            if !v.contains(&w) { v.push(w); }
        }
    }
    v
}

fn maintenant_s() -> f64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}
fn jours_depuis(t: f64) -> i64 { ((maintenant_s() - t) / 86400.0).floor().max(0.0) as i64 }

fn lancement(p: &Path, l: &Path, nom: Option<String>, cps: &[PathBuf], ins: &Inscriptions) -> Lancement {
    let rel = l.strip_prefix(p).map(|r| r.to_path_buf()).unwrap_or_default();
    let jumeaux: Vec<PathBuf> = cps.iter().map(|c| c.join(&rel)).filter(|d| d.is_dir()).collect();
    let mut declare = "non";
    let settings = crate::copilot::settings(p);
    let local: Option<Value> = serde_json::from_str(&lis(&settings)).ok();
    if let Some(s) = &local {
        if s.get("enabledPlugins").and_then(|e| e.get(crate::copilot::PAQUET))
            .and_then(Value::as_bool) == Some(true) { declare = "paquet"; }
    }
    let deny = crate::copilot::perimetre(l).ok().map(|d| d.len());
    let (mut inscrit, mut inscrite) = match ins {
        Inscriptions::Illisibles => (None, None),
        Inscriptions::Toutes(v) => (Some(true), v.clone()),
        Inscriptions::Chemins(c) => {
            let j: Vec<PathBuf> = jumeaux.iter().map(|j| j.canonicalize().unwrap_or_else(|_| j.clone())).collect();
            match c.iter().find(|(p, _)| j.contains(p)) {
                Some((_, v)) => (Some(true), v.clone()), None => (Some(false), None),
            }
        }
    };
    if declare == "paquet" && inscrit != Some(true) {
        let global: Option<Value> = serde_json::from_str(&lis(&crate::hote::maison_copilot().join("settings.json"))).ok();
        if local.as_ref().is_some_and(resolu) || global.as_ref().is_some_and(resolu) {
            inscrit = Some(true); inscrite = None;
        }
    }
    let trace = jumeaux.iter()
        .filter_map(|j| serde_json::from_str::<Value>(&lis(&crate::briefing::etat_du_briefing(j))).ok())
        .filter_map(|v| v.get("derniere").and_then(|d| d.as_f64())
            .map(|d| (v.get("version").and_then(|x| x.as_str()).map(String::from), d)))
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
    Lancement { nom, declare, inscrit, inscrite, trace, deny }
}

fn harnais(p: &Path, ins: &Inscriptions) -> Harnais {
    let p = &p.canonicalize().unwrap_or_else(|_| p.to_path_buf());
    let agents: Vec<PathBuf> = trie(&p.join("agents")).into_iter()
        .filter(|d| d.is_dir() && (d.join("AGENTS.md").is_file() || d.join("CLAUDE.md").is_file() || d.join(".github/copilot").is_dir())).collect();
    let dossiers: Vec<(Option<String>, PathBuf)> = if agents.is_empty() { vec![(None, p.clone())] }
        else { agents.iter().map(|d| (Some(nom(d)), d.clone())).collect() };
    let r = crate::memoire::resous(&dossiers[0].1);
    let anciens: Vec<String> = ANCIENS.iter().chain(MONTENT.iter())
        .filter(|n| p.join(".memory").join(n).is_file()).map(|s| s.to_string()).collect();
    use crate::memoire::Forme;
    let forme = match r.forme {
        Forme::Brain => "brain", Forme::EnPlace => "en-place", Forme::Deportee => "deportee",
        Forme::Ambigue => "ambigue",
        Forme::HorsDepot | Forme::SansMemoire => if !anciens.is_empty() { "ancienne" }
                            else if p.join(".mind").is_dir() { "mind-seul" } else { "aucune" },
    };
    let (mut manque, mut surplus) = (vec![], vec![]);
    let aff = |d: &Path| format!("{}/", crate::socle::chemin_affiche(p, d));
    let fact = match &r.fact {
        Some(d) => {
            let ici = if d.is_dir() { md_de(d, "md") } else { vec![] };
            for a in crate::socle::FAITS_MONO {
                if !ici.contains(&a.to_string()) { manque.push(format!("{}{}", aff(d), a)); }
            }
            for x in &ici {
                if !crate::socle::faits_tous().contains(&x.as_str()) { surplus.push(format!("{}{}", aff(d), x)); }
            }
            ici
        }
        None => vec![],
    };
    let (mut minds, mut mind) = (vec![], vec![]);
    for (_, l) in &dossiers {
        let Some(m) = crate::memoire::resous(l).mind else { continue };
        let ici = if m.is_dir() { md_de(&m, "md") } else { vec![] };
        for a in MIND_ATTENDU { if !ici.contains(&a.to_string()) { manque.push(format!("{}{}", aff(&m), a)); } }
        for x in &ici { if !MIND_ATTENDU.contains(&x.as_str()) { surplus.push(format!("{}{}", aff(&m), x)); } }
        mind.extend(ici.iter().map(|x| format!("{}{}", aff(&m), x)));
        if m.is_dir() { minds.push(m); }
    }
    // Une mémoire que le résolveur ne sert pas garde un état LISIBLE : le
    // tableau le montre, pour que « à trier » dise aussi depuis quand.
    if minds.is_empty() {
        if let Some(m) = [".mind", ".memory"].iter().map(|c| p.join(c)).find(|m| m.join("state.md").is_file()) {
            minds.push(m);
        }
    }
    // Les instructions du projet (`AGENTS.md`, ou un `CLAUDE.md` que Copilot lit
    // aussi) nomment-elles la mémoire ? Les `@imports` comptent. Depuis le
    // briefing c'est une information, plus un verdict : le harnais sert
    // l'index de la mémoire à l'entrée, qu'il la nomme ou non.
    let mut oriente = false;
    if p.join("AGENTS.md").is_file() || p.join("CLAUDE.md").is_file() {
        let (mut vu, mut restants): (Vec<PathBuf>, Vec<PathBuf>) = (vec![], vec![if p.join("AGENTS.md").is_file() { p.join("AGENTS.md") } else { p.join("CLAUDE.md") }]);
        while let Some(f) = if vu.len() < 8 { restants.pop() } else { None } {
            if vu.contains(&f) || !f.is_file() { continue; }
            vu.push(f.clone());
            let t = lis(&f);
            if t.contains(".mind") || t.contains("brain/") || t.contains("memoire/") { oriente = true; break; }
            for c in import_re().captures_iter(&t) {
                let j = f.parent().unwrap_or(Path::new("")).join(&c[1]);
                restants.push(j.canonicalize().unwrap_or(j));
            }
        }
    }
    let cps = copies(p);
    Harnais {
        git: p.join(".git").exists(), depot: r.racine.is_some(), forme, fact_dir: r.fact.clone().filter(|d| d.is_dir()), fact,
        minds, mind, manque, surplus, anciens,
        lancements: dossiers.iter().map(|(n, l)| lancement(p, l, n.clone(), &cps, ins)).collect(),
        oriente, logs: if p.join(".logs").is_dir() { md_de(&p.join(".logs"), "md").len() } else { 0 },
    }
}

fn forme_mot(h: &Harnais) -> &'static str {
    match h.forme {
        "brain" => "brain/", "en-place" => "en place (.fact/ .mind/)", "deportee" => "déportée (memoire/)",
        "ambigue" => "À CHEVAL", "ancienne" => "taxonomie d'avant", "mind-seul" => "tout dans .mind/",
        _ => "aucune",
    }
}

fn jauge(h: &Harnais) -> String {
    let n = h.lancements.len();
    let equipe = h.lancements.iter().any(|l| l.nom.is_some());
    let agents = if equipe { format!(" · {} agent(s)", n) } else { String::new() };
    // À plusieurs, les faits en tiennent un de plus : qui tient quoi.
    let faits = crate::socle::FAITS_MONO.len() + usize::from(equipe);
    format!("faits {}/{} · état {}/{}{}", h.fact.len(), faits, h.mind.len(), MIND_ATTENDU.len() * n, agents)
}

/// `0.10.4-local` → (0, 10, 4). Ce qui ne se lit pas ne se compare pas.
fn numeros(v: &str) -> Option<(u32, u32, u32)> {
    let mut it = v.split(|c: char| !c.is_ascii_digit()).filter(|x| !x.is_empty()).map(|x| x.parse().ok());
    Some((it.next()??, it.next()??, it.next()??))
}

fn ligne_paquet(l: &Lancement) -> String {
    format!("{}déclaré {} · inscrit {} · servi {}",
        l.nom.as_ref().map(|n| format!("{} — ", n)).unwrap_or_default(),
        match l.declare { "paquet" => "oui", _ => "NON" },
        match l.inscrit { Some(true) => "oui", Some(false) => "NON", None => "?" },
        match &l.trace {
            None => "NON".to_string(),
            Some((v, t)) => format!("{} il y a {} j", v.as_deref().unwrap_or("avant 0.10.0"), jours_depuis(*t)),
        })
}

/// `A, B : ` à plusieurs — rien en mono : l'agent EST le projet.
fn qui(ls: &[&Lancement]) -> String {
    let n: Vec<String> = ls.iter().filter_map(|l| l.nom.clone()).collect();
    if n.is_empty() { String::new() } else { format!("{} : ", n.join(", ")) }
}

/// Quoi faire. Le programme ne le fait pas — c'est une décision, pas un geste.
/// CHAQUE COMMANDE CITÉE ICI EXISTE : un conseil qui envoie vers une commande
/// morte apprend à ne plus lire les conseils (voir les essais).
fn verdict(h: &Harnais) -> (&'static str, String) {
    let brain = h.forme == "brain";
    if !h.depot {
        return ("sans-git", "Pas de dépôt git : le harnais ne cherche la mémoire que dans un dépôt, et ses gardes \
se déclenchent au commit. `git init`, puis relire.".into());
    }
    match h.forme {
        "aucune" => return ("neuf", "Aucune mémoire : `harnais adopte` la pose et branche le paquet — à blanc \
d'abord, `--go` pour écrire.".into()),
        "ancienne" => return ("ancien", format!("Ancienne taxonomie dans `.memory/` ({}) : aucun \
outil ne la migre — le tri se fait à la main, puis `harnais adopte`.", h.anciens.join(", "))),
        "mind-seul" => return ("ancien", "Tout dans `.mind/`, sans faits du projet : l'organisation d'avant les \
faits. Répartir faits et état à la main, puis `harnais brain-migre`.".into()),
        "ambigue" => return ("ambigu", "À cheval entre `brain/` et l'organisation d'avant : le harnais refuse de \
choisir et ne sert AUCUNE mémoire. `harnais brain-migre` termine la migration.".into()),
        _ => {}
    }
    let pose = if brain { "`harnais adopte --go` le pose sans rien écraser." }
               else { "à créer à la main — ou passer en `brain/` avec `harnais brain-migre`." };
    if h.mind.is_empty() && !h.fact.is_empty() {
        return ("sans-agent", format!("Des faits, aucun état d'agent — il manque {} : {}", h.manque.join(", "), pose));
    }
    if !h.manque.is_empty() { return ("incomplet", format!("Il manque {} : {}", h.manque.join(", "), pose)); }
    let non: Vec<&Lancement> = h.lancements.iter().filter(|l| l.declare == "non").collect();
    if !non.is_empty() {
        return ("non-branche", format!("{}Rien ne déclare le paquet : {}", qui(&non),
            if brain { "`harnais adopte --go` le branche." } else { "`harnais brain-migre`, puis `harnais adopte --go`." }));
    }
    let ni: Vec<&Lancement> = h.lancements.iter().filter(|l| l.declare == "paquet" && l.inscrit == Some(false)).collect();
    if !ni.is_empty() {
        return ("non-inscrit", format!("{}Paquet déclaré mais marketplace locale non résolue : vérifier le chemin dans .github/copilot/settings.json.", qui(&ni)));
    }
    let nm: Vec<&Lancement> = h.lancements.iter().filter(|l| l.declare == "paquet" && l.inscrit.is_none()).collect();
    if !nm.is_empty() {
        return ("non-mesure", format!("{}Les inscriptions au paquet n'ont pas pu être lues : qu'il se charge au \
prochain démarrage n'est PAS vérifié.", qui(&nm)));
    }
    let js: Vec<&Lancement> = h.lancements.iter().filter(|l| l.trace.is_none()).collect();
    if !js.is_empty() {
        return ("jamais-servi", format!("{}Aucune trace d'entrée : l'agent n'a pas démarré depuis qu'il est \
branché — ou le paquet ne se charge pas. Le démarrer, puis relire.", qui(&js)));
    }
    if !h.git {
        return ("sans-git", "Pas de dépôt git : les gardes se déclenchent au commit, elles sont donc inertes.".into());
    }
    if !h.surplus.is_empty() {
        return ("surplus", format!("La mémoire porte {} fichier(s) que le harnais ne prévoit pas ({}) : les faits \
en tiennent quatre, cinq à plusieurs ; l'état d'un agent, deux.", h.surplus.len(), h.surplus.join(", ")));
    }
    let sd: Vec<&Lancement> = h.lancements.iter().filter(|l| l.deny.unwrap_or(0) == 0).collect();
    if !sd.is_empty() {
        return ("sans-deny", format!("{}Aucune règle `deny` : ce qui doit être interdit ici ne l'est que par la \
prose, donc se redemande à chaque session.", qui(&sd)));
    }
    // LA RÉFÉRENCE EST CE QUI EST INSCRIT, pas la version de ce programme-ci :
    // c'est l'inscription que l'agent chargera à son prochain démarrage. Ce
    // programme ne sert qu'à voir si l'inscription elle-même a pris du retard.
    let ici = crate::version_annoncee();
    let vieilles: Vec<&Lancement> = h.lancements.iter()
        .filter(|l| matches!((l.inscrite.as_deref().and_then(numeros), numeros(ici)), (Some(a), Some(b)) if a < b)).collect();
    if !vieilles.is_empty() {
        let v = vieilles[0].inscrite.clone().unwrap_or_default();
        return ("inscription-vieille", format!("{}Inscrit en {} alors que le paquet en est à {} : dans le dossier, \
corriger la marketplace locale, puis redémarrer Copilot.", qui(&vieilles), v, ici));
    }
    let vieux: Vec<&Lancement> = h.lancements.iter().filter(|l| {
        let Some((v, _)) = &l.trace else { return false };
        let reference = l.inscrite.as_deref().unwrap_or(ici);
        match (v.as_deref().and_then(numeros), numeros(reference)) { (None, _) => true, (Some(a), Some(b)) => a < b, _ => false }
    }).collect();
    if !vieux.is_empty() {
        let d: Vec<String> = vieux.iter().map(|l| {
            let (v, t) = l.trace.as_ref().unwrap();
            format!("{}{} (entrée il y a {} j), {} inscrite",
                    l.nom.as_ref().map(|n| format!("{} — ", n)).unwrap_or_default(),
                    v.as_deref().unwrap_or("une version d'avant la 0.10.0"), jours_depuis(*t),
                    l.inscrite.as_deref().unwrap_or(ici))
        }).collect();
        return ("en-retard", format!("La session tourne encore sur {} : la nouvelle arrivera à son prochain \
démarrage.", d.join(" · ")));
    }
    if h.forme == "en-place" || h.forme == "deportee" {
        return ("v1", "Servi, en organisation d'avant (`.fact/`, `.mind/`) : `harnais brain-migre` la passe en \
`brain/` quand tu le décides.".into());
    }
    let v: Vec<String> = h.lancements.iter().filter_map(|l| l.trace.as_ref().and_then(|(v, _)| v.clone())).collect();
    ("ok", format!("Servi en {}, mémoire complète.", v.first().cloned().unwrap_or_default()))
}

struct Projet {
    nom: String, harnais: Harnais, champs: Entete, taches: Vec<Tache>,
    fraicheur: &'static str, jours: Option<i64>, verdict: &'static str, conseil: String,
    attente: Vec<Tache>, encours: usize, afaire: usize,
}

fn scanne(racine: &Path, un_seul: &str) -> Vec<Projet> {
    let aujourdhui = chrono::Local::now().date_naive();
    let ins = inscriptions();
    let mut dossiers = trie(racine);
    dossiers.sort_by_key(|d| nom(d).to_lowercase());
    let mut out = vec![];
    for d in dossiers {
        let n = nom(&d);
        if !d.is_dir() || n.starts_with('.') { continue; }
        if un_seul.is_empty() && IGNORE.contains(&n.as_str()) { continue; }
        if !un_seul.is_empty() && n.to_lowercase() != un_seul.to_lowercase() { continue; }
        let h = harnais(&d, &ins);
        // Une seule voix : l'état le plus en difficulté, et les tâches réunies.
        let (mut e, mut t): (Entete, Vec<Tache>) = (vec![], vec![]);
        for m in &h.minds {
            let x = entete(&lis(&m.join("state.md")));
            if !x.is_empty() && (e.is_empty() || get(&x, "sante") == Some("rouge")) { e = x; }
            t.extend(taches(&lis(&m.join("todo.md"))));
        }
        // Le `cap` appartient au PROJET : il vit dans les faits, là où le
        // résolveur les trouve — avant eux, dans l'état.
        if let Some(fd) = &h.fact_dir {
            let b = entete(&lis(&fd.join("base.md")));
            e.retain(|(k, _)| k != "cap");
            if let Some(c) = get(&b, "cap").filter(|c| !c.is_empty()) { e.push(("cap".into(), c.to_string())); }
        }
        let (etat, jours) = fraicheur(get(&e, "maj").unwrap_or(""), aujourdhui);
        let (code, conseil) = verdict(&h);
        out.push(Projet {
            nom: n, fraicheur: etat, jours, verdict: code, conseil,
            attente: t.iter().filter(|x| !x.qui.is_empty() && x.qui != DEHORS && x.etat != "fait").cloned().collect(),
            encours: t.iter().filter(|x| x.etat == "encours").count(),
            afaire: t.iter().filter(|x| x.etat == "afaire").count(),
            harnais: h, champs: e, taches: t,
        });
    }
    out
}

fn symbole(v: &str) -> &'static str {
    match v { "ok" => "OK  ", "v1" => "V1  ", "en-retard" => "RETD", "neuf" => "NEUF", "ancien" => "TRI ",
        "ambigu" => "AMBI", "incomplet" => "MANQ", "sans-agent" => "AGT?", "non-branche" => "BRCH",
        "non-inscrit" => "INSC", "jamais-servi" => "SERV",
        "inscription-vieille" => "MAJ ", "non-mesure" => "????", "sans-git" => "GIT ", "surplus" => "TROP",
        "sans-deny" => "DENY", _ => "?   " }
}
fn frais_mot(f: &str) -> &'static str {
    match f { "frais" => "à jour", "tiede" => "tiède", "perime" => "PÉRIMÉ", _ => "ILLISIBLE" }
}
fn rang(p: &str) -> u8 { match p { "haut" => 0, "moyen" => 1, "" => 2, _ => 3 } }
fn oui(b: bool) -> &'static str { if b { "oui" } else { "NON" } }
/// Le plus faible des dossiers de lancement : c'est lui qui laisse passer.
fn deny_txt(h: &Harnais) -> String {
    h.lancements.iter().filter_map(|l| l.deny).min().map(|n| n.to_string()).unwrap_or_else(|| "—".into())
}

fn terminal(projets: &[Projet], racine: &Path) {
    println!("Atelier : {} — {} projet(s)\n", racine.display(), projets.len());
    let mut att: Vec<(&str, &Tache)> = vec![];
    for p in projets {
        let (h, e) = (&p.harnais, &p.champs);
        println!("── {} [{}] {}", gauche(&p.nom, 22), symbole(p.verdict), p.conseil);
        if let Some(c) = get(e, "cap").filter(|c| !c.is_empty()) { println!("     cap    : {}", coupe(c, 90)); }
        let maj = get(e, "maj").unwrap_or("—");
        let j = p.jours.map(|j| format!(" ({} j)", j)).unwrap_or_default();
        let jalon = get(e, "jalon").filter(|s| !s.is_empty()).unwrap_or("—");
        println!("     maj    : {} — {}{}   santé : {}   jalon : {}", maj, frais_mot(p.fraicheur), j,
            get(e, "sante").unwrap_or("—"), coupe(jalon, 44));
        println!("     mémoire: {} · {} · .logs {} · git {}", forme_mot(h), jauge(h), h.logs, oui(h.git));
        for l in &h.lancements { println!("     paquet : {}", ligne_paquet(l)); }
        for l in &h.lancements {
            let d = if let Some(n) = &l.nom { racine.join(&p.nom).join("agents").join(n) } else { racine.join(&p.nom) };
            if crate::copilot::ancien_paquet(&d) { println!("     ATTENTION : {} déclare encore harnais@atelier (risque de double chargement)", d.join(".claude/settings.json").display()); }
            if d != racine.join(&p.nom) && crate::copilot::settings(&d).is_file() { println!("     ATTENTION : {} est inerte hors de la racine Git", crate::copilot::settings(&d).display()); }
        }
        println!("     contexte: AGENTS.md→mémoire {} · deny {}", oui(h.oriente), deny_txt(h));
        if !p.taches.is_empty() {
            println!("     tâches : {} en cours · {} à faire · {} attendent une décision", p.encours, p.afaire, p.attente.len());
        }
        for a in &p.attente { att.push((&p.nom, a)); }
        println!();
    }
    println!("{}", "═".repeat(64));
    if !att.is_empty() {
        println!("CE QUI ATTEND UNE DÉCISION — {} point(s), la seule colonne qui ne se délègue pas\n", att.len());
        att.sort_by_key(|(_, a)| rang(&a.prio));
        for (n, a) in att {
            println!("  [{}] {} @{} {}", gauche(if a.prio.is_empty() { "—" } else { &a.prio }, 5), gauche(n, 18), gauche(&a.qui, 9), coupe(&a.titre, 60));
        }
    } else {
        println!("Aucune tâche `@<qui>` ouverte — ce qui peut vouloir dire deux choses :");
        println!("rien n'attend, ou personne n'en a déclaré. Le second cas est le plus fréquent.");
    }
}

/// `html.escape(s, quote=True)` — les cinq, dans cet ordre.
fn e(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;").replace('"', "&quot;").replace('\'', "&#x27;")
}

const CSS: &str = "
:root{--fond:#f3f4f6;--carte:#fff;--creux:#e9ebef;--encre:#15181e;--doux:#4a5160;
--pale:#767e8e;--trait:#d6d9e0;--accent:#3b4e8f;--vert:#2f7d4f;--orange:#9a6b12;
--rouge:#a5432f;--vert-f:#e4f0e9;--orange-f:#f7eeda;--rouge-f:#f6e7e3;--acc-f:#e6e9f4}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--fond:#14161b;
--carte:#1b1e25;--creux:#23272f;--encre:#e7e9ed;--doux:#a8afbd;--pale:#7c8494;
--trait:#2e333d;--accent:#9bb0e8;--vert:#7bc49a;--orange:#d8b45c;--rouge:#e2907e;
--vert-f:#1c2a22;--orange-f:#2c2618;--rouge-f:#33221e;--acc-f:#232b42}}
*{box-sizing:border-box}
body{margin:0;background:var(--fond);color:var(--encre);font:15px/1.6 -apple-system,
BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.p{max-width:78rem;margin:0 auto;padding:2.5rem 1.25rem 4rem}
h1{font-size:1.9rem;margin:0 0 .3rem;letter-spacing:-.01em}
.sous{color:var(--pale);font-size:.9rem;margin:0 0 2rem}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,\"Cascadia Mono\",monospace}
.att{background:var(--carte);border:1px solid var(--trait);border-left:3px solid var(--rouge);
border-radius:5px;padding:1.1rem 1.25rem;margin-bottom:2rem}
.att h2{font-size:1rem;margin:0 0 .8rem;color:var(--rouge);letter-spacing:.02em}
.att ul{margin:0;padding-left:1.1rem}.att li{margin-bottom:.4rem}
.att .p-{display:inline-block;font-size:.68rem;padding:.08rem .4rem;border-radius:3px;
margin-right:.5rem;font-family:ui-monospace,monospace;background:var(--creux);color:var(--doux)}
.att .p-haut{background:var(--rouge-f);color:var(--rouge)}
.att .proj{color:var(--pale);font-size:.85rem}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(21rem,1fr));gap:.9rem}
.c{background:var(--carte);border:1px solid var(--trait);border-radius:6px;padding:1rem 1.1rem}
.c h3{margin:0;font-size:1.05rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.b{font-size:.66rem;padding:.12rem .45rem;border-radius:3px;font-family:ui-monospace,monospace;
letter-spacing:.03em;text-transform:uppercase}
.b-ok{background:var(--vert-f);color:var(--vert)}
.b-warn{background:var(--orange-f);color:var(--orange)}
.b-bad{background:var(--rouge-f);color:var(--rouge)}
.cap{color:var(--doux);font-size:.88rem;margin:.55rem 0 .8rem}
.meta{font-size:.79rem;color:var(--pale);font-family:ui-monospace,monospace;
border-top:1px solid var(--trait);padding-top:.6rem;margin-top:.2rem;
display:flex;flex-wrap:wrap;gap:.15rem .9rem}
.meta b{font-weight:500;color:var(--doux)}
.no{color:var(--rouge)}
.conseil{margin-top:.7rem;font-size:.83rem;background:var(--acc-f);color:var(--accent);
padding:.45rem .6rem;border-radius:4px}
.barre{display:flex;height:5px;border-radius:3px;overflow:hidden;background:var(--creux);margin:.7rem 0 .35rem}
.barre i{display:block}.b1{background:var(--vert)}.b2{background:var(--accent)}.b3{background:var(--trait)}
.tt{font-size:.78rem;color:var(--pale)}
footer{margin-top:2.5rem;padding-top:1rem;border-top:1px solid var(--trait);
color:var(--pale);font-size:.8rem}
";

fn badge(v: &str) -> (&'static str, String) {
    let (c, t) = match v {
        "ok" => ("b-ok", "servi"), "v1" => ("b-warn", "organisation d'avant"),
        "en-retard" => ("b-warn", "version en retard"), "neuf" => ("b-bad", "sans mémoire"),
        "ancien" => ("b-bad", "taxonomie ancienne"), "ambigu" => ("b-bad", "à cheval"),
        "sans-agent" => ("b-bad", "aucun agent"), "incomplet" => ("b-warn", "mémoire incomplète"),
        "non-branche" => ("b-bad", "paquet non déclaré"), "non-inscrit" => ("b-bad", "non inscrit"),
        "jamais-servi" => ("b-bad", "jamais servi"),
        "inscription-vieille" => ("b-warn", "inscription à mettre à jour"),
        "non-mesure" => ("b-warn", "non mesuré"), "sans-git" => ("b-warn", "sans git"),
        "surplus" => ("b-warn", "fichier en trop"), "sans-deny" => ("b-warn", "aucun deny"),
        autre => return ("b-warn", autre.to_string()),
    };
    (c, t.to_string())
}
fn badge_frais(f: &str) -> (&'static str, &'static str) {
    match f { "frais" => ("b-ok", "à jour"), "tiede" => ("b-warn", "tiède"), "perime" => ("b-bad", "périmé"), _ => ("b-bad", "en-tête illisible") }
}

fn page(projets: &[Projet], racine: &Path, watch: u64) -> String {
    let mut att: Vec<(&str, &Tache)> = projets.iter().flat_map(|p| p.attente.iter().map(move |a| (p.nom.as_str(), a))).collect();
    att.sort_by_key(|(_, a)| rang(&a.prio));
    let mut bloc = vec![format!("<div class=\"att\"><h2>Ce qui attend une décision — {} point(s)</h2>", att.len())];
    if !att.is_empty() {
        bloc.push("<ul>".into());
        for (n, a) in &att {
            bloc.push(format!("<li><span class=\"p- p-{}\">{}</span>{} <span class=\"proj\">— {} · @{}</span></li>",
                e(&a.prio), e(if a.prio.is_empty() { "—" } else { &a.prio }), e(&a.titre), e(n), e(&a.qui)));
        }
        bloc.push("</ul>".into());
    } else {
        bloc.push("<p style=\"margin:0;font-size:.9rem\">Aucune tâche <span class=\"mono\">@&lt;qui&gt;</span> \
ouverte. Deux lectures possibles : rien n'attend, ou personne n'en a déclaré.</p>".into());
    }
    bloc.push("</div>".into());

    let mut cartes = vec![];
    for p in projets {
        let (h, ch) = (&p.harnais, &p.champs);
        let (bv, bt) = badge(p.verdict);
        let (fv, ft) = badge_frais(p.fraicheur);
        let fait = p.taches.iter().filter(|x| x.etat == "fait").count();
        let (enc, af) = (p.encours, p.afaire);
        let tot = std::cmp::max(fait + enc + af, 1) as f64;
        let mut c = vec![format!("<div class=\"c\"><h3>{} <span class=\"b {}\">{}</span> <span class=\"b {}\">{}</span></h3>",
            e(&p.nom), bv, e(&bt), fv, e(ft))];
        c.push(format!("<p class=\"cap\">{}</p>", e(get(ch, "cap").filter(|s| !s.is_empty()).unwrap_or("— pas de <span>cap:</span> déclaré —"))));
        if !p.taches.is_empty() {
            c.push(format!("<div class=\"barre\"><i class=\"b1\" style=\"width:{:.1}%\"></i><i class=\"b2\" style=\"width:{:.1}%\"></i><i class=\"b3\" style=\"width:{:.1}%\"></i></div>",
                100.0 * fait as f64 / tot, 100.0 * enc as f64 / tot, 100.0 * af as f64 / tot));
            c.push(format!("<div class=\"tt\">{} fait · {} en cours · {} à faire</div>", fait, enc, af));
        }
        let non = |ok: bool, t: &str| if ok { t.to_string() } else { format!("<span class=\"no\">{}</span>", t) };
        c.push(format!("<div class=\"meta\"><span><b>maj</b> {}</span><span><b>santé</b> {}</span><span>{}</span><span><b>mémoire</b> {} · {}</span><span><b>.logs</b> {}</span></div>",
            e(get(ch, "maj").filter(|s| !s.is_empty()).unwrap_or("—")), e(get(ch, "sante").filter(|s| !s.is_empty()).unwrap_or("—")),
            non(h.git, "git"), e(forme_mot(h)), e(&jauge(h)), h.logs));
        for l in &h.lancements {
            let d = if let Some(n) = &l.nom { racine.join(&p.nom).join("agents").join(n) } else { racine.join(&p.nom) };
            if crate::copilot::ancien_paquet(&d) { c.push(format!("<div class=\"conseil\">ATTENTION : {} déclare encore harnais@atelier (double chargement possible)</div>", e(&d.join(".claude/settings.json").display().to_string()))); }
            if d != racine.join(&p.nom) && crate::copilot::settings(&d).is_file() { c.push(format!("<div class=\"conseil\">ATTENTION : {} est inerte hors de la racine Git</div>", e(&crate::copilot::settings(&d).display().to_string()))); }
            let servi = l.trace.is_some();
            c.push(format!("<div class=\"meta\"><span>{}</span></div>",
                if l.declare != "non" && l.inscrit != Some(false) && servi { e(&ligne_paquet(l)) }
                else { format!("<span class=\"no\">{}</span>", e(&ligne_paquet(l))) }));
        }
        c.push(format!("<div class=\"meta\"><span>{}</span><span><b>deny</b> {}</span></div>",
            non(h.oriente, "AGENTS.md → mémoire"), deny_txt(h)));
        if p.verdict != "ok" { c.push(format!("<div class=\"conseil\">{}</div>", e(&p.conseil))); }
        c.push("</div>".into());
        cartes.push(c.concat());
    }
    // `meta refresh` est le SEUL rafraîchissement qui marche depuis `file://`.
    let refresh = if watch > 0 { format!("<meta http-equiv=refresh content={}>", watch) } else { String::new() };
    let pied = if watch > 0 {
        format!("Régénérée toutes les {} s tant que <span class=mono>--watch</span> tourne.", watch)
    } else {
        "Relevé daté, pas un tableau vivant. Régénérer avec <span class=mono>harnais equipe-vue --html</span>.".into()
    };
    format!("<!doctype html><html lang=fr><head><meta charset=utf-8>\
<meta name=viewport content='width=device-width,initial-scale=1'>{}\
<title>Agentic Team</title><style>{}</style></head><body><div class=p>\
<h1>Agentic Team</h1>\
<p class=sous><span class=mono>{}</span> · {} projets · relevé du {}</p>\
{}<div class=g>{}</div>\
<footer>Page autonome : aucun serveur, aucune ressource externe. {}</footer>\
</div></body></html>", refresh, CSS, e(&racine.display().to_string()), projets.len(),
        chrono::Local::now().format("%d/%m/%Y à %H:%M"), bloc.concat(), cartes.concat(), pied)
}

#[cfg(unix)]
mod signaux {
    use std::sync::atomic::{AtomicBool, Ordering};
    pub static ARRET: AtomicBool = AtomicBool::new(false);
    extern "C" fn attrape(_: i32) { ARRET.store(true, Ordering::SeqCst); }
    extern "C" { fn signal(sig: i32, h: extern "C" fn(i32)) -> usize; }
    /// SIGINT ET SIGTERM : un `kill` simple laissait, en Python, la balise
    /// `refresh` en place, et la page se rechargeait sur un relevé mort.
    pub fn arme() { unsafe { signal(2, attrape); signal(15, attrape); } }
    pub fn arrete() -> bool { ARRET.load(Ordering::SeqCst) }
}
#[cfg(not(unix))]
mod signaux { pub fn arme() {} pub fn arrete() -> bool { false } }

fn valeur(args: &[String], cle: &str) -> Option<String> {
    let mut it = args.iter();
    while let Some(a) = it.next() {
        if a == cle { return it.next().cloned(); }
        if let Some(v) = a.strip_prefix(&format!("{}=", cle)) { return Some(v.to_string()); }
    }
    None
}
fn developpe(p: &str) -> PathBuf {
    let h = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")).map(PathBuf::from);
    if p == "~" { if let Some(h) = h { return h; } }
    if let Some(r) = p.strip_prefix("~/") { if let Some(h) = h { return h.join(r); } }
    PathBuf::from(p)
}
fn resous(p: PathBuf) -> PathBuf {
    // Comme `Path.resolve()` : le parent résolu même quand le fichier n'existe pas encore.
    if let Ok(c) = p.canonicalize() { return c; }
    match (p.parent(), p.file_name()) {
        (Some(d), Some(n)) if !d.as_os_str().is_empty() => d.canonicalize().map(|d| d.join(n)).unwrap_or(p.clone()),
        _ => std::env::current_dir().map(|d| d.join(&p)).unwrap_or(p.clone()),
    }
}
fn arret(msg: String) -> i32 { eprintln!("{}", msg); 1 }

pub fn main(args: &[String]) -> i32 {
    if args.iter().any(|a| a == "-h" || a == "--help") {
        println!("harnais equipe-vue [--racine R] [--projet NOM] [--html PAGE [--watch N]]\n\n\
Lit la mémoire de tous les projets d'un atelier : le diagnostic au terminal, ou\n\
une page autonome. Strictement en lecture — n'écrit que la page demandée.");
        return 0;
    }
    let racine = resous(developpe(&valeur(args, "--racine").unwrap_or_else(|| "~/Agentic".into())));
    let un_seul = valeur(args, "--projet").unwrap_or_default();
    let html = valeur(args, "--html").unwrap_or_default();
    let watch: u64 = match valeur(args, "--watch").map(|w| w.parse::<u64>()) {
        None => 0, Some(Ok(w)) => w,
        Some(Err(_)) => { eprintln!("harnais equipe-vue : --watch attend un nombre de secondes"); return 2; }
    };
    if !racine.is_dir() { return arret(format!("Racine introuvable : {}", racine.display())); }
    if watch > 0 && html.is_empty() {
        return arret("--watch n'a de sens qu'avec --html : sans page à réécrire, il n'y a rien à rafraîchir.".into());
    }
    if watch > 0 && watch < 5 {
        return arret("--watch en dessous de 5 s relit tous les .mind/ en boucle pour rien. 60 s convient.".into());
    }
    let releve = || -> Result<Vec<Projet>, String> {
        let p = scanne(&racine, &un_seul);
        if p.is_empty() {
            return Err(format!("Aucun projet trouvé dans {}{}", racine.display(),
                if un_seul.is_empty() { String::new() } else { format!(" pour « {} »", un_seul) }));
        }
        Ok(p)
    };
    if html.is_empty() {
        return match releve() { Ok(p) => { terminal(&p, &racine); 0 } Err(m) => arret(m) };
    }
    let cible = resous(developpe(&html));
    if let Some(d) = cible.parent() { let _ = std::fs::create_dir_all(d); }
    let ecris = |w: u64| -> Result<usize, String> {
        let p = releve()?;
        std::fs::write(&cible, page(&p, &racine, w)).map_err(|e| e.to_string())?;
        Ok(p.len())
    };
    let n = match ecris(watch) { Ok(n) => n, Err(m) => return arret(m) };
    let ko = std::fs::metadata(&cible).map(|m| m.len()).unwrap_or(0) as f64 / 1024.0;
    println!("Page écrite : {}  ({} projets, {:.0} Ko)", cible.display(), n, ko);
    if watch == 0 {
        println!("Elle s'ouvre d'un double-clic — aucun serveur nécessaire.");
        return 0;
    }
    println!("Suivi toutes les {} s. La page se recharge seule ; Ctrl-C pour arrêter.", watch);
    signaux::arme();
    'suivi: loop {
        for _ in 0..(watch * 4) {
            if signaux::arrete() { break 'suivi; }
            std::thread::sleep(std::time::Duration::from_millis(250));
        }
        let _ = ecris(watch);
    }
    // Réécrire une dernière fois sans refresh : la page reste lisible et cesse
    // de se prétendre vivante.
    match ecris(0) {
        Ok(_) => println!("\nSuivi arrêté — la page reste en place, en relevé daté."),
        Err(m) => println!("\nSuivi arrêté, mais la page garde son meta-refresh ({}). Elle se rechargera sur \
un relevé figé : sa date en tête ne bougera plus.", m),
    }
    0
}


#[cfg(test)]
mod essais {
    use super::*;
    use std::fs;

    fn dossier(nom: &str, git: bool) -> PathBuf {
        let d = std::env::temp_dir().join(format!("harnais-vue-{}-{}", nom, std::process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        if git { std::process::Command::new("git").args(["init", "-q"]).current_dir(&d).status().unwrap(); }
        d.canonicalize().unwrap()
    }
    /// Pose les réglages Copilot du dépôt qui porte `d` — paquet et `deny`
    /// donnés en JSON —, et le fichier de périmètre de `d` qui en découle.
    fn branche(d: &Path, t: &str) {
        let depot = crate::copilot::racine_git(d).unwrap_or_else(|_| d.to_path_buf());
        let reglages = crate::copilot::settings(&depot);
        let v: Value = serde_json::from_str(t).unwrap();
        let deny = v.get("permissions").and_then(|p| p.get("deny"))
            .and_then(Value::as_array).map(|d| d.len()).unwrap_or(0);
        let perimetre = d.join(".github/copilot/perimetre.json");
        let _ = fs::remove_file(&perimetre);
        if deny > 0 {
            fs::create_dir_all(perimetre.parent().unwrap()).unwrap();
            fs::write(perimetre, serde_json::json!({"deny": [d.join("agents/voisin")]}).to_string()).unwrap();
        }
        fs::create_dir_all(reglages.parent().unwrap()).unwrap();
        fs::write(reglages, t).unwrap();
    }
    fn ecris(d: &Path, f: &str, t: &str) {
        let p = d.join(f);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, t).unwrap();
    }
    const DECLARE: &str = r#"{"enabledPlugins":{"harnais@atelier-copilot":true},"permissions":{"deny":["Bash(x*)"]}}"#;
    /// La version de ce programme, sans son suffixe de construction locale.
    fn courante() -> String { let (a, b, c) = numeros(crate::version_annoncee()).unwrap(); format!("{a}.{b}.{c}") }
    /// `""` : une trace d'avant la 0.10.0, sans version.
    fn trace(d: &Path, v: &str) {
        let v = if v.is_empty() { String::new() } else { format!(r#", "version": "{v}""#) };
        let f = crate::briefing::etat_du_briefing(d);
        fs::create_dir_all(f.parent().unwrap()).unwrap();
        fs::write(&f, format!(r#"{{"derniere": {}, "evenement": "SessionStart"{v}}}"#, maintenant_s())).unwrap();
    }
    /// Un projet `brain/` à un agent, complet, déclaré, avec ses `deny`.
    fn brain_mono(nom: &str) -> PathBuf {
        let d = dossier(nom, true);
        for f in crate::socle::FAITS_MONO { ecris(&d, &format!("brain/fact/{f}"), "x\n"); }
        for f in MIND_ATTENDU { ecris(&d, &format!("brain/mind/{f}"), "x\n"); }
        branche(&d, DECLARE);
        d
    }
    fn inscrit(ds: &[&Path], v: &str) -> Inscriptions {
        Inscriptions::Chemins(ds.iter().map(|d| (d.to_path_buf(), Some(v.to_string()))).collect())
    }
    fn juge(d: &Path, ins: &Inscriptions) -> (&'static str, String) { verdict(&harnais(d, ins)) }

    /// Chaque condition, retirée SEULE, fait tomber le « servi » — sinon un
    /// verdict qui dit toujours « ok » passerait les mêmes essais.
    #[test]
    fn servi_seulement_si_declare_inscrit_et_trace_et_chaque_manque_seul_le_fait_tomber() {
        let d = brain_mono("servi");
        let v = courante();
        trace(&d, &v);
        let ins = inscrit(&[&d], &v);
        assert_eq!(juge(&d, &ins).0, "ok");
        assert_eq!(juge(&d, &Inscriptions::Chemins(vec![])).0, "non-inscrit");
        assert_eq!(juge(&d, &Inscriptions::Illisibles).0, "non-mesure", "illisible n'est pas « inscrit »");
        assert_eq!(juge(&d, &Inscriptions::Toutes(Some(v.clone()))).0, "ok", "une inscription globale vaut pour tous");
        fs::remove_file(crate::briefing::etat_du_briefing(&d)).unwrap();
        assert_eq!(juge(&d, &ins).0, "jamais-servi");
        trace(&d, &v);
        branche(&d, r#"{"permissions":{"deny":["Bash(x*)"]}}"#);
        assert_eq!(juge(&d, &ins).0, "non-branche");
        branche(&d, r#"{"enabledPlugins":{"harnais@atelier-copilot":true}}"#);
        assert_eq!(juge(&d, &ins).0, "sans-deny");
        branche(&d, DECLARE);
        ecris(&d, "brain/fact/journal.md", "x\n");
        assert_eq!(juge(&d, &ins).0, "surplus");
        fs::remove_file(d.join("brain/fact/journal.md")).unwrap();
        fs::remove_file(d.join("brain/mind/todo.md")).unwrap();
        let (v2, c) = juge(&d, &ins);
        assert_eq!(v2, "incomplet");
        assert!(c.contains("brain/mind/todo.md") && c.contains("harnais adopte --go"), "{c}");
        fs::remove_file(d.join("brain/mind/state.md")).unwrap();
        assert_eq!(juge(&d, &ins).0, "sans-agent");
        let _ = fs::remove_dir_all(&d);
    }

    /// La référence est ce qui est INSCRIT : c'est ce que l'agent chargera.
    #[test]
    fn le_retard_se_juge_contre_la_version_inscrite() {
        let d = brain_mono("retard");
        let v = courante();
        trace(&d, "0.0.1");
        assert_eq!(juge(&d, &inscrit(&[&d], &v)).0, "en-retard");
        trace(&d, "");
        let (x, c) = juge(&d, &inscrit(&[&d], &v));
        assert_eq!(x, "en-retard");
        assert!(c.contains("avant la 0.10.0"), "{c}");
        trace(&d, &v);
        assert_eq!(juge(&d, &inscrit(&[&d], &v)).0, "ok");
        // Une trace PLUS RÉCENTE que l'inscrite n'est pas un retard.
        trace(&d, "999.0.0");
        assert_eq!(juge(&d, &inscrit(&[&d], &v)).0, "ok");
        trace(&d, "0.0.1");
        let (x, c) = juge(&d, &inscrit(&[&d], "0.0.1"));
        assert_eq!(x, "inscription-vieille", "{c}");
        assert!(c.contains("marketplace locale"), "{c}");
        let _ = fs::remove_dir_all(&d);
    }

    #[test]
    fn toutes_les_formes_de_memoire_sont_vues() {
        let d = dossier("neuf", true);
        assert_eq!(juge(&d, &Inscriptions::Chemins(vec![])).0, "neuf");
        ecris(&d, ".memory/business.md", "x\n");
        let (x, c) = juge(&d, &Inscriptions::Chemins(vec![]));
        assert_eq!(x, "ancien");
        assert!(c.contains("business.md"), "{c}");
        let _ = fs::remove_dir_all(&d);

        let d = dossier("mind-seul", true);
        ecris(&d, ".mind/state.md", "x\n");
        assert_eq!(juge(&d, &Inscriptions::Chemins(vec![])).0, "ancien");
        let _ = fs::remove_dir_all(&d);

        let d = dossier("sans-git", false);
        for f in crate::socle::FAITS_MONO { ecris(&d, &format!("brain/fact/{f}"), "x\n"); }
        assert_eq!(juge(&d, &Inscriptions::Chemins(vec![])).0, "sans-git");
        let _ = fs::remove_dir_all(&d);

        let d = dossier("v1", true);
        for f in crate::socle::FAITS_MONO { ecris(&d, &format!(".fact/{f}"), "x\n"); }
        for f in MIND_ATTENDU { ecris(&d, &format!(".mind/{f}"), "x\n"); }
        branche(&d, DECLARE);
        trace(&d, &courante());
        let ins = inscrit(&[&d], &courante());
        assert_eq!(juge(&d, &ins).0, "v1");
        fs::create_dir_all(d.join("brain")).unwrap();
        let (x, c) = juge(&d, &ins);
        assert_eq!(x, "ambigu");
        assert!(c.contains("harnais brain-migre"), "{c}");
        let _ = fs::remove_dir_all(&d);
    }

    /// À plusieurs, l'état de chaque agent vit dans `brain/mind/<nom>/`, et ses
    /// réglages dans `agents/<nom>/` — ceux de la racine sont inertes.
    #[test]
    fn a_plusieurs_chaque_agent_est_lu_depuis_son_dossier() {
        let d = dossier("equipe", true);
        for f in crate::socle::faits_tous() { ecris(&d, &format!("brain/fact/{f}"), "x\n"); }
        let v = courante();
        let mut ags = vec![];
        for a in ["Alpha", "Beta"] {
            for f in MIND_ATTENDU { ecris(&d, &format!("brain/mind/{a}/{f}"), "x\n"); }
            let ag = d.join("agents").join(a);
            ecris(&ag, "CLAUDE.md", "x\n");
            branche(&ag, DECLARE);
            trace(&ag, &v);
            ags.push(ag);
        }
        let ins = inscrit(&[&ags[0], &ags[1]], &v);
        let h = harnais(&d, &ins);
        assert_eq!(verdict(&h).0, "ok");
        assert!(jauge(&h).contains("faits 5/5") && jauge(&h).contains("état 4/4"), "{}", jauge(&h));
        let (x, c) = juge(&d, &inscrit(&[&ags[0]], &v));
        assert_eq!(x, "non-inscrit");
        assert!(c.starts_with("Beta : "), "l'agent en défaut est nommé : {c}");
        fs::remove_file(d.join("brain/mind/Beta/todo.md")).unwrap();
        let (x, c) = juge(&d, &ins);
        assert_eq!(x, "incomplet");
        assert!(c.contains("brain/mind/Beta/todo.md"), "{c}");
        let _ = fs::remove_dir_all(&d);
    }

    /// Un agent qui se lance depuis une copie de travail n'a, dans l'arbre
    /// principal, qu'une trace ancienne — ou aucune.
    #[test]
    fn une_trace_dans_une_copie_de_travail_compte() {
        let d = brain_mono("copie");
        let c = d.with_file_name(format!("{}-copie", d.file_name().unwrap().to_string_lossy()));
        let _ = fs::remove_dir_all(&c);
        let git = |a: &[&str]| std::process::Command::new("git").args(["-c", "user.email=e@e", "-c", "user.name=e"])
            .args(a).current_dir(&d).output().unwrap();
        assert!(git(&["commit", "-q", "--allow-empty", "-m", "x"]).status.success());
        // Git ne lit pas la forme longue des chemins Windows (`\\?\C:\…`), que
        // rend `canonicalize()`. On la lui retire ; le programme, lui, reçoit ce
        // que git écrit et le canonicalise.
        let pour_git = c.to_string_lossy().trim_start_matches(r"\\?\").to_string();
        let ajout = git(&["worktree", "add", "-q", &pour_git]);
        assert!(ajout.status.success(), "{}", String::from_utf8_lossy(&ajout.stderr));
        let c = c.canonicalize().unwrap();
        let v = courante();
        let ins = inscrit(&[&c], &v);
        assert_eq!(juge(&d, &ins).0, "jamais-servi", "témoin : sans la trace de la copie");
        trace(&c, &v);
        assert_eq!(juge(&d, &ins).0, "ok");
        let _ = fs::remove_dir_all(&c);
        let _ = fs::remove_dir_all(&d);
    }

    /// Ce qui fait qu'un conseil ne cite rien de mort. Une commande se cite
    /// entre accents graves : « le harnais refuse » est de la prose.
    fn commandes_mortes(texte: &str) -> Vec<String> {
        let main = include_str!("main.rs");
        let skills = Path::new(env!("CARGO_MANIFEST_DIR")).join("../skills");
        let mut mortes = vec![];
        for c in Regex::new(r"`harnais ([a-z][a-z-]*)").unwrap().captures_iter(texte) {
            if !main.contains(&format!("\"{}\" =>", &c[1])) { mortes.push(format!("harnais {}", &c[1])); }
        }
        for c in Regex::new(r"(?:^|[\s`(])/([a-z][a-z0-9-]*)").unwrap().captures_iter(texte) {
            if !skills.join(&c[1]).join("SKILL.md").is_file() { mortes.push(format!("/{}", &c[1])); }
        }
        for c in Regex::new(r"`copilot plugin ([a-z]+)").unwrap().captures_iter(texte) {
            if !["install", "update", "uninstall", "list", "marketplace"].contains(&&c[1]) {
                mortes.push(format!("copilot plugin {}", &c[1]));
            }
        }
        mortes
    }

    /// Le défaut d'origine : deux conseils renvoyaient à des compétences
    /// supprimées. Tous les verdicts sont produits, et chacun est relu.
    #[test]
    fn aucun_conseil_ne_renvoie_a_une_commande_qui_n_existe_pas() {
        // témoins : la vérification mord sur les deux morts d'origine
        let (u, y) = ("/agentic-".to_string() + "upgrade", "/agentic-".to_string() + "sync");
        assert_eq!(commandes_mortes(&format!("lancer `{u}` puis {y}")), vec![u.as_str(), y.as_str()]);
        // Composée à l'exécution : écrite en clair, le contrôle de la
        // documentation la prendrait pour une vraie citation.
        assert_eq!(commandes_mortes(&format!("`harnais {}`", "inexistant")), vec!["harnais inexistant"]);
        assert!(commandes_mortes("`harnais adopte --go` puis `/agentic-adopte`, dans brain/mind/").is_empty());
        assert!(commandes_mortes("le harnais refuse de choisir").is_empty());
        assert_eq!(commandes_mortes("`copilot plugin upgrade x`"), vec!["copilot plugin upgrade"]);

        let mut vus: std::collections::BTreeMap<&str, String> = Default::default();
        let mut note = |d: &Path, ins: &Inscriptions| { let (v, c) = juge(d, ins); vus.insert(v, c); };
        let v = courante();
        let d = brain_mono("tous");
        let ins = inscrit(&[&d], &v);
        note(&d, &Inscriptions::Chemins(vec![]));
        note(&d, &Inscriptions::Illisibles);
        note(&d, &ins);
        trace(&d, &v); note(&d, &ins);
        trace(&d, "0.0.1"); note(&d, &ins); note(&d, &inscrit(&[&d], "0.0.1"));
        trace(&d, &v);
        branche(&d, "{}"); note(&d, &ins);
        branche(&d, r#"{"enabledPlugins":{"harnais@atelier-copilot":true}}"#); note(&d, &ins);
        branche(&d, DECLARE);
        ecris(&d, "brain/fact/journal.md", "x\n"); note(&d, &ins);
        fs::remove_file(d.join("brain/fact/journal.md")).unwrap();
        fs::remove_file(d.join("brain/mind/todo.md")).unwrap(); note(&d, &ins);
        fs::remove_file(d.join("brain/mind/state.md")).unwrap(); note(&d, &ins);
        let _ = fs::remove_dir_all(&d);
        let d = dossier("tous-v1", true);
        note(&d, &ins);
        ecris(&d, ".mind/state.md", "x\n"); note(&d, &ins);
        ecris(&d, ".memory/business.md", "x\n"); note(&d, &ins);
        for f in crate::socle::FAITS_MONO { ecris(&d, &format!(".fact/{f}"), "x\n"); }
        fs::remove_dir_all(d.join(".memory")).unwrap();
        ecris(&d, ".mind/todo.md", "x\n");
        branche(&d, DECLARE); trace(&d, &v);
        note(&d, &inscrit(&[&d], &v));
        branche(&d, "{}"); note(&d, &inscrit(&[&d], &v));
        fs::create_dir_all(d.join("brain")).unwrap(); note(&d, &ins);
        let _ = fs::remove_dir_all(&d);
        let d = dossier("tous-sans-git", false);
        note(&d, &ins);
        let _ = fs::remove_dir_all(&d);

        // Chaque verdict que le tableau sait afficher a été produit ici : un
        // verdict ajouté sans essai fait échouer celui-ci.
        let tous = ["ok", "v1", "en-retard", "neuf", "ancien", "ambigu", "incomplet", "sans-agent",
                    "non-branche", "non-inscrit", "non-mesure", "jamais-servi", "sans-git", "surplus",
                    "sans-deny", "inscription-vieille"];
        for t in tous {
            assert!(vus.contains_key(t), "verdict jamais produit par l'essai : {t}");
            assert_ne!(symbole(t), "?   ", "{t} sans symbole");
        }
        assert_eq!(vus.len(), tous.len(), "verdicts produits : {:?}", vus.keys());
        for (v, c) in &vus {
            assert!(commandes_mortes(c).is_empty(), "{v} cite une commande morte : {c}");
        }
    }
}
