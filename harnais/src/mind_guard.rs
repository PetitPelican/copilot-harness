//! LE GARDE DE COMMIT — hook PreToolUse (Bash), sur `git commit`.
//!
//! Port de `hooks/mind-guard.py`. Il garde deux choses, et pas la même façon :
//!
//! ```text
//! .fact/          mémoire PARTAGÉE du projet — ne s'écrit qu'à la demande
//! .mind/state.md  déclaration de l'agent — doit rester LISIBLE et FRAÎCHE
//! ```
//!
//! UN EN-TÊTE CASSÉ EST PIRE QU'UN EN-TÊTE VIEUX. Le tableau de bord range le
//! projet en « aucune déclaration » et il disparaît du tableau de bord sans que
//! personne s'en aperçoive : un fichier illisible est un silence, et un silence
//! se lit comme une absence de problème.
//!
//! LES DEUX ÉCHAPPATOIRES SE LISENT EN FIN DE COMMANDE, PAS N'IMPORTE OÙ.
//! C'était un test de sous-chaîne brut : une branche `essai-fact-ok` désarmait
//! le garde, sans intention et sans trace. Et `mind-ok` ne lève QUE les règles
//! sur la déclaration de l'agent — jamais celle sur `.fact/`, qui protège la
//! mémoire des autres agents. Une clé, une serrure.
//!
//! **fail-open** : toute erreur, ambiguïté ou dépôt non git laisse passer.
//!
//! CE QUE LE PORTAGE COMPARE. La sortie est un document JSON lu par un
//! analyseur, pas un flux d'octets : Python échappe les accents en `\uXXXX`,
//! Rust les écrit tels quels. Le contrôle différentiel compare donc les JSON
//! ANALYSÉS — même document, deux encodages. Tout le reste, y compris le texte
//! exact de chaque refus, doit coïncider au caractère près.

use regex::Regex;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::memoire;

// --- à ajuster selon le projet ---------------------------------------------
const PREFIXES_IGNORES: &[&str] = &[".github/copilot/", ".mind/", ".fact/", "docs/",
                                    ".memory/", ".logs/"];
const EXT_CODE: &[&str] = &[
    ".py", ".sql", ".qmd", ".ipynb", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".h", ".hpp", ".cpp", ".cc",
    ".cs", ".swift", ".scala", ".sh", ".ps1", ".r", ".jl", ".vue", ".svelte",
    ".dart", ".ex", ".exs",
];
const DOSSIERS_SRC: &[&str] = &["src/", "app/", "lib/", "python/", "sql/",
                                "packages/", "services/", "api/"];
// ---------------------------------------------------------------------------

/// Deux contrats, selon la forme. Avant migration le `cap` est dans
/// `state.md` ; après, il appartient au projet et vit dans `.fact/base.md` —
/// le réclamer ici ferait échouer tout commit d'un projet correctement migré.
/// LES NOMS QUE LE SOCLE PRÉVOIT. Ils sont ici et dans `migration.rs`, qui
/// s'en sert comme condition AVANT de déplacer — deux emplois, une seule
/// liste ne suffirait que si les deux vivaient dans le même module ; à défaut,
/// les changer ensemble. `roles.md` n'existe qu'à plusieurs agents, et on ne
/// le refuse pas en mono : un projet qui vient de se convertir le porte avant
/// que quoi que ce soit d'autre ne bouge.
// La liste vit dans le socle : voir `socle::FAITS_MONO`. Trois copies (ici,
// dans `briefing.rs` et dans `migration.rs`) d'accord entre elles seraient la
// forme la plus tranquille d'un futur désaccord.
fn noms_fact() -> Vec<&'static str> { crate::socle::faits_tous() }
const NOMS_MIND: &[&str] = &["state.md", "todo.md"];

const CHAMPS_REQUIS: &[&str] = &["maj", "cap", "jalon"];
const CHAMPS_REQUIS_FACT: &[&str] = &["maj", "sante", "jalon"];

pub struct Git(PathBuf);

