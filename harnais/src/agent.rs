//! L'AGENT ACTIF — qui parle, quand le dossier ne le dit plus.
//!
//! Sous le CLI, une session s'ouvrait DANS `agents/<nom>/` : le dossier de
//! lancement disait qui parlait, et tout le harnais le lisait là. L'app Copilot
//! lance chaque conversation à la RACINE d'une copie de travail, et l'agent se
//! choisit dans un menu du champ de saisie (les profils
//! `.github/agents/<nom>.agent.md`). Aucun hook ne reçoit ce choix, ni dans sa
//! charge ni dans son environnement. Il est écrit dans le JOURNAL DE SESSION de
//! Copilot — mesuré dans l'app et dans le CLI 1.0.91-1 :
//!
//! ```text
//! ~/.copilot/session-state/<session_id>/events.jsonl
//! {"type":"subagent.selected","data":{"agentName":"ops",…}}   un agent choisi
//! {"type":"subagent.deselected","data":{}}                     « Default agent »
//! ```
//!
//! Écrit avant le premier hook, souvent deux fois de suite ; un nouveau à chaque
//! changement par le menu ; un nouveau en tête de la session qu'ouvre `/clear` ;
//! intact après `/compact`. Les sous-agents de l'outil task écrivent
//! `subagent.started|configured|completed`, avec un `agentId` à la racine, et
//! jamais `selected` : tout événement qui porte un `agentId` est ignoré quand
//! même — un sous-agent ne doit pas pouvoir changer l'agent de la session.
//!
//! LA RÈGLE, dans cet ordre :
//!
//! 1. le dernier `selected` du journal désigne un agent du projet → lui (menu) ;
//! 2. sinon le dossier de lancement est sous `agents/<nom>/` → lui (dossier) ;
//! 3. sinon, un projet à plusieurs agents qui en a un nommé QA → QA (défaut) ;
//! 4. sinon aucun agent, et le briefing le dit.
//!
//! Un agent choisi dans le menu qui n'est pas un agent du projet n'est PAS le
//! « Default agent » : il ne prend pas QA, et le briefing le signale.
//!
//! LE HARNAIS SE PLACE ALORS DANS LE DOSSIER DE L'AGENT : `COPILOT_PROJECT_DIR`
//! devient `<copie>/agents/<nom>`, comme si la session y avait été lancée. Les
//! modules qui lisent la position de l'agent — état, todo, garde de commit,
//! périmètre, journal, fin de tour — la lisent donc juste sans changer d'une
//! ligne. Ce que ce dossier ne dit PAS, le vrai dossier de la session, reste
//! connu ici : c'est depuis lui que se lisent les chemins relatifs d'un outil,
//! et que s'affichent les chemins du briefing.

use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// L'agent pris quand rien n'est choisi — décision de @user pour les projets à
/// plusieurs agents. Il ne s'applique que si le projet a un agent de ce nom.
pub const DEFAUT: &str = "QA";

/// Au-delà, le rôle servi par le briefing est coupé, et le briefing le dit.
const ROLE_MAX_LIGNES: usize = 250;
const ROLE_MAX_OCTETS: usize = 16_000;

/// Ce que le journal dit du choix, ramené au dernier état.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Choix {
    /// Aucun `selected` ni `deselected` lisible.
    Rien,
    /// Un agent choisi, et la ligne où ce choix a COMMENCÉ — la première d'une
    /// suite d'événements identiques, pour que le doublon que l'app écrit au
    /// démarrage ne passe pas pour un changement.
    Agent { nom: String, ligne: usize },
    /// « Default agent » choisi, à cette ligne.
    Retire { ligne: usize },
}

/// Une lecture du journal de session.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Lecture {
    pub chemin: Option<PathBuf>,
    /// Le fichier existait-il au moment de la lecture ?
    pub trouve: bool,
    pub lignes: usize,
    /// Les compactions terminées : chacune peut avoir effacé le briefing du
    /// contexte, le briefing doit donc repartir après.
    pub compactions: usize,
    pub choix: Choix,
}

impl Lecture {
    pub fn vide() -> Lecture {
        Lecture { chemin: None, trouve: false, lignes: 0, compactions: 0, choix: Choix::Rien }
    }
    /// Ce qu'on a lu, dit en une phrase — c'est aussi la sonde qui répond à
    /// « l'événement était-il sur le disque quand le hook a lu ? ».
    pub fn etat(&self) -> String {
        match (&self.chemin, self.trouve) {
            (None, _) => "pas d'identifiant de session : journal non lu".into(),
            (Some(_), false) => "journal de session introuvable".into(),
            (Some(_), true) => format!("journal de session : {} ligne(s) lue(s)", self.lignes),
        }
    }
}

