//! OÙ VIT LA MÉMOIRE D'UN PROJET — une seule autorité, pour tous.
//!
//! Port de `hooks/memoire.py`. Ce n'est pas un hook : c'est le module que les
//! autres importent. Sans autorité unique, chaque programme résoudrait de son
//! côté l'emplacement de `.mind/` et `.fact/`. Tant qu'ils sont d'accord ça ne
//! se voit pas ; le jour où l'emplacement change, un oublié ne proteste pas —
//! il lit l'ancien endroit, le trouve vide, et se tait.
//!
//! DEUX FORMES COEXISTENT, ET C'EST VOULU.
//!
//! ```text
//! en place   <projet>/.fact/ et <projet>/agents/<nom>/.mind/
//! déportée   <racine du dépôt>/memoire/ porte les deux
//! ```
//!
//! Un projet est déporté si — et seulement si — ce dossier existe.
//!
//! LE REPÈRE EST `--git-common-dir`, JAMAIS `--show-toplevel`. Le second rend
//! l'arbre de travail COURANT : appelé depuis trois copies d'un même projet il
//! rend trois chemins, donc trois dossiers `memoire/`, et on aurait
//! reconstruit avec l'outil censé réparer le défaut qu'il répare.
//!
//! **fail-open** : toute erreur rend `None`, et l'appelant retombe sur la
//! forme en place. Rendre `None` n'est PAS une erreur — c'est la réponse « ce
//! projet n'est pas déporté ».
//!
//! MAIS CE `None` A UN COÛT : `pour_agent()` rend `None` POUR DIRE « en
//! place », donc chaque appelant doit savoir ce que « en place » veut dire —
//! donc le recomposer, en dur, chacun de son côté. Le symptôme n'est pas la
//! négligence des appelants : c'est la signature.
//!
//! D'OÙ `resous()`, qui rend TOUJOURS des chemins et une FORME NOMMÉE. Le
//! `None` ne survit que pour « hors dépôt », la seule vraie absence de réponse.
//! Et la forme cesse de se DEVINER : la déduire de la présence d'un dossier,
//! en plusieurs endroits, avec deux contrats d'état qui en dépendent, ferait
//! retomber des projets sur un contrat qu'aucun ne remplit, et refuser tous
//! leurs enregistrements dès le premier jour.
//!
//! TANT QUE LES OUTILS PYTHON VIVENT, LES DEUX RÉSOLVEURS DOIVENT S'ACCORDER.
//! C'est ce que prouve la sous-commande `memoire`, qui rend le même JSON que
//! son homologue Python — un désaccord se lit à l'octet, pas à l'œil.

use std::path::{Path, PathBuf};
use std::process::Command;

const NOM: &str = "memoire";

/// LA FORME CIBLE. Un CERVEAU, plusieurs ESPRITS.
///
/// ```text
/// mono   <projet>/brain/fact/              les faits du projet
///        <projet>/brain/mind/              state.md · todo.md
///
/// multi  <racine>/brain/fact/              COMMUN aux agents, + roles.md
///        <racine>/brain/mind/<nom>/        un esprit par agent
///        <racine>/brain/workspace/         le carnet commun
/// ```
///
/// CE QUE ÇA SIMPLIFIE, et ce n'était pas prévu : le dossier est TOUJOURS à la
/// racine. « Déportée » cesse d'être une FORME — deux arbres à connaître, deux
/// branches dans chaque appelant — pour devenir une PROPRIÉTÉ : `brain/` a-t-il
/// son propre dépôt git ? Elle ne décide plus que d'une chose, où l'on commite.
const BRAIN: &str = "brain";

/// LA MÊME QUESTION N'EST POSÉE QU'UNE FOIS PAR PROCESSUS.
///
/// Sans cache, un briefing lancerait `git` à répétition pour DEUX questions
/// seulement : `--git-common-dir` et `--show-toplevel`. À 10 ms le lancement,
/// ces processus seraient la totalité du coût du hook : le hook le plus cher de
/// l'atelier ne calculerait rien, il redemanderait.
///
/// La mise en cache est SANS RISQUE DE PÉREMPTION, et c'est ce qui la rend
/// acceptable ici : la racine d'un dépôt ne peut pas changer pendant qu'un hook
/// s'exécute. Le cache meurt avec le processus — il ne peut donc pas servir une
/// réponse d'hier, ce qui est exactement le défaut que ce dispositif existe pour
/// éviter. On ne met en cache QUE ces questions de topologie ; rien qui décrive
/// un CONTENU.
fn git(depart: &Path, args: &[&str]) -> Option<String> {
    use std::collections::HashMap;
    use std::sync::{Mutex, OnceLock};
    static VUS: OnceLock<Mutex<HashMap<String, Option<String>>>> = OnceLock::new();
    let cle = format!("{}\u{1}{}", depart.display(), args.join("\u{1}"));
    if let Some(v) = VUS.get_or_init(|| Mutex::new(HashMap::new()))
                        .lock().ok().and_then(|m| m.get(&cle).cloned()) {
        return v;
    }
    let r = git_sans_cache(depart, args);
    if let Ok(mut m) = VUS.get_or_init(|| Mutex::new(HashMap::new())).lock() {
        m.insert(cle, r.clone());
    }
    r
}

