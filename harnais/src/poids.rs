//! LA CONFIANCE DES FAITS — `brain/poids.json`.
//!
//! L'unité est la SECTION d'un fichier de faits (un titre `##` et ce qui le
//! suit). Chaque section porte une confiance qui part de son niveau
//! d'établissement (mesuré 80, dit 85, observé 60, supposé 40, inconnu 50),
//! puis bouge avec les résultats : une garde qui mord, un constat qui tient, un
//! constat démenti. La confiance doit être facile à perdre et lente à
//! reconstruire.
//!
//! DEUX ÉTATS, ET ILS N'ONT PAS LA MÊME DURÉE DE VIE.
//! · `brain/poids.json` est COMMITÉ : il suit le projet d'une session à l'autre,
//!   d'un worktree à l'autre, d'un agent à l'autre. Pour ne pas le réécrire à
//!   chaque lecture, la date de dernière lecture d'une section n'y bouge qu'une
//!   fois par jour.
//! · le registre de session est LOCAL (dossier d'état du paquet) : il retient
//!   quelles sections ont été lues depuis le dernier verdict, et rien d'autre.
//!   Le vider quand un résultat tombe est ce qui rend le lien causal : une
//!   section lue il y a trois jours n'est pas punie pour un échec d'aujourd'hui.
//!
//! Mesuré sur Copilot CLI 1.0.90-0 : une lecture par l'outil `view` arrive au
//! hook après outil sous `tool_name: "Read"`, avec `tool_input.path` en absolu
//! et, pour une lecture partielle, `view_range: [début, fin]` ; une lecture par
//! le shell arrive sous `tool_name: "Bash"`, la commande en clair.
//!
//! RIEN N'EST JAMAIS DÉPLACÉ NI EFFACÉ. Le rapport signale ; trier les faits
//! reste une décision de @user.

use regex::Regex;
use serde_json::{json, Map, Value};
use std::path::{Path, PathBuf};

use crate::nature::{self, Maison};

/// Sous ce seuil, une section est signalée comme peu sûre.
pub const SEUIL_PEU_SUR: f64 = 50.0;
/// Sans lecture depuis cette durée (graduée par la nature), une section dort.
pub const DORMANT_J: f64 = 30.0;
/// Au-delà de ce nombre de fichiers nommés par une seule commande, c'est un
/// inventaire, pas une lecture : on ne compte rien.
const FICHIERS_MAX: usize = 2;

fn aujourdhui() -> String { chrono::Local::now().format("%Y-%m-%d").to_string() }

/// Le fichier des poids d'un projet en forme `brain/` ; aucun pour les autres.
pub fn fichier(r: &crate::memoire::Resolution) -> Option<PathBuf> {
    if r.forme != crate::memoire::Forme::Brain { return None; }
    r.fact.as_ref()?.parent().map(|b| b.join("poids.json"))
}

/// Les sections d'un fichier de faits : (titre, première ligne, dernière ligne),
/// numérotées à partir de 1, bornes comprises.
pub fn sections(texte: &str) -> Vec<(String, usize, usize)> {
    let titre = Regex::new(r"^##\s+(.+?)\s*$").unwrap();
    let lignes: Vec<&str> = texte.lines().collect();
    let mut out: Vec<(String, usize, usize)> = Vec::new();
    for (i, l) in lignes.iter().enumerate() {
        let n = i + 1;
        if l.starts_with("# ") {
            if let Some(d) = out.last_mut() { if d.2 == 0 { d.2 = n - 1; } }
        } else if let Some(c) = titre.captures(l) {
            if let Some(d) = out.last_mut() { if d.2 == 0 { d.2 = n - 1; } }
            out.push((c[1].to_string(), n, 0));
        }
    }
    if let Some(d) = out.last_mut() { if d.2 == 0 { d.2 = lignes.len(); } }
    out
}

/// La clé d'une section dans `poids.json`.
pub fn cle(fichier: &str, titre: &str) -> String { format!("{fichier} › {titre}") }