impl Git {
    fn run(&self, args: &[&str]) -> (i32, String) {
        match Command::new("git").args(args).current_dir(&self.0).output() {
            Ok(o) => (o.status.code().unwrap_or(1),
                      String::from_utf8_lossy(&o.stdout).to_string()),
            Err(_) => (1, String::new()),
        }
    }
}

/// Ce que la forme exige : un `#` de commentaire shell, le mot, puis la fin.
pub fn autorise(cmd: &str, mot: &str) -> bool {
    Regex::new(&format!(r"#\s*{}\s*$", regex::escape(mot)))
        .map(|r| r.is_match(cmd)).unwrap_or(false)
}

/// L'en-tête `---` en tête de fichier, en YAML plat. `{}` si absent.
pub fn entete(texte: &str) -> Vec<(String, String)> {
    let re = Regex::new(r"(?s)^\s*---\s*\n(.*?)\n---\s*(\n|$)").unwrap();
    let m = match re.captures(texte) { Some(m) => m, None => return Vec::new() };
    let cmt = Regex::new(r"\s+#.*$").unwrap();
    let mut out = Vec::new();
    for l in m.get(1).unwrap().as_str().lines() {
        if l.contains(':') && !l.trim_start().starts_with('#') {
            let (c, v) = l.split_once(':').unwrap();
            out.push((c.trim().to_lowercase(),
                      cmt.replace(v, "").trim().to_string()));
        }
    }
    out
}

fn champ<'a>(e: &'a [(String, String)], cle: &str) -> Option<&'a str> {
    // Python : le DERNIER gagne, un dict écrase la clé répétée.
    e.iter().rev().find(|(k, _)| k == cle).map(|(_, v)| v.as_str())
}

fn aujourd_hui() -> String {
    chrono::Local::now().date_naive().format("%Y-%m-%d").to_string()
}

/// Les reproches, ÉTIQUETÉS PAR NATURE. La distinction n'est pas cosmétique :
/// un fichier illisible fait disparaître le projet du tableau de bord sans
/// bruit, un fichier périmé l'y montre avec une date fausse.
pub fn verifie_state(texte: &str, champs: &[&str]) -> Vec<(&'static str, String)> {
    let d = entete(texte);
    if d.is_empty() {
        return vec![("structure",
            "il n'a plus d'en-tête `---` en première ligne — le collecteur le \
range en « aucune déclaration » et le projet disparaît du tableau de bord".into())];
    }
    let mut maux = Vec::new();
    let manquants: Vec<String> = champs.iter()
        .filter(|c| champ(&d, c).map(|v| v.is_empty()).unwrap_or(true))
        .map(|c| format!("`{}:`", c)).collect();
    if !manquants.is_empty() {
        maux.push(("structure", format!("il lui manque {}", manquants.join(", "))));
    }
    let maj = champ(&d, "maj").unwrap_or("");
    if !maj.is_empty() {
        if !Regex::new(r"^\d{4}-\d{2}-\d{2}$").unwrap().is_match(maj) {
            let court: String = maj.chars().take(20).collect();
            maux.push(("structure",
                format!("`maj:` doit être une date ISO `AAAA-MM-JJ`, pas « {} »", court)));
        } else if maj != aujourd_hui() {
            maux.push(("fraicheur", format!(
                "`maj:` porte {} alors que le commit est d'aujourd'hui ({}) — le \
tableau de bord datera ce projet du mauvais jour", maj, aujourd_hui())));
        }
    }
    maux
}

/// Deux jeux de préfixes à ignorer, pas un : le harnais de l'AGENT et celui du
/// PROJET. N'ignorer que le second faisait compter `agents/ios/.github/copilot/`
/// pour du code projet.
pub fn est_du_code(f: &str, lot: &str, projet: &str) -> bool {
    for p in PREFIXES_IGNORES {
        if f.starts_with(&format!("{}{}", lot, p)) || f.starts_with(&format!("{}{}", projet, p)) {
            return false;
        }
    }
    if f.starts_with(&format!("{}site/", projet))
        && !f.starts_with(&format!("{}site/_content/", projet)) {
        return false;   // moteur / rendu généré du site de doc
    }
    if EXT_CODE.iter().any(|e| f.ends_with(e)) {
        return true;
    }
    DOSSIERS_SRC.iter().any(|d| f.starts_with(&format!("{}{}", lot, d))
                              || f.starts_with(&format!("{}{}", projet, d)))
}