fn git_sans_cache(depart: &Path, args: &[&str]) -> Option<String> {
    let o = Command::new("git").args(args).current_dir(depart).output().ok()?;
    if !o.status.success() {
        return None;
    }
    let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

/// Le point de départ : `COPILOT_PROJECT_DIR`, sinon le dossier courant.
pub fn depart_defaut() -> PathBuf {
    std::env::var("COPILOT_PROJECT_DIR")
        .ok()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

/// La racine du dépôt PRINCIPAL — la même depuis tous ses arbres de travail.
pub fn racine_depot(depart: &Path) -> Option<PathBuf> {
    let g = PathBuf::from(git(depart, &["rev-parse", "--path-format=absolute",
                                        "--git-common-dir"])?);
    if g.file_name().map(|n| n == ".git").unwrap_or(false) {
        g.parent().map(|p| p.to_path_buf())
    } else {
        None
    }
}

/// `<racine>/memoire`, ou `None` si ce projet n'est pas déporté.
pub fn base(depart: &Path) -> Option<PathBuf> {
    let racine = arbre_courant(depart)?;
    let b = racine.join(NOM);
    if b.is_dir() { Some(b) } else { None }
}

/// Même chose quand on tient déjà la racine du projet — sans appeler git.
pub fn base_projet(projet: &Path) -> Option<PathBuf> {
    let b = projet.join(NOM);
    if b.is_dir() { Some(b) } else { None }
}

/// L'arbre de travail COURANT — celui d'où l'on parle.
pub fn arbre_courant(depart: &Path) -> Option<PathBuf> {
    git(depart, &["rev-parse", "--show-toplevel"]).map(PathBuf::from)
}

/// `agents/<nom>` si l'agent en est un, sinon `""`.
///
/// LES DEUX REPÈRES NE SONT PAS INTERCHANGEABLES, et les confondre est un
/// défaut : la POSITION d'un agent se mesure dans SON arbre de travail,
/// l'IDENTITÉ du dépôt sur le dépôt principal.
pub fn lot(depart: &Path) -> String {
    let a = match arbre_courant(depart) {
        Some(a) => a,
        None => return String::new(),
    };
    let (d, a) = match (depart.canonicalize(), a.canonicalize()) {
        (Ok(d), Ok(a)) => (d, a),
        _ => return String::new(),
    };
    let rel = match d.strip_prefix(&a) {
        Ok(r) => r,
        Err(_) => return String::new(),   // hors de l'arbre : comme relative_to qui lève
    };
    let p: Vec<String> = rel.components()
        .map(|c| c.as_os_str().to_string_lossy().to_string()).collect();
    if p.len() >= 2 && p[0] == "agents" { format!("{}/{}", p[0], p[1]) } else { String::new() }
}

/// LA FORME D'UN PROJET — une valeur, plus une déduction.
///
/// Déduite de la présence d'un dossier en plusieurs endroits, elle ferait
/// changer autant de comportements à la fois dès qu'il déménage, dont le
/// contrat que `mind-guard` exige d'un état d'agent. Ici elle se transporte.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Forme {
    /// Aucun dépôt au-dessus : la plupart des gardes ne s'appliquent pas.
    HorsDepot,
    /// UN DÉPÔT, ET AUCUNE MÉMOIRE — le cas normal avant adoption. Lui donner
    /// le nom `HorsDepot` ferait écrire au diagnostic « forme : hors-depot »
    /// et, à la ligne suivante, la racine du dépôt. Même comportement partout :
    /// seul le nom diffère.
    SansMemoire,
    /// v1 · `<projet>/.fact/` et `<projet>[/agents/<nom>]/.mind/`.
    EnPlace,
    /// v1 · `<racine>/memoire/` porte les deux, pour tous les arbres de travail.
    Deportee,
    /// v2 · `<racine>/brain/` porte tout, mono comme multi. Une seule règle.
    Brain,
    /// LES DEUX À LA FOIS. État qu'une migration interrompue laisse derrière
    /// elle. On ne choisit PAS : un choix silencieux lit le mauvais fichier et
    /// se tait. L'appelant décide quoi faire d'une ambiguïté nommée.
    Ambigue,
}

impl Forme {
    pub fn mot(&self) -> &'static str {
        match self {
            Forme::HorsDepot => "hors-depot",
            Forme::SansMemoire => "sans-memoire",
            Forme::EnPlace => "en-place",
            Forme::Deportee => "deportee",
            Forme::Brain => "brain",
            Forme::Ambigue => "AMBIGUE",
        }
    }
    /// Vrai quand le projet a migré vers `.fact/` — ce que plusieurs endroits
    /// déduisaient chacun de leur côté.
    pub fn a_des_faits(&self) -> bool {
        matches!(self, Forme::EnPlace | Forme::Deportee | Forme::Brain | Forme::Ambigue)
    }
}

/// Tout ce qu'un appelant doit savoir, résolu UNE fois.
///
/// `fact` et `mind` sont absolus. `prefixe_fact` est le même dossier vu depuis
/// le DÉPÔT QUI PORTE SES COMMITS, avec sa barre finale — c'est ce que `git
/// diff --cached` rend, et c'est la seule forme contre laquelle une garde de
/// commit peut comparer. Ce dépôt n'est PAS toujours la racine : c'est l'arbre
/// courant, la mémoire déportée, ou `brain/` quand il a son propre dépôt.
/// `base_des_prefixes` le nomme.
#[derive(Debug, Clone)]
pub struct Resolution {
    pub forme: Forme,
    /// Le dépôt de mémoire : le checkout courant. Aucun repli vers la mémoire
    /// du dépôt principal — une session en worktree a la sienne.
    pub racine: Option<PathBuf>,
    /// L'arbre de travail COURANT — celui d'où l'on parle. C'est LUI qui donne
    /// les préfixes, parce que `git diff --cached` rend des chemins relatifs à
    /// l'arbre courant. Les confondre ne se voit que dans un worktree, et
    /// alors la garde compare des chemins qui ne se rencontrent jamais.
    pub arbre: Option<PathBuf>,
    pub projet: Option<PathBuf>,
    /// `agents/<nom>` — nu, c'est un identifiant.
    pub lot: String,
    /// Le même avec sa barre finale, ou vide. C'est un PRÉFIXE de chemin, et
    /// les deux ne s'échangent pas : `format!("{}.mind", lot)` sans la barre
    /// rend `agents/ios.mind`, qui ne désigne rien et ne proteste pas.
    pub prefixe_lot: String,
    /// Le NOM nu de l'agent (`Projet QA`), sans `agents/`. En v2 c'est lui qui
    /// nomme le sous-dossier de `mind/` — `agents/` n'existe plus dans le
    /// cerveau, il ne désigne que le dossier de LANCEMENT dans le code.
    pub nom_agent: String,
    pub fact: Option<PathBuf>,
    pub mind: Option<PathBuf>,
    /// Le carnet commun. N'existe qu'en équipe — en mono il n'y a personne à
    /// qui écrire, et un dossier vide se lirait comme un carnet muet.
    pub workspace: Option<PathBuf>,
    /// `brain/` a-t-il son PROPRE dépôt git ? Ne décide plus que d'une chose :
    /// où l'on commite la mémoire. C'est ce qui reste de « déportée » une fois
    /// que ce n'est plus une forme.
    pub brain_autonome: bool,
    pub prefixe_projet: String,
    pub prefixe_fact: String,
    /// L'ESPRIT VU DEPUIS LE DÉPÔT QUI PORTE LES COMMITS — avec barre finale.
    ///
    /// Il existe parce que `mind_guard` le composait à la main
    /// (`format!("{}.mind/state.md", lot)`) : sur un arbre migré vers `brain/`
    /// ce nom ne désigne plus rien, et le contrôle de lisibilité laissait
    /// passer un `state.md` sans en-tête sans un mot. Même défaut que `prefixe_fact` réparait, à un dossier près.
    pub prefixe_mind: String,
}