/// D'où vient l'agent actif.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Source {
    /// Choisi dans le menu de l'app (ou par `--agent` dans le CLI).
    Menu { ligne: usize },
    /// Le dossier de lancement est celui de l'agent.
    Dossier,
    /// Rien n'est choisi : l'agent par défaut du projet. `ligne` est celle du
    /// « Default agent » quand il a été choisi explicitement.
    Defaut { ligne: Option<usize> },
    /// Un agent choisi dans le menu qui n'est pas un agent du projet.
    Inconnu { nom: String, ligne: usize },
    /// Projet à plusieurs agents, rien de choisi, pas d'agent par défaut.
    Aucun,
}

#[derive(Debug, Clone)]
pub struct Session {
    /// Le dossier de lancement déclaré par l'hôte — la vraie session.
    pub reel: PathBuf,
    /// La racine de la copie de travail courante.
    pub arbre: Option<PathBuf>,
    /// Les agents du projet, dans l'ordre des dossiers. Vide : projet mono.
    pub agents: Vec<String>,
    /// Le nom du dossier `agents/<nom>` de l'agent actif.
    pub actif: Option<String>,
    pub source: Source,
    pub lecture: Lecture,
    /// Le dossier où le harnais s'est placé, quand il n'est pas `reel`.
    pub place: Option<PathBuf>,
}

impl Session {
    /// Ce qui doit faire repartir le briefing quand il change : l'agent, d'où
    /// il vient, la ligne où ce choix a commencé, et les compactions. Le nombre
    /// de lignes lues n'y est PAS : il change à chaque tour.
    pub fn signature(&self) -> String {
        let (genre, ligne) = match &self.source {
            Source::Menu { ligne } => ("menu", *ligne),
            Source::Dossier => ("dossier", 0),
            Source::Defaut { ligne } => ("defaut", ligne.unwrap_or(0)),
            Source::Inconnu { ligne, .. } => ("inconnu", *ligne),
            Source::Aucun => ("aucun", 0),
        };
        format!("agent={}|{}|{}|compactions={}", self.actif.as_deref().unwrap_or("-"), genre,
                ligne, self.lecture.compactions)
    }
}

static SESSION: OnceLock<Session> = OnceLock::new();

/// La session résolue par `pose()`, ou `None` hors hook.
pub fn session() -> Option<&'static Session> { SESSION.get() }

/// Le journal de la session : `transcript_path` quand la charge le donne (fin
/// de tour), sinon `<COPILOT_HOME>/session-state/<session_id>/events.jsonl`.
/// Un identifiant qui n'a pas la forme d'un nom de dossier n'est pas suivi :
/// il ne compose jamais un chemin.
pub fn chemin_journal(charge: &Value, maison_copilot: &Path) -> Option<PathBuf> {
    if let Some(t) = charge.get("transcript_path").and_then(Value::as_str).filter(|s| !s.trim().is_empty()) {
        return Some(PathBuf::from(t));
    }
    let id = charge.get("session_id").and_then(Value::as_str)?.trim();
    if id.is_empty() || id.len() > 128
        || !id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_') {
        return None;
    }
    Some(maison_copilot.join("session-state").join(id).join("events.jsonl"))
}

/// LE DERNIER CHOIX D'AGENT DU JOURNAL. Lu en entier, une ligne à la fois : le
/// choix est en tête du fichier, et un changement peut tomber n'importe où.
/// Seules les lignes qui portent `subagent.` ou `compaction_complete` sont
/// décodées — ces journaux font des dizaines de Mo.
pub fn lis_journal(chemin: &Path) -> Lecture {
    use std::io::BufRead;
    let mut l = Lecture { chemin: Some(chemin.to_path_buf()), ..Lecture::vide() };
    let f = match std::fs::File::open(chemin) { Ok(f) => f, Err(_) => return l };
    l.trouve = true;
    let mut lecteur = std::io::BufReader::with_capacity(1 << 16, f);
    let mut brut: Vec<u8> = Vec::new();
    loop {
        brut.clear();
        match lecteur.read_until(b'\n', &mut brut) { Ok(0) | Err(_) => break, Ok(_) => () }
        l.lignes += 1;
        let texte = String::from_utf8_lossy(&brut);
        if !texte.contains("subagent.") && !texte.contains("compaction_complete") { continue; }
        let e: Value = match serde_json::from_str(texte.trim()) { Ok(e) => e, Err(_) => continue };
        if e.get("agentId").is_some_and(|v| !v.is_null()) { continue; }
        match e.get("type").and_then(Value::as_str) {
            Some("session.compaction_complete") => l.compactions += 1,
            Some("subagent.selected") => {
                let nom = e.get("data").and_then(|d| d.get("agentName")).and_then(Value::as_str)
                    .map(str::trim).unwrap_or("");
                if nom.is_empty() { continue; }
                match &l.choix {
                    Choix::Agent { nom: n, .. } if n == nom => (),
                    _ => l.choix = Choix::Agent { nom: nom.to_string(), ligne: l.lignes },
                }
            }
            Some("subagent.deselected") => {
                if !matches!(l.choix, Choix::Retire { .. }) {
                    l.choix = Choix::Retire { ligne: l.lignes };
                }
            }
            _ => (),
        }
    }
    l
}