fn prefixe(rel: &Path) -> String {
    let s = rel.to_string_lossy();
    if s.is_empty() || s == "." { String::new() } else { format!("{}/", s) }
}

/// `contexte()` tel que la version Python l'appelle : git depuis le dossier
/// COURANT, `depart` seulement pour l'arithmétique de chemins.
pub fn contexte_defaut(depart: &Path) -> (String, String, Option<String>) {
    contexte(&Git(std::env::current_dir().unwrap_or_else(|_| depart.to_path_buf())), depart)
}

/// `(lot, projet, faits)` — où l'agent travaille, et sous quelle forme.
///
/// `git diff --cached --name-only` rend des chemins relatifs à la RACINE DU
/// DÉPÔT, jamais au dossier courant. Un agent de `agents/ios/` voit donc
/// `agents/ios/.mind/state.md`, et la constante `.mind/state.md` ne
/// correspondrait plus à rien : le garde laisserait passer TOUT, sans le dire.
pub fn contexte(g: &Git, depart: &Path) -> (String, String, Option<String>) {
    let (rc, out) = g.run(&["rev-parse", "--show-toplevel"]);
    if rc != 0 {
        return (String::new(), String::new(), None);
    }
    let racine = match PathBuf::from(out.trim()).canonicalize() {
        Ok(r) => r,
        Err(_) => return (String::new(), String::new(), None),
    };
    let agent = match depart.canonicalize() {
        Ok(a) => a,
        Err(_) => return (String::new(), String::new(), None),
    };
    let lot = match agent.strip_prefix(&racine) {
        Ok(r) => prefixe(r),
        Err(_) => return (String::new(), String::new(), None),
    };
    // Le projet : le premier ancêtre qui porte un `.fact/`, sans jamais sortir
    // du dépôt. Absent = forme d'avant migration, tout se lit dans `.mind/`.
    let mut p = agent.clone();
    loop {
        if p.join(".fact").is_dir() {
            let pre = p.strip_prefix(&racine).map(prefixe).unwrap_or_default();
            return (lot, pre.clone(), Some(format!("{}.fact/", pre)));
        }
        if p == racine || p.parent().is_none() {
            return (lot.clone(), lot, None);
        }
        p = p.parent().unwrap().to_path_buf();
    }
}

/// Le contenu tel qu'il sera COMMITÉ, pas celui du disque : lire le disque
/// laisserait passer une correction non indexée.
fn indexe(g: &Git, chemin: &str) -> Option<String> {
    let (rc, out) = g.run(&["show", &format!(":{}", chemin)]);
    if rc == 0 { Some(out) } else { None }
}

/// Le fichier tel qu'il est SUR LE DISQUE. Déportée, la mémoire n'est pas dans
/// l'index du dépôt de code ; le disque est alors la seule vérité.
fn lis_disque(p: &Path) -> String {
    std::fs::read_to_string(p).unwrap_or_default()
}

fn echantillon(v: &[String], n: usize) -> String {
    let mut s = v.iter().take(n).cloned().collect::<Vec<_>>().join(", ");
    if v.len() > n { s.push_str(", …"); }
    s
}

