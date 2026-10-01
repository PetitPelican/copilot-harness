//! LE CARNET D'ÉQUIPE — l'espace commun d'un projet multi-agents.
//!
//! Port de `hooks/carnet.py`. Ce n'est pas un hook : c'est le module que le
//! briefing et la fin de tour importent.
//!
//! LE CONSTAT DE DÉPART : trois agents, trois copies physiques du dépôt, et tout
//! ce qu'un agent écrit ne voyage que dans SA copie. Un agent peut avoir des
//! enregistrements de retard et lire une liste de tâches tronquée, sans que rien,
//! nulle part, ne le lui dise.
//!
//! Le mur n'est pas entre les agents : il est entre leurs copies.
//!
//! CE QUI EN DÉCIDE LA FORME, ET QU'ON NE CHANGE PAS SANS TOUT CASSER :
//!
//! 1. HORS SUIVI DE VERSION — un dossier suivi par git serait recopié dans les
//!    trois copies à chaque fusion, et on aurait reconstruit le défaut.
//! 2. UN SEUL ÉCRIVAIN PAR FICHIER — la LECTURE est toujours la fusion des
//!    trois. C'est ce que des fichiers séparés donnent gratuitement, là où un
//!    espace unique doit le racheter en rôles et droits.
//! 3. ON AJOUTE, ON NE SUPPRIME JAMAIS.
//! 4. LE CHIFFRE DE CONFIANCE NE VIT PAS DANS LE CARNET. Une entrée est
//!    immuable et un chiffre bouge : surcouche dans `.etat/confiance.json`,
//!    indexée par l'empreinte de l'entrée.
//!
//! **fail-open partout** : toute erreur rend une valeur vide, jamais un panic.
//!
//! DEUX PIÈGES DU PORTAGE, ET ILS SONT SILENCIEUX. `round()` de Python arrondit
//! **au pair le plus proche**, pas au supérieur : `format!("{:.1}")` de Rust
//! fait la même chose, `f64::round` non. Et `json.dumps` garde **l'ordre
//! d'insertion** des clés : sans le drapeau `preserve_order`, les deux versions
//! écriraient le même document dans un ordre différent.

use regex::Regex;
use serde_json::{json, Map, Value};
use serde::Serialize;
use sha1::{Digest, Sha1};
use std::path::{Path, PathBuf};
use unicode_normalization::UnicodeNormalization;

use crate::memoire;

// Le départ fixé par le niveau, et les poids du résultat, vivent dans
// `nature.rs` : cette copie et celle de la fin de tour y sont réunies. Ne
// restent ici que les crans propres au carnet.
pub const OUBLI: f64 = 0.97;
pub const EFFONDRE: f64 = 0.5;
const PLANCHER: f64 = 5.0;
const PLAFOND: f64 = 99.0;
/// Le chiffre n'est AFFICHÉ qu'après avoir bougé deux fois. Avant ça, c'est le
/// niveau de départ déguisé en mesure — le défaut qu'on reprochait au chiffre
/// saisi à la main. Ne pas retirer cette borne.
const MOUVEMENTS_AVANT_AFFICHAGE: i64 = 2;

fn re(p: &str) -> Regex { Regex::new(p).unwrap() }

fn entete_re() -> Regex {
    re(r"^##\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\s*·\s*(.+?)\s*·\s*(.+?)(?:\s*·\s*(.+?))?\s*$")
}
fn pour_re() -> Regex { re(r"(?m)^\s*↗\s*(.+?)\s*:\s*(.+?)\s*$") }
/// Même syntaxe que les constats de `attente` — on ne crée pas un second
/// dialecte de réouverture, il divergerait au premier changement.
fn rejeu_re() -> Regex { re(r"(?im)^\s*↻\s*(machine|service)\s*::\s*(.+?)\s*::\s*(.+?)\s*$") }
/// `↩ <empreinte>` : cette entrée est traitée. Seul geste « social » du
/// dispositif — sans lui, une demande resterait en tête d'un briefing pour
/// toujours, et l'agent apprendrait à ne plus la lire.
fn acquit_re() -> Regex { re(r"(?m)^\s*↩\s*([0-9a-f]{6,12})\s*$") }

pub fn sansaccents(s: &str) -> String {
    s.to_lowercase().nfd().filter(|c| !unicode_normalization::char::is_combining_mark(*c)).collect()
}

/// `round(x, 1)` de Python — au PAIR le plus proche, pas au supérieur.
fn arrondi1(x: f64) -> f64 { format!("{:.1}", x).parse().unwrap_or(x) }
/// `int(round(x))` de Python — même règle.
fn arrondi0(x: f64) -> i64 { format!("{:.0}", x).parse().unwrap_or(0.0) as i64 }