/// LES AGENTS DU PROJET : les dossiers de `agents/` qui ont un ESPRIT — dans le
/// cerveau (`brain/mind/<nom>/`), en place (`agents/<nom>/.mind/`) ou déporté.
/// Un dossier `agents/` de code n'en a pas : un projet mono qui en porte un
/// reste mono, et personne n'est placé dedans.
pub fn agents_du_projet(arbre: &Path) -> Vec<String> {
    let mut v: Vec<String> = std::fs::read_dir(arbre.join("agents")).map(|it| it.flatten()
        .filter(|e| e.path().is_dir())
        .map(|e| e.file_name().to_string_lossy().to_string())
        .filter(|n| !n.starts_with('.'))
        .filter(|n| arbre.join("brain/mind").join(n).is_dir()
                 || arbre.join("agents").join(n).join(".mind").is_dir()
                 || arbre.join("memoire/agents").join(n).join(".mind").is_dir())
        .collect()).unwrap_or_default();
    v.sort();
    if let Ok(it) = std::fs::read_dir(arbre.join("brain/mind")) {
        for e in it.flatten().filter(|e| e.path().is_dir()) {
            let n = e.file_name().to_string_lossy().to_string();
            if profil(arbre, &n).is_file() && !v.contains(&n) { v.push(n); }
        }
    }
    v.sort();
    v
}

pub fn profil(arbre: &Path, nom: &str) -> PathBuf {
    arbre.join(".github/agents").join(format!("{}.agent.md", nom_de_profil(nom)))
}

pub fn perimetre_compact(arbre: &Path, nom: &str) -> PathBuf {
    arbre.join(".github/copilot/perimetres").join(format!("{}.json", nom_de_profil(nom)))
}

/// Où un agent compact dépose ce qu'il produit : un dossier par agent, sous
/// `brain/`. C'est le SEUL endroit où ce chemin est écrit ; la garde de commit
/// l'ignore comme `docs/` (un livrable en `.sql` n'est pas du code projet).
pub const BANC: &str = "brain/workbench";

pub fn banc(nom: &str) -> String {
    format!("{BANC}/{nom}")
}

/// Ce qui fait tenir le harnais : profils, périmètres, réglages. Un agent n'y écrit
/// pas : y toucher, c'est changer le rôle ou les limites d'un autre. Le reste de
/// `.github/` (CI, MCP, modèles de PR…) appartient au projet.
pub const CONTROLE: [&str; 2] = [".github/agents", ".github/copilot"];

pub fn compact(arbre: &Path, nom: &str) -> bool {
    perimetre_compact(arbre, nom).exists()
        || std::fs::read_to_string(profil(arbre, nom)).ok()
            .is_some_and(|t| t.contains("<!-- harnais:role:start -->"))
        || (!arbre.join("agents").join(nom).is_dir() && profil(arbre, nom).is_file())
}

/// Le contexte du hook n'est pas le dossier de travail de Copilot.
pub fn contexte(arbre: &Path, nom: &str) -> PathBuf {
    if compact(arbre, nom) { arbre.join("brain/mind").join(nom) }
    else { arbre.join("agents").join(nom) }
}

/// Le nom de profil d'un agent : celui que `harnais equipe` écrit dans
/// `.github/agents/<nom>.agent.md` — le dossier slugifié, en minuscules.
pub fn nom_de_profil(dossier: &str) -> String {
    crate::equipe::slug(dossier).to_lowercase().trim_matches('-').to_string()
}

/// Le dossier d'agent que désigne un nom choisi dans le menu — à la casse près,
/// ou par son nom de profil.
pub fn correspond(nom: &str, agents: &[String]) -> Option<String> {
    let n = nom.trim().to_lowercase();
    if n.is_empty() { return None; }
    agents.iter().find(|a| a.to_lowercase() == n).cloned()
        .or_else(|| agents.iter().find(|a| nom_de_profil(a) == n).cloned())
}