/// Rend `Some(motif)` pour refuser, `None` pour laisser passer.
pub fn juge(entree: &str, depart: &Path) -> Option<String> {
    let d: Value = serde_json::from_str(entree).ok()?;
    let cmd = d.get("tool_input").and_then(|o| o.get("command"))
        .and_then(|v| v.as_str()).unwrap_or("");
    if !Regex::new(r"\bgit\b.+\bcommit\b").unwrap().is_match(cmd) {
        return None;
    }
    // GIT TOURNE DEPUIS LE DOSSIER COURANT, PAS DEPUIS `depart`. La version
    // Python appelle `_git` sans `cwd`, donc depuis le processus ; `depart`
    // (`COPILOT_PROJECT_DIR`) ne sert qu'à l'arithmétique de chemins. Les
    // confondre ne se voit que si les deux pointent des dépôts DIFFÉRENTS —
    // et alors le garde jugerait l'index du mauvais dépôt.
    let g = Git(std::env::current_dir().unwrap_or_else(|_| depart.to_path_buf()));

    // `mind-ok` N'EST PAS TESTÉ ICI : chaque échappatoire est testée devant la
    // règle qu'elle lève, et pas avant.
    // LA FORME EST DEMANDÉE, PLUS DEVINÉE. Elle se lisait ici sur la présence
    // d'un `.fact/`, et DEUX CONTRATS D'EN-TÊTE en dépendent — déplacer ce
    // dossier ferait retomber des projets sur `CHAMPS_REQUIS`, qui exige
    // un `cap:` qu'aucun de leurs `state.md` ne porte. Tous leurs commits
    // seraient refusés dès le premier jour, celui de la migration compris.
    // GIT DEPUIS LE DOSSIER COURANT, POSITION DEPUIS `depart` — les deux
    // repères de ce fichier, déjà nommés plus haut, et déjà confondus une fois.
    let r = memoire::resous_depuis(&std::env::current_dir()
                                       .unwrap_or_else(|_| depart.to_path_buf()), depart);
    // `prefixe_lot`, PAS `lot` : ce qui suit compose des chemins.
    let (lot, projet) = (r.prefixe_lot.clone(), r.prefixe_projet.clone());
    // En forme DÉPORTÉE, `.fact/` n'est pas dans CE dépôt : aucun chemin rendu
    // par `git diff --cached` ne peut le viser. La serrure y est donc inerte
    // par construction, et le relais vit dans le hook de fin de tour, qui juge
    // le dépôt de mémoire. Le mot impossible le dit au lieu de le taire.
    let faits = match r.forme {
        memoire::Forme::EnPlace | memoire::Forme::Ambigue => Some(r.prefixe_fact.clone()),
        // v2 · le cerveau. Ce qui décide n'est plus la forme mais son
        // autonomie : un cerveau qui a son propre dépôt ne montre aucun de ses
        // chemins ici, exactement comme la mémoire déportée d'avant.
        memoire::Forme::Brain if r.brain_autonome => Some("«cerveau à part»".to_string()),
        memoire::Forme::Brain => Some(r.prefixe_fact.clone()),
        memoire::Forme::Deportee => Some("«déporté»".to_string()),
        memoire::Forme::HorsDepot | memoire::Forme::SansMemoire => None,
    };
    // `prefixe_mind`, DEMANDÉ AU RÉSOLVEUR. Composer
    // `format!("{}.mind/state.md", lot)` donnerait un nom juste avant la
    // migration et faux après : sur un arbre `brain/`, aucun fichier indexé ne
    // s'appelle `.mind/state.md`, donc le contrôle de lisibilité ci-dessous ne
    // trouverait JAMAIS son fichier et laisserait passer un en-tête cassé :
    // `allow`. Le garde n'aurait pas faibli, il regarderait ailleurs.
    let state = format!("{}state.md", r.prefixe_mind);
    // `resous()` rend TOUJOURS des chemins — c'est tout l'intérêt. Mais lire
    // `Some(chemin)` comme « la mémoire est déportée » supposerait que
    // l'ancienne signature ne rendait un chemin que dans ce cas : le sens était
    // porté par la présence, pas par le nom. Ici on demande la
    // FORME, et les chemins ne servent plus qu'à lire des fichiers.
    // « La mémoire vit dans un AUTRE dépôt » — le seul sens qui reste. En v1
    // c'était la forme déportée ; en v2 c'est un cerveau qui a son propre `.git`.
    let deportee = r.forme == memoire::Forme::Deportee
                   || (r.forme == memoire::Forme::Brain && r.brain_autonome);
    let (d_mind, d_fact) = if deportee { (r.mind.clone(), r.fact.clone()) }
                           else { (None, None) };
    let champs = if r.forme.a_des_faits() { CHAMPS_REQUIS_FACT } else { CHAMPS_REQUIS };

    let (rc, out) = g.run(&["diff", "--cached", "--name-only"]);
    if rc != 0 {
        return None;   // pas un dépôt git, ou git indisponible
    }
    let fichiers: Vec<String> = out.lines().map(|f| f.trim().to_string())
        .filter(|f| !f.is_empty()).collect();
    if fichiers.is_empty() {
        return None;   // `git commit --amend`, commit vide… : rien à juger
    }

    // 0. `.fact/` NE S'ÉCRIT QU'À LA DEMANDE DE @user. C'est la seule mémoire
    // partagée par tous les agents d'un projet : un agent qui la réécrit depuis
    // son lot efface ce qu'un autre y avait mis, et personne ne le voit.
    if let Some(f) = &faits {
        // `fact-neuf` VAUT `fact-ok`, et ce n'est pas une clé partagée : c'est
        // une hiérarchie, déclarée ici plutôt que subie. `autorise()` ancre le
        // mot en FIN de commande — deux mots ne peuvent donc pas cohabiter. Or
        // créer un cinquième fichier de faits, c'est nécessairement toucher aux
        // faits : les deux serrures se ferment sur le même commit. Sans cette
        // ligne, `fact-neuf` serait une serrure qu'aucune commande ne peut
        // ouvrir.
        if !autorise(cmd, "fact-ok") && !autorise(cmd, "fact-neuf") {
            let touches: Vec<String> = fichiers.iter().filter(|x| x.starts_with(f))
                .cloned().collect();
            if !touches.is_empty() {
                return Some(format!(
"mind-guard : ce commit modifie `.fact/` ({}). Ces fichiers sont partagés par \
TOUS les agents du projet et ne s'écrivent qu'à la demande de @user — un \
agent qui les réécrit depuis son lot efface le travail d'un autre en silence. Si \
@user l'a demandé, ajoute ` # fact-ok` à la fin de la commande : \
l'autorisation restera dans l'historique.", echantillon(&touches, 4)));
            }
        }
    }

    // 0 bis. LE PLAFOND, ET IL PORTE SUR LES NOMS.
    //
    // « Jamais un 5ᵉ fichier dans les faits, jamais un 3ᵉ dans l'esprit, sans le
    // demander au commanditaire » est une règle du socle, et sans ce code elle
    // ne serait **vérifiée nulle part** : un `fact/extra.md` indexé passerait
    // sans un mot. Une règle qu'aucun mécanisme ne
    // porte se lit comme tenue, parce que rien ne la contredit jamais.
    //
    // UNE CLÉ, UNE SERRURE : ` # fact-ok` autorise à ÉCRIRE les faits, pas à en
    // créer un cinquième. Le mot est donc distinct — et c'est voulu : la
    // première autorisation est courante, la seconde change la forme du projet.
    // Un mot qui ouvrirait les deux ferait passer la seconde à chaque fois
    // qu'on demande la première.
    //
    // Le plafond ne compte QUE les fichiers à la racine du dossier : un
    // sous-dossier et son contenu n'ont pas de plafond. Aucun n'est prévu :
    // rien ne crée ni ne lit de sous-dossier `belief/` ou `experience/`.
    if let Some(f) = &faits {
        if !autorise(cmd, "fact-neuf") {
            let intrus: Vec<String> = fichiers.iter()
                .filter_map(|x| x.strip_prefix(f.as_str()))
                .filter(|reste| !reste.contains('/'))
                .filter(|reste| !noms_fact().contains(reste))
                .map(|s| s.to_string()).collect();
            if !intrus.is_empty() {
                return Some(format!(
"mind-guard : ce commit ajoute un fichier de faits que le socle ne prévoit pas ({}). Les faits d'un projet tiennent en quatre noms — `base`, `architecture`, `stack`, `rules` — plus `roles` à plusieurs agents, et ce plafond existe pour qu'on sache toujours où chercher. Un cinquième nom se demande à @user. S'il l'a accordé, ajoute ` # fact-neuf` à la fin de la commande.",
                    echantillon(&intrus, 4)));
            }
        }
    }
    if !r.prefixe_mind.is_empty() && !autorise(cmd, "mind-neuf") {
        let intrus: Vec<String> = fichiers.iter()
            .filter_map(|x| x.strip_prefix(r.prefixe_mind.as_str()))
            .filter(|reste| !reste.contains('/'))
            .filter(|reste| !NOMS_MIND.contains(reste))
            .map(|s| s.to_string()).collect();
        if !intrus.is_empty() {
            return Some(format!(
"mind-guard : ce commit ajoute un fichier d'état que le socle ne prévoit pas ({}). L'esprit d'un agent tient en deux fichiers — `state` et `todo` — et le reste se range dans `docs/`, dans les faits, ou dans la mémoire auto selon ce que c'est. Un troisième nom se demande à @user. S'il l'a accordé, ajoute ` # mind-neuf` à la fin de la commande.", echantillon(&intrus, 4)));
        }
    }

    if autorise(cmd, "mind-ok") {
        return None;
    }

    // 1. LISIBILITÉ — vaut même sans code, un fichier cassé est le pire cas.
    if fichiers.contains(&state) || d_mind.is_some() {
        let texte = match &d_mind {
            Some(m) => Some(lis_disque(&m.join("state.md"))),
            None => indexe(&g, &state),
        };
        // `None` = suppression ou renommage : ce n'est pas notre sujet.
        if let Some(t) = texte {
            let maux = verifie_state(&t, champs);
            if !maux.is_empty() {
                let tete = if maux.iter().any(|(k, _)| *k == "structure") {
                    "ne serait plus lisible par le tableau de bord"
                } else { "n'est pas à jour" };
                let liste = maux.iter().map(|(_, m)| m.clone())
                    .collect::<Vec<_>>().join(" ; ");
                return Some(format!(
                    "mind-guard : `{}` {} — {}. Corrige, réindexe (`git add {}`), \
puis recommite.", state, tete, liste, state));
            }
        }
    }

    // 2. FRAÎCHEUR — du code sort, la déclaration doit suivre.
    let code: Vec<String> = fichiers.iter()
        .filter(|f| est_du_code(f, &lot, &projet)).cloned().collect();
    if code.is_empty() {
        return None;
    }

    // Le projet doit savoir dire où il va. `.fact/base.md` porte le `cap:` —
    // il n'est pas dans `state.md`, parce qu'un projet n'a qu'une destination
    // même à plusieurs agents.
    if let Some(f) = &faits {
        let contenu = match &d_fact {
            Some(df) => lis_disque(&df.join("base.md")),
            None => {
                let (rc, tete) = g.run(&["show", &format!("HEAD:{}base.md", f)]);
                match indexe(&g, &format!("{}base.md", f)) {
                    Some(s) if !s.is_empty() => s,
                    _ => if rc == 0 { tete } else { String::new() },
                }
            }
        };
        if champ(&entete(&contenu), "cap").map(|v| v.is_empty()).unwrap_or(true) {
            return Some(format!(
"mind-guard : `{}base.md` ne porte pas de `cap:` — le tableau de bord n'a alors \
AUCUNE réponse au niveau du projet, quel que soit le nombre d'agents qui s'y \
déclarent. Écris-y l'en-tête `---` avec `cap:`, puis recommite (` # fact-ok`, \
c'est `.fact/`).", f));
        }
    }

    // DÉPORTÉ, `state.md` n'est JAMAIS dans l'index du dépôt de code : exiger
    // qu'il y soit bloquerait tous les commits, pour toujours. La règle devient
    // « il doit être plus récent que le code », lue sur le disque.
    if let Some(m) = &d_mind {
        // LES CHEMINS DE `git diff --cached` SONT RELATIFS À LA RACINE DU DÉPÔT,
        // jamais au dossier courant — les stat-er tels quels ne trouverait rien,
        // et le garde laisserait tout passer sans le dire.
        let (rc, out) = g.run(&["rev-parse", "--show-toplevel"]);
        if rc != 0 { return None; }
        let rr = PathBuf::from(out.trim());
        let s = match std::fs::metadata(m.join("state.md")).and_then(|x| x.modified()) {
            Ok(t) => t,
            Err(_) => return None,
        };
        let mut recent: Option<std::time::SystemTime> = None;
        for f in &code {
            if let Ok(t) = std::fs::metadata(rr.join(f)).and_then(|x| x.modified()) {
                if recent.map(|r| t > r).unwrap_or(true) { recent = Some(t); }
            }
        }
        match recent {
            None => return None,
            Some(r) if s >= r => return None,
            _ => {}
        }
        return Some(format!(
"mind-guard : du code projet est indexé ({}) alors que ta déclaration d'état n'a \
pas bougé depuis. C'est ce que le tableau de bord lit pour savoir où en est ce \
projet. Mets `.mind/state.md` à jour (dont le champ `maj:`), puis recommite. Si \
elle n'a vraiment pas à bouger, ajoute ` # mind-ok` à la fin de la commande.\n\n\
Ta mémoire est DÉPORTÉE dans `memoire/` : il n'y a rien à `git add`, elle est \
versionnée à part et commitée toute seule en fin de tour.", echantillon(&code, 5)));
    }

    if !fichiers.contains(&state) {
        return Some(format!(
"mind-guard : du code projet est indexé ({}) sans mise à jour de `{}`. C'est ce \
que le tableau de bord lit pour savoir où en est ce projet — pas poussé, mais lu \
sur le disque : un commit qui le laisse en arrière rend le projet muet. Mets-le à \
jour (dont le champ `maj:`), indexe-le (`git add {}`), puis recommite. Si la \
déclaration n'a vraiment pas à bouger, ajoute ` # mind-ok` à la fin de la \
commande.\n\n`.mind/todo.md` n'est plus exigé ICI — c'est le hook `Stop` qui le \
réclame, à chaque fin de tour.", echantillon(&code, 5), state, state));
    }
    None
}

