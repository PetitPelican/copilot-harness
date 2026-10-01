//! LE MÉNAGE D'UN PROJET — ou de tout un atelier — sans jamais décider à la
//! place de quelqu'un. Porté de `agentic-clean.py` : le script n'existait
//! qu'en Python, donc échouait en silence sur Windows.
//!
//! Trois familles, rendues SÉPARÉMENT parce qu'elles n'ont pas la même nature :
//!
//!   1. CACHES RÉGÉNÉRABLES  supprimés (sous `--apply`), avec la commande qui les
//!                           refait. Un `node_modules` n'est pas une donnée.
//!   2. RÉSIDUS DE MIGRATION listés seulement. Ce sont des phrases que quelqu'un a
//!                           écrites ; seul l'agent du projet sait si elles sont
//!                           reprises ailleurs.
//!   3. MÉMOIRE HYPERTROPHIÉE listée seulement. Trier, c'est choisir ce qu'on
//!                           oublie — un programme n'a pas à le faire.
//!
//! **Dry-run par défaut.** `--apply` n'agit QUE sur la famille 1.
//!
//! LE PORTAGE EST À L'OCTET, bizarreries comprises : il rend ce que rendait le
//! Python sur l'atelier fabriqué de `controles/corpus-menage.sh`, et le témoin
//! figé AVANT le retrait du script le prouve. Deux bizarreries connues sont
//! gardées exprès pour cette raison, et se corrigent à part, en le disant :
//! la « plus ancienne date » est triée comme du texte, et un projet en
//! `brain/` voit sa mémoire cherchée dans `.memory/`.

use regex::Regex;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Chaque entrée dit COMMENT ça repousse. Sans cette colonne, la suppression
/// est un pari ; avec elle, c'est une opération réversible.
/// `dist` et `build` n'appartiennent à aucun écosystème : voir `refait_par`.
/// `.build` (Swift Package Manager) : un cache volumineux, facile à oublier.
const CACHES: &[(&str, &str)] = &[
    ("node_modules", "npm ci  (ou pnpm install / yarn install)"),
    (".turbo", "refait seul au prochain `turbo`"),
    (".next", "npm run build"),
    (".astro", "npm run build  (ou `astro sync`)"),
    (".nuxt", "npm run build"),
    (".svelte-kit", "npm run build"),
    (".parcel-cache", "refait seul au prochain build"),
    (".vite", "refait seul au prochain build"),
    ("dist", ""),
    ("build", ""),
    (".venv", "uv sync  (ou python3 -m venv .venv && pip install -r requirements.txt)"),
    ("venv", "uv sync  (ou python3 -m venv venv && pip install -r requirements.txt)"),
    ("__pycache__", "refait seul à l'import suivant"),
    (".mypy_cache", "refait seul au prochain mypy"),
    (".pytest_cache", "refait seul au prochain pytest"),
    (".ruff_cache", "refait seul au prochain ruff"),
    (".gradle", "refait seul au prochain build Gradle"),
    ("DerivedData", "refait seul au prochain build Xcode"),
    (".build", "refait seul au prochain `swift build`"),
    ("Pods", "pod install"),
    ("coverage", "refait seul au prochain run de tests"),
    (".nyc_output", "refait seul au prochain run de tests"),
];

fn est_cache(nom: &str) -> bool { CACHES.iter().any(|(n, _)| *n == nom) }
/// On ne descend jamais DANS un cache : y chercher d'autres caches coûte des
/// minutes sur un `node_modules` de 6 Go pour ne rien apprendre.
fn ne_pas_descendre(nom: &str) -> bool { est_cache(nom) || nom == ".git" }

/// `MONTENT` nomme des fichiers qui ont une place ailleurs, `ANCIENS` des
/// fichiers qui n'en ont plus. Tout le reste de `docs/` est de la matière de
/// domaine, qu'on se garde de signaler.
const MONTENT: &[&str] = &["state.md", "rules.md", "architecture.md"];
const ANCIENS: &[&str] = &["charter.md", "business.md", "clients.md", "overview.md"];
/// `docs/` ne contient que de l'écrit à la main.
const GENERE: &[&str] = &[".pdf", ".html", ".png", ".jpg", ".jpeg", ".zip", ".docx", ".xlsx", ".svg"];
const SEUIL_LIGNES: usize = 500;