/// LA RÉSOLUTION — pure : le dossier de lancement, ce que le journal dit.
pub fn resous(reel: &Path, lecture: Lecture) -> Session {
    let arbre = crate::memoire::arbre_courant(reel)
        .map(|a| a.canonicalize().unwrap_or(a));
    let agents = arbre.as_deref().map(agents_du_projet).unwrap_or_default();
    let mut s = Session { reel: reel.to_path_buf(), arbre: arbre.clone(), agents: agents.clone(),
                          actif: None, source: Source::Aucun, lecture, place: None };
    let Some(arbre) = arbre else { return s };
    if agents.is_empty() { return s; }
    let lot = crate::memoire::lot(reel);
    let dossier = lot.rsplit_once('/').map(|(_, n)| n.to_string())
        .filter(|n| agents.contains(n));
    match s.lecture.choix.clone() {
        Choix::Agent { nom, ligne } => match correspond(&nom, &agents) {
            Some(a) => { s.actif = Some(a); s.source = Source::Menu { ligne }; }
            None => { s.actif = dossier.clone(); s.source = Source::Inconnu { nom, ligne }; }
        },
        choix => {
            let ligne = match choix { Choix::Retire { ligne } => Some(ligne), _ => None };
            if let Some(d) = dossier.clone() {
                s.actif = Some(d);
                s.source = Source::Dossier;
            } else if let Some(q) = correspond(DEFAUT, &agents) {
                s.actif = Some(q);
                s.source = Source::Defaut { ligne };
            }
        }
    }
    // Se placer, sauf si la session est DÉJÀ dans ce dossier.
    if let (Some(a), Source::Menu { .. } | Source::Defaut { .. }) = (&s.actif, &s.source) {
        if dossier.as_deref() != Some(a.as_str()) {
            let cible = contexte(&arbre, a);
            if cible.is_dir() { s.place = Some(cible); }
        }
    }
    s
}

/// APPELÉE PAR `hote::prepare`, une fois par hook : résout l'agent actif et, au
/// besoin, place le harnais dans son dossier. Fail-open : sans dépôt, sans
/// journal, sans agents, rien ne bouge.
pub fn pose(charge: &Value) {
    let reel = std::env::var_os("COPILOT_PROJECT_DIR").filter(|s| !s.is_empty()).map(PathBuf::from)
        .or_else(|| charge.get("cwd").and_then(Value::as_str).filter(|s| !s.is_empty()).map(PathBuf::from));
    let Some(reel) = reel else { return };
    let lecture = chemin_journal(charge, &crate::hote::maison_copilot())
        .map(|c| lis_journal(&c)).unwrap_or_else(Lecture::vide);
    let s = resous(&reel, lecture);
    if let Some(p) = &s.place { std::env::set_var("COPILOT_PROJECT_DIR", p); }
    let _ = SESSION.set(s);
}

/// D'où s'affichent les chemins du briefing : le VRAI dossier de la session
/// quand le harnais s'est placé ailleurs — un chemin relatif au dossier de
/// l'agent ne s'ouvrirait pas depuis la racine où l'agent travaille.
pub fn ancre_affichage(r: &Path) -> PathBuf {
    match session() {
        Some(s) if s.place.as_deref().is_some_and(|p| same(p, r)) =>
            s.reel.canonicalize().unwrap_or_else(|_| s.reel.clone()),
        _ => r.to_path_buf(),
    }
}

fn same(a: &Path, b: &Path) -> bool {
    a.canonicalize().ok().zip(b.canonicalize().ok()).is_some_and(|(x, y)| x == y) || a == b
}

/// Le rôle d'un agent, tel qu'il est écrit — `AGENTS.md`, ou à défaut
/// `CLAUDE.md`. `None` si aucun des deux n'existe.
fn role(dossier: &Path) -> Option<(PathBuf, String)> {
    ["AGENTS.md", "CLAUDE.md"].iter().map(|n| dossier.join(n))
        .find(|p| p.is_file())
        .map(|p| { let t = std::fs::read_to_string(&p).unwrap_or_default(); (p, t) })
}

/// Coupe un rôle trop long, et le dit.
fn borne(t: &str) -> (String, bool) {
    let mut out = String::new();
    for (i, ligne) in t.lines().enumerate() {
        if i >= ROLE_MAX_LIGNES || out.len() + ligne.len() + 1 > ROLE_MAX_OCTETS { return (out, true); }
        out.push_str(ligne);
        out.push('\n');
    }
    (out, false)
}