fn nb(v: &Value) -> f64 { v.as_f64().unwrap_or(0.0) }

/// La valeur telle que Python l'écrirait : un entier quand la borne a mordu
/// (`min(99, …)` rend l'entier 99), un flottant sinon.
fn borne(x: f64) -> Value {
    if x > PLAFOND { json!(PLAFOND as i64) }
    else if x < PLANCHER { json!(PLANCHER as i64) }
    else { json!(x) }
}

pub fn espace(depart_: &Path, creer: bool) -> Option<PathBuf> {
    memoire::racine_depot(depart_)?;
    // LA FORME DÉCIDE, ET ELLE EST DÉCIDÉE UNE SEULE FOIS — dans le résolveur.
    //
    // Une règle propre ici — `memoire/equipe` si le dossier existe, `equipe`
    // sinon — ignorerait le cerveau : sur un projet en `brain/`, `equipe-amorce`
    // créerait le carnet à la racine pendant que le résolveur le cherche dans
    // `brain/workspace/`. Le carnet naîtrait INVISIBLE — créé pour de bon,
    // lu par personne, et rien dans la sortie ne le laisserait deviner.
    let e = memoire::resous(depart_).workspace_prevu()?;
    if creer && std::fs::create_dir_all(e.join(".etat")).is_err() {
        return None;
    }
    if e.is_dir() { Some(e) } else { None }
}

/// AMORCER LE CARNET — le geste que rien d'autre ne fait : `espace()` n'est
/// jamais appelé avec `creer` vrai ailleurs. Sans lui, le carnet d'équipe est
/// LU partout et CRÉÉ nulle part — un projet neuf qui passe en multi-agents
/// n'en aurait jamais. Tout ce qui en dépend — les entrées, les chiffres de
/// confiance, le résumé servi au briefing — resterait muet sans que rien ne
/// l'explique.
///
/// La règle qui place le dossier vit dans `espace()`, et elle y reste : la
/// recopier ici ferait deux vérités qui se décalent au premier changement.
pub fn amorce(depart_: &Path) -> Option<PathBuf> {
    espace(depart_, true)
}

pub fn slug(nom: &str) -> String {
    let n = if nom.is_empty() { "agent" } else { nom };
    n.chars().map(|c| if c.is_ascii_alphanumeric() || c == '_' || c == '-' { c } else { '-' })
        .collect()
}

pub fn fichier(esp: &Path, agent: &str, quand: chrono::NaiveDate) -> PathBuf {
    esp.join(format!("{}-{}.md", quand.format("%Y-%m"), slug(agent)))
}

/// Date + auteur + première ligne. Uniques parce qu'on n'écrase jamais.
pub fn empreinte(date: &str, heure: &str, auteur: &str, texte: &str) -> String {
    let t: String = texte.chars().take(120).collect();
    let mut h = Sha1::new();
    h.update(format!("{} {}|{}|{}", date, heure, auteur, t).as_bytes());
    format!("{:x}", h.finalize())[..12].to_string()
}

#[derive(Debug, Clone)]
pub struct Entree {
    pub date: String, pub heure: String, pub auteur: String,
    pub issue: String, pub niveau: String, pub texte: String,
    pub pour: Vec<(String, String)>,
    pub rejeu: Option<(String, String, String)>,
    pub vus: Vec<String>, pub id: String, pub quand: String,
    pub rang: Option<String>,
}