#[derive(Default)]
struct Rapport { caches: Vec<String>, residus: Vec<String>, memoire: Vec<String> }

fn mo(n: u64) -> f64 { n as f64 / 1048576.0 }

/// `docs/` après migration, `.memory/` avant. La FORME décide, jamais la
/// simple présence d'un `docs/`.
fn dossier_memoire(projet: &Path) -> PathBuf {
    if projet.join(".fact").is_dir() { projet.join("docs") } else { projet.join(".memory") }
}

/// Les entrées d'un dossier, triées par nom : le Python suivait l'ordre du
/// système de fichiers, qui ne se promet nulle part. Trier ne change rien au
/// témoin, et rend le rapport stable d'une machine à l'autre.
fn entrees(d: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(d).map(|it| it.flatten().map(|e| e.path()).collect())
        .unwrap_or_default();
    v.sort();
    v
}

/// Un dossier tel que `os.walk` le voit : un lien vers un dossier est LISTÉ
/// comme dossier, mais jamais parcouru.
fn est_dossier(p: &Path) -> bool { p.is_dir() }
fn est_lien(p: &Path) -> bool {
    std::fs::symlink_metadata(p).map(|m| m.file_type().is_symlink()).unwrap_or(false)
}

/// Taille d'une arborescence, comptée comme `du` la compte. Les LIENS DURS
/// (pnpm relie ses paquets) ne se comptent qu'une fois par `(device, inode)` —
/// sinon la taille annoncée dépasse largement le poids réel du projet. Les
/// liens symboliques ne sont jamais suivis.
fn poids(chemin: &Path, vus: &mut HashSet<(u64, u64)>) -> u64 {
    let mut total = 0u64;
    let mut pile = vec![chemin.to_path_buf()];
    while let Some(d) = pile.pop() {
        for p in entrees(&d) {
            let Ok(m) = std::fs::symlink_metadata(&p) else { continue };
            if m.file_type().is_symlink() { continue; }
            if m.is_dir() { pile.push(p); continue; }
            if let Some(cle) = inode(&m) {
                if cle.2 > 1 {
                    if !vus.insert((cle.0, cle.1)) { continue; }
                }
            }
            total += m.len();
        }
    }
    total
}

#[cfg(unix)]
fn inode(m: &std::fs::Metadata) -> Option<(u64, u64, u64)> {
    use std::os::unix::fs::MetadataExt;
    Some((m.dev(), m.ino(), m.nlink()))
}
#[cfg(not(unix))]
fn inode(_m: &std::fs::Metadata) -> Option<(u64, u64, u64)> { None }

/// `Some(true)` ignoré, `Some(false)` suivi, `None` pas un dépôt git. C'est le
/// discriminant de tout le ménage : le MÊME dossier suivi par git est du
/// contenu que quelqu'un a décidé de versionner.
fn ignore_par_git(projet: &Path, chemin: &Path) -> Option<bool> {
    if !projet.join(".git").exists() { return None; }
    let r = Command::new("git").arg("-C").arg(projet).args(["check-ignore", "-q"]).arg(chemin)
        .output().ok()?;
    Some(r.status.code() == Some(0))
}

/// Comment CE dossier-là se reconstruit. `dist/` et `build/` ne disent rien
/// de leur écosystème : on regarde ce qui se trouve à côté, puis chez le
/// parent — sinon on promet « npm run build » devant un `dist` de PyInstaller.
fn refait_par(cache: &Path) -> String {
    let nom = cache.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    if let Some((_, fixe)) = CACHES.iter().find(|(n, _)| *n == nom) {
        if !fixe.is_empty() { return fixe.to_string(); }
    }
    let parent = cache.parent().map(Path::to_path_buf).unwrap_or_default();
    let grand = parent.parent().map(Path::to_path_buf).unwrap_or_default();
    for d in [parent, grand] {
        if !d.is_dir() { continue; }
        if entrees(&d).iter().any(|p| p.extension().map(|e| e == "spec").unwrap_or(false)) {
            return "pyinstaller <le .spec d'à côté>".into();
        }
        if d.join("package.json").is_file() { return "npm run build".into(); }
        if d.join("pyproject.toml").is_file() {
            return "python -m build  (ou le script de packaging du projet)".into();
        }
        if d.join("Cargo.toml").is_file() { return "cargo build".into(); }
    }
    "LE BUILD DU PROJET — non identifié, vérifier avant de supprimer".into()
}