/// LES LIGNES DU BRIEFING SUR L'AGENT — `(en tête, en fin)`.
///
/// En tête, une ligne qui dit QUI parle et D'OÙ on le sait. En fin, le RÔLE,
/// relu à l'instant, quand Copilot ne l'a pas chargé de lui-même : une session
/// lancée à la racine ne lit pas `agents/<nom>/AGENTS.md`, et un profil qui
/// demande au modèle de l'ouvrir laisse la lecture à sa bonne volonté — mesuré.
/// Le briefing MONTRE, il ne pointe pas.
pub fn lignes_briefing(s: &Session) -> (Vec<String>, Vec<String>) {
    let (mut tete, mut fin) = (Vec::new(), Vec::new());
    if s.agents.is_empty() { return (tete, fin); }
    let menu = "le menu d'agent du champ de saisie";
    let liste = s.agents.join(", ");
    match &s.source {
        Source::Menu { ligne } => tete.push(format!(
            "agent  : {} — choisi dans {menu} (journal de session, ligne {ligne}).",
            s.actif.as_deref().unwrap_or("?"))),
        Source::Dossier => tete.push(format!(
            "agent  : {} — la session est lancée dans son dossier.", s.actif.as_deref().unwrap_or("?"))),
        Source::Defaut { ligne } => {
            let pourquoi = match ligne {
                Some(l) => format!("« Default agent » est choisi dans {menu} (journal de session, ligne {l})"),
                None => format!("aucun agent n'est choisi dans {menu} ({})", s.lecture.etat()),
            };
            tete.push(format!("agent  : {} — l'agent PAR DÉFAUT de ce projet : {pourquoi}.",
                              s.actif.as_deref().unwrap_or("?")));
            let autres: Vec<&str> = s.agents.iter().map(String::as_str)
                .filter(|a| Some(*a) != s.actif.as_deref()).collect();
            tete.push(format!("         Tu tiens ce rôle et ce périmètre. Pour un autre agent ({}), \
@user le choisit dans le menu.", autres.join(", ")));
        }
        Source::Inconnu { nom, ligne } => {
            tete.push(format!("agent  : « {nom} », choisi dans {menu} (journal de session, ligne {ligne}), \
n'est pas un agent de ce projet ({liste})."));
            tete.push(match &s.actif {
                Some(a) => format!("         Le dossier de lancement garde l'agent {a}."),
                None => "         Aucun lot ne s'applique : ni état d'agent, ni périmètre — RIEN n'est gardé.".into(),
            });
        }
        Source::Aucun => {
            tete.push(format!("agent  : AUCUN — rien n'est choisi dans {menu} ({}), et ce projet n'a pas \
d'agent {DEFAUT} par défaut.", s.lecture.etat()));
            tete.push(format!("         Aucun lot ne s'applique : ni état d'agent, ni périmètre — RIEN n'est \
gardé. Les agents : {liste}."));
        }
    }
    // Le rôle n'est servi que si la session n'est PAS dans le dossier de
    // l'agent : là, Copilot le charge déjà, et le servir deux fois le paierait
    // deux fois.
    if let (Some(a), Some(arbre)) = (&s.actif, &s.arbre) {
        if s.place.is_none() && !compact(arbre, a) { return (tete, fin); }
        if compact(arbre, a) && matches!(s.source, Source::Menu { .. }) {
            let p = profil(arbre, a);
            tete.push(if p.is_file() {
                format!("         Rôle : {} — profil choisi dans le menu ; non recopié par le briefing.",
                    crate::socle::chemin_affiche(&s.reel, &p))
            } else { format!("         Rôle ABSENT : {} ; restaurer le profil avant de travailler.", p.display()) });
            return (tete, fin);
        }
        let dossier = contexte(arbre, a);
        let base = s.reel.canonicalize().unwrap_or_else(|_| s.reel.clone());
        let affiche = |p: &Path| crate::socle::chemin_affiche(&base, p);
        let role_actif = if compact(arbre, a) {
            let p = profil(arbre, a);
            match std::fs::read_to_string(&p) {
                Ok(t) => {
                    let t = t.strip_prefix("---\r\n").and_then(|t| t.split_once("\r\n---\r\n").map(|(_, b)| b))
                        .or_else(|| t.strip_prefix("---\n").and_then(|t| t.split_once("\n---\n").map(|(_, b)| b)))
                        .unwrap_or(&t).to_string();
                    Some((p, t))
                },
                Err(e) => {
                    tete.push(format!("         Profil illisible : {} : {e}", p.display()));
                    None
                }
            }
        } else { role(&dossier) };
        match role_actif {
            Some((p, t)) => {
                let (texte, coupe) = borne(&t);
                fin.push(format!("── Ton rôle · {} — relu à l'instant ──", affiche(&p)));
                fin.extend(texte.lines().map(String::from));
                if coupe {
                    fin.push(format!("[… coupé à {ROLE_MAX_LIGNES} lignes ou {ROLE_MAX_OCTETS} octets : \
la suite est dans {}]", affiche(&p)));
                }
                fin.push("── fin du rôle ──".into());
            }
            None => tete.push(format!("         Rôle ABSENT : ni AGENTS.md ni CLAUDE.md dans {} — ce rôle \
n'est écrit nulle part.", affiche(&dossier))),
        }
    }
    (tete, fin)
}