impl Resolution {
    /// Le dossier depuis lequel se lisent `prefixe_fact`, `prefixe_mind` et
    /// `prefixe_projet` — `None` quand il n'y a rien à préfixer.
    pub fn base_des_prefixes(&self) -> Option<PathBuf> {
        match self.forme {
            Forme::Brain if self.brain_autonome => self.projet.clone(),
            Forme::Brain | Forme::EnPlace => self.arbre.clone(),
            Forme::Deportee => self.racine.as_ref().map(|r| r.join(NOM)),
            Forme::HorsDepot | Forme::SansMemoire | Forme::Ambigue => None,
        }
    }
    /// OÙ LE CARNET D'ÉQUIPE DOIT VIVRE — qu'il existe déjà ou non.
    ///
    /// `workspace` ci-dessus ne rend le chemin que si le dossier EST là : c'est
    /// ce qu'il faut pour lire. Pour CRÉER, il faut l'emplacement prévu, et
    /// c'est ce que cette fonction rend.
    ///
    /// UNE SEULE VÉRITÉ, ICI. Cette règle existerait en DEUX exemplaires : ici,
    /// qui connaît les trois formes, et dans `carnet.rs`, qui n'en connaîtrait
    /// que deux — `memoire/equipe` et `equipe`. Sur un projet en `brain/`,
    /// `equipe-amorce` créerait donc le carnet à la racine pendant que le
    /// résolveur le cherche dans le cerveau : **le carnet naîtrait invisible**,
    /// et rien ne le dirait.
    pub fn workspace_prevu(&self) -> Option<PathBuf> {
        match self.forme {
            // Le cerveau range le commun avec le reste du commun.
            Forme::Brain => self.projet.as_ref().map(|c| c.join("workspace")),
            // Déportée : à côté de la mémoire, pas à côté du code.
            Forme::Deportee => self.projet.as_ref().map(|b| b.join("equipe")),
            Forme::EnPlace | Forme::HorsDepot | Forme::SansMemoire => self.racine.as_ref().map(|r| r.join("equipe")),
            // AMBIGUË : deux arbres cohabitent, on ne choisit pas. Créer un
            // carnet ici, c'est en créer un que l'autre arbre ne verra pas.
            Forme::Ambigue => None,
        }
    }
}

fn prefixe(p: &Path, racine: &Path) -> String {
    match p.strip_prefix(racine) {
        Ok(r) if r.as_os_str().is_empty() => String::new(),
        Ok(r) => format!("{}/", r.to_string_lossy()),
        Err(_) => String::new(),
    }
}

/// Le premier ancêtre qui porte un `.fact/`, sans jamais sortir du dépôt.
fn porteur_des_faits(depart: &Path, racine: &Path) -> Option<PathBuf> {
    let mut p = depart.to_path_buf();
    loop {
        if p.join(".fact").is_dir() {
            return Some(p);
        }
        if p == racine {
            return None;
        }
        match p.parent() {
            Some(q) => p = q.to_path_buf(),
            None => return None,
        }
    }
}

/// LA RÉSOLUTION. Toujours des chemins, toujours une forme nommée.
pub fn resous(depart: &Path) -> Resolution {
    resous_depuis(depart, depart)
}