/// Les caches, sans jamais descendre dans un cache déjà trouvé.
fn cherche_caches(projet: &Path) -> Vec<PathBuf> {
    let mut trouves = Vec::new();
    let mut pile = vec![projet.to_path_buf()];
    while let Some(d) = pile.pop() {
        for p in entrees(&d) {
            if !est_dossier(&p) { continue; }
            let nom = p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
            if est_cache(&nom) { trouves.push(p); }
            else if !ne_pas_descendre(&nom) && !est_lien(&p) { pile.push(p); }
        }
    }
    // Par COMPOSANTS, comme `sorted()` trie des chemins Python — pas comme du
    // texte : « app/x » et « app.y » ne se rangent pas pareil.
    trouves.sort();
    trouves
}

fn relatif(projet: &Path, p: &Path) -> String {
    p.strip_prefix(projet).unwrap_or(p).components()
        .map(|c| c.as_os_str().to_string_lossy().to_string()).collect::<Vec<_>>().join("/")
}

fn gauche(s: &str, n: usize) -> String {
    let l = s.chars().count();
    if l >= n { s.to_string() } else { format!("{}{}", s, " ".repeat(n - l)) }
}

/// Supprime — c'est la SEULE famille qui écrit. Le registre des inodes est
/// partagé par TOUS les caches du projet : deux `node_modules` pnpm qui
/// pointent le même inode ne sont comptés qu'une fois.
fn famille_caches(projet: &Path, rap: &mut Rapport, appliquer: bool) -> u64 {
    let (mut rendu, mut vus, mut menus) = (0u64, HashSet::new(), Vec::<String>::new());
    for c in cherche_caches(projet) {
        let p = poids(&c, &mut vus);
        let rel = relatif(projet, &c);
        let nom = c.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
        let etat = ignore_par_git(projet, &c);
        if etat == Some(false) {
            rap.residus.push(format!("{} {:>8.1} Mo  SUIVI PAR GIT — pas supprimé. C'est un \
problème de .gitignore, pas de ménage.", gauche(&rel, 42), mo(p)));
            continue;
        }
        if etat.is_none() && ["dist", "build", "coverage"].contains(&nom.as_str()) {
            rap.residus.push(format!("{} {:>8.1} Mo  hors dépôt git et nom ambigu — pas supprimé, \
vérifier que ce n'est pas de la source.", gauche(&rel, 42), mo(p)));
            continue;
        }
        // Un monorepo a vingt `.turbo` vides : on les compte, on ne les
        // détaille pas — un rapport qu'on ne lit pas ne protège de rien.
        if mo(p) < 1.0 { menus.push(rel); }
        else { rap.caches.push(format!("{} {:>8.1} Mo  <- {}", gauche(&rel, 42), mo(p), refait_par(&c))); }
        rendu += p;
        if appliquer { let _ = std::fs::remove_dir_all(&c); }
    }
    if !menus.is_empty() {
        let mut noms: Vec<String> = menus.iter()
            .map(|m| m.rsplit('/').next().unwrap_or(m).to_string()).collect();
        noms.sort(); noms.dedup();
        rap.caches.push(format!("{} {:>8}     {} dossier(s) : {}",
            gauche("(caches de moins de 1 Mo)", 42), "<1 Mo", menus.len(), noms.join(", ")));
    }
    rendu
}

/// Tous les fichiers sous `d`, récursivement, liens non suivis.
fn fichiers_sous(d: &Path) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut pile = vec![d.to_path_buf()];
    while let Some(x) = pile.pop() {
        for p in entrees(&x) {
            if p.is_dir() { if !est_lien(&p) { pile.push(p.clone()); } continue; }
            out.push(p);
        }
    }
    out
}