/// Les carnets de TOUS les agents, fusionnés et triés — du plus récent au plus
/// ancien. C'est le point de tout le dispositif : l'écriture est séparée, la
/// lecture ne l'est jamais.
pub fn entrees(esp: &Path, depuis: Option<&str>) -> Vec<Entree> {
    if !esp.is_dir() { return Vec::new(); }
    let (rt, rp, rr, ra) = (entete_re(), pour_re(), rejeu_re(), acquit_re());
    let mut fichiers: Vec<PathBuf> = match std::fs::read_dir(esp) {
        Ok(it) => it.filter_map(|e| e.ok().map(|e| e.path()))
                    .filter(|p| p.extension().map(|x| x == "md").unwrap_or(false)).collect(),
        Err(_) => return Vec::new(),
    };
    fichiers.sort();
    let mut out: Vec<Entree> = Vec::new();
    for f in fichiers {
        let texte = match std::fs::read_to_string(&f) { Ok(t) => t, Err(_) => continue };
        let mut bloc: Vec<(String, String, String, String, String, Vec<String>)> = Vec::new();
        for l in texte.lines() {
            if let Some(m) = rt.captures(l) {
                let g = |i: usize| m.get(i).map(|x| x.as_str().trim().to_string()).unwrap_or_default();
                let niv = m.get(5).map(|x| x.as_str().trim().to_string())
                    .filter(|s| !s.is_empty()).unwrap_or_else(|| "observé".into());
                bloc.push((g(1), g(2), g(3), g(4), niv, Vec::new()));
            } else if let Some(c) = bloc.last_mut() {
                c.5.push(l.to_string());
            }
        }
        for (date, heure, auteur, issue, niveau, corps_l) in bloc {
            let corps = corps_l.join("\n").trim().to_string();
            // LES TROIS MARQUEURS, PAS DEUX. L'empreinte est calculée sur ce
            // texte ; en oublier un ici et l'entrée relue n'a plus la même
            // empreinte que l'entrée écrite — sa confiance devient
            // introuvable, silencieusement.
            let texte = corps.lines()
                .filter(|x| { let t = x.trim_start();
                    !(t.starts_with('↗') || t.starts_with('↻') || t.starts_with('↩')) })
                .map(|x| x.trim()).filter(|x| !x.is_empty())
                .collect::<Vec<_>>().join(" ");
            let pour: Vec<(String, String)> = rp.captures_iter(&corps)
                .map(|c| (c[1].trim().to_string(), c[2].trim().to_string())).collect();
            let rejeu = rr.captures(&corps).map(|c| (c[1].to_lowercase(),
                c[2].to_string(), c[3].to_string()));
            let vus: Vec<String> = ra.captures_iter(&corps).map(|c| c[1].to_string()).collect();
            let id = empreinte(&date, &heure, &auteur, &texte);
            let quand = format!("{} {}", date, heure);
            out.push(Entree { date, heure, auteur, issue, niveau, texte, pour,
                              rejeu, vus, id, quand, rang: None });
        }
    }
    out.sort_by(|a, b| b.quand.cmp(&a.quand));   // stable, comme Python
    match depuis { Some(d) => out.into_iter().filter(|e| e.quand.as_str() >= d).collect(),
                   None => out }
}

/// Une entrée, EN AJOUT SEUL. Rend son empreinte, ou `None`.
///
/// C'est le seul écrivain du carnet, et il n'écrit que ce que l'agent a
/// DÉLIBÉRÉMENT marqué : une case cochée qui porte `↗`. Une case sans `↗` ne
/// produit rien — décider qu'un travail ne concerne personne reste le jugement
/// de l'agent, jamais celui de la machine.
pub fn ecrire(esp: &Path, agent: &str, texte: &str, issue: &str,
              niveau: Option<&str>, pour: &[(String, String)],
              rejeu: Option<&str>, vus: &[String]) -> Option<String> {
    if texte.trim().is_empty() { return None; }
    let quand = chrono::Local::now();
    let niveau = niveau.map(|s| s.to_string()).unwrap_or_else(||
        if rejeu.is_some() { "mesuré".into() } else { "observé".into() });
    let f = fichier(esp, agent, quand.date_naive());
    let mut bloc: Vec<String> = Vec::new();
    if !f.exists() {
        bloc.push(format!("# Carnet d\'équipe — {} · {}", agent, quand.format("%B %Y")));
        bloc.push(String::new());
        bloc.push("Écrit par le hook `attente` quand une tâche cochée porte `↗`.".into());
        bloc.push("**En ajout seul** : on n\'y réécrit rien, on n\'y supprime rien.".into());
        bloc.push(String::new());
    }
    bloc.push(format!("## {} {} · {} · {} · {}", quand.format("%Y-%m-%d"),
                      quand.format("%H:%M"), agent, issue, niveau));
    bloc.push(texte.trim().to_string());
    for (qui, quoi) in pour { bloc.push(format!("↗ {} : {}", qui, quoi)); }
    if let Some(r) = rejeu {
        bloc.push(format!("↻ {}", r.trim_start_matches(|c| c == '↻' || c == ' ').trim()));
    }
    // L'ACQUITTEMENT est le seul geste « social » du dispositif.
    for v in vus { bloc.push(format!("↩ {}", v)); }
    bloc.push(String::new());
    use std::io::Write;
    let mut fh = std::fs::OpenOptions::new().create(true).append(true).open(&f).ok()?;
    write!(fh, "{}\n", bloc.join("\n")).ok()?;
    let ident = empreinte(&quand.format("%Y-%m-%d").to_string(),
                          &quand.format("%H:%M").to_string(), agent, texte.trim());
    naissance(esp, &ident, &niveau);
    Some(ident)
}

// ── la confiance : une surcouche, jamais le carnet ───────────────────────

fn etat(esp: &Path) -> PathBuf { esp.join(".etat").join("confiance.json") }