/// La même, quand GIT ne tourne pas là où l'agent se tient.
///
/// Les deux coïncident presque toujours, et c'est ce qui rend la confusion
/// invisible. Mais la garde de commit juge l'index du dépôt où `git commit`
/// s'exécute — le DOSSIER COURANT — pendant que la position de l'agent se lit
/// sur `COPILOT_PROJECT_DIR`. Les confondre ne se voit que si les deux pointent
/// des dépôts différents, et alors on juge le mauvais index en silence.
pub fn resous_depuis(ou_git: &Path, depart: &Path) -> Resolution {
    let vide = Resolution {
        forme: Forme::HorsDepot, racine: None, arbre: None, projet: None,
        lot: String::new(), prefixe_lot: String::new(),
        nom_agent: String::new(), workspace: None, brain_autonome: false, fact: None, mind: None,
        prefixe_projet: String::new(), prefixe_fact: String::new(),
        prefixe_mind: String::new(),
    };
    // CANONICALISÉE, comme `arbre` et `deportee` plus bas. C'est la MÊME
    // divergence, sur le champ qui l'avait échappé : `racine_depot()` rend ce
    // que git écrit, et tout le reste de la résolution passe par
    // `canonicalize()`. Deux orthographes du même dossier dans une seule
    // structure, et celle du carnet d'équipe se composait sur la mauvaise.
    // Sous Windows, le témoin du carnet attendrait `\\?\C:\…\equipe` et
    // recevrait `C:/…\equipe`. macOS ne peut pas le voir — les deux
    // orthographes y coïncident, et c'est ce qui laisserait passer le champ.
    let racine = match racine_depot(ou_git) { Some(r) => r, None => return vide };
    let principal = racine.canonicalize().unwrap_or(racine);
    // L'arbre courant sert à TOUTE l'arithmétique de chemins ; la racine ne
    // sert qu'à trouver la mémoire déportée. Hors worktree les deux coïncident,
    // et c'est ce qui rend la confusion presque toujours invisible.
    let arbre = arbre_courant(ou_git).and_then(|a| a.canonicalize().ok())
        .unwrap_or_else(|| principal.clone());
    // Copilot App isole les sessions en worktrees : leurs faits et leur état
    // appartiennent au checkout, jamais au poste principal de l'utilisateur.
    let racine = arbre.clone();
    let l = lot(depart);
    let lp = if l.is_empty() { String::new() } else { format!("{}/", l) };
    // CANONICALISÉ, comme `arbre`. `racine_depot()` rend ce que git écrit —
    // sous Windows `C:/x/y`, avec des barres obliques — tandis que tout le
    // reste d'ici passe par `canonicalize()`, qui rend `\\?\C:\x\y`. Les deux
    // désignent le même dossier et Rust les lit toutes deux, mais elles ne
    // sont PAS ÉGALES : un `strip_prefix` entre les deux ne mord pas, et rien
    // ne le signale. Visible sous Windows seulement — le portage diverge sur
    // les bords, jamais au milieu.
    let deportee = base_projet(&racine).map(|b| b.canonicalize().unwrap_or(b));

    let depart_c = depart.canonicalize().unwrap_or_else(|_| depart.to_path_buf());
    let en_place = porteur_des_faits(&depart_c, &arbre);
    let nom = l.rsplit('/').next().unwrap_or("").to_string();

    // ── L'ANCIEN ET LE NEUF EN MÊME TEMPS ? ─────────────────────────────
    // La question se pose AVANT de choisir lequel lire : c'est ce qu'une
    // migration interrompue laisse derrière elle, et servir l'un des deux
    // servirait l'état d'hier, sans un mot.
    //
    // ELLE NE PORTE QUE SUR v1 CONTRE v2. À l'intérieur de v1, `memoire/` et
    // un `.fact/` résiduel cohabitent LÉGITIMEMENT — le déport ne supprime pas
    // l'ancien dossier, et la règle « le déporté gagne » est établie. Élargie
    // de trop, elle ferait cesser des briefings de trouver leurs faits — le
    // contrôle différentiel le dit tout de suite.
    let cerveau = racine.join(BRAIN);
    if cerveau.is_dir() && (deportee.is_some() || en_place.is_some()) {
        return Resolution {
            forme: Forme::Ambigue,
            fact: None, mind: None, workspace: None, brain_autonome: false,
            projet: None, prefixe_projet: String::new(), prefixe_fact: String::new(),
            prefixe_mind: String::new(),
            lot: l, prefixe_lot: lp, nom_agent: nom,
            racine: Some(racine), arbre: Some(arbre),
        };
    }

    // ── v2 · LE CERVEAU ─────────────────────────────────────────────────
    // Une seule règle, mono comme multi.
    if cerveau.is_dir() {
        let c = cerveau.canonicalize().unwrap_or(cerveau);
        let esprit = if nom.is_empty() { c.join("mind") } else { c.join("mind").join(&nom) };
        let ws = c.join("workspace");
        return Resolution {
            forme: Forme::Brain,
            brain_autonome: c.join(".git").exists(),
            fact: Some(c.join("fact")),
            mind: Some(esprit),
            workspace: if ws.is_dir() { Some(ws) } else { None },
            projet: Some(c),
            // Les chemins que la garde compare viennent du dépôt qui porte le
            // cerveau : nus s'il est autonome, préfixés sinon.
            prefixe_projet: String::new(),
            prefixe_fact: format!("{}fact/", if racine.join(BRAIN).join(".git").exists()
                                              { String::new() } else { format!("{}/", BRAIN) }),
            prefixe_mind: format!("{}mind/{}", if racine.join(BRAIN).join(".git").exists()
                                               { String::new() } else { format!("{}/", BRAIN) },
                                  if nom.is_empty() { String::new() }
                                  else { format!("{}/", nom) }),
            lot: l, prefixe_lot: lp, nom_agent: nom,
            racine: Some(racine), arbre: Some(arbre),
        };
    }
    if let Some(b) = deportee {
        // DÉPORTÉE. Les chemins de commit visent le dépôt de MÉMOIRE, pas celui
        // du code : le préfixe y est donc nu, sans le lot.
        return Resolution {
            forme: Forme::Deportee,
            fact: Some(b.join(".fact")),
            mind: Some(if l.is_empty() { b.join(".mind") } else { b.join(&l).join(".mind") }),
            projet: Some(b.clone()),
            prefixe_projet: String::new(),
            prefixe_fact: ".fact/".into(),
            prefixe_mind: format!("{}.mind/", lp),
            lot: l, prefixe_lot: lp, nom_agent: nom,
            workspace: { let w = b.join("equipe"); if w.is_dir() { Some(w) } else { None } },
            brain_autonome: b.join(".git").exists(),
            racine: Some(racine), arbre: Some(arbre),
        };
    }

    match en_place {
        Some(p) => Resolution {
            forme: Forme::EnPlace,
            prefixe_projet: prefixe(&p, &arbre),
            prefixe_fact: format!("{}.fact/", prefixe(&p, &arbre)),
            prefixe_mind: format!("{}.mind/", lp),
            fact: Some(p.join(".fact")),
            mind: Some(arbre.join(&l).join(".mind")),
            projet: Some(p), lot: l, prefixe_lot: lp, nom_agent: nom,
            workspace: None, brain_autonome: false,
            racine: Some(racine), arbre: Some(arbre),
        },
        // Un dépôt sans `.fact/` : forme d'AVANT la migration. Les chemins sont
        // rendus quand même — l'appelant doit pouvoir dire « cherché ici,
        // absent », jamais rester muet.
        None => Resolution {
            forme: Forme::SansMemoire,
            mind: Some(arbre.join(&l).join(".mind")),
            fact: None,
            projet: None,
            prefixe_projet: String::new(),
            prefixe_fact: String::new(),
            prefixe_mind: format!("{}.mind/", lp),
            lot: l, prefixe_lot: lp, nom_agent: nom,
            workspace: None, brain_autonome: false,
            racine: Some(racine), arbre: Some(arbre),
        },
    }
}