fn nom_de(p: &Path) -> String { p.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default() }

/// Listée, jamais supprimée.
fn famille_residus(projet: &Path, rap: &mut Rapport) {
    let memoire = dossier_memoire(projet);
    let nom_mem = nom_de(&memoire);
    if nom_mem == "docs" && memoire.is_dir() {
        let mut genere: Vec<String> = fichiers_sous(&memoire).into_iter()
            .filter(|f| f.extension().map(|e| GENERE.contains(&format!(".{}", e.to_string_lossy().to_lowercase()).as_str())).unwrap_or(false))
            .map(|f| nom_de(&f)).collect();
        genere.sort();
        if !genere.is_empty() {
            let tete = genere.iter().take(5).cloned().collect::<Vec<_>>().join(", ");
            rap.residus.push(format!("docs/ porte {} fichier(s) qui ressemblent à des sorties de build \
({}{}) : `docs/` ne contient que de l'écrit à la main — les sortir vers `site/` ou un dossier de build.",
                genere.len(), tete, if genere.len() > 5 { ", …" } else { "" }));
        }
    }
    if memoire.is_dir() {
        for f in entrees(&memoire) {
            if !f.is_file() || f.extension().map(|e| e != "md").unwrap_or(true) { continue; }
            let n = nom_de(&f);
            if MONTENT.contains(&n.as_str()) {
                rap.residus.push(format!("{}/{} dit des FAITS ACTUELS : MONTE dans .fact/ ou \
.mind/, il y a déjà sa place", nom_mem, gauche(&n, 33)));
            } else if ANCIENS.contains(&n.as_str()) {
                rap.residus.push(format!("{}/{} ancienne taxonomie : à trier, son \
contenu se répartit entre .fact/, .mind/ et docs/", nom_mem, gauche(&n, 33)));
            }
        }
        let archive = memoire.join("archive");
        if archive.is_dir() {
            let fs = fichiers_sous(&archive);
            let mut couverts: Vec<String> = fs.iter().map(|p| nom_de(p))
                .filter(|n| MONTENT.contains(&n.as_str()) || ANCIENS.contains(&n.as_str())).collect();
            let n_couverts = couverts.len();
            couverts.sort(); couverts.dedup();
            rap.residus.push(format!("docs/archive/{} {} fichier(s), {:.1} Mo — dont {} repris \
par .mind/ ({})", gauche("", 25), fs.len(), mo(poids(&archive, &mut HashSet::new())), n_couverts,
                if couverts.is_empty() { "aucun".to_string() } else { couverts.join(", ") }));
        }
    }
    let re = Regex::new(r"(?i)\.(bak|old|orig|sav)\b|\.bak[-.]|\.avant[-.]|~$").unwrap();
    let mut pile = vec![projet.to_path_buf()];
    let mut trouves = Vec::new();
    while let Some(d) = pile.pop() {
        for p in entrees(&d) {
            let n = nom_de(&p);
            if p.is_dir() {
                if !ne_pas_descendre(&n) && !est_lien(&p) { pile.push(p); }
                continue;
            }
            if re.is_match(&n) { trouves.push(p); }
        }
    }
    trouves.sort();
    for p in trouves {
        let taille = std::fs::metadata(&p).map(|m| m.len()).unwrap_or(0);
        rap.residus.push(format!("{} {:>8.1} Mo  sauvegarde manuelle", gauche(&relatif(projet, &p), 42), mo(taille)));
    }
}