pub fn confiances(esp: &Path) -> Map<String, Value> {
    std::fs::read_to_string(etat(esp)).ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}

fn ecrire_etat(esp: &Path, d: &Map<String, Value>) {
    if std::fs::create_dir_all(esp.join(".etat")).is_err() { return; }
    let mut buf = Vec::new();
    let mut s = serde_json::Serializer::with_formatter(
        &mut buf, serde_json::ser::PrettyFormatter::with_indent(b" "));
    if Value::Object(d.clone()).serialize(&mut s).is_err() { return; }
    let tmp = etat(esp).with_extension("tmp");
    if std::fs::write(&tmp, &buf).is_ok() { let _ = std::fs::rename(&tmp, etat(esp)); }
}

fn auj() -> String { chrono::Local::now().date_naive().format("%Y-%m-%d").to_string() }

pub fn naissance(esp: &Path, ident: &str, niveau: &str) {
    let mut d = confiances(esp);
    if d.contains_key(ident) { return; }
    let mut e = Map::new();
    e.insert("n".into(), json!(crate::nature::depart(niveau, crate::nature::Maison::Carnet)));
    e.insert("m".into(), json!(0));
    e.insert("niveau".into(), json!(niveau));
    e.insert("vu".into(), json!(auj()));
    d.insert(ident.into(), Value::Object(e));
    ecrire_etat(esp, &d);
}

/// Ce que l'agent avait LU bouge quand il déclare son issue. Faisable ici
/// parce que c'est le briefing qui sert les entrées — il sait donc exactement
/// ce qui a été lu, sans que l'agent désigne rien.
pub fn bouge(esp: &Path, idents: &[String], facteur: f64, marque: bool) {
    if idents.is_empty() { return; }
    let mut d = confiances(esp);
    let a = auj();
    for i in idents {
        let c = match d.get_mut(i).and_then(|v| v.as_object_mut()) { Some(c) => c, None => continue };
        let n = arrondi1(nb(c.get("n").unwrap_or(&json!(0))) * facteur);
        c.insert("n".into(), borne(n));
        if marque {
            let m = c.get("m").and_then(|v| v.as_i64()).unwrap_or(0);
            c.insert("m".into(), json!(m + 1));
        }
        c.insert("vu".into(), json!(a.clone()));
    }
    ecrire_etat(esp, &d);
}

/// Un `↻` rejoué. TIENT rend son plancher de niveau — c'est ce qui fait que les
/// deux étages se tiennent : une mesure refaite RESTAURE la confiance, là où
/// l'accumulation seule ne fait que l'éroder. MUET ne conclut RIEN, jamais.
pub fn replancher(esp: &Path, ident: &str, verdict: &str) {
    let mut d = confiances(esp);
    let c = match d.get_mut(ident).and_then(|v| v.as_object_mut()) { Some(c) => c, None => return };
    if verdict == "TIENT" {
        let niv = c.get("niveau").and_then(|v| v.as_str()).unwrap_or("").to_string();
        c.insert("n".into(), json!(crate::nature::depart(&niv, crate::nature::Maison::Carnet)));
    } else if verdict == "TOMBÉ" {
        let n = arrondi1(nb(c.get("n").unwrap_or(&json!(0))) * EFFONDRE);
        c.insert("n".into(), if n < PLANCHER { json!(PLANCHER as i64) } else { json!(n) });
    } else {
        return;
    }
    let m = c.get("m").and_then(|v| v.as_i64()).unwrap_or(0);
    c.insert("m".into(), json!(m + 1));
    c.insert("vu".into(), json!(auj()));
    ecrire_etat(esp, &d);
}

/// Ce qui n'est jamais relu descend d'un cran, sans être détruit.
///
/// LE DÉLAI SUIT LA NATURE. `jours` est celui d'un fait.
/// Une entrée de carnet est une EXPÉRIENCE — ce qu'un agent a fait, et dit
/// l'avoir fait — et attend une fois et demie plus longtemps avant de
/// descendre ; une entrée « supposé » est une CROYANCE et attend deux fois
/// moins. Le cran, lui, ne change pas : la nature étire le temps, elle ne
/// frappe pas plus fort.
pub fn oubli(esp: &Path, jours: i64) {
    let mut d = confiances(esp);
    if d.is_empty() { return; }
    let aujd = chrono::Local::now().date_naive();
    let mut change = false;
    let a = auj();
    for (_, v) in d.iter_mut() {
        let c = match v.as_object_mut() { Some(c) => c, None => continue };
        let niv = c.get("niveau").and_then(|x| x.as_str()).map(String::from);
        let (nat, _) = crate::nature::de(crate::nature::Maison::Carnet, niv.as_deref(), None);
        let delai = crate::nature::duree(nat, jours as f64).round() as i64;
        let limite = (aujd - chrono::Duration::days(delai)).format("%Y-%m-%d").to_string();
        let vu = c.get("vu").and_then(|x| x.as_str()).unwrap_or("9999").to_string();
        if vu < limite {
            let n = arrondi1(nb(c.get("n").unwrap_or(&json!(0))) * OUBLI);
            c.insert("n".into(), if n < PLANCHER { json!(PLANCHER as i64) } else { json!(n) });
            c.insert("vu".into(), json!(a.clone()));
            change = true;
        }
    }
    if change { ecrire_etat(esp, &d); }
}