pub fn main(entree: &str) {
    let depart = memoire::depart_defaut();
    if let Some(motif) = juge(entree, &depart) {
        println!("{}", crate::hote::refus(&motif));
    }
    // Pas de sortie = décision par défaut (allow).
}

#[cfg(test)]
mod essais {
    use super::*;

    /// LE PLAFOND PORTE SUR LES NOMS, et il a deux mots distincts.
    ///
    /// La règle « jamais un 5ᵉ fichier de faits, jamais un 3ᵉ d'esprit, sans le
    /// demander » vit dans le socle et, sans ce code, ne serait vérifiée
    /// NULLE PART : un `fact/extra.md` indexé passerait sans un mot.
    #[test]
    fn le_plafond_porte_sur_les_noms() {
        for n in ["base.md", "architecture.md", "stack.md", "rules.md", "roles.md"] {
            assert!(noms_fact().contains(&n), "{} devrait être admis", n);
        }
        // CE QUE LE PLAFOND REFUSE — sinon on épingle une liste qui dit oui à tout.
        for n in ["extra.md", "notes.md", "base.txt", "Base.md"] {
            assert!(!noms_fact().contains(&n), "{} devrait être refusé", n);
        }
        assert_eq!(NOMS_MIND, &["state.md", "todo.md"]);
        assert!(!NOMS_MIND.contains(&"belief.md"));

        // `fact-neuf` VAUT `fact-ok` — la hiérarchie, pas une clé partagée.
        // Sans elle la serrure ne s'ouvrirait jamais : `autorise()` ancre le mot
        // en FIN de commande, deux mots ne peuvent donc pas cohabiter.
        assert!(autorise("git commit -m x # fact-neuf", "fact-neuf"));
        assert!(!autorise("git commit -m x # fact-ok", "fact-neuf"));
        // ET L'INVERSE RESTE FAUX : `fact-ok` n'autorise pas un 5ᵉ nom.
        assert!(!autorise("git commit -m x # fact-neuf", "mind-neuf"));
    }