/// Les sections touchées par une lecture : celles qui chevauchent la plage
/// (`fin` = -1 ou absente : jusqu'à la fin), toutes sans plage.
pub fn lues(nom: &str, texte: &str, plage: Option<(i64, i64)>) -> Vec<String> {
    sections(texte).into_iter().filter(|(_, debut, fin)| match plage {
        None => true,
        Some((a, b)) => {
            let b = if b < 0 { i64::MAX } else { b };
            (*debut as i64) <= b && (*fin as i64) >= a
        }
    }).map(|(t, _, _)| cle(nom, &t)).collect()
}

fn lis_json(f: &Path) -> Map<String, Value> {
    std::fs::read_to_string(f).ok()
        .and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}

/// Clés triées à tous les niveaux : un diff de `poids.json` ne montre que ce
/// qui a bougé.
fn trie(v: &Value) -> Value {
    match v {
        Value::Object(o) => {
            let mut cles: Vec<&String> = o.keys().collect();
            cles.sort();
            Value::Object(cles.into_iter().map(|k| (k.clone(), trie(&o[k]))).collect())
        }
        Value::Array(a) => Value::Array(a.iter().map(trie).collect()),
        _ => v.clone(),
    }
}

/// Écriture atomique : un fichier tronqué se lirait comme une mémoire neuve.
fn ecris_json(f: &Path, v: &Map<String, Value>) {
    let Ok(t) = serde_json::to_string_pretty(&trie(&Value::Object(v.clone()))) else { return };
    let tmp = f.with_extension("json.tmp");
    if std::fs::write(&tmp, t + "\n").is_ok() { let _ = std::fs::rename(&tmp, f); }
}

/// Le niveau et la nature déclarés d'une section, lus sur sa ligne d'établissement.
fn etablissement(texte: &str, titre: &str) -> (Option<String>, Option<String>) {
    crate::briefing::etablissements(texte).into_iter().find(|e| e.titre == titre)
        .map(|e| (Some(e.niveau), e.nature)).unwrap_or((None, None))
}

/// Inscrit des lectures dans `poids.json` — une entrée neuve part de son
/// niveau ; `jours_lus` et `vu` ne bougent qu'une fois par jour et par section.
pub fn inscris(poids: &Path, fact: &Path, cles: &[String]) -> bool {
    let mut p = lis_json(poids);
    let jour = aujourdhui();
    p.entry("schema").or_insert(json!(1));
    p.entry("depuis").or_insert(json!(jour));
    let mut change = !poids.exists();
    let mut s = p.get("sections").and_then(|v| v.as_object().cloned()).unwrap_or_default();
    for k in cles {
        let (fichier, titre) = k.split_once(" › ").unwrap_or((k.as_str(), ""));
        let e = s.entry(k.clone()).or_insert_with(|| {
            change = true;
            let texte = std::fs::read_to_string(fact.join(fichier)).unwrap_or_default();
            let (niv, _) = etablissement(&texte, titre);
            json!({"conf": nature::depart(niv.as_deref().unwrap_or(""), Maison::Faits),
                   "jours_lus": 0, "verdicts": 0, "vu": Value::Null})
        });
        if let Some(o) = e.as_object_mut() {
            if o.get("vu").and_then(|v| v.as_str()) != Some(jour.as_str()) {
                let n = o.get("jours_lus").and_then(|v| v.as_i64()).unwrap_or(0) + 1;
                o.insert("jours_lus".into(), json!(n));
                o.insert("vu".into(), json!(jour));
                change = true;
            }
        }
    }
    p.insert("sections".into(), Value::Object(s));
    if change { ecris_json(poids, &p); }
    change
}

// ── le registre de session ──────────────────────────────────────────────────

fn registre(etat: &Path, session: &str) -> PathBuf {
    let s: String = session.chars().map(|c| if c.is_ascii_alphanumeric() || c == '-' { c } else { '_' }).collect();
    etat.join("lectures").join(format!("{s}.json"))
}