/// Le chiffre, ou `None` tant qu'il n'a pas bougé deux fois.
pub fn chiffre(conf: &Map<String, Value>, ident: &str) -> Option<i64> {
    let c = conf.get(ident)?.as_object()?;
    if c.get("m").and_then(|v| v.as_i64()).unwrap_or(0) < MOUVEMENTS_AVANT_AFFICHAGE {
        return None;
    }
    Some(arrondi0(nb(c.get("n").unwrap_or(&json!(0)))))
}

// ── ce que le briefing a servi ───────────────────────────────────────────

fn lu_fichier(esp: &Path, agent: &str, session: &str) -> PathBuf {
    esp.join(".etat").join(format!("{}-{}.lu", slug(agent), slug(session)))
}

pub fn sert(esp: &Path, agent: &str, session: &str, idents: &[String]) {
    if idents.is_empty() { return; }
    if std::fs::create_dir_all(esp.join(".etat")).is_err() { return; }
    let f = lu_fichier(esp, agent, session);
    let mut tout: Vec<String> = std::fs::read_to_string(&f).unwrap_or_default()
        .split_whitespace().map(|s| s.to_string()).collect();
    tout.extend(idents.iter().cloned());
    tout.sort(); tout.dedup();
    let _ = std::fs::write(&f, tout.join("\n"));
}

pub fn lu(esp: &Path, agent: &str, session: &str) -> Vec<String> {
    std::fs::read_to_string(lu_fichier(esp, agent, session)).unwrap_or_default()
        .split_whitespace().map(|s| s.to_string()).collect()
}

// ── le résumé servi au démarrage ─────────────────────────────────────────

/// `↗ PO :` doit atteindre « Projet PO ». On compare sans accents, dans les
/// deux sens : un agent écrit tantôt le nom court, tantôt le nom complet.
pub fn vise(cible: &str, agent: &str) -> bool {
    let (c, a) = (sansaccents(cible).trim().to_string(), sansaccents(agent).trim().to_string());
    if c.is_empty() || a.is_empty() { return false; }
    if ["tous", "all", "equipe", "*"].contains(&c.as_str()) { return true; }
    c == a || a.split_whitespace().any(|w| w == c)
        || a.ends_with(&format!(" {}", c)) || c.ends_with(&format!(" {}", a))
}

/// Les empreintes que CET agent a déclaré avoir traitées.
pub fn acquits(esp: &Path, agent: &str) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    if !esp.is_dir() { return out; }
    let fin = format!("-{}.md", slug(agent));
    let ra = acquit_re();
    if let Ok(it) = std::fs::read_dir(esp) {
        for p in it.filter_map(|e| e.ok().map(|e| e.path())) {
            if !p.file_name().map(|n| n.to_string_lossy().ends_with(&fin)).unwrap_or(false) {
                continue;
            }
            if let Ok(t) = std::fs::read_to_string(&p) {
                out.extend(ra.captures_iter(&t).map(|c| c[1].to_string()));
            }
        }
    }
    out.sort(); out.dedup();
    out
}