    #[test]
    fn l_echappatoire_se_lit_en_FIN_de_commande() {
        assert!(autorise("git commit -m x # mind-ok", "mind-ok"));
        assert!(autorise("git commit -m x #fact-ok  ", "fact-ok"));
        assert!(autorise("git commit -m x # fact-ok\n", "fact-ok"));
        // LE DÉFAUT RÉPARÉ : une sous-chaîne n'importe où désarmait le garde.
        assert!(!autorise("git checkout -b essai-fact-ok && git commit -m x", "fact-ok"));
        assert!(!autorise("git commit -m 'répare fact-ok un jour'", "fact-ok"));
        assert!(!autorise("git commit -m x", "mind-ok"));
        // UNE CLÉ, UNE SERRURE : `mind-ok` n'ouvre pas la serrure de `.fact/`.
        assert!(!autorise("git commit -m x # mind-ok", "fact-ok"));
    }

    #[test]
    fn l_entete_se_lit_comme_le_tableau_de_bord() {
        let e = entete("---\nmaj: 2026-09-09\ncap: aller là   # un commentaire\n---\n\ntexte");
        assert_eq!(champ(&e, "maj"), Some("2026-09-09"));
        assert_eq!(champ(&e, "cap"), Some("aller là"));
        // TÉMOINS NÉGATIFS : pas d'en-tête, en-tête non fermé, texte nu.
        assert!(entete("texte sans en-tête").is_empty());
        assert!(entete("---\nmaj: x\n").is_empty());
        assert!(entete("").is_empty());
    }