/// Ajoute au registre de la session les sections lues : (fichier des poids, clé).
pub fn retiens(etat: &Path, session: &str, poids: &Path, cles: &[String]) {
    if session.is_empty() || cles.is_empty() { return; }
    let f = registre(etat, session);
    let mut r = lis_json(&f);
    let p = poids.display().to_string();
    let mut liste = r.get(&p).and_then(|v| v.as_array().cloned()).unwrap_or_default();
    for k in cles {
        if !liste.iter().any(|x| x.as_str() == Some(k)) { liste.push(json!(k)); }
    }
    r.insert(p, Value::Array(liste));
    if let Some(d) = f.parent() { let _ = std::fs::create_dir_all(d); }
    ecris_json(&f, &r);
}

/// UN RÉSULTAT RETOMBE SUR CE QUI A SERVI À L'OBTENIR : les sections lues dans
/// cette session depuis le dernier verdict voient leur confiance multipliée,
/// puis le registre est vidé. Rend le nombre de sections touchées.
pub fn resultat(etat: &Path, session: &str, mult: f64) -> usize {
    let f = registre(etat, session);
    let r = lis_json(&f);
    let mut n = 0;
    for (poids, cles) in &r {
        let poids = Path::new(poids);
        let mut p = lis_json(poids);
        let Some(s) = p.get_mut("sections").and_then(|v| v.as_object_mut()) else { continue };
        for k in cles.as_array().into_iter().flatten().filter_map(|x| x.as_str()) {
            let Some(o) = s.get_mut(k).and_then(|v| v.as_object_mut()) else { continue };
            let c = o.get("conf").and_then(|v| v.as_f64()).unwrap_or(50.0) * mult;
            let c = (c * 10.0).round() / 10.0;
            o.insert("conf".into(), json!(c.clamp(1.0, 100.0)));
            let v = o.get("verdicts").and_then(|v| v.as_i64()).unwrap_or(0) + 1;
            o.insert("verdicts".into(), json!(v));
            n += 1;
        }
        ecris_json(poids, &p);
    }
    let _ = std::fs::remove_file(&f);
    n
}

// ── le hook après lecture ───────────────────────────────────────────────────