/// Rend `(lignes, empreintes servies)`.
///
/// L'ORDRE EST LA MOITIÉ DU DISPOSITIF, et il n'est pas chronologique :
///   1. ce qui est ADRESSÉ à l'agent et qu'il n'a pas acquitté — sans limite d'âge,
///      parce qu'une demande ne cesse pas d'exister en vieillissant ;
///   2. les ÉCHECS des autres, jamais masqués : un échec sert d'examen, jamais
///      d'exemple ;
///   3. le reste, par date.
pub fn resume(esp: &Path, agent: &str, heures: i64, maxi: usize) -> (Vec<String>, Vec<String>) {
    oubli(esp, 30);
    let limite = (chrono::Local::now() - chrono::Duration::hours(heures))
        .format("%Y-%m-%d %H:%M").to_string();
    let conf = confiances(esp);
    let vus = acquits(esp, agent);
    let (mut pour_moi, mut echecs, mut reste) = (Vec::new(), Vec::new(), Vec::new());
    for mut e in entrees(esp, None) {
        if e.auteur == agent { continue; }        // un agent ne se relit pas lui-même
        if e.pour.iter().any(|(q, _)| vise(q, agent)) && !vus.contains(&e.id) {
            e.rang = Some("→ POUR TOI".into()); pour_moi.push(e);
        } else if sansaccents(&e.issue).starts_with("echou") {
            if e.quand >= limite { e.rang = Some("ÉCHEC".into()); echecs.push(e); }
        } else if e.quand >= limite {
            e.rang = Some(e.issue.clone()); reste.push(e);
        }
    }
    let total = pour_moi.len() + echecs.len() + reste.len();
    let choix: Vec<Entree> = pour_moi.into_iter().chain(echecs).chain(reste).take(maxi).collect();
    if choix.is_empty() { return (Vec::new(), Vec::new()); }
    let mut lignes = Vec::new();
    for e in &choix {
        let n = chiffre(&conf, &e.id);
        let marque = e.rang.clone().unwrap_or_else(|| e.issue.clone());
        let mut quoi = e.texte.clone();
        for (q, p) in &e.pour {
            if vise(q, agent) { quoi = p.clone(); break; }   // ce qui me concerne
        }
        let quoi: String = quoi.chars().take(110).collect();
        let jour: String = e.date.chars().skip(5).collect();
        // L'EMPREINTE EST DANS LA LIGNE QUI DEMANDE DE L'ACQUITTER. Sans elle,
        // le briefing disait « acquitte par `↩ <empreinte>` » sans jamais
        // donner l'empreinte : le seul geste social du carnet était inerte.
        // Sans lui, des entrées qui visent un agent resteraient en tête de son
        // briefing sans moyen de les en sortir, et deviner le calcul est vain :
        // la troncature du texte à 120 caractères le cache. Un identifiant
        // qu'on demande se montre.
        let acquit = if e.rang.as_deref() == Some("→ POUR TOI") {
            format!(" ↩ {}", e.id)
        } else { String::new() };
        lignes.push(format!("  {} · {} · {}{}{} — {}", jour, e.auteur, marque, acquit,
            n.map(|x| format!(" ({})", x)).unwrap_or_default(), quoi));
    }
    if total > choix.len() {
        lignes.push(format!("  … et {} autre(s) dans `equipe/`", total - choix.len()));
    }
    (lignes, choix.iter().map(|e| e.id.clone()).collect())
}

/// `harnais carnet <espace> <agent>` — rend la lecture du carnet en JSON, pour
/// la comparer à celle de Python. C'est un instrument, pas un hook.
pub fn main(args: &[String]) {
    let (sortie, code) = lecture(&PathBuf::from(args.first().cloned().unwrap_or_default()),
                                 &args.get(1).cloned().unwrap_or_default());
    println!("{}", sortie);
    if code != 0 { std::process::exit(code); }
}

/// Rend `(json, code de sortie)`.
///
/// « CE DOSSIER N'EXISTE PAS » ET « CE CARNET EST VIDE » APPELLENT DEUX GESTES
/// OPPOSÉS, et rendraient la même chose : `{"entrees":[]}`, code 0. Un agent
/// qui appelle l'instrument avec sa charge sur l'entrée standard au lieu de
/// deux arguments lirait un dossier vide, et conclurait que le carnet d'équipe
/// est vide. Un instrument qui ne trouve pas son objet le DIT — c'est la même
/// règle que le reste du harnais.
fn lecture(esp: &Path, agent: &str) -> (Value, i32) {
    if !esp.is_dir() {
        return (json!({"raison": format!("ce dossier n'existe pas : {}", esp.display()),
                       "entrees": [], "resume": [], "servis": [], "confiances": {}}), 2);
    }
    let es: Vec<Value> = entrees(esp, None).into_iter().map(|e| json!({
        "date": e.date, "heure": e.heure, "auteur": e.auteur, "issue": e.issue,
        "niveau": e.niveau, "texte": e.texte, "id": e.id, "quand": e.quand,
        "pour": e.pour.iter().map(|(a, b)| json!([a, b])).collect::<Vec<_>>(),
        "rejeu": match &e.rejeu { None => Value::Null,
            Some((s, c, m)) => json!({"source": s, "cmd": c, "motif": m}) },
        "vus": e.vus,
    })).collect();
    let vide = es.is_empty();
    let (lignes, servis) = resume(esp, agent, 48, 8);
    let mut o = json!({"entrees": es, "resume": lignes, "servis": servis,
                       "confiances": Value::Object(confiances(esp))});
    // Le dossier est là, il ne porte aucune entrée : on le dit, sans faire de
    // ce cas normal une erreur.
    if vide { o["vide"] = json!(true); }
    (o, 0)
}