/// `(mind, fact)` pour l'agent qui parle — ou `(None, None)` si en place.
pub fn pour_agent(depart: &Path) -> (Option<PathBuf>, Option<PathBuf>) {
    let b = match base(depart) {
        Some(b) => b,
        None => return (None, None),
    };
    let l = lot(depart);
    let mind = if l.is_empty() { b.join(".mind") } else { b.join(&l).join(".mind") };
    (Some(mind), Some(b.join(".fact")))
}

/// `(fact, [(nom, mind)])` — la vue de tout le projet, pour les tableaux.
pub fn pour_projet(projet: &Path) -> (Option<PathBuf>, Option<Vec<(Option<String>, PathBuf)>>) {
    let b = match base_projet(projet) {
        Some(b) => b,
        None => return (None, None),
    };
    let fact = b.join(".fact");
    let mut etats: Vec<(Option<String>, PathBuf)> = Vec::new();
    let ag = b.join("agents");
    if ag.is_dir() {
        if let Ok(it) = std::fs::read_dir(&ag) {
            let mut v: Vec<PathBuf> = it.filter_map(|e| e.ok().map(|e| e.path())).collect();
            v.sort();   // `sorted()` de Python : par chaîne, même parent donc par nom
            for d in v {
                if d.join(".mind").is_dir() {
                    etats.push((Some(d.file_name().unwrap_or_default()
                                      .to_string_lossy().to_string()), d.join(".mind")));
                }
            }
        }
    }
    if etats.is_empty() && b.join(".mind").is_dir() {
        etats.push((None, b.join(".mind")));
    }
    (if fact.is_dir() { Some(fact) } else { None },
     if etats.is_empty() { None } else { Some(etats) })
}

fn j(p: &Option<PathBuf>) -> serde_json::Value {
    p.as_ref().map(|x| serde_json::Value::String(x.to_string_lossy().into()))
        .unwrap_or(serde_json::Value::Null)
}

/// `harnais memoire [depart]` — rend la résolution en JSON, pour la comparer
/// à celle de Python. C'est un instrument, pas un hook.
pub fn main(args: &[String]) {
    let depart = args.first().map(PathBuf::from).unwrap_or_else(depart_defaut);
    let (mind, fact) = pour_agent(&depart);
    let (pf, pe) = pour_projet(&depart);
    let etats = match pe {
        None => serde_json::Value::Null,
        Some(v) => serde_json::Value::Array(v.into_iter().map(|(n, m)| {
            serde_json::json!([n, m.to_string_lossy()])
        }).collect()),
    };
    println!("{}", serde_json::json!({
        "racine_depot": j(&racine_depot(&depart)),
        "base":         j(&base(&depart)),
        "base_projet":  j(&base_projet(&depart)),
        "arbre":        j(&arbre_courant(&depart)),
        "lot":          lot(&depart),
        "mind":         j(&mind),
        "fact":         j(&fact),
        "projet_fact":  j(&pf),
        "projet_etats": etats,
    }));
}