/// `harnais agent` — QUI PARLE, ET D'OÙ JE LE SAIS. Lecture seule : rien n'est
/// écrit, rien n'est supprimé. C'est la sonde qu'on lance sur un poste au lieu
/// de fouiller `~/.copilot` à la main.
///
///     harnais agent [--session <id> | --journal <events.jsonl>] [--racine <dossier>]
pub fn main(args: &[String]) -> i32 {
    if args.iter().any(|a| a == "-h" || a == "--help") {
        println!("harnais agent [--session <id> | --journal <events.jsonl>] [--racine <dossier>]\n\n\
L'agent actif tel que les hooks le résolvent : le journal de session lu, le choix trouvé,\n\
la règle appliquée (menu, dossier, défaut {DEFAUT}) et le dossier où le harnais se place.\n\
Lecture seule.");
        return 0;
    }
    let valeur = |cle: &str| args.iter().position(|a| a == cle).and_then(|i| args.get(i + 1)).cloned();
    let racine = valeur("--racine").map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    let mut charge = serde_json::Map::new();
    if let Some(j) = valeur("--journal") { charge.insert("transcript_path".into(), Value::String(j)); }
    if let Some(id) = valeur("--session") { charge.insert("session_id".into(), Value::String(id)); }
    let charge = Value::Object(charge);
    let lecture = chemin_journal(&charge, &crate::hote::maison_copilot())
        .map(|c| lis_journal(&c)).unwrap_or_else(Lecture::vide);
    let s = resous(&racine, lecture);
    let chemin = s.lecture.chemin.as_ref().map(|p| p.display().to_string())
        .unwrap_or_else(|| "(aucun : ni --session ni --journal)".into());
    println!("journal : {chemin}");
    println!("lu      : {}", s.lecture.etat());
    println!("choix   : {}", match &s.lecture.choix {
        Choix::Rien => "aucun `subagent.selected` ni `deselected`".to_string(),
        Choix::Agent { nom, ligne } => format!("« {nom} », ligne {ligne}"),
        Choix::Retire { ligne } => format!("« Default agent », ligne {ligne}"),
    });
    println!("compact.: {}", s.lecture.compactions);
    println!("agents  : {}", if s.agents.is_empty() { "aucun (projet à un agent, ou pas de dépôt)".to_string() }
                              else { s.agents.join(", ") });
    println!("actif   : {}", s.actif.as_deref().unwrap_or("aucun"));
    println!("source  : {:?}", s.source);
    println!("placé   : {}", s.place.as_ref().map(|p| p.display().to_string())
                                  .unwrap_or_else(|| "non — le dossier de lancement est gardé".into()));
    0
}

#[cfg(test)]
mod essais {
    use super::*;
    use serde_json::json;