/// Listée, jamais touchée. Trier, c'est choisir ce qu'on oublie.
fn famille_memoire(projet: &Path, rap: &mut Rapport) {
    let memoire = dossier_memoire(projet);
    if !memoire.is_dir() { return; }
    let date = Regex::new(r"\b(20\d\d)[-/](\d\d)[-/](\d\d)\b|\b(\d\d)/(\d\d)/(20\d\d)\b").unwrap();
    let mut fs: Vec<PathBuf> = fichiers_sous(&memoire).into_iter()
        .filter(|f| f.extension().map(|e| e == "md").unwrap_or(false)).collect();
    fs.sort_by_key(|p| p.to_string_lossy().to_string());
    for f in fs {
        let Ok(octets) = std::fs::read(&f) else { continue };
        let texte = String::from_utf8_lossy(&octets);
        let lignes: Vec<&str> = texte.lines().collect();
        if lignes.len() < SEUIL_LIGNES { continue; }
        // TRIÉES COMME DU TEXTE — la bizarrerie du Python, gardée à l'octet :
        // une date « JJ/MM/AAAA » passe devant une date « AAAA-MM-JJ ».
        let mut dates: Vec<String> = lignes.iter()
            .filter_map(|l| date.find(l).map(|m| m.as_str().to_string())).collect();
        dates.sort();
        rap.memoire.push(format!("{} {:>5} lignes  la plus ancienne entrée datée : {}",
            gauche(&relatif(projet, &f), 42), lignes.len(),
            dates.first().cloned().unwrap_or_else(|| "aucune date lisible".into())));
    }
}

fn developpe(p: &str) -> PathBuf {
    if let Some(reste) = p.strip_prefix("~/") {
        if let Some(h) = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")) {
            return PathBuf::from(h).join(reste);
        }
    }
    PathBuf::from(p)
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
        println!("harnais menage [--projet P | --racine R] [--apply]\n\n\
Fait le ménage d'un projet — ou de tout un atelier — sans jamais décider à la\n\
place de quelqu'un. Dry-run par défaut ; `--apply` ne supprime que les caches\n\
régénérables, jamais un résidu ni une mémoire.");
        return 0;
    }
    let appliquer = args.iter().any(|a| a == "--apply");
    let racine = valeur(args, "--racine").filter(|s| !s.is_empty());
    let cibles: Vec<PathBuf> = if let Some(r) = racine {
        let r = developpe(&r);
        let r = r.canonicalize().unwrap_or(r);
        entrees(&r).into_iter().filter(|p| p.is_dir() && !nom_de(p).starts_with('.')).collect()
    } else {
        let p = developpe(&valeur(args, "--projet").unwrap_or_else(|| ".".into()));
        vec![p.canonicalize().unwrap_or(p)]
    };

    println!("Agentic clean — {}", if appliquer { "APPLY" } else { "DRY-RUN" });
    println!("Cible{} : {}", if cibles.len() > 1 { "s" } else { "" },
        cibles.iter().map(|c| nom_de(c)).collect::<Vec<_>>().join(", "));
    println!();

    let mut total = 0u64;
    let barre = "═".repeat(78);
    for cible in &cibles {
        if !cible.is_dir() { continue; }
        let mut rap = Rapport::default();
        let rendu = famille_caches(cible, &mut rap, appliquer);
        famille_residus(cible, &mut rap);
        famille_memoire(cible, &mut rap);
        total += rendu;
        if rap.caches.is_empty() && rap.residus.is_empty() && rap.memoire.is_empty() { continue; }
        println!("{}", barre);
        println!("  {}", nom_de(cible));
        println!("{}", barre);
        if !rap.caches.is_empty() {
            println!("\n1. CACHES RÉGÉNÉRABLES — {} ({:.1} Mo)",
                if appliquer { "SUPPRIMÉS" } else { "à supprimer" }, mo(rendu));
            for m in &rap.caches { println!("   {}", m); }
        }
        if !rap.residus.is_empty() {
            println!("\n2. RÉSIDUS — listés seulement, à trancher par l'agent du projet");
            for m in &rap.residus { println!("   {}", m); }
        }
        if !rap.memoire.is_empty() {
            println!("\n3. MÉMOIRE AU-DELÀ DE {} LIGNES — à découper, jamais automatiquement", SEUIL_LIGNES);
            for m in &rap.memoire { println!("   {}", m); }
        }
        println!();
    }
    println!("{}", "─".repeat(78));
    println!("Total récupérable : {:.1} Mo", mo(total));
    if !appliquer {
        println!("\nDry-run. `--apply` supprime la FAMILLE 1 seulement — les familles 2 et 3 ne sont \
jamais supprimées par ce script.");
    } else {
        println!("\nLes familles 2 et 3 n'ont pas été touchées : elles demandent un jugement sur du \
contenu, pas une règle.");
    }
    0
}