/// LA RÉSOLUTION ENTIÈRE, EN JSON — pour les outils du poste.
///
/// `memoire` existe déjà et rend un contrat d'AVANT `brain/`, que le contrôle
/// différentiel compare octet pour octet à la version Python. Y ajouter des
/// champs le ferait échouer pour une bonne raison ; on ajoute donc une porte,
/// on ne déforme pas l'ancienne. Elle disparaîtra avec Python.
///
/// Elle existe pour que les outils hors de ce programme cessent de recomposer
/// `<projet>/.fact` à la main. Sinon ils rendraient
/// « mémoire absente » sur un projet migré, ce qui est la forme la plus
/// dangereuse de faux : un tableau de bord vide se lit comme un projet vide.
pub fn resolution_json(args: &[String]) -> i32 {
    let d = args.first().map(PathBuf::from)
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default());
    let r = resous(&d);
    let s = |o: &Option<PathBuf>| match o {
        Some(p) => format!("{:?}", p.to_string_lossy()),
        None => "null".to_string(),
    };
    println!(
"{{\"forme\":{:?},\"racine\":{},\"arbre\":{},\"projet\":{},\"fact\":{},\"mind\":{},\
\"workspace\":{},\"lot\":{:?},\"nom_agent\":{:?},\"brain_autonome\":{},\
\"prefixe_fact\":{:?},\"prefixe_mind\":{:?},\"prefixe_projet\":{:?},\"prefixes_depuis\":{},\
\"a_des_faits\":{}}}",
        r.forme.mot(), s(&r.racine), s(&r.arbre), s(&r.projet), s(&r.fact), s(&r.mind),
        s(&r.workspace), r.lot, r.nom_agent, r.brain_autonome,
        r.prefixe_fact, r.prefixe_mind, r.prefixe_projet, s(&r.base_des_prefixes()),
        r.forme.a_des_faits());
    0
}

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn copilot_resout_la_memoire_du_worktree_jamais_celle_du_principal() {
        let d = depot("worktree-isole");
        let git = |args: &[&str]| {
            let o = Command::new("git").args(["-c", "user.name=test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false"]).args(args).current_dir(&d).output().unwrap();
            assert!(o.status.success(), "{args:?} : {}", String::from_utf8_lossy(&o.stderr));
        };
        std::fs::create_dir_all(d.join("brain/fact")).unwrap();
        std::fs::create_dir_all(d.join("brain/mind")).unwrap();
        std::fs::write(d.join("brain/fact/base.md"), "principal").unwrap();
        git(&["add", "."]);
        git(&["commit", "-qm", "initial"]);
        let w = PathBuf::from(d.to_string_lossy().trim_start_matches(r"\\?\")).join("copie");
        git(&["worktree", "add", "-q", "-b", "copie", w.to_str().unwrap()]);
        std::fs::write(w.join("brain/fact/base.md"), "copie").unwrap();
        let r = resous(&w);
        assert_eq!(r.racine, Some(w.canonicalize().unwrap()));
        assert_eq!(r.fact, Some(w.canonicalize().unwrap().join("brain/fact")));
        assert_eq!(std::fs::read_to_string(r.fact.unwrap().join("base.md")).unwrap(), "copie");
        std::fs::remove_dir_all(w.join("brain")).unwrap();
        assert_eq!(resous(&w).forme, Forme::SansMemoire, "pas de repli sur le principal");
        git(&["worktree", "remove", "--force", w.to_str().unwrap()]);
        std::fs::remove_dir_all(d).unwrap();
    }

    fn bac(n: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("harnais-memoire-{}", n));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d.canonicalize().unwrap()
    }

    /// LE PRÉFIXE DE L'ESPRIT SUIT LA FORME, dans les trois formes.
    ///
    /// `mind_guard` composait ce chemin à la main. Sur un arbre migré le nom
    /// composé ne désignait plus rien, et le contrôle de lisibilité laissait
    /// passer un `state.md` sans en-tête. Ce test épingle les trois formes
    /// ensemble : c'est leur DIVERGENCE qui est le sujet, pas l'une d'elles.
    #[test]
    fn le_prefixe_de_l_esprit_suit_la_forme() {
        let d = bac("pfx-mind");
        let git = |a: &[&str]| { let _ = std::process::Command::new("git")
            .args(a).current_dir(&d).output(); };
        git(&["init", "-q", "-b", "main"]);

        // v1 · en place
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        std::fs::create_dir_all(d.join(".mind")).unwrap();
        assert_eq!(resous(&d).prefixe_mind, ".mind/");

        // v2 · LE CERVEAU, ET L'ANCIEN A DISPARU. Les laisser cohabiter rend
        // `Ambigue` — c'est le but de cette forme, et la migration retire
        // l'ancien dans le même geste. Créer les deux et attendre `Brain`
        // épinglerait un arbre qui ne peut pas exister après migration.
        std::fs::remove_dir_all(d.join(".fact")).unwrap();
        std::fs::remove_dir_all(d.join(".mind")).unwrap();
        std::fs::create_dir_all(d.join("brain/fact")).unwrap();
        std::fs::create_dir_all(d.join("brain/mind")).unwrap();
        let r = resous(&d);
        assert_eq!(r.prefixe_mind, "brain/mind/");
        assert_eq!(r.prefixe_fact, "brain/fact/");

        // v2 · le cerveau, à plusieurs — l'esprit porte le nom de l'agent
        let a = d.join("agents/ios");
        std::fs::create_dir_all(a.join(".github/copilot")).unwrap();
        std::fs::create_dir_all(d.join("brain/mind/ios")).unwrap();
        let r = resous(&a);
        assert_eq!(r.prefixe_mind, "brain/mind/ios/");
        // ET LE COMMUN RESTE COMMUN : les faits ne prennent pas le nom.
        assert_eq!(r.prefixe_fact, "brain/fact/");
    }

    #[test]
    fn hors_depot_tout_rend_none() {
        let d = bac("hors");
        // TÉMOIN NÉGATIF : sans dépôt, aucune résolution ne doit inventer un chemin.
        assert_eq!(racine_depot(&d), None);
        assert_eq!(base(&d), None);
        assert_eq!(pour_agent(&d), (None, None));
        assert_eq!(lot(&d), "");
    }

    #[test]
    fn un_projet_sans_dossier_memoire_ne_bouge_pas() {
        let d = bac("enplace");
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        // Pas de `memoire/` : la réponse est « résous comme avant », pas une erreur.
        assert_eq!(base_projet(&d), None);
        assert_eq!(pour_projet(&d), (None, None));
    }

    #[test]
    fn un_projet_deporte_rend_ses_deux_maisons() {
        let d = bac("deporte");
        for s in [".fact", ".mind", "agents/Projet PO/.mind", "agents/QA/.mind"] {
            std::fs::create_dir_all(d.join(NOM).join(s)).unwrap();
        }
        let (fact, etats) = pour_projet(&d);
        assert_eq!(fact, Some(d.join(NOM).join(".fact")));
        let e = etats.unwrap();
        // Deux agents, classés — et le `.mind` racine EST ignoré quand des
        // agents existent : c'est la règle de la version Python.
        assert_eq!(e.len(), 2);
        assert_eq!(e[0].0.as_deref(), Some("Projet PO"));
        assert_eq!(e[1].0.as_deref(), Some("QA"));
    }

    #[test]
    fn mono_agent_retombe_sur_le_mind_racine() {
        let d = bac("mono");
        std::fs::create_dir_all(d.join(NOM).join(".mind")).unwrap();
        let (_, etats) = pour_projet(&d);
        let e = etats.unwrap();
        assert_eq!(e.len(), 1);
        assert_eq!(e[0].0, None, "aucun nom : c'est le projet lui-même");
    }

    // ── `resous()` : la forme est une VALEUR ──────────────────────────────
    //
    // Chaque cas porte son contraire. Un contrôle qui ne rend jamais `Ambigue`
    // ne prouve pas qu'il sait la reconnaître.

    fn depot(n: &str) -> PathBuf {
        let d = bac(n);
        std::process::Command::new("git").args(["init", "-q"]).current_dir(&d)
            .output().unwrap();
        d
    }

    #[test]
    fn resous_hors_depot_ne_devine_rien() {
        let r = resous(&bac("r-hors"));
        assert_eq!(r.forme, Forme::HorsDepot);
        assert_eq!(r.racine, None);
        assert_eq!(r.fact, None);
        // TÉMOIN : hors dépôt, `mind` aussi reste vide — sinon on inventerait
        // un chemin dans un dossier qui n'appartient à personne.
        assert_eq!(r.mind, None);
        assert!(!r.forme.a_des_faits());
    }

    #[test]
    fn un_depot_sans_memoire_ne_se_dit_plus_hors_depot() {
        // Ce cas se nommait « hors-depot » alors que la ligne suivante du
        // diagnostic donnait la racine du dépôt.
        let d = depot("r-sansmem");
        let r = resous(&d);
        assert_eq!(r.forme, Forme::SansMemoire);
        assert_eq!(r.forme.mot(), "sans-memoire");
        assert!(r.racine.is_some());
        assert_eq!(r.base_des_prefixes(), None);
        // TÉMOIN : le même dossier avec des faits change de forme, et sa base
        // des préfixes est l'arbre — pas `None` pour tout le monde.
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        let r = resous(&d);
        assert_eq!(r.forme, Forme::EnPlace);
        assert_eq!(r.base_des_prefixes(), r.arbre);
        assert!(r.base_des_prefixes().is_some());
    }

    #[test]
    fn resous_en_place_rend_des_chemins_et_un_prefixe() {
        let d = depot("r-enplace");
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        let r = resous(&d);
        assert_eq!(r.forme, Forme::EnPlace);
        assert_eq!(r.fact, Some(d.join(".fact")));
        assert_eq!(r.mind, Some(d.join(".mind")));
        // Le préfixe est ce que `git diff --cached` rend, barre finale comprise.
        assert_eq!(r.prefixe_fact, ".fact/");
        assert!(r.forme.a_des_faits());
    }

    #[test]
    fn resous_en_place_depuis_un_agent_porte_le_lot() {
        let d = depot("r-agent");
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        let a = d.join("agents").join("QA");
        std::fs::create_dir_all(&a).unwrap();
        let r = resous(&a);
        assert_eq!(r.forme, Forme::EnPlace);
        assert_eq!(r.lot, "agents/QA");
        // Les faits sont au PROJET, l'état est à l'AGENT — c'est toute la règle.
        assert_eq!(r.fact, Some(d.join(".fact")));
        assert_eq!(r.mind, Some(d.join("agents/QA/.mind")));
        assert_eq!(r.prefixe_fact, ".fact/");
    }

    #[test]
    fn resous_deportee_vise_le_depot_de_memoire() {
        let d = depot("r-deporte");
        std::fs::create_dir_all(d.join(NOM).join(".fact")).unwrap();
        let r = resous(&d);
        assert_eq!(r.forme, Forme::Deportee);
        assert_eq!(r.fact, Some(d.join(NOM).join(".fact")));
        // DÉPORTÉE : le préfixe est NU. Les chemins que la garde compare
        // viennent du dépôt de mémoire, où le lot n'existe pas.
        assert_eq!(r.prefixe_fact, ".fact/");
        assert_eq!(r.prefixe_projet, "");
        assert!(r.forme.a_des_faits());
    }

    #[test]
    fn dans_la_v1_le_deporte_gagne_et_ce_n_est_pas_une_ambiguite() {
        let d = depot("r-v1-deux");
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        std::fs::create_dir_all(d.join(NOM).join(".fact")).unwrap();
        let r = resous(&d);
        // LE DÉPORT NE SUPPRIME PAS L'ANCIEN DOSSIER : les deux cohabitent
        // légitimement, et la règle « le déporté gagne » est établie. Élargir
        // l'ambiguïté à ce cas ferait cesser des briefings de trouver leurs
        // faits. Un garde trop large casse ce qu'il devait protéger.
        assert_eq!(r.forme, Forme::Deportee);
        assert_eq!(r.fact, Some(d.join(NOM).join(".fact")));
    }

    #[test]
    fn resous_sans_faits_ne_pretend_pas_en_avoir() {
        let d = depot("r-avant");
        // Ni `.fact/` ni `memoire/` : la forme d'AVANT la migration.
        let r = resous(&d);
        assert_eq!(r.fact, None);
        // TÉMOIN : c'est ici que se jouait le piège du `cap:`. Un projet sans
        // faits ne doit pas être annoncé comme en ayant, sinon la garde de
        // commit lui réclame le mauvais contrat d'en-tête.
        assert!(!r.forme.a_des_faits());
        // Mais le chemin de l'état est rendu quand même : l'appelant doit
        // pouvoir dire « cherché ici, absent », jamais rester muet.
        assert_eq!(r.mind, Some(d.join(".mind")));
    }

    // ── v2 · le cerveau ──────────────────────────────────────────────────

    #[test]
    fn resous_v2_mono_un_seul_esprit() {
        let d = depot("r-brain-mono");
        for s in ["fact", "mind"] {
            std::fs::create_dir_all(d.join(BRAIN).join(s)).unwrap();
        }
        let r = resous(&d);
        assert_eq!(r.forme, Forme::Brain);
        assert_eq!(r.fact, Some(d.join(BRAIN).join("fact")));
        // MONO : pas de niveau `<nom>`. Il n'y a qu'un esprit, le nommer serait
        // inventer une équipe qui n'existe pas.
        assert_eq!(r.mind, Some(d.join(BRAIN).join("mind")));
        // Pas de carnet non plus : personne à qui écrire, et un dossier vide
        // se lirait comme un carnet muet.
        assert_eq!(r.workspace, None);
        assert!(!r.brain_autonome);
        assert!(r.forme.a_des_faits());
    }

    /// LE CARNET NAÎT LÀ OÙ ON LE CHERCHE, dans chaque forme.
    ///
    /// Une règle en double — la copie de `carnet.rs` ne connaîtrait pas le
    /// cerveau — créerait, sur un projet en `brain/`, le carnet à la racine
    /// alors qu'il est cherché dans le cerveau : il naîtrait invisible, sans
    /// un mot.
    ///
    /// Le témoin porte les deux sens : chaque forme rend SON emplacement, et
    /// aucune ne rend celui d'une autre. Une fonction qui répondrait `equipe`
    /// à tout passerait le seul cas `en-place`.
    #[test]
    fn le_carnet_nait_la_ou_on_le_cherche() {
        let d = depot("r-ws");
        // en place : le carnet est à la racine du dépôt de code
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        assert_eq!(resous(&d).workspace_prevu(), Some(d.join("equipe")));

        // cerveau : le carnet est DANS le cerveau, pas à côté
        let b = depot("r-ws-brain");
        std::fs::create_dir_all(b.join(BRAIN).join("fact")).unwrap();
        let vu = resous(&b).workspace_prevu().unwrap();
        assert!(vu.ends_with("brain/workspace"), "cerveau : rendu {vu:?}");
        assert!(!vu.ends_with("equipe"), "cerveau : rend l'emplacement d'en-place");

        // AMBIGUË : deux arbres, aucun choix. Créer ici, c'est créer un carnet
        // que l'autre arbre ne verra jamais.
        let a = depot("r-ws-ambigu");
        std::fs::create_dir_all(a.join(BRAIN).join("fact")).unwrap();
        std::fs::create_dir_all(a.join(".fact")).unwrap();
        assert_eq!(resous(&a).forme, Forme::Ambigue);
        assert_eq!(resous(&a).workspace_prevu(), None);
    }

    /// UNE SEULE ORTHOGRAPHE PAR DOSSIER, dans toute la résolution.
    ///
    /// Hors worktree, `racine` et `arbre` désignent le même dossier. S'ils ne
    /// s'écrivent pas pareil, tout ce qui mélange les deux — `strip_prefix`,
    /// `==`, la composition du carnet — cesse de mordre sans rien dire.
    ///
    /// TÉMOIN NÉGATIF : sous Windows, avec la racine non canonicalisée, `racine`
    /// vaudrait `C:/…` et `arbre` `\\?\C:\…` ; le témoin du carnet tomberait
    /// là-dessus. Sur macOS les deux orthographes coïncident : ce test y passe
    /// dans les deux sens, et c'est exactement pourquoi le défaut ne se voit que
    /// sous Windows.
    #[test]
    fn la_racine_et_l_arbre_s_ecrivent_pareil() {
        let d = depot("r-orthographe");
        std::fs::create_dir_all(d.join(".fact")).unwrap();
        let r = resous(&d);
        assert_eq!(r.racine, r.arbre, "deux orthographes du même dossier");
        // Et le carnet se compose sur cette orthographe-là, pas sur une autre.
        assert_eq!(r.workspace_prevu(), Some(d.join("equipe")));
    }

    #[test]
    fn resous_v2_multi_un_esprit_par_agent() {
        let d = depot("r-brain-multi");
        for s in ["fact", "mind/Projet QA", "workspace"] {
            std::fs::create_dir_all(d.join(BRAIN).join(s)).unwrap();
        }
        std::fs::create_dir_all(d.join("agents").join("Projet QA")).unwrap();
        let r = resous(&d.join("agents").join("Projet QA"));
        assert_eq!(r.forme, Forme::Brain);
        assert_eq!(r.lot, "agents/Projet QA");
        // `agents/` n'existe PAS dans le cerveau : il ne désigne que le dossier
        // de lancement, dans le code. Le cerveau range par NOM.
        assert_eq!(r.nom_agent, "Projet QA");
        assert_eq!(r.mind, Some(d.join(BRAIN).join("mind").join("Projet QA")));
        assert_eq!(r.fact, Some(d.join(BRAIN).join("fact")));
        assert_eq!(r.workspace, Some(d.join(BRAIN).join("workspace")));
    }

    #[test]
    fn resous_refuse_de_choisir_entre_les_trois_arbres() {
        // TROIS combinaisons, et aucune ne doit rendre un arbre. C'est l'état
        // qu'une migration interrompue laisse : servir l'un des deux servirait
        // l'état d'hier, sans un mot.
        // L'ANCIEN CONTRE LE NEUF, et seulement ça. `.fact` + `memoire` est
        // une cohabitation de v1, pas une migration à moitié faite.
        for (a, b) in [(".fact", BRAIN), (NOM, BRAIN)] {
            let d = depot(&format!("r-3arbres-{}-{}", a.trim_start_matches('.'), b));
            std::fs::create_dir_all(d.join(a)).unwrap();
            std::fs::create_dir_all(d.join(b)).unwrap();
            let r = resous(&d);
            assert_eq!(r.forme, Forme::Ambigue, "{} + {} devait être ambigu", a, b);
            // ET RIEN N'EST RENDU. Un chemin rendu serait lu.
            assert_eq!(r.fact, None);
            assert_eq!(r.mind, None);
        }
    }

    #[test]
    fn resous_v2_sait_si_le_cerveau_a_son_depot() {
        let d = depot("r-brain-autonome");
        std::fs::create_dir_all(d.join(BRAIN).join("fact")).unwrap();
        assert!(!resous(&d).brain_autonome);
        // Ce qui reste de « déportée » une fois que ce n'est plus une forme :
        // une propriété, qui ne décide que d'une chose — où l'on commite.
        std::process::Command::new("git").args(["init", "-q"])
            .current_dir(d.join(BRAIN)).output().unwrap();
        assert!(resous(&d).brain_autonome);
    }
}