    fn dossier(nom: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("agent-actif-{}-{}", nom, std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn git(d: &Path, a: &[&str]) {
        let ok = std::process::Command::new("git").args(a).current_dir(d)
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_AUTHOR_NAME", "t").env("GIT_AUTHOR_EMAIL", "t@t")
            .env("GIT_COMMITTER_NAME", "t").env("GIT_COMMITTER_EMAIL", "t@t")
            .status().unwrap().success();
        assert!(ok, "git {:?}", a);
    }

    /// Un projet `brain/` à trois agents, commité.
    fn projet(nom: &str, agents: &[&str]) -> PathBuf {
        let d = dossier(nom);
        git(&d, &["init", "-q"]);
        std::fs::create_dir_all(d.join("brain/fact")).unwrap();
        std::fs::write(d.join("brain/fact/base.md"), "---\ncap: essai\n---\n").unwrap();
        for a in agents {
            std::fs::create_dir_all(d.join("agents").join(a)).unwrap();
            std::fs::write(d.join("agents").join(a).join("AGENTS.md"), format!("# {a} — rôle\n\nRÔLE-{a}\n")).unwrap();
            std::fs::create_dir_all(d.join("brain/mind").join(a)).unwrap();
            std::fs::write(d.join("brain/mind").join(a).join("state.md"), "---\nmaj: 2026-01-01\n---\n").unwrap();
        }
        git(&d, &["add", "-A"]);
        git(&d, &["commit", "-q", "-m", "projet"]);
        d.canonicalize().unwrap()
    }

    fn journal(d: &Path, lignes: &[Value]) -> PathBuf {
        let p = d.join("events.jsonl");
        let t: String = lignes.iter().map(|v| format!("{v}\n")).collect();
        std::fs::write(&p, t).unwrap();
        p
    }

    fn choisi(nom: &str) -> Value { json!({"type": "subagent.selected", "data": {"agentName": nom}}) }
    fn retire() -> Value { json!({"type": "subagent.deselected", "data": {}}) }

    #[test]
    fn le_journal_rend_le_dernier_choix_et_ignore_les_sous_agents() {
        let d = dossier("journal");
        // Le démarrage tel que l'app l'écrit : deux `selected` identiques.
        let p = journal(&d, &[json!({"type": "session.start"}), choisi("ops"), choisi("ops"),
                              json!({"type": "user.message", "data": {"content": "subagent.selected ?"}})]);
        let l = lis_journal(&p);
        assert!(l.trouve);
        assert_eq!(l.lignes, 4);
        assert_eq!(l.choix, Choix::Agent { nom: "ops".into(), ligne: 2 },
                   "le doublon du démarrage ne déplace pas la ligne du choix");

        // « Default agent », puis retour, puis un sous-agent qui ne compte pas.
        let p = journal(&d, &[choisi("ops"), choisi("ops"), retire(),
                              json!({"type": "session.compaction_complete"}),
                              choisi("ops"),
                              json!({"type": "subagent.started", "agentId": "a1", "data": {"agentName": "task"}}),
                              json!({"type": "subagent.selected", "agentId": "a1", "data": {"agentName": "explore"}})]);
        let l = lis_journal(&p);
        assert_eq!(l.choix, Choix::Agent { nom: "ops".into(), ligne: 5 });
        assert_eq!(l.compactions, 1);

        let p = journal(&d, &[choisi("ops"), retire(), retire()]);
        assert_eq!(lis_journal(&p).choix, Choix::Retire { ligne: 2 });

        // Une ligne illisible ne casse pas la lecture.
        std::fs::write(&p, "{pas du json subagent.\n{\"type\":\"subagent.selected\",\"data\":{\"agentName\":\"qa\"}}\n").unwrap();
        assert_eq!(lis_journal(&p).choix, Choix::Agent { nom: "qa".into(), ligne: 2 });

        let absent = lis_journal(&d.join("absent.jsonl"));
        assert!(!absent.trouve);
        assert_eq!(absent.choix, Choix::Rien);
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn le_chemin_du_journal_ne_se_compose_qu_avec_un_identifiant_sain() {
        let m = Path::new("/maison/.copilot");
        assert_eq!(chemin_journal(&json!({"session_id": "7d09-18_41"}), m),
                   Some(m.join("session-state/7d09-18_41/events.jsonl")));
        assert_eq!(chemin_journal(&json!({"session_id": "x", "transcript_path": "/t/events.jsonl"}), m),
                   Some(PathBuf::from("/t/events.jsonl")), "la fin de tour donne le chemin");
        assert_eq!(chemin_journal(&json!({"session_id": "../../etc"}), m), None);
        assert_eq!(chemin_journal(&json!({"session_id": ""}), m), None);
        assert_eq!(chemin_journal(&json!({}), m), None);
    }

    #[test]
    fn le_nom_du_menu_designe_le_dossier() {
        let a = vec!["OPS".to_string(), "Projet QA".to_string(), "QA".to_string()];
        assert_eq!(correspond("ops", &a).as_deref(), Some("OPS"));
        assert_eq!(correspond("projet-qa", &a).as_deref(), Some("Projet QA"));
        assert_eq!(correspond("QA", &a).as_deref(), Some("QA"));
        assert_eq!(correspond("reviewer", &a), None);
        assert_eq!(nom_de_profil("Projet QA"), "projet-qa");
    }

    #[test]
    fn la_regle_menu_dossier_defaut() {
        let d = projet("regle", &["OPS", "PO", "QA"]);
        let lecture = |c: Choix| Lecture { chemin: Some(d.join("j")), trouve: true, lignes: 9,
                                            compactions: 0, choix: c };

        // 1. Le menu gagne, et le harnais se place dans le dossier de l'agent.
        let s = resous(&d, lecture(Choix::Agent { nom: "ops".into(), ligne: 2 }));
        assert_eq!(s.actif.as_deref(), Some("OPS"));
        assert_eq!(s.source, Source::Menu { ligne: 2 });
        assert_eq!(s.place, Some(d.join("agents/OPS")));

        // 2. Rien de choisi, session lancée dans un dossier d'agent : lui, sur place.
        let s = resous(&d.join("agents/PO"), lecture(Choix::Rien));
        assert_eq!((s.actif.as_deref(), &s.source, &s.place), (Some("PO"), &Source::Dossier, &None));

        // 3. « Default agent » ou rien, à la racine : QA, et c'est dit.
        let s = resous(&d, lecture(Choix::Retire { ligne: 80 }));
        assert_eq!((s.actif.as_deref(), &s.source), (Some("QA"), &Source::Defaut { ligne: Some(80) }));
        assert_eq!(s.place, Some(d.join("agents/QA")));
        let s = resous(&d, Lecture::vide());
        assert_eq!((s.actif.as_deref(), &s.source), (Some("QA"), &Source::Defaut { ligne: None }));

        // Un agent du menu qui n'est pas du projet ne prend PAS le défaut.
        let s = resous(&d, lecture(Choix::Agent { nom: "reviewer".into(), ligne: 4 }));
        assert_eq!((s.actif.as_deref(), &s.place), (None, &None));
        assert!(matches!(s.source, Source::Inconnu { .. }));

        // Le menu l'emporte sur le dossier.
        let s = resous(&d.join("agents/PO"), lecture(Choix::Agent { nom: "ops".into(), ligne: 3 }));
        assert_eq!(s.place, Some(d.join("agents/OPS")));
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn sans_qa_ni_choix_aucun_agent_et_mono_reste_mono() {
        let d = projet("sans-qa", &["OPS", "PO"]);
        let s = resous(&d, Lecture::vide());
        assert_eq!((s.actif.as_deref(), &s.source, &s.place), (None, &Source::Aucun, &None));
        let (tete, _) = lignes_briefing(&s);
        let t = tete.join("\n");
        assert!(t.contains("agent  : AUCUN") && t.contains("RIEN n'est gardé"), "{t}");
        std::fs::remove_dir_all(&d).unwrap();

        // Un dossier `agents/` de CODE, sans esprit : le projet reste mono.
        let d = projet("mono", &[]);
        std::fs::create_dir_all(d.join("agents/QA")).unwrap();
        let s = resous(&d, Lecture::vide());
        assert!(s.agents.is_empty());
        assert_eq!((&s.place, lignes_briefing(&s).0.len()), (&None, 0));
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn dans_une_copie_de_travail_le_placement_vise_la_copie() {
        let d = projet("copie", &["OPS", "QA"]);
        let w = dossier("copie-w").join("session");
        git(&d, &["worktree", "add", "-q", "-b", "session", w.to_str().unwrap()]);
        let w = w.canonicalize().unwrap();
        let s = resous(&w, Lecture { choix: Choix::Agent { nom: "ops".into(), ligne: 2 }, ..Lecture::vide() });
        assert_eq!(s.place, Some(w.join("agents/OPS")), "jamais le dossier principal");
        let (tete, fin) = lignes_briefing(&s);
        assert!(tete[0].contains("OPS") && tete[0].contains("ligne 2"), "{tete:?}");
        assert!(fin.iter().any(|l| l == "RÔLE-OPS"), "le rôle est MONTRÉ : {fin:?}");
        assert!(fin[0].contains("agents/OPS/AGENTS.md"), "chemin relatif à la vraie session : {}", fin[0]);
        git(&d, &["worktree", "remove", "--force", w.to_str().unwrap()]);
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn le_role_est_servi_hors_de_son_dossier_seulement_et_borne() {
        let d = projet("role", &["OPS", "QA"]);
        // Dans son dossier : Copilot charge le rôle, le briefing ne le double pas.
        let s = resous(&d.join("agents/OPS"), Lecture::vide());
        assert!(lignes_briefing(&s).1.is_empty());
        // Un rôle trop long est coupé, et c'est dit.
        let long: String = (0..400).map(|i| format!("ligne {i}\n")).collect();
        std::fs::write(d.join("agents/QA/AGENTS.md"), long).unwrap();
        let s = resous(&d, Lecture::vide());
        let fin = lignes_briefing(&s).1;
        assert!(fin.iter().any(|l| l.contains("coupé")));
        assert!(fin.len() < 260);
        std::fs::remove_dir_all(&d).unwrap();
    }

    #[test]
    fn la_signature_change_avec_l_agent_le_choix_et_la_compaction_pas_avec_la_lecture() {
        let d = projet("signature", &["OPS", "QA"]);
        let lu = |c: Choix, n: usize, k: usize| Lecture { chemin: Some(d.join("j")), trouve: true,
                                                          lignes: n, compactions: k, choix: c };
        let a = resous(&d, lu(Choix::Agent { nom: "ops".into(), ligne: 2 }, 10, 0)).signature();
        assert_eq!(a, resous(&d, lu(Choix::Agent { nom: "ops".into(), ligne: 2 }, 99, 0)).signature());
        assert_ne!(a, resous(&d, lu(Choix::Agent { nom: "ops".into(), ligne: 95 }, 99, 0)).signature(),
                   "un retour sur ops après « Default agent » rebriefe");
        assert_ne!(a, resous(&d, lu(Choix::Agent { nom: "ops".into(), ligne: 2 }, 99, 1)).signature(),
                   "une compaction rebriefe");
        assert_ne!(a, resous(&d, lu(Choix::Retire { ligne: 80 }, 99, 0)).signature());
        std::fs::remove_dir_all(&d).unwrap();
    }
}