/// `harnais carnet-essai <espace> <json des empreintes>` — rejoue EXACTEMENT
/// la même suite d'écritures que le contrôle différentiel côté Python. Il
/// n'existe que pour ça : sans lui, on ne comparerait que la lecture, et les
/// écritures — arrondis, bornes, ordre des clés — sont justement là où deux
/// implémentations divergent en silence.
pub fn essai(args: &[String]) {
    let esp = PathBuf::from(args.first().cloned().unwrap_or_default());
    let ids: Vec<String> = serde_json::from_str(args.get(1).map(|s| s.as_str()).unwrap_or("[]"))
        .unwrap_or_default();
    for (i, niveau) in ["mesuré", "observé", "supposé"].iter().enumerate() {
        if let Some(id) = ids.get(i) { naissance(&esp, id, niveau); }
    }
    bouge(&esp, &ids, crate::nature::REUSSITE, true);
    bouge(&esp, &ids[..1.min(ids.len())], crate::nature::ECHEC_DECLARE, true);
    if ids.len() >= 3 {
        replancher(&esp, &ids[0], "TIENT");
        replancher(&esp, &ids[1], "TOMBÉ");
        replancher(&esp, &ids[2], "MUET");
    }
    sert(&esp, "CTO", "sess-1", &ids);
    println!("{}", json!({"lu": lu(&esp, "CTO", "sess-1")}));
}

#[cfg(test)]
mod essais {
    use super::*;

    #[test]
    fn l_arrondi_est_celui_de_python_au_pair() {
        // PIÈGE SILENCIEUX : `f64::round` arrondirait 0,5 au supérieur.
        assert_eq!(arrondi0(0.5), 0);
        assert_eq!(arrondi0(1.5), 2);
        assert_eq!(arrondi0(2.5), 2);
        assert_eq!(arrondi1(82.35), 82.3);
        assert_eq!(arrondi1(80.0 * 1.03), 82.4);
    }

    #[test]
    fn la_visee_atteint_le_nom_court_et_le_long() {
        assert!(vise("PO", "Projet PO"));
        assert!(vise("Projet PO", "Projet PO"));
        assert!(vise("tous", "n'importe qui"));
        assert!(vise("équipe", "Projet QA"), "sans accents, dans les deux sens");
        // TÉMOINS NÉGATIFS : une visée qui rate ne doit RIEN servir.
        assert!(!vise("OPS", "Projet PO"));
        assert!(!vise("", "Projet PO"));
        assert!(!vise("PO", ""));
    }

    #[test]
    fn le_chiffre_se_tait_avant_deux_mouvements() {
        let mut c = Map::new();
        c.insert("x".into(), json!({"n": 82.4, "m": 1}));
        assert_eq!(chiffre(&c, "x"), None, "un seul mouvement : c'est le niveau déguisé");
        c.insert("y".into(), json!({"n": 82.4, "m": 2}));
        assert_eq!(chiffre(&c, "y"), Some(82));
        assert_eq!(chiffre(&c, "absent"), None);
    }

    /// Fabrique un carnet : une entrée par (auteur, texte, visée).
    fn carnet_essai(nom: &str, entrees: &[(&str, &str, Option<&str>)]) -> PathBuf {
        let esp = std::env::temp_dir().join(format!("harnais-carnet-{}-{}", nom, std::process::id()));
        let _ = std::fs::remove_dir_all(&esp);
        std::fs::create_dir_all(&esp).unwrap();
        let jour = chrono::Local::now().format("%Y-%m-%d").to_string();
        for (i, (auteur, texte, pour)) in entrees.iter().enumerate() {
            let vise = pour.map(|q| format!("\n↗ {} : {}", q, texte)).unwrap_or_default();
            std::fs::write(esp.join(format!("{}-{}.md", jour, i)),
                format!("## {} 10:0{} · {} · réussi · mesuré\n{}{}\n", jour, i, auteur, texte, vise)).unwrap();
        }
        esp
    }