    #[test]
    fn le_state_est_juge_sur_sa_structure_puis_sa_fraicheur() {
        let ok = format!("---\nmaj: {}\nsante: verte\njalon: x\n---\n", aujourd_hui());
        assert!(verifie_state(&ok, CHAMPS_REQUIS_FACT).is_empty());
        // structure : sans en-tête, le projet DISPARAÎT du tableau de bord
        let m = verifie_state("rien", CHAMPS_REQUIS_FACT);
        assert_eq!(m.len(), 1); assert_eq!(m[0].0, "structure");
        // structure : champ manquant
        let m = verifie_state(&format!("---\nmaj: {}\n---\n", aujourd_hui()), CHAMPS_REQUIS_FACT);
        assert!(m.iter().any(|(k, v)| *k == "structure" && v.contains("`sante:`")));
        // structure : date qui n'est pas une date
        let m = verifie_state("---\nmaj: hier\nsante: v\njalon: x\n---\n", CHAMPS_REQUIS_FACT);
        assert!(m.iter().any(|(k, v)| *k == "structure" && v.contains("« hier »")));
        // fraîcheur : date valide mais pas celle du jour
        let m = verifie_state("---\nmaj: 2020-01-01\nsante: v\njalon: x\n---\n", CHAMPS_REQUIS_FACT);
        assert_eq!(m.len(), 1); assert_eq!(m[0].0, "fraicheur");
    }

    #[test]
    fn le_harnais_de_l_agent_n_est_pas_du_code_projet() {
        assert!(est_du_code("src/a.ts", "", ""));
        assert!(est_du_code("truc.py", "", ""));
        assert!(est_du_code("agents/ios/src/a.ts", "agents/ios/", ""));
        // LES DEUX JEUX DE PRÉFIXES, et c'est le défaut que ça répare :
        assert!(!est_du_code("agents/ios/.github/copilot/garde.py", "agents/ios/", ""));
        assert!(!est_du_code(".fact/base.md", "", ""));
        assert!(!est_du_code("docs/decisions.md", "", ""));
        assert!(!est_du_code(".logs/2026-09-09.md", "", ""));
        assert!(!est_du_code("site/index.html", "", ""), "rendu généré");
        assert!(est_du_code("site/_content/a.py", "", ""), "mais son contenu, si");
        assert!(!est_du_code("LISEZMOI.md", "", ""));
    }
}