/// Les fichiers de faits nommés dans une commande shell, hors de ce qu'elle
/// ÉCRIT (`> fichier`, `Set-Content`, `Out-File`…).
pub fn fichiers_dans_commande(cmd: &str) -> Vec<String> {
    let ecrit = Regex::new(r"(?i)\b(set-content|add-content|out-file|tee-object|sed\s+-i)\b").unwrap();
    if ecrit.is_match(cmd) { return Vec::new(); }
    let re = Regex::new(r#"(?i)[^\s'"`;|<>]*brain[/\\]fact[/\\](?:base|architecture|stack|rules|roles)\.md"#).unwrap();
    let mut out: Vec<String> = Vec::new();
    for m in re.find_iter(cmd) {
        if cmd[..m.start()].trim_end().ends_with('>') { continue; }
        let s = m.as_str().to_string();
        if !out.contains(&s) { out.push(s); }
    }
    out
}

/// Une lecture d'un fichier de faits : (fichier des poids, dossier des faits,
/// nom du fichier). Le projet est celui du FICHIER lu, pas celui de la session.
fn fait_lu(chemin: &Path) -> Option<(PathBuf, PathBuf, String)> {
    let nom = chemin.file_name()?.to_string_lossy().to_string();
    if !crate::socle::faits_tous().contains(&nom.as_str()) { return None; }
    let dossier = chemin.parent()?;
    let r = crate::memoire::resous(dossier);
    let fact = r.fact.clone()?;
    let meme = |a: &Path, b: &Path| a.canonicalize().ok().zip(b.canonicalize().ok()).is_some_and(|(x, y)| x == y);
    if !meme(&fact, dossier) { return None; }
    Some((fichier(&r)?, fact, nom))
}

/// `harnais lecture` — PostToolUse/Read|Bash. Ne bloque jamais, ne dit rien.
pub fn main(entree: &str) {
    let d: Value = match serde_json::from_str(entree) { Ok(v) => v, Err(_) => return };
    let session = d.get("session_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let cwd = d.get("cwd").and_then(|v| v.as_str()).map(PathBuf::from)
        .unwrap_or_else(crate::memoire::depart_defaut);
    let ti = d.get("tool_input");
    let lectures: Vec<(PathBuf, Option<(i64, i64)>)> = match d.get("tool_name").and_then(|v| v.as_str()) {
        Some("Read") => {
            let Some(p) = ti.and_then(|t| t.get("file_path").or_else(|| t.get("path"))).and_then(|v| v.as_str()) else { return };
            let plage = ti.and_then(|t| t.get("view_range")).and_then(|v| v.as_array())
                .and_then(|a| Some((a.first()?.as_i64()?, a.get(1)?.as_i64()?)));
            vec![(PathBuf::from(p), plage)]
        }
        Some("Bash") => {
            let cmd = ti.and_then(|t| t.get("command")).and_then(|v| v.as_str()).unwrap_or("");
            let f = fichiers_dans_commande(cmd);
            if f.len() > FICHIERS_MAX { return; }
            f.into_iter().map(|s| { let p = PathBuf::from(&s); (if p.is_absolute() { p } else { cwd.join(p) }, None) }).collect()
        }
        _ => return,
    };
    let etat = crate::socle::socle();
    for (chemin, plage) in lectures {
        let Some((poids, fact, nom)) = fait_lu(&chemin) else { continue };
        let texte = std::fs::read_to_string(fact.join(&nom)).unwrap_or_default();
        let cles = lues(&nom, &texte, plage);
        if cles.is_empty() { continue; }
        inscris(&poids, &fact, &cles);
        retiens(&etat, &session, &poids, &cles);
    }
}

// ── le rapport ──────────────────────────────────────────────────────────────

pub struct Etat { pub cle: String, pub conf: f64, pub jours_lus: i64, pub vu: Option<String>,
                  pub dort: bool, pub peu_sur: bool, pub orpheline: bool }

/// L'état de chaque section inscrite. Une section jamais lue depuis la création
/// de `poids.json` ne dort qu'une fois la mesure assez ancienne : un compteur à
/// zéro est une absence de preuve, pas une péremption.
pub fn etats(poids: &Path, fact: &Path) -> Vec<Etat> {
    let p = lis_json(poids);
    let depuis = p.get("depuis").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let jours = |iso: &str| chrono::NaiveDate::parse_from_str(iso, "%Y-%m-%d").ok()
        .map(|d| (chrono::Local::now().date_naive() - d).num_days() as f64);
    let mut out = Vec::new();
    let Some(s) = p.get("sections").and_then(|v| v.as_object()) else { return out };
    for (k, v) in s {
        let (fichier, titre) = k.split_once(" › ").unwrap_or((k.as_str(), ""));
        let texte = std::fs::read_to_string(fact.join(fichier)).unwrap_or_default();
        let orpheline = !sections(&texte).iter().any(|(t, _, _)| t == titre);
        let (niv, nat) = etablissement(&texte, titre);
        let (n, _) = nature::de(Maison::Faits, niv.as_deref(), nat.as_deref());
        let conf = v.get("conf").and_then(|x| x.as_f64()).unwrap_or(50.0);
        let vu = v.get("vu").and_then(|x| x.as_str()).map(String::from);
        let age = vu.as_deref().and_then(jours).or_else(|| jours(&depuis));
        let dort = age.is_some_and(|a| a > nature::duree(n, DORMANT_J));
        out.push(Etat { cle: k.clone(), conf, jours_lus: v.get("jours_lus").and_then(|x| x.as_i64()).unwrap_or(0),
                        vu, dort, peu_sur: conf < SEUIL_PEU_SUR, orpheline });
    }
    out
}

/// Une ou deux lignes pour le briefing, ou rien.
pub fn ligne_briefing(poids: &Path, fact: &Path) -> Option<String> {
    if !poids.exists() { return None; }
    let e = etats(poids, fact);
    let peu: Vec<String> = e.iter().filter(|x| x.peu_sur && !x.orpheline)
        .map(|x| format!("{} ({:.0})", x.cle, x.conf)).collect();
    let dort: Vec<String> = e.iter().filter(|x| x.dort && !x.orpheline).map(|x| x.cle.clone()).collect();
    if peu.is_empty() && dort.is_empty() { return None; }
    let court = |v: &[String]| {
        let mut t: Vec<String> = v.iter().take(3).cloned().collect();
        if v.len() > 3 { t.push(format!("… et {} autre(s)", v.len() - 3)); }
        t.join(" · ")
    };
    let mut l = Vec::new();
    if !peu.is_empty() {
        l.push(format!("poids  : {} section(s) peu sûre(s) — des résultats les ont démenties : {}. \
Revérifie avant de t'en servir.", peu.len(), court(&peu)));
    }
    if !dort.is_empty() {
        l.push(format!("{}{} section(s) endormie(s), plus lue(s) depuis longtemps : {}. \
`harnais curateur` pour le détail.", if l.is_empty() { "poids  : " } else { "         " }, dort.len(), court(&dort)));
    }
    Some(l.join("\n"))
}

/// `harnais curateur [dossier]` — le détail, en lecture seule.
pub fn curateur(args: &[String]) -> i32 {
    let ici = args.first().map(PathBuf::from).unwrap_or_else(crate::memoire::depart_defaut);
    let r = crate::memoire::resous(&ici);
    let (Some(poids), Some(fact)) = (fichier(&r), r.fact.clone()) else {
        println!("curateur : pas de mémoire `brain/` ici ({}).", ici.display());
        return 1;
    };
    if !poids.exists() {
        println!("curateur : aucune lecture inscrite encore ({} n'existe pas).", poids.display());
        return 0;
    }
    let mut e = etats(&poids, &fact);
    e.sort_by(|a, b| a.conf.partial_cmp(&b.conf).unwrap_or(std::cmp::Ordering::Equal));
    println!("{}\n", poids.display().to_string().trim_start_matches(r"\\?\"));
    println!("  {:>5}  {:>4}  {:<10}  {:<9}  section", "conf", "jours", "vu", "état");
    for x in &e {
        let etat = if x.orpheline { "disparue" } else if x.peu_sur { "peu sûre" } else if x.dort { "endormie" } else { "active" };
        println!("  {:>5.1}  {:>4}  {:<10}  {:<9}  {}", x.conf, x.jours_lus,
                 x.vu.as_deref().unwrap_or("jamais"), etat, x.cle);
    }
    println!("\n  Rien n'est déplacé ni effacé : trier les faits reste une décision de @user.");
    0
}

#[cfg(test)]
mod essais {
    use super::*;

    const STACK: &str = "# Stack\n\n## Le langage\n> **mesuré** · 01/10/2026 — `python --version`\nPython 3.14.\n\n\
## Le port\n> **dit** · 01/10/2026 — donné à l'oral\nLe service écoute sur 8080.\n";

    #[test]
    fn une_plage_ne_credite_que_les_sections_qu_elle_touche() {
        assert_eq!(sections(STACK), vec![("Le langage".into(), 3, 6), ("Le port".into(), 7, 9)]);
        // La lecture partielle mesurée sur Copilot : view_range [7, 9].
        assert_eq!(lues("stack.md", STACK, Some((7, 9))), vec!["stack.md › Le port"]);
        assert_eq!(lues("stack.md", STACK, Some((1, -1))).len(), 2, "-1 = jusqu'à la fin");
        assert_eq!(lues("stack.md", STACK, None).len(), 2, "sans plage, tout le fichier");
        // TÉMOIN : une plage avant la première section ne crédite rien.
        assert!(lues("stack.md", STACK, Some((1, 2))).is_empty());
    }

    #[test]
    fn la_commande_shell_qui_lit_compte_celle_qui_ecrit_non() {
        assert_eq!(fichiers_dans_commande("Get-Content brain/fact/stack.md"), vec!["brain/fact/stack.md"]);
        assert_eq!(fichiers_dans_commande(r"type C:\p\brain\fact\rules.md"), vec![r"C:\p\brain\fact\rules.md"]);
        assert!(fichiers_dans_commande("echo x > brain/fact/stack.md").is_empty());
        assert!(fichiers_dans_commande("Set-Content brain/fact/stack.md 'x'").is_empty());
        assert!(fichiers_dans_commande("cat brain/fact/notes.md").is_empty(), "pas un fichier de faits");
    }

    fn banc(nom: &str) -> (PathBuf, PathBuf, PathBuf) {
        let d = std::env::temp_dir().join(format!("harnais-poids-{nom}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(d.join("brain/fact")).unwrap();
        std::fs::write(d.join("brain/fact/stack.md"), STACK).unwrap();
        (d.join("brain/poids.json"), d.join("brain/fact"), d.join("etat"))
    }

    #[test]
    fn une_section_part_de_son_niveau_et_une_journee_ne_compte_qu_une_fois() {
        let (poids, fact, _) = banc("depart");
        assert!(inscris(&poids, &fact, &["stack.md › Le port".into(), "stack.md › Le langage".into()]));
        assert!(!inscris(&poids, &fact, &["stack.md › Le port".into()]), "même jour : rien ne bouge");
        let p = lis_json(&poids);
        assert_eq!(p["sections"]["stack.md › Le port"]["conf"], json!(85), "dit → 85");
        assert_eq!(p["sections"]["stack.md › Le langage"]["conf"], json!(80), "mesuré → 80");
        assert_eq!(p["sections"]["stack.md › Le port"]["jours_lus"], json!(1));
        let _ = std::fs::remove_dir_all(poids.parent().unwrap().parent().unwrap());
    }

    #[test]
    fn le_resultat_ne_touche_que_ce_qui_a_ete_lu_puis_le_registre_se_vide() {
        let (poids, fact, etat) = banc("resultat");
        inscris(&poids, &fact, &["stack.md › Le port".into(), "stack.md › Le langage".into()]);
        retiens(&etat, "S1", &poids, &["stack.md › Le port".into()]);
        assert_eq!(resultat(&etat, "S1", nature::DEMENTI), 1);
        let p = lis_json(&poids);
        assert_eq!(p["sections"]["stack.md › Le port"]["conf"], json!(76.5), "85 × 0,90");
        assert_eq!(p["sections"]["stack.md › Le langage"]["conf"], json!(80), "TÉMOIN : non lue, intacte");
        assert_eq!(resultat(&etat, "S1", nature::DEMENTI), 0, "le registre a été vidé");
        // Une autre session n'est pas touchée par le verdict de la première.
        retiens(&etat, "S2", &poids, &["stack.md › Le langage".into()]);
        assert_eq!(resultat(&etat, "S1", nature::DEMENTI), 0);
        let _ = std::fs::remove_dir_all(poids.parent().unwrap().parent().unwrap());
    }

    #[test]
    fn le_briefing_ne_dit_rien_tant_que_tout_va_bien() {
        let (poids, fact, etat) = banc("briefing");
        inscris(&poids, &fact, &["stack.md › Le port".into()]);
        assert_eq!(ligne_briefing(&poids, &fact), None);
        for _ in 0..5 { retiens(&etat, "S", &poids, &["stack.md › Le port".into()]); resultat(&etat, "S", nature::ECHEC_DECLARE); }
        let l = ligne_briefing(&poids, &fact).expect("une section démentie se signale");
        assert!(l.contains("stack.md › Le port") && l.contains("peu sûre"), "{l}");
        let _ = std::fs::remove_dir_all(poids.parent().unwrap().parent().unwrap());
    }
}