    /// LE SEUL GESTE SOCIAL DU CARNET. La ligne qui demande d'acquitter porte
    /// l'empreinte ; celle qui ne le demande pas ne la porte pas.
    #[test]
    fn la_ligne_qui_te_vise_porte_son_empreinte_et_les_autres_non() {
        let esp = carnet_essai("vise", &[
            ("Projet PO", "la base change de forme", Some("QA")),
            ("Projet OPS", "le socle a bougé", None),
        ]);
        let (lignes, servis) = resume(&esp, "Projet QA", 48, 8);
        let pour_toi: Vec<&String> = lignes.iter().filter(|l| l.contains("POUR TOI")).collect();
        assert_eq!(pour_toi.len(), 1, "{:?}", lignes);
        let id = servis.first().cloned().unwrap_or_default();
        assert!(!id.is_empty() && pour_toi[0].contains(&format!("↩ {}", id)),
                "l'empreinte demandée doit être dans la ligne : {:?}", lignes);
        // TÉMOIN NÉGATIF : l'entrée qui ne vise personne n'en porte pas —
        // sinon « porte une empreinte » ne dirait rien de la visée.
        let autres: Vec<&String> = lignes.iter().filter(|l| !l.contains("POUR TOI")).collect();
        assert!(!autres.is_empty() && autres.iter().all(|l| !l.contains("↩ ")), "{:?}", lignes);
        // Et l'empreinte servie est bien celle que le fichier porte : un agent
        // qui la recopie acquitte VRAIMENT cette entrée.
        let e = entrees(&esp, None).into_iter().find(|e| e.auteur == "Projet PO").unwrap();
        assert_eq!(id, e.id);
        let _ = std::fs::remove_dir_all(&esp);
    }

    /// « Absent » et « vide » appellent deux gestes opposés.
    #[test]
    fn l_instrument_distingue_le_dossier_absent_du_carnet_vide() {
        let nulle_part = std::env::temp_dir().join("harnais-carnet-nulle-part-xyz");
        let _ = std::fs::remove_dir_all(&nulle_part);
        let (v, code) = lecture(&nulle_part, "X");
        assert_eq!(code, 2);
        assert!(v["raison"].as_str().unwrap_or("").contains("n'existe pas"), "{v}");

        let esp = carnet_essai("vide", &[]);
        let (v, code) = lecture(&esp, "X");
        assert_eq!(code, 0, "un carnet vide n'est pas une erreur");
        assert_eq!(v["vide"], json!(true));
        assert!(v["raison"].is_null(), "vide n'est pas absent : {v}");

        // TÉMOIN : un carnet qui porte une entrée ne dit ni l'un ni l'autre.
        let esp2 = carnet_essai("plein", &[("Projet PO", "quelque chose", None)]);
        let (v, code) = lecture(&esp2, "Projet QA");
        assert_eq!(code, 0);
        assert!(v["vide"].is_null() && v["raison"].is_null(), "{v}");
        let _ = std::fs::remove_dir_all(&esp);
        let _ = std::fs::remove_dir_all(&esp2);
    }

    #[test]
    fn l_oubli_suit_la_nature_de_part_et_d_autre_de_chaque_seuil() {
        let esp = std::env::temp_dir().join("harnais-carnet-oubli-nature");
        let _ = std::fs::remove_dir_all(&esp);
        std::fs::create_dir_all(esp.join(".etat")).unwrap();
        let il_y_a = |n: i64| (chrono::Local::now().date_naive() - chrono::Duration::days(n))
            .format("%Y-%m-%d").to_string();
        let mut d = Map::new();
        for (id, niv, j) in [("cro-14", "supposé", 14), ("cro-16", "supposé", 16),
                             ("exp-31", "observé", 31), ("exp-44", "mesuré", 44),
                             ("exp-46", "mesuré", 46)] {
            d.insert(id.into(), json!({"n": 50, "m": 0, "niveau": niv, "vu": il_y_a(j)}));
        }
        ecrire_etat(&esp, &d);
        oubli(&esp, 30);
        let c = confiances(&esp);
        let n = |id: &str| nb(&c[id]["n"]);
        // Une CROYANCE attend 15 j : à 14 elle tient, à 16 elle descend d'un cran.
        assert_eq!(n("cro-14"), 50.0);
        assert_eq!(n("cro-16"), 48.5);
        // Une EXPÉRIENCE attend 45 j — et à 31 elle tient, là où la règle plate
        // d'avant l'aurait fait descendre. C'est le témoin du changement.
        assert_eq!(n("exp-31"), 50.0);
        assert_eq!(n("exp-44"), 50.0);
        assert_eq!(n("exp-46"), 48.5);
        let _ = std::fs::remove_dir_all(&esp);
    }

    #[test]
    fn le_slug_et_l_empreinte_ne_bougent_pas() {
        assert_eq!(slug("Projet PO"), "Projet-PO");
        assert_eq!(slug(""), "agent");
        // L'empreinte est le lien entre l'entrée et sa confiance : si elle
        // change, la confiance devient introuvable EN SILENCE.
        assert_eq!(empreinte("2026-09-09", "10:00", "CTO", "un texte").len(), 12);
        assert_ne!(empreinte("2026-09-09", "10:00", "CTO", "un texte"),
                   empreinte("2026-09-09", "10:00", "CTO", "un AUTRE texte"));
    }
}
